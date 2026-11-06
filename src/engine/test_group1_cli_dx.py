"""
Unit and Integration Tests for Phase 14 Group 1 (CLI Ergonomics & DX Improvements)
==================================================================================

Covers:
1. FDB-101-009: scs new dual syntax support (positional, flags --code/--name, and mixed)
2. FDB-101-012: Universal project argument acceptance (positional vs --project)
   across status, record, handover, approve, reject, and rollback.
3. FDB-101-001: Windows CLI wrappers (bin/scs.cmd, bin/scs.ps1).
"""

import io
import os
import sys
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine import scs_cli, vault_store


class TestGroup1CliDx(unittest.TestCase):
    """Test suite verifying Group 1 CLI ergonomics and wrapper invocations."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="scs_group1_test_"))
        self.old_cwd = Path.cwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. FDB-101-009: scs new dual syntax tests
    # -------------------------------------------------------------------------

    def test_new_positional_syntax_backward_compat(self):
        """Verify that existing v1.0.1 positional syntax continues to work identically."""
        p_dir = self.test_dir / "ProjPos"
        rc = scs_cli.main(["new", "POS1", "Positional Project", "--path", str(p_dir)])
        self.assertEqual(rc, 0)
        self.assertTrue((p_dir / ".continuity" / "canonical" / "ledger.json").exists())

    def test_new_flag_syntax_code_and_name(self):
        """Verify scs new --code CODE --name 'Name' works properly."""
        p_dir = self.test_dir / "ProjFlag"
        rc = scs_cli.main(["new", "--code", "FLG1", "--name", "Flag Project", "--path", str(p_dir)])
        self.assertEqual(rc, 0)
        vault_dir = p_dir / ".continuity"
        self.assertTrue(vault_dir.exists())
        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(ledger["project"]["code"], "FLG1")
        self.assertEqual(ledger["project"]["name"], "Flag Project")

    def test_new_mixed_syntax_flag_code_pos_name(self):
        """Verify scs new --code CODE 'Name' works properly."""
        p_dir = self.test_dir / "ProjMix1"
        rc = scs_cli.main(["new", "--code", "MIX1", "Mixed Project One", "--path", str(p_dir)])
        self.assertEqual(rc, 0)
        vault_dir = p_dir / ".continuity"
        self.assertTrue(vault_dir.exists())
        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(ledger["project"]["code"], "MIX1")
        self.assertEqual(ledger["project"]["name"], "Mixed Project One")

    def test_new_mixed_syntax_pos_code_flag_name(self):
        """Verify scs new CODE --name 'Name' works properly."""
        p_dir = self.test_dir / "ProjMix2"
        rc = scs_cli.main(["new", "MIX2", "--name", "Mixed Project Two", "--path", str(p_dir)])
        self.assertEqual(rc, 0)
        vault_dir = p_dir / ".continuity"
        self.assertTrue(vault_dir.exists())
        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(ledger["project"]["code"], "MIX2")
        self.assertEqual(ledger["project"]["name"], "Mixed Project Two")

    def test_new_missing_arguments_error_handling(self):
        """Verify error is reported when required parameters are omitted."""
        # Neither code nor name
        rc1 = scs_cli.main(["new"])
        self.assertEqual(rc1, 1)

        # Only code provided
        rc2 = scs_cli.main(["new", "SOLO"])
        self.assertEqual(rc2, 1)

        rc3 = scs_cli.main(["new", "--code", "SOLO"])
        self.assertEqual(rc3, 1)

    # -------------------------------------------------------------------------
    # 2. FDB-101-012: Universal project argument handling tests
    # -------------------------------------------------------------------------

    def test_status_positional_and_flag_syntax(self):
        """Verify scs status supports both positional and --project flag."""
        p_dir = self.test_dir / "StatusProj"
        scs_cli.main(["new", "--code", "STATP", "--name", "Status Project", "--path", str(p_dir)])

        # Positional project code
        rc1 = scs_cli.main(["status", "STATP"])
        self.assertEqual(rc1, 0)

        # Flag project code
        rc2 = scs_cli.main(["status", "--project", "STATP"])
        self.assertEqual(rc2, 0)

        # Positional path
        rc3 = scs_cli.main(["status", str(p_dir)])
        self.assertEqual(rc3, 0)

    def test_handover_positional_and_flag_syntax(self):
        """Verify scs handover supports both positional and --project flag."""
        p_dir = self.test_dir / "HandoverProj"
        scs_cli.main(["new", "--code", "HOP", "--name", "Handover Project", "--path", str(p_dir)])

        # Positional project code
        rc1 = scs_cli.main(["handover", "HOP"])
        self.assertEqual(rc1, 0)

        # Flag project code
        rc2 = scs_cli.main(["handover", "--project", "HOP"])
        self.assertEqual(rc2, 0)

    def test_approve_positional_and_flag_syntax(self):
        """Verify scs approve supports both positional project code and --project."""
        p_dir = self.test_dir / "ApproveProj"
        scs_cli.main(["new", "--code", "APRP", "--name", "Approve Project", "--path", str(p_dir)])

        # Stage a test proposal via vault_store.append_staging_proposals
        vault_dir = p_dir / ".continuity"
        proposals = [{
            "proposal_type": "DECISION",
            "statement": "Adopt standardized CLI argument aliases",
            "why": "Ergonomics improvement",
            "source_session_code": "SES001"
        }]
        vault_store.append_staging_proposals(vault_dir, proposals)

        # Test scs approve <PROJECT> --all (positional project with --all)
        rc = scs_cli.main(["approve", "APRP", "--all"])
        self.assertEqual(rc, 0)

        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger["decisions"]), 1)

    def test_reject_positional_and_flag_syntax(self):
        """Verify scs reject supports both positional project and --project flag."""
        p_dir = self.test_dir / "RejectProj"
        scs_cli.main(["new", "--code", "REJP", "--name", "Reject Project", "--path", str(p_dir)])

        vault_dir = p_dir / ".continuity"
        staging_data = {
            "protocol": "scs-staging/1.0",
            "updated_at": "2026-11-06T21:00:00+08:00",
            "proposals": [
                {
                    "id": "P01",
                    "proposal_type": "DECISION",
                    "statement": "Proposal to discard via flag",
                    "why": "Testing flag",
                    "source_session_code": "SES001"
                },
                {
                    "id": "P02",
                    "proposal_type": "DECISION",
                    "statement": "Proposal to discard via positional",
                    "why": "Testing positional",
                    "source_session_code": "SES001"
                }
            ]
        }
        vault_store.write_staging(vault_dir, staging_data)

        # 1. Reject using flag syntax: scs reject P01 --project REJP
        rc1 = scs_cli.main(["reject", "P01", "--project", "REJP"])
        self.assertEqual(rc1, 0)

        # 2. Reject using positional project syntax: scs reject REJP P02
        rc2 = scs_cli.main(["reject", "REJP", "P02"])
        self.assertEqual(rc2, 0)

        # Quarantine should now be empty
        st = vault_store.read_staging(vault_dir)
        self.assertEqual(len(st.get("proposals", [])), 0)

    def test_rollback_positional_and_flag_syntax(self):
        """Verify scs rollback supports positional project and positional/flag snapshots."""
        p_dir = self.test_dir / "RollbackProj"
        scs_cli.main(["new", "--code", "ROLP", "--name", "Rollback Project", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        # Baseline snapshot exists (e.g. SNP-*-001)
        snap_files = sorted((vault_dir / "snapshots").glob("SNP-*.json"))
        self.assertTrue(len(snap_files) >= 1)
        base_snap_code = snap_files[0].stem

        # 1. Rollback using flag syntax: scs rollback --project ROLP --snapshot <CODE>
        rc1 = scs_cli.main(["rollback", "--project", "ROLP", "--snapshot", base_snap_code])
        self.assertEqual(rc1, 0)

        # 2. Rollback using positional project and positional snapshot: scs rollback ROLP <CODE>
        rc2 = scs_cli.main(["rollback", "ROLP", base_snap_code])
        self.assertEqual(rc2, 0)

        # 3. Rollback using positional project and --snapshot flag: scs rollback ROLP --snapshot <CODE>
        rc3 = scs_cli.main(["rollback", "ROLP", "--snapshot", base_snap_code])
        self.assertEqual(rc3, 0)

    # -------------------------------------------------------------------------
    # 3. FDB-101-001: Windows CLI wrappers tests
    # -------------------------------------------------------------------------

    def test_windows_wrappers_exist(self):
        """Verify that bin/scs.cmd and bin/scs.ps1 exist and contain valid launcher scripts."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        cmd_wrapper = repo_root / "bin" / "scs.cmd"
        ps1_wrapper = repo_root / "bin" / "scs.ps1"

        self.assertTrue(cmd_wrapper.exists(), f"Missing wrapper: {cmd_wrapper}")
        self.assertTrue(ps1_wrapper.exists(), f"Missing wrapper: {ps1_wrapper}")

        cmd_content = cmd_wrapper.read_text(encoding="utf-8")
        self.assertIn("engine.scs_cli", cmd_content)
        self.assertIn("VIRTUAL_ENV", cmd_content)

        ps1_content = ps1_wrapper.read_text(encoding="utf-8")
        self.assertIn("engine.scs_cli", ps1_content)
        self.assertIn("VIRTUAL_ENV", ps1_content)

    def test_windows_cmd_wrapper_execution(self):
        """Verify executing bin/scs.cmd with --help exits with code 0 on Windows."""
        if sys.platform != "win32":
            self.skipTest("Windows-only wrapper test")

        repo_root = Path(__file__).resolve().parent.parent.parent
        cmd_wrapper = repo_root / "bin" / "scs.cmd"
        p = subprocess.run(
            [str(cmd_wrapper), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(p.returncode, 0)
        self.assertIn("SCS_AG_v2", p.stdout)
        self.assertIn("Available subcommands", p.stdout)

    def test_windows_ps1_wrapper_execution(self):
        """Verify executing bin/scs.ps1 with --help exits with code 0 on Windows."""
        if sys.platform != "win32":
            self.skipTest("Windows-only wrapper test")

        repo_root = Path(__file__).resolve().parent.parent.parent
        ps1_wrapper = repo_root / "bin" / "scs.ps1"
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_wrapper), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(p.returncode, 0)
        self.assertIn("SCS_AG_v2", p.stdout)
        self.assertIn("Available subcommands", p.stdout)


if __name__ == "__main__":
    unittest.main()
