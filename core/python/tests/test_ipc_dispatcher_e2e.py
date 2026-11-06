"""End-to-end tests for the SCSDispatcher IPC layer."""

import unittest
import tempfile
from pathlib import Path

from scs_core.db.database import VaultDatabase
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService
from scs_core.ipc.dispatcher import SCSDispatcher


class TestIPCDispatcherE2E(unittest.TestCase):
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
        self.reconciler = ReadOnlyReconciler(self.db)
        self.protocol_svc = ProtocolEngineService(
            self.db,
            self.project_svc,
            self.decision_svc,
            self.checklist_svc,
            self.artifact_svc,
            self.gate_svc,
            self.reconciler,
        )

        self.dispatcher = SCSDispatcher(
            self.db,
            self.project_svc,
            self.decision_svc,
            self.checklist_svc,
            self.artifact_svc,
            self.gate_svc,
            self.reconciler,
            self.protocol_svc,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_ipc_user_lifecycle(self):
        # 1. Get initial dashboard (seeds default project)
        res = self.dispatcher.invoke("get_dashboard_state")
        self.assertTrue(res["ok"])
        data = res["data"]
        self.assertIsNotNone(data["active_project"])
        proj_id = data["active_project"]["id"]

        # 2. Update session focus
        res = self.dispatcher.invoke("update_project_session", {
            "project_id": proj_id,
            "objective": "Build SCS-HUD Lite",
            "current_focus": "IPC testing",
            "next_action": "Complete UI",
        })
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["current_focus"], "IPC testing")

        # 3. Stage AI capture text
        sample_delta = """
```scs-delta
{
  "decisions": [
    {"statement": "Use Tauri IPC pattern", "why": "Seamless future migration"}
  ],
  "tasks": [
    {"title": "Implement web frontend", "why": "Progressive disclosure UI"}
  ]
}
```
"""
        res = self.dispatcher.invoke("stage_raw_capture", {
            "project_id": proj_id,
            "raw_text": sample_delta,
        })
        self.assertTrue(res["ok"])
        staged = res["data"]
        self.assertEqual(len(staged), 2)

        # 4. Human approves all proposals
        res = self.dispatcher.invoke("approve_all_proposals", {"project_id": proj_id})
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["approved_count"], 2)

        # 5. Verify tasks and decisions updated in dashboard
        res = self.dispatcher.invoke("get_dashboard_state", {"project_id": proj_id})
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["data"]["tasks"]), 1)
        self.assertEqual(len(res["data"]["decisions"]), 1)

        task_id = res["data"]["tasks"][0]["id"]

        # 6. Cycle task status to IN_PROGRESS then COMPLETED
        res = self.dispatcher.invoke("cycle_task_status", {"task_id": task_id})
        self.assertEqual(res["data"]["status"], "IN_PROGRESS")

        res = self.dispatcher.invoke("cycle_task_status", {"task_id": task_id})
        self.assertEqual(res["data"]["status"], "COMPLETED")

        # 7. Generate Bootstrap prompt
        res = self.dispatcher.invoke("generate_bootstrap", {"project_id": proj_id})
        self.assertTrue(res["ok"])
        self.assertIn("Build SCS-HUD Lite", res["data"]["prompt_text"])
        self.assertIn("Use Tauri IPC pattern", res["data"]["prompt_text"])

        # 8. Create Snapshot
        res = self.dispatcher.invoke("create_snapshot", {
            "project_id": proj_id,
            "label": "E2E Verified",
        })
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["data"]["checksum_sha256"]), 64)

        # 9. Generate Handover package
        res = self.dispatcher.invoke("generate_handover", {
            "project_id": proj_id,
            "save_to_exports": False,
        })
        self.assertTrue(res["ok"])
        self.assertIn("SESSION HANDOVER PACKAGE", res["data"]["markdown_content"])

    def test_stage_proposal_with_rationale(self):
        res = self.dispatcher.invoke("get_dashboard_state")
        proj_id = res["data"]["active_project"]["id"]

        # Stage structured proposal via cmd_stage_proposal
        res = self.dispatcher.invoke("stage_proposal", {
            "project_id": proj_id,
            "proposal_type": "DECISION",
            "title": "Use SQLite WAL Mode",
            "rationale_why": "Enables concurrent zero-lock readers",
        })
        self.assertTrue(res["ok"])
        prop = res["data"]
        self.assertEqual(prop["title"], "Use SQLite WAL Mode")
        self.assertEqual(prop["rationale_why"], "Enables concurrent zero-lock readers")
        self.assertEqual(prop["proposal_type"], "DECISION")

        # Test text parsing of labeled line with (Why: ...)
        staged = self.protocol_svc.parse_and_stage_capture(
            project_id=proj_id,
            raw_text="Decision: Strict O_RDONLY (Why: Prevent disk mutation)",
        )
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["title"], "Strict O_RDONLY")
        self.assertEqual(staged[0]["rationale_why"], "Prevent disk mutation")

    def test_duplicate_project_code_validation(self):
        # 1. Create a project
        res = self.dispatcher.invoke("create_project", {
            "code": "UNIQUE_PRJ",
            "name": "First Project",
        })
        self.assertTrue(res["ok"])

        # 2. Try creating duplicate project
        dup = self.dispatcher.invoke("create_project", {
            "code": "UNIQUE_PRJ",
            "name": "Duplicate Project",
        })
        self.assertFalse(dup["ok"])
        self.assertEqual(dup["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("already in use", dup["error"]["message"])

        # 3. Empty code check
        empty = self.dispatcher.invoke("create_project", {
            "code": "   ",
            "name": "Empty Code",
        })
        self.assertFalse(empty["ok"])
        self.assertEqual(empty["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
