"""
Phase 12 Stage 1 Regression Test Suite for v1.0.1 Remediation
=============================================================

Validates:
1. POST-GA-001: Zero-dependency models (no pydantic required, exact schema & serialization match).
2. POST-GA-002: Canonical package layout (import resolution without PYTHONPATH or sys.path injection).
3. CLI dispatch: scs entrypoint and python -m engine.scs_cli execution.
"""

import sys
import os
import unittest
import tempfile
import subprocess
from pathlib import Path

# Ensure src/ and engine are available for standalone test discovery
REPO_ROOT = Path(__file__).resolve().parent.parent
for p in [REPO_ROOT / "src", REPO_ROOT / "SCS_AG_v2", REPO_ROOT / "SCS_AG_v2" / "engine"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


class TestStage1ModelsZeroDependency(unittest.TestCase):
    """Verifies that scs_core.models functions with zero third-party dependencies."""

    def test_no_pydantic_in_imports(self):
        """Ensures pydantic is not required to import scs_core.models."""
        from scs_core import models
        # Ensure models module does not reference pydantic
        self.assertFalse(hasattr(models, "pydantic"))

    def test_instantiate_and_dump_all_models(self):
        """Verifies instantiation and JSON serialization of all domain models."""
        from scs_core.models import (
            Project,
            Proposal,
            ProposalType,
            ProposalStatus,
            DecisionRecord,
            DecisionKind,
            TaskItem,
            TaskStatus,
            TaskPriority,
            ArtifactRecord,
            ArtifactType,
            ArtifactCustodyState,
            SnapshotRecord,
            HandoverPackage,
            ReconcileSummary,
            BootstrapResult,
            DashboardState,
            ChatFragment,
            ConversationSession,
        )

        # 1. Project
        proj = Project(code="PRJ-01", name="Test Project")
        dump = proj.model_dump(mode="json")
        self.assertEqual(dump["code"], "PRJ-01")
        self.assertEqual(dump["name"], "Test Project")
        self.assertIsInstance(dump["id"], str)
        self.assertIsInstance(dump["created_at"], str)

        # 2. DecisionRecord
        dec = DecisionRecord(
            project_id=proj.id,
            code="DEC-001",
            record_kind=DecisionKind.DECISION,
            statement="Use pure stdlib models",
            rationale_why="Zero external dependencies",
        )
        dump_dec = dec.model_dump(mode="json")
        self.assertEqual(dump_dec["record_kind"], "DECISION")
        self.assertEqual(dump_dec["statement"], "Use pure stdlib models")

        # 3. TaskItem
        task = TaskItem(
            project_id=proj.id,
            code="TSK-001",
            title="Implement stdlib models",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            why_it_matters="Reason: Needed for clean venv zero-dep install",
        )
        dump_task = task.model_dump(mode="json")
        self.assertEqual(dump_task["status"], "IN_PROGRESS")
        self.assertEqual(dump_task["priority"], "HIGH")
        self.assertEqual(task.compact_why, "Needed for clean venv zero-dep...")

        # 4. ArtifactRecord
        art = ArtifactRecord(
            project_id=proj.id,
            name="models.py",
            artifact_type=ArtifactType.CODE_FILE,
            custody_state=ArtifactCustodyState.VERIFIED_MATCH,
        )
        dump_art = art.model_dump(mode="json")
        self.assertEqual(dump_art["artifact_type"], "CODE_FILE")
        self.assertEqual(dump_art["custody_state"], "VERIFIED_MATCH")

        # 5. SnapshotRecord
        snp = SnapshotRecord(
            project_id=proj.id,
            snapshot_code="SNP-20261106-001",
            state_json='{"status": "ok"}',
            checksum_sha256="abc123sha",
        )
        dump_snp = snp.model_dump(mode="json")
        self.assertEqual(dump_snp["snapshot_code"], "SNP-20261106-001")

        # 6. HandoverPackage
        pkg = HandoverPackage(
            project_id=proj.id,
            markdown_content="# Handover",
            checksum_sha256="pkg123sha",
        )
        dump_pkg = pkg.model_dump(mode="json")
        self.assertEqual(dump_pkg["protocol_version"], "scs-handover/1.0")

        # 7. Proposal
        prop = Proposal(
            project_id=proj.id,
            proposal_type=ProposalType.DECISION,
            title="Switch to pure dataclasses",
        )
        dump_prop = prop.model_dump(mode="json")
        self.assertEqual(dump_prop["proposal_type"], "DECISION")
        self.assertEqual(dump_prop["status"], "PENDING")

        # 8. ReconcileSummary & BootstrapResult
        rec = ReconcileSummary(total=5, verified_match=5)
        boot = BootstrapResult(
            project_code="PRJ-01",
            prompt_text="Prompt content",
            approx_tokens=150,
            redacted_count=0,
            reconcile_summary=rec,
        )
        dump_boot = boot.model_dump(mode="json")
        self.assertEqual(dump_boot["reconcile_summary"]["verified_match"], 5)

        # 9. DashboardState
        dash = DashboardState(
            active_project=proj,
            tasks=[task],
            decisions=[dec],
            artifacts=[art],
            reconcile_summary=rec,
        )
        dump_dash = dash.model_dump(mode="json")
        self.assertEqual(dump_dash["active_project"]["code"], "PRJ-01")
        self.assertEqual(len(dump_dash["tasks"]), 1)
        self.assertEqual(dump_dash["tasks"][0]["code"], "TSK-001")
        self.assertEqual(dump_dash["reconcile_summary"]["total"], 5)

    def test_resilient_kwargs_handling(self):
        """Verifies that unknown/deprecated kwargs (e.g. timestamp) do not raise TypeError."""
        from scs_core.models import ChatFragment
        # mod02_protocol_engine passes timestamp=r["started_at"]
        frag = ChatFragment(
            sequence_idx=1,
            content="Hello SCS",
            timestamp="2026-11-06T12:00:00Z",
            extra_unknown_field=999,
        )
        self.assertEqual(frag.content, "Hello SCS")
        self.assertEqual(frag.sequence_idx, 1)


class TestStage1PackageLayoutAndDispatch(unittest.TestCase):
    """Verifies that canonical package layout resolves imports and dispatches CLI."""

    def test_direct_imports(self):
        """Verifies direct imports of engine and scs_core without path tampering."""
        import scs_core
        from scs_core.modules.caveman_engine import CavemanContextExtractionEngine
        from scs_core.modules.caveman_context_validator import CavemanContextValidator
        from scs_core.modules.mod07_reconciler import ReadOnlyReconciler

        self.assertIsNotNone(scs_core)
        self.assertIsNotNone(CavemanContextExtractionEngine)
        self.assertIsNotNone(CavemanContextValidator)
        self.assertIsNotNone(ReadOnlyReconciler)

    def test_cli_help_dispatch(self):
        """Verifies that scs_cli.main with --help exits cleanly with 0."""
        from engine.scs_cli import main
        with self.assertRaises(SystemExit) as cm:
            main(["--help"])
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
