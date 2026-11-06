"""Unit & integration test suite for Session Custody, Continuity_MD Chapters, and AI_HANDOVER_PACKAGE."""

import unittest
import tempfile
import shutil
from pathlib import Path

from scs_core.db.database import VaultDatabase
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService
from scs_core.modules.caveman_engine import CavemanContextExtractionEngine
from scs_core.ipc.dispatcher import SCSDispatcher
from scs_core.models import CheckpointStatus, DecisionKind, TaskStatus


class TestCheckpointEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test_vault.db"
        self.exports_dir = self.temp_dir / "exports"
        self.snapshots_dir = self.temp_dir / "snapshots"

        self.db = VaultDatabase(self.db_path)
        self.proj_svc = ProjectSessionService(self.db, snapshots_dir=self.snapshots_dir)
        self.dec_svc = DecisionLedgerService(self.db)
        self.chk_svc = ChecklistEngineService(self.db)
        self.art_svc = ArtifactRegistryService(self.db)
        self.gate_svc = ApprovalGateService(self.db, self.dec_svc, self.chk_svc, self.art_svc)
        self.rec_svc = ReadOnlyReconciler(self.db)
        self.proto_svc = ProtocolEngineService(
            self.db, self.proj_svc, self.dec_svc, self.chk_svc, self.art_svc, self.gate_svc, self.rec_svc,
            exports_dir=self.exports_dir,
        )
        self.dispatcher = SCSDispatcher(
            self.db, self.proj_svc, self.dec_svc, self.chk_svc, self.art_svc, self.gate_svc, self.rec_svc, self.proto_svc
        )
        self.project = self.proj_svc.ensure_default_project()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_chat_sessions_raw_evidence_and_duplicate_guard(self):
        """Verifies pasting sessions stores verbatim raw evidence with zero premature processing or snapshots."""
        p_id = self.project.id
        for i in range(1, 4):
            raw_transcript = (
                f"You said:\nSession {i}: Should we use SQLite?\n\n"
                f"ChatGPT said:\nCertainly! I recommend SQLite for local offline storage."
            )
            res = self.dispatcher.invoke("add_chat_fragment", {
                "project_id": p_id,
                "text": raw_transcript,
            })
            self.assertTrue(res["ok"])
            self.assertEqual(res["data"]["session_code"], f"SES-{i:03d}")
            self.assertEqual(res["data"]["total_sessions"], i)
            self.assertEqual(res["data"]["pending_sessions"], i)
            self.assertEqual(res["data"]["processed_sessions"], 0)
            self.assertEqual(res["data"]["fragment_count"], i)
            self.assertFalse(res["data"]["auto_generated"])
            raw_path = Path(res["data"]["raw_file_path"])
            self.assertTrue(raw_path.exists())
            self.assertEqual(raw_path.read_text(encoding="utf-8"), raw_transcript)

        # Zero snapshots created on paste
        self.assertEqual(len(self.proj_svc.list_snapshots(p_id)), 0)

        # Duplicate SHA-256 guard when prevent_duplicate=True
        dup_res = self.dispatcher.invoke("add_chat_fragment", {
            "project_id": p_id,
            "text": (
                "You said:\nSession 1: Should we use SQLite?\n\n"
                "ChatGPT said:\nCertainly! I recommend SQLite for local offline storage."
            ),
            "prevent_duplicate": True,
        })
        self.assertFalse(dup_res["ok"])
        self.assertIn("Duplicate session", dup_res["error"]["message"])

        sess_res = self.dispatcher.invoke("get_conversation_session", {"project_id": p_id})
        self.assertTrue(sess_res["ok"])
        self.assertEqual(sess_res["data"]["total_sessions"], 3)
        self.assertEqual(sess_res["data"]["pending_sessions"], 3)
        self.assertEqual(len(sess_res["data"]["session"]["fragments"]), 3)

    def test_caveman_preserves_all_five_continuity_pillars(self):
        """Verifies Caveman preserves Decision History, Technical Reasoning, Governance, Evolution, and Operational State."""
        engine = CavemanContextExtractionEngine()
        sessions = [
            (
                "# Architecture & Persistence Session\n"
                "You said:\n"
                "We need an offline persistence engine. Current JSON files risk data loss if the process crashes.\n"
                "ChatGPT said:\n"
                "Option A: SQLite with WAL mode.\n"
                "Option B: LevelDB key-value store.\n"
                "I recommend SQLite with WAL mode because it gives ACID transactions.\n"
                "You said:\n"
                "We ruled out LevelDB due to lack of relational queries.\n"
                "Let's use SQLite with WAL mode because of zero-configuration ACID transactions.\n"
                "Governance: Do not break architecture freeze across [000. Character_Spec.md](https://docs.google.com/document/d/123/edit?usp=sharing) and latency must remain under 4.5ms.\n"
                "Argon:\n"
                "Configured journal_mode=WAL in src/scs_core/db/database.py.\n"
                "Root cause of previous lock bug fixed by single-writer transaction context.\n"
                "All 61 unittest tests PASSED (Exit 0) and write benchmark hit 15,000 ops/sec.\n"
                "Important clarification: Turning point — atomic unit is a complete session instead of small fragments.\n"
                "- [x] Initial project scaffold\n"
                "- [ ] Create database migration\n"
                "TBD: How to handle multi-process read locks?\n"
                "How would you like to proceed?"
            )
        ]

        extracted = engine.extract(sessions, project_code="TEST_PRJ", active_focus="Persistence Layer", session_codes=["SES-001"])

        # Pillar 1: Decision History (what, why, alternatives considered, why rejected)
        self.assertGreaterEqual(len(extracted.decisions), 1)
        dec = next(d for d in extracted.decisions if "sqlite" in d.title.lower())
        self.assertIn("acid", dec.reasoning.lower())
        self.assertIn("leveldb", dec.alternatives_considered.lower())
        self.assertTrue(any("leveldb" in r["statement"].lower() and "relational" in r["why"].lower() for r in extracted.rejected_options))

        # Pillar 2: Technical Reasoning (architecture, implementation, testing, problems & solutions)
        self.assertGreaterEqual(len(extracted.architecture_discussions), 1)
        self.assertGreaterEqual(len(extracted.implementation_approaches), 1)
        self.assertTrue(any("15,000 ops/sec" in t or "PASSED" in t for t in extracted.testing_results))
        self.assertTrue(any("root cause" in p.lower() or "data loss" in p.lower() for p in extracted.problems_and_solutions))

        # Pillar 3: Governance Constraints (no truncation on '000.' or '4.5ms')
        self.assertTrue(any("000. Character_Spec.md" in c and "4.5ms" in c for c in extracted.constraints))

        # Pillar 4: Project Evolution
        self.assertTrue(any("turning point" in e.lower() for e in extracted.project_evolution))

        # Pillar 5: Operational State & URL/fluff-free Open Questions
        self.assertTrue(any("migration" in t["title"].lower() for t in extracted.pending_tasks))
        self.assertTrue(any("scaffold" in t["title"].lower() for t in extracted.completed_tasks))
        self.assertTrue(any("database.py" in a["path"].lower() for a in extracted.artifacts))
        self.assertTrue(any("read locks" in q.lower() for q in extracted.open_questions))
        self.assertFalse(any("usp=sharing" in q.lower() for q in extracted.open_questions))
        self.assertFalse(any("how would you like to proceed" in q.lower() for q in extracted.open_questions))

    def test_custody_order_unsealed_draft_then_human_approval_seal(self):
        """Verifies Raw Evidence → Unsealed Continuity_MD Draft → Human Approval → Sealed Snapshot."""
        p_id = self.project.id
        self.dispatcher.invoke("add_chat_fragment", {
            "project_id": p_id,
            "text": "User: What database should we pick?\nAI: I recommend SQLite.\nUser: Let's use SQLite because local offline storage is required.",
        })
        self.dispatcher.invoke("add_chat_fragment", {
            "project_id": p_id,
            "text": "AI: Next tasks:\n- [ ] Implement checkpoint generator\n- [ ] Write documentation in docs/spec.md",
        })

        # Step 1: Generate Continuity MD Draft (MUST NOT seal snapshot or write export yet)
        res = self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})
        self.assertTrue(res["ok"])
        draft = res["data"]

        self.assertEqual(draft["status"], CheckpointStatus.GENERATED.value)
        self.assertEqual(draft["chapter_code"], "Continuity_MD_01")
        self.assertEqual(draft["session_range"], "SES-001..SES-002")
        self.assertEqual(draft["snapshot_code"], "PENDING_APPROVAL")
        self.assertIsNone(draft["file_path"])
        self.assertEqual(len(self.proj_svc.list_snapshots(p_id)), 0, "No snapshot allowed before human approval")
        self.assertEqual(len(self.dec_svc.list_decisions(p_id)), 0, "No ledger mutation before human approval")

        md = draft["markdown_content"]
        self.assertIn("Continuity_MD_01", md)
        self.assertIn("## 1. Context", md)
        self.assertIn("## 2. Key Decisions", md)
        self.assertIn("## 3. Constraints", md)
        self.assertIn("## 4. Tasks", md)
        self.assertIn("## 5. Artifacts", md)
        self.assertIn("## 7. Technical Reasoning & Project Evolution", md)
        self.assertIn("Next Session Bootstrap", md)
        self.assertIn("```scs-bootstrap", md)

        # Step 2: Human Approves & Seals Snapshot
        app_res = self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})
        self.assertTrue(app_res["ok"])
        sealed = app_res["data"]
        self.assertTrue(sealed["approved"])
        self.assertTrue(sealed["snapshot_code"].startswith("SNP-"))
        self.assertTrue(Path(sealed["file_path"]).exists())
        self.assertEqual(Path(sealed["file_path"]).name, f"{self.project.code}_Continuity_MD_01.md")
        self.assertGreater(sealed["promoted_decisions"], 0)
        self.assertGreater(sealed["promoted_tasks"], 0)
        self.assertGreater(sealed["promoted_artifacts"], 0)

        # Snapshot now exists and contains promoted items
        snaps = self.proj_svc.list_snapshots(p_id)
        self.assertEqual(len(snaps), 1)
        self.assertTrue(any("docs/spec.md" == (a.relative_path or "") for a in self.art_svc.list_artifacts(p_id)))

        # Raw session evidence remains preserved in SQLite & disk
        dash = self.dispatcher.invoke("get_dashboard_state", {"project_id": p_id})["data"]
        self.assertEqual(dash["total_sessions"], 2)
        self.assertEqual(dash["processed_sessions"], 2)
        self.assertEqual(dash["pending_sessions"], 0)
        self.assertEqual(dash["continuity_md_count"], 1)

    def test_no_auto_checkpoint_at_10_sessions(self):
        """Verifies pasting 10 sessions accumulates raw evidence without auto-processing."""
        p_id = self.project.id
        for i in range(1, 11):
            res = self.dispatcher.invoke("add_chat_fragment", {
                "project_id": p_id,
                "text": f"User: Working on session {i}.\nAI: Recorded progress for session {i}.",
            })
            self.assertTrue(res["ok"])
            self.assertFalse(res["data"]["auto_generated"])
            self.assertIsNone(res["data"]["checkpoint"])

        self.assertTrue(res["data"]["recommended_batch_ready"])
        self.assertEqual(res["data"]["pending_sessions"], 10)
        self.assertEqual(len(self.proj_svc.list_snapshots(p_id)), 0)

    def test_35_sessions_into_4_chapters_and_master_ai_handover_package(self):
        """End-to-end verification of 35 sessions → Continuity_MD_01..04 → AI_HANDOVER_PACKAGE.md."""
        proj = self.proj_svc.create_project(
            code="CONTINUITY35",
            name="Thirty-Five Session Project",
            objective="Build resilient multi-session AI continuity engine",
            next_action="",
        )
        p_id = proj.id

        # Batch 1: Sessions 001..010 -> Continuity_MD_01.md
        for s in range(1, 11):
            txt = f"You said:\nSession {s} architecture exploration.\nGemini:\nEvaluated storage layer in session {s}."
            if s == 3:
                txt += "\nYou said:\nLet's use PostgreSQL because of relational indexing.\nConstraint: System must run 100% offline without cloud servers."
            self.dispatcher.invoke("add_chat_fragment", {"project_id": p_id, "text": txt})

        d1 = self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})["data"]
        self.assertEqual(d1["chapter_code"], "Continuity_MD_01")
        self.assertEqual(d1["session_range"], "SES-001..SES-010")
        a1 = self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})["data"]
        self.assertTrue(Path(a1["file_path"]).exists())

        # Batch 2: Sessions 011..020 -> Continuity_MD_02.md (includes Decision Reversal!)
        for s in range(11, 21):
            txt = f"You said:\nSession {s} persistence refinement.\nChatGPT said:\nReviewed daemon footprint in session {s}."
            if s == 14:
                txt += (
                    "\nYou said:\nChange of plans: let's use SQLite WAL instead of PostgreSQL because we must be single-binary zero-config.\n"
                    "ChatGPT said:\nInitial write benchmark verified (18,000 ops/sec) in src/scs_core/db/database.py."
                )
            self.dispatcher.invoke("add_chat_fragment", {"project_id": p_id, "text": txt})

        d2 = self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})["data"]
        self.assertEqual(d2["chapter_code"], "Continuity_MD_02")
        self.assertEqual(d2["session_range"], "SES-011..SES-020")
        self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})

        # Batch 3: Sessions 021..030 -> Continuity_MD_03.md
        for s in range(21, 31):
            txt = f"You said:\nSession {s} IPC implementation.\nArgon:\nImplemented RPC handler in src/scs_host/local_rpc_server.py."
            if s == 25:
                txt += "\nArgon:\nProblem: Header overflow at 430px width; fixed by 3-action primary hierarchy.\n- [x] Verify HTTP auth token checks"
            self.dispatcher.invoke("add_chat_fragment", {"project_id": p_id, "text": txt})

        d3 = self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})["data"]
        self.assertEqual(d3["chapter_code"], "Continuity_MD_03")
        self.assertEqual(d3["session_range"], "SES-021..SES-030")
        self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})

        # Batch 4: Sessions 031..035 -> Continuity_MD_04.md
        for s in range(31, 36):
            txt = f"You said:\nSession {s} handover synthesis.\nArgon:\nFinalizing handover merger in session {s}."
            if s == 35:
                txt += "\nYou said:\n- [ ] Run final Phase 5 regression suite\nDo not use aggressive text compression because reasoning context is required."
            self.dispatcher.invoke("add_chat_fragment", {"project_id": p_id, "text": txt})

        d4 = self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})["data"]
        self.assertEqual(d4["chapter_code"], "Continuity_MD_04")
        self.assertEqual(d4["session_range"], "SES-031..SES-035")
        self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})

        # Master Handover Synthesis: Continuity_MD_01..04 -> CONTINUITY35_AI_HANDOVER_PACKAGE.md
        pkg_res = self.dispatcher.invoke("generate_handover", {
            "project_id": p_id,
            "save_to_exports": True,
        })
        self.assertTrue(pkg_res["ok"])
        pkg = pkg_res["data"]

        self.assertEqual(pkg["chapters_merged"], 4)
        self.assertEqual(pkg["total_sessions"], 35)
        self.assertEqual(pkg["processed_sessions"], 35)
        self.assertEqual(pkg["pending_sessions"], 0)
        self.assertEqual(pkg["file_name"], "CONTINUITY35_AI_HANDOVER_PACKAGE.md")
        self.assertTrue(Path(pkg["exported_file_path"]).exists())

        master_md = pkg["markdown_content"]
        # All 4 chapters merged
        for ch_code in ("Continuity_MD_01", "Continuity_MD_02", "Continuity_MD_03", "Continuity_MD_04"):
            self.assertIn(ch_code, master_md)
        self.assertIn("SES-001..SES-010", master_md)
        self.assertIn("SES-031..SES-035", master_md)

        # Superseded PostgreSQL moved out of active decisions into evolution/rejected; SQLite WAL active
        active_decs = self.dec_svc.list_decisions(p_id, active_only=True, kind=DecisionKind.DECISION)
        self.assertTrue(any("sqlite wal" in d.statement.lower() for d in active_decs))
        self.assertFalse(any("postgresql" in d.statement.lower() for d in active_decs))
        self.assertIn("SUPERSEDED", master_md)

        # Preserves reasoning, tests, problems, governance, rejected options, tasks, and scs-handover block
        self.assertIn("18,000 ops/sec", master_md)
        self.assertIn("Header overflow at 430px", master_md)
        self.assertIn("aggressive text compression", master_md.lower())
        self.assertIn("Run final Phase 5 regression suite", master_md)
        self.assertIn("```scs-handover", master_md)

        # All 35 raw session evidence files remain preserved on disk
        raw_files = list((self.exports_dir / "sessions").glob("CONTINUITY35_SES-*.md"))
        self.assertEqual(len(raw_files), 35)

        # Project next_action updated on approval
        updated_proj = self.proj_svc.get_project(p_id)
        self.assertIn("Run final Phase 5 regression suite", updated_proj.next_action)

    def test_cross_chapter_conflict_and_stateless_approval_recovery(self):
        """Verifies constraints sealed in Chapter 1 detect conflicts in Chapter 2 and approval survives host restart."""
        p_id = self.project.id

        # Chapter 1: Seal an offline governance constraint
        self.dispatcher.invoke("add_chat_fragment", {
            "project_id": p_id,
            "text": "User: Constraint: System must operate 100% offline without cloud servers.",
        })
        self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})
        self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})

        # Chapter 2: Introduce contradictory cloud task without repeating the constraint text
        self.dispatcher.invoke("add_chat_fragment", {
            "project_id": p_id,
            "text": "User: Sprint tasks:\n- [ ] Deploy AWS Lambda sync worker",
        })
        d2 = self.dispatcher.invoke("generate_checkpoint", {"project_id": p_id})["data"]
        self.assertGreaterEqual(d2["extracted_summary"]["conflicts_count"], 1)
        self.assertIn("ACTIVE CONFLICTS DETECTED", d2["markdown_content"])

        # Simulate host restart (cold _draft_cache) before human approval
        self.proto_svc._draft_cache.clear()
        app2 = self.dispatcher.invoke("approve_checkpoint", {"project_id": p_id})
        self.assertTrue(app2["ok"])
        self.assertEqual(app2["data"]["chapter_code"], "Continuity_MD_02")


if __name__ == "__main__":
    unittest.main()
