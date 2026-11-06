"""Tests for Bootstrap prompt generation and secret scrubber."""

import unittest
import tempfile
from pathlib import Path

from scs_core.db.database import VaultDatabase
from scs_core.models import DecisionKind, TaskPriority, TaskStatus
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService


class TestBootstrapAndScrubber(unittest.TestCase):
    def setUp(self):
        self.temp_db_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_db_dir.name) / "test_vault.db"
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

        self.proj = self.project_svc.ensure_default_project()

    def tearDown(self):
        self.temp_db_dir.cleanup()

    def test_bootstrap_generation_contains_all_core_sections(self):
        # 1. Add decision, rejected option, task, artifact
        self.decision_svc.create_decision(
            self.proj.id,
            DecisionKind.DECISION,
            statement="Use SQLite WAL for storage",
            rationale_why="Fast local ACID",
        )
        self.decision_svc.create_decision(
            self.proj.id,
            DecisionKind.REJECTED_OPTION,
            statement="Do not use PostgreSQL",
            rationale_why="Heavy external service dependency",
        )
        self.checklist_svc.create_task(
            self.proj.id,
            title="Implement reconciler",
            priority=TaskPriority.HIGH,
            status=TaskStatus.IN_PROGRESS,
            why_it_matters="Verify real files on disk",
        )
        self.artifact_svc.register_artifact(
            self.proj.id,
            name="schema.sql",
            conversation_note="Drafted in chat",
        )

        res = self.protocol_svc.compile_bootstrap(self.proj.id, include_sync_footer=True)
        self.assertIn("=== [SCS CONTINUITY BOOTSTRAP: SCS_DEMO] ===", res.prompt_text)
        self.assertIn("Use SQLite WAL for storage", res.prompt_text)
        self.assertIn("⛔ [REJ-001] Do not use PostgreSQL", res.prompt_text)
        self.assertIn("[IN_PROGRESS] Implement reconciler", res.prompt_text)
        self.assertIn("schema.sql", res.prompt_text)
        self.assertIn("```scs-delta", res.prompt_text)
        self.assertGreater(res.approx_tokens, 50)
        self.assertEqual(res.redacted_count, 0)

    def test_pre_bootstrap_secret_scrubber_redacts_keys(self):
        # Inject an API key into a task title/why
        self.checklist_svc.create_task(
            self.proj.id,
            title="Configure test token",
            why_it_matters="Using key sk-1234567890abcdef1234567890 for test",
        )
        res = self.protocol_svc.compile_bootstrap(self.proj.id)
        self.assertNotIn("sk-1234567890abcdef1234567890", res.prompt_text)
        self.assertIn("[REDACTED_SECRET]", res.prompt_text)
        self.assertGreaterEqual(res.redacted_count, 1)


if __name__ == "__main__":
    unittest.main()
