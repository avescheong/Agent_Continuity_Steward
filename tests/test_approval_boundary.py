"""Tests for Human Approval Boundary and Proposal Quarantine Inbox."""

import unittest
import tempfile
from pathlib import Path
from scs_core.db.database import VaultDatabase
from scs_core.models import ProposalType, ProposalStatus, TaskStatus
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService


class TestApprovalBoundary(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_vault.db"
        self.db = VaultDatabase(self.db_path)

        self.project_svc = ProjectSessionService(self.db)
        self.decision_svc = DecisionLedgerService(self.db)
        self.checklist_svc = ChecklistEngineService(self.db)
        self.artifact_svc = ArtifactRegistryService(self.db)

        self.gate_svc = ApprovalGateService(
            self.db, self.decision_svc, self.checklist_svc, self.artifact_svc
        )
        self.proj = self.project_svc.ensure_default_project()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_staged_proposals_do_not_mutate_canonical_state(self):
        # Stage proposals for all 7 types
        for ptype in ProposalType:
            self.gate_svc.stage_proposal(
                project_id=self.proj.id,
                proposal_type=ptype,
                title=f"Sample {ptype.value}",
                rationale_why="Testing boundary",
            )

        # Invariant: 0 canonical rows should exist
        self.assertEqual(len(self.checklist_svc.list_tasks(self.proj.id)), 0)
        self.assertEqual(len(self.decision_svc.list_decisions(self.proj.id)), 0)
        self.assertEqual(len(self.artifact_svc.list_artifacts(self.proj.id)), 0)

        # 7 proposals must be pending
        proposals = self.gate_svc.list_proposals(self.proj.id)
        self.assertEqual(len(proposals), 7)

    def test_rejection_leaves_canonical_tables_clean(self):
        prop = self.gate_svc.stage_proposal(
            project_id=self.proj.id,
            proposal_type=ProposalType.TASK,
            title="Unwanted task",
        )
        success = self.gate_svc.reject_proposal(prop.id)
        self.assertTrue(success)

        # Canonical tables untouched
        self.assertEqual(len(self.checklist_svc.list_tasks(self.proj.id)), 0)
        # Pending count 0
        self.assertEqual(len(self.gate_svc.list_proposals(self.proj.id, ProposalStatus.PENDING)), 0)

    def test_approval_creates_canonical_entities(self):
        # 1. Task
        p_task = self.gate_svc.stage_proposal(
            project_id=self.proj.id,
            proposal_type=ProposalType.TASK,
            title="Implement feature",
            rationale_why="High value",
        )
        res_task = self.gate_svc.approve_proposal(p_task.id)
        tasks = self.checklist_svc.list_tasks(self.proj.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Implement feature")
        self.assertEqual(tasks[0].status, TaskStatus.PENDING)

        # 2. Blocker
        p_block = self.gate_svc.stage_proposal(
            project_id=self.proj.id,
            proposal_type=ProposalType.BLOCKER,
            title="Database locked",
            rationale_why="Missing credentials",
        )
        self.gate_svc.approve_proposal(p_block.id)
        tasks = self.checklist_svc.list_tasks(self.proj.id)
        self.assertEqual(len(tasks), 2)
        blocker_task = next(t for t in tasks if t.title == "Database locked")
        self.assertEqual(blocker_task.status, TaskStatus.BLOCKED)
        self.assertEqual(blocker_task.blocker_reason, "Missing credentials")

        # 3. Decision
        p_dec = self.gate_svc.stage_proposal(
            project_id=self.proj.id,
            proposal_type=ProposalType.DECISION,
            title="Use SQLite WAL",
            rationale_why="Simplicity",
        )
        self.gate_svc.approve_proposal(p_dec.id)
        decisions = self.decision_svc.list_decisions(self.proj.id)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].statement, "Use SQLite WAL")

        # 4. Artifact
        p_art = self.gate_svc.stage_proposal(
            project_id=self.proj.id,
            proposal_type=ProposalType.ARTIFACT,
            title="spec.md",
            rationale_why="Discussed in chat",
        )
        self.gate_svc.approve_proposal(p_art.id)
        artifacts = self.artifact_svc.list_artifacts(self.proj.id)
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].name, "spec.md")
        self.assertEqual(artifacts[0].custody_state.value, "CONVERSATION_ONLY")


if __name__ == "__main__":
    unittest.main()
