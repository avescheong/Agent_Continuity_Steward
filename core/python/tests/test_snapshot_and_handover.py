"""Tests for Snapshot creation, SHA-256 seal determinism, and Handover export/import round-trip."""

import unittest
import tempfile
import json
from pathlib import Path

from scs_core.db.database import VaultDatabase
from scs_core.models import DecisionKind, TaskPriority, TaskStatus, ProposalType
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService


class TestSnapshotAndHandover(unittest.TestCase):
    def setUp(self):
        self.temp_db_dir = tempfile.TemporaryDirectory()
        self.temp_snap_dir = tempfile.TemporaryDirectory()
        self.temp_exp_dir = tempfile.TemporaryDirectory()

        self.db_path = Path(self.temp_db_dir.name) / "test_vault.db"
        self.db = VaultDatabase(self.db_path)

        self.project_svc = ProjectSessionService(self.db, snapshots_dir=Path(self.temp_snap_dir.name))
        self.decision_svc = DecisionLedgerService(self.db)
        self.checklist_svc = ChecklistEngineService(self.db)
        self.artifact_svc = ArtifactRegistryService(self.db)
        self.gate_svc = ApprovalGateService(
            self.db, self.decision_svc, self.checklist_svc, self.artifact_svc
        )
        self.reconciler = ReadOnlyReconciler(self.db)
        self.protocol_svc = ProtocolEngineService(
            self.db,
            self.project_svc,
            self.decision_svc,
            self.checklist_svc,
            self.artifact_svc,
            self.gate_svc,
            self.reconciler,
            exports_dir=Path(self.temp_exp_dir.name),
        )

        self.proj = self.project_svc.ensure_default_project()

    def tearDown(self):
        self.temp_db_dir.cleanup()
        self.temp_snap_dir.cleanup()
        self.temp_exp_dir.cleanup()

    def test_snapshot_creation_and_mirror_file(self):
        self.decision_svc.create_decision(
            self.proj.id, DecisionKind.DECISION, statement="Initial choice", rationale_why="Fast"
        )
        self.checklist_svc.create_task(
            self.proj.id, title="Initial task", why_it_matters="Core foundation"
        )

        snp = self.project_svc.create_snapshot(self.proj.id, label="Milestone 1")
        self.assertTrue(snp.snapshot_code.startswith("SNP-"))
        self.assertEqual(len(snp.checksum_sha256), 64)
        self.assertTrue(Path(snp.mirror_file_path).exists())

        # Verify project latest snapshot pointer updated
        updated_proj = self.project_svc.get_project(self.proj.id)
        self.assertEqual(updated_proj.latest_snapshot_id, snp.id)
        self.assertEqual(updated_proj.latest_snapshot_sha256, snp.checksum_sha256)

    def test_handover_package_export_and_reimport_roundtrip(self):
        # 1. Populate state
        self.decision_svc.create_decision(
            self.proj.id, DecisionKind.DECISION, statement="Decision A", rationale_why="Reason A"
        )
        self.decision_svc.create_decision(
            self.proj.id, DecisionKind.REJECTED_OPTION, statement="Rejected B", rationale_why="Why not"
        )
        self.decision_svc.create_decision(
            self.proj.id, DecisionKind.CONSTRAINT, statement="Constraint C", rationale_why="Boundary C"
        )
        self.checklist_svc.create_task(
            self.proj.id, title="Task Alpha", why_it_matters="Crucial step"
        )
        self.artifact_svc.register_artifact(
            self.proj.id, name="blueprint.md", conversation_note="Core spec"
        )

        # 2. Generate handover package (now 3-layer output: AI handover + human briefing + recovery card)
        pkg = self.protocol_svc.generate_handover_package(self.proj.id, save_to_exports=True)
        self.assertIn("## 1. Executive Summary", pkg["markdown_content"])
        self.assertIn("```scs-handover", pkg["markdown_content"])
        self.assertTrue(Path(pkg["exported_file_path"]).exists())
        self.assertIn("human_briefing_content", pkg)
        self.assertIn("human_briefing_file_path", pkg)
        self.assertTrue(Path(pkg["human_briefing_file_path"]).exists())
        self.assertIn("recovery_card_content", pkg)
        self.assertIn("recovery_card_file_path", pkg)
        self.assertTrue(Path(pkg["recovery_card_file_path"]).exists())

        # 3. Verify Human Briefing structure (Sections A through G)
        briefing_content = pkg["human_briefing_content"]
        self.assertIn("## A. Project Identity", briefing_content)
        self.assertIn("## B. Journey Summary", briefing_content)
        self.assertIn("## C. Decision Memory", briefing_content)
        self.assertIn("## D. Current Operational State", briefing_content)
        self.assertIn("## E. Operator Checklist", briefing_content)
        self.assertIn("## F. Warnings & Frozen Boundaries", briefing_content)
        self.assertIn("## G. Next Recommended Action", briefing_content)

        # 4. Verify Project Recovery Card structure (Fast 30-60s Checklist)
        rec_card = pkg["recovery_card_content"]
        self.assertIn("## 📍 Where We Are", rec_card)
        self.assertIn("## ✅ Completed", rec_card)
        self.assertIn("## 🟡 Current Focus", rec_card)
        self.assertIn("## 🔒 Important Decisions", rec_card)
        self.assertIn("## ⚠️ Remember", rec_card)
        self.assertIn("## ⏭️ Next Actions", rec_card)

        # Verify Recovery Card content filtering
        self.assertIn("Decision A", rec_card)
        self.assertIn("Reason A", rec_card)
        self.assertIn("Constraint C", rec_card)
        self.assertIn("Rejected B", rec_card)
        self.assertNotIn("```scs-handover", rec_card)
        self.assertNotIn("JSON", rec_card)
        self.assertNotIn("Would you like me to", rec_card)
        self.assertNotIn("[SES-", rec_card)
        self.assertNotIn("RECONCILIATION STATUS", rec_card)

        # 5. Create a brand-new project and re-import via parse_and_stage_capture
        proj2 = self.project_svc.create_project(code="PRJ_IMPORT", name="Imported Project")
        staged = self.protocol_svc.parse_and_stage_capture(
            proj2.id, pkg["markdown_content"], source_origin="HANDOVER_IMPORT"
        )

        # Invariant: Must land in proposals table first (Human Approval Boundary!)
        self.assertGreaterEqual(len(staged), 5)
        pending_proposals = self.gate_svc.list_proposals(proj2.id)
        self.assertEqual(len(pending_proposals), len(staged))

        # Verify proposal types preserved exactly during handover import
        staged_dec = next(s for s in staged if s["title"] == "Decision A")
        staged_rej = next(s for s in staged if s["title"] == "Rejected B")
        staged_con = next(s for s in staged if s["title"] == "Constraint C")
        self.assertEqual(staged_dec["proposal_type"], ProposalType.DECISION)
        self.assertEqual(staged_rej["proposal_type"], ProposalType.REJECTED_OPTION)
        self.assertEqual(staged_con["proposal_type"], ProposalType.CONSTRAINT)

        # Approve all and verify canonical state restored in project 2 with correct record kinds
        approved_count = self.gate_svc.approve_all(proj2.id)
        self.assertEqual(approved_count, len(staged))

        tasks_p2 = self.checklist_svc.list_tasks(proj2.id)
        decs_p2 = self.decision_svc.list_decisions(proj2.id)
        arts_p2 = self.artifact_svc.list_artifacts(proj2.id)

        self.assertTrue(any(t.title == "Task Alpha" for t in tasks_p2))
        dec_a = next(d for d in decs_p2 if d.statement == "Decision A")
        rej_b = next(d for d in decs_p2 if d.statement == "Rejected B")
        con_c = next(d for d in decs_p2 if d.statement == "Constraint C")
        self.assertEqual(dec_a.record_kind, DecisionKind.DECISION)
        self.assertEqual(rej_b.record_kind, DecisionKind.REJECTED_OPTION)
        self.assertEqual(con_c.record_kind, DecisionKind.CONSTRAINT)
        self.assertTrue(any(a.name == "blueprint.md" for a in arts_p2))

    def test_project_recovery_card_strict_human_filtering(self):
        """Verifies Recovery Card rigorously filters conversational questions, raw extraction, and scene codes."""
        proj = self.project_svc.create_project(
            code="FLTR_PRJ",
            name="Filter Test Project",
        )
        # Simulate conversational junk that might have been staged into project focus & next action
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE projects SET current_focus = ?, next_action = ? WHERE id = ?;",
                (
                    "[SES-014] Evidence — RECONCILIATION STATUS: In Progress",
                    "Would you like me to proceed with Phase 1 & Phase 2 inside Interactive HTML?",
                    proj.id,
                ),
            )
        self.decision_svc.create_decision(
            proj.id, DecisionKind.DECISION, statement="Offline-first architecture.", rationale_why="No cloud dependency required."
        )
        self.decision_svc.create_decision(
            proj.id, DecisionKind.CONSTRAINT, statement="Cannot speak (CH01_S02_BAKER) → Spell of Voice", rationale_why="Audio continuity rule"
        )
        self.checklist_svc.create_task(
            proj.id, title="Implement watercolor living canvas", why_it_matters="Visual core"
        )

        card_res = self.protocol_svc.generate_recovery_card(proj.id)
        card = card_res["markdown_content"]

        # Required strict negative assertions
        self.assertNotIn("Would you like me to", card)
        self.assertNotIn("[SES-", card)
        self.assertNotIn("RECONCILIATION STATUS", card)
        self.assertNotIn("(CH01_S02_BAKER)", card)
        self.assertNotIn("Active development sealed under", card)
        self.assertNotIn("Execute next planned milestone", card)
        self.assertNotIn("Continue development", card)
        self.assertNotIn("Advance project", card)
        where_we_are = card.split("## 📍 Where We Are")[1].split("##")[0]
        self.assertNotIn("Continuity_MD", where_we_are)

        # Required positive structural assertions
        self.assertIn("## 📍 Where We Are", card)
        self.assertIn("## ✅ Completed", card)
        self.assertIn("## 🟡 Current Focus", card)
        self.assertIn("## 🔒 Important Decisions", card)
        self.assertIn("## ⚠️ Remember", card)
        self.assertIn("## ⏭️ Next Actions", card)

        # Required content assertions (checklist decision format & single-page brevity)
        self.assertIn("🔒 Offline-first architecture", card)
        self.assertIn("Why: No cloud dependency required", card)
        self.assertIn("Implement watercolor living canvas", card)
        self.assertTrue(card.count("\n") <= 75, f"Recovery card length ({card.count(chr(10))} lines) exceeds single page limit")


if __name__ == "__main__":
    unittest.main()
