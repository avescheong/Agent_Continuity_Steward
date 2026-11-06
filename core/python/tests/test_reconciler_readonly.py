"""Tests for Read-Only SSOT Reconciler and filesystem security invariants."""

import unittest
import tempfile
import ast
from pathlib import Path
from scs_core.db.database import VaultDatabase
from scs_core.models import ArtifactType, ArtifactCustodyState
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler


class TestReconcilerReadOnly(unittest.TestCase):
    def setUp(self):
        self.temp_db_dir = tempfile.TemporaryDirectory()
        self.temp_proj_dir = tempfile.TemporaryDirectory()

        self.db_path = Path(self.temp_db_dir.name) / "test_vault.db"
        self.db = VaultDatabase(self.db_path)

        self.project_svc = ProjectSessionService(self.db)
        self.artifact_svc = ArtifactRegistryService(self.db)
        self.reconciler = ReadOnlyReconciler(self.db)

        self.proj_root = Path(self.temp_proj_dir.name)
        self.proj = self.project_svc.create_project(
            code="TEST_PRJ",
            name="Test Project",
            root_paths=[str(self.proj_root)],
        )

    def tearDown(self):
        self.temp_db_dir.cleanup()
        self.temp_proj_dir.cleanup()

    def test_reconciler_contains_no_write_calls(self):
        """AST security inspection: mod07_reconciler must contain zero write/delete calls."""
        from scs_core.modules import mod07_reconciler
        reconciler_code = Path(mod07_reconciler.__file__).read_text(encoding="utf-8")
        tree = ast.parse(reconciler_code)
        
        forbidden_calls = {"remove", "unlink", "rmdir", "rename", "replace", "mkdir", "write_text", "write_bytes"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                    self.fail(f"Forbidden mutating call found in mod07_reconciler: {func.attr}")

    def test_full_artifact_custody_lifecycle(self):
        # 1. Conversation only
        art1 = self.artifact_svc.register_artifact(
            project_id=self.proj.id,
            name="blueprint.md",
            conversation_note="Discussed in chat",
        )
        art1 = self.reconciler.reconcile_artifact(art1, self.proj.root_paths)
        self.assertEqual(art1.custody_state, ArtifactCustodyState.CONVERSATION_ONLY)

        # 2. Bind path to a non-existent file -> MISSING
        self.artifact_svc.bind_path(art1.id, relative_path="docs/blueprint.md")
        art1 = self.artifact_svc.get_artifact(art1.id)
        art1 = self.reconciler.reconcile_artifact(art1, self.proj.root_paths)
        self.assertEqual(art1.custody_state, ArtifactCustodyState.MISSING)

        # 3. Create file on disk -> LOCAL_FILE_EXISTS
        doc_dir = self.proj_root / "docs"
        doc_dir.mkdir(parents=True, exist_ok=True)
        file_path = doc_dir / "blueprint.md"
        file_path.write_text("Hello Blueprint v1", encoding="utf-8")

        art1 = self.reconciler.reconcile_artifact(art1, self.proj.root_paths)
        self.assertEqual(art1.custody_state, ArtifactCustodyState.LOCAL_FILE_EXISTS)
        self.assertIsNotNone(art1.observed_sha256)

        # 4. Lock baseline -> VERIFIED_MATCH
        self.artifact_svc.lock_baseline_checksum(art1.id)
        art1 = self.artifact_svc.get_artifact(art1.id)
        self.assertEqual(art1.custody_state, ArtifactCustodyState.VERIFIED_MATCH)

        # 5. Modify file on disk -> MODIFIED
        file_path.write_text("Hello Blueprint v2 (Changed)", encoding="utf-8")
        art1 = self.reconciler.reconcile_artifact(art1, self.proj.root_paths)
        self.assertEqual(art1.custody_state, ArtifactCustodyState.MODIFIED)

        # 6. Delete file -> MISSING
        file_path.unlink()
        art1 = self.reconciler.reconcile_artifact(art1, self.proj.root_paths)
        self.assertEqual(art1.custody_state, ArtifactCustodyState.MISSING)

    def test_path_traversal_blocked(self):
        art = self.artifact_svc.register_artifact(
            project_id=self.proj.id,
            name="sensitive.txt",
            relative_path="../../outside.txt",
        )
        art = self.reconciler.reconcile_artifact(art, self.proj.root_paths)
        self.assertEqual(art.custody_state, ArtifactCustodyState.UNKNOWN)

    def test_required_markers_check(self):
        f = self.proj_root / "spec.html"
        f.write_text("<html><div id='forecast-modal'></div></html>", encoding="utf-8")

        art = self.artifact_svc.register_artifact(
            project_id=self.proj.id,
            name="spec.html",
            relative_path="spec.html",
            required_markers=["#forecast-modal", "LCK-013"],
        )
        art = self.reconciler.reconcile_artifact(art, self.proj.root_paths)
        # Because LCK-013 is missing from file, state must be MODIFIED
        self.assertEqual(art.custody_state, ArtifactCustodyState.MODIFIED)
        self.assertIn("LCK-013", art.missing_markers)
        self.assertNotIn("#forecast-modal", art.missing_markers)


if __name__ == "__main__":
    unittest.main()
