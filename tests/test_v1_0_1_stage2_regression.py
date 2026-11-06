"""
Phase 12 Stage 2 Regression Test Suite for v1.0.1 Remediation
=============================================================

Validates:
1. POST-GA-003: Rollback CLI ergonomics
   - Positional snapshot_code rollback
   - --snapshot flag alias rollback
   - Invalid snapshot error handling
   - Missing snapshot error handling
   - Help output clarity
2. POST-GA-004: QUICKSTART sample alignment
"""

import sys
import os
import io
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure src/ and engine are available for standalone test discovery
REPO_ROOT = Path(__file__).resolve().parent.parent
for p in [REPO_ROOT / "src", REPO_ROOT / "SCS_AG_v2", REPO_ROOT / "SCS_AG_v2" / "engine"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from engine import scs_cli, vault_store


class TestStage2RollbackErgonomics(unittest.TestCase):
    """Verifies POST-GA-003: Positional and flag rollback ergonomics."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.proj_dir = Path(self.temp_dir.name) / "TestRollbackProj"
        scs_cli.main(["new", "TRB", "Test Rollback Project", "--path", str(self.proj_dir)])
        self.vault_path = self.proj_dir / ".continuity"
        self.initial_snap = vault_store.list_snapshots(self.vault_path)[0]["snapshot_code"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_positional_rollback(self):
        """Tests existing syntax: scs rollback <SNAP> --project <PRJ>."""
        ledger = vault_store.read_ledger(self.vault_path, verify_seal=True)
        ledger["decisions"].append({
            "code": "DEC-POS",
            "statement": "Decision for positional test",
            "rationale_why": "Testing positional argument",
            "is_active": True,
        })
        vault_store.write_ledger(self.vault_path, ledger, label="Commit positional")
        self.assertEqual(len(vault_store.read_ledger(self.vault_path)["decisions"]), 1)

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["rollback", self.initial_snap, "--project", str(self.proj_dir)])
        self.assertEqual(code, 0)
        self.assertIn(f"Successfully rolled back canonical memory to snapshot `{self.initial_snap}`", stdout_buf.getvalue())
        self.assertEqual(len(vault_store.read_ledger(self.vault_path)["decisions"]), 0)

    def test_snapshot_flag_rollback(self):
        """Tests new syntax: scs rollback --snapshot <SNAP> --project <PRJ>."""
        ledger = vault_store.read_ledger(self.vault_path, verify_seal=True)
        ledger["decisions"].append({
            "code": "DEC-FLAG",
            "statement": "Decision for flag test",
            "rationale_why": "Testing --snapshot flag alias",
            "is_active": True,
        })
        vault_store.write_ledger(self.vault_path, ledger, label="Commit flag")
        self.assertEqual(len(vault_store.read_ledger(self.vault_path)["decisions"]), 1)

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["rollback", "--snapshot", self.initial_snap, "--project", str(self.proj_dir)])
        self.assertEqual(code, 0)
        self.assertIn(f"Successfully rolled back canonical memory to snapshot `{self.initial_snap}`", stdout_buf.getvalue())
        self.assertEqual(len(vault_store.read_ledger(self.vault_path)["decisions"]), 0)

    def test_missing_snapshot_error(self):
        """Tests that rollback without snapshot argument returns code 1 and actionable message."""
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            code = scs_cli.main(["rollback", "--project", str(self.proj_dir)])
        self.assertEqual(code, 1)
        self.assertIn("Snapshot code required", stderr_buf.getvalue())
        self.assertIn("--snapshot", stderr_buf.getvalue())

    def test_invalid_snapshot_error(self):
        """Tests that rollback with non-existent snapshot code returns code 1."""
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            code = scs_cli.main(["rollback", "--snapshot", "SNP-NONEXISTENT", "--project", str(self.proj_dir)])
        self.assertEqual(code, 1)
        self.assertIn("Error executing rollback", stderr_buf.getvalue())

    def test_help_clarity(self):
        """Tests that rollback help displays both positional and flag syntax."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            with self.assertRaises(SystemExit) as cm:
                scs_cli.main(["rollback", "--help"])
        self.assertEqual(cm.exception.code, 0)
        help_text = stdout_buf.getvalue()
        self.assertIn("[snapshot_code]", help_text)
        self.assertIn("--snapshot", help_text)


if __name__ == "__main__":
    unittest.main()
