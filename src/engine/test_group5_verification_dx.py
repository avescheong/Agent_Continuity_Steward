"""
Unit and Integration Tests for Phase 14 Group 5 (Git Pre-Commit Verification Tooling)
=====================================================================================

Covers:
1. FDB-101-007: Standalone Git Pre-Commit Hook Guard & Verification
   - scs hook install --git: Safe hook installation in .git/hooks/pre-commit
   - Existing hook preservation (appends SCS guard without overwriting existing linters)
   - Idempotent re-installation protection
   - scripts/scs-pre-commit.py: Standalone zero-dependency seal verification
   - Successful validation on intact ledger and seal
   - Fail-closed rejection on corrupted JSON ledger
   - Fail-closed rejection on cryptographic seal mismatch (tampered state)
   - Fail-closed rejection on missing canonical ledger
   - Staging quarantine advisory notice without blocking commits
"""

import io
import json
import os
import sys
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine import scs_cli, vault_store

# Import standalone script module for direct testing
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import importlib.util
pre_commit_spec = importlib.util.spec_from_file_location("scs_pre_commit", str(SCRIPTS_DIR / "scs-pre-commit.py"))
scs_pre_commit = importlib.util.module_from_spec(pre_commit_spec)
pre_commit_spec.loader.exec_module(scs_pre_commit)


class TestGroup5VerificationDx(unittest.TestCase):
    """Test suite verifying Group 5 Git pre-commit hook installation and verification."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="scs_group5_test_"))
        self.old_cwd = Path.cwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. FDB-101-007: CLI Hook Installation Tests (scs hook install --git)
    # -------------------------------------------------------------------------

    def test_hook_install_in_fresh_git_repo(self):
        """Verify scs hook install --git creates pre-commit hook in fresh repo."""
        repo_dir = self.test_dir / "FreshGitRepo"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        git_dir.mkdir()

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Successfully installed SCS Git pre-commit hook", output)

        hook_file = git_dir / "hooks" / "pre-commit"
        self.assertTrue(hook_file.exists())
        hook_text = hook_file.read_text(encoding="utf-8")
        self.assertIn("#!/bin/sh", hook_text)
        self.assertIn("SCS PRE-COMMIT GUARD START", hook_text)
        self.assertIn("scripts/scs-pre-commit.py", hook_text)

        # Check script deployed in repo
        target_script = repo_dir / "scripts" / "scs-pre-commit.py"
        self.assertTrue(target_script.exists())

    def test_hook_install_preserves_existing_hook_content(self):
        """Verify scs hook install --git preserves existing linter/test hook content."""
        repo_dir = self.test_dir / "ExistingHookRepo"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        existing_hook = hooks_dir / "pre-commit"
        existing_hook.write_text(
            "#!/bin/sh\n# Existing custom linter\nnpm run lint || exit 1\n",
            encoding="utf-8",
        )

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Appended SCS verification guard to existing hook", output)
        self.assertIn("Existing hook commands preserved", output)

        hook_text = existing_hook.read_text(encoding="utf-8")
        # Existing commands must remain intact at the top
        self.assertIn("npm run lint || exit 1", hook_text)
        # SCS guard must be appended
        self.assertIn("SCS PRE-COMMIT GUARD START", hook_text)
        self.assertTrue(hook_text.index("npm run lint") < hook_text.index("SCS PRE-COMMIT GUARD START"))

    def test_hook_install_idempotent(self):
        """Verify calling scs hook install multiple times does not duplicate guard."""
        repo_dir = self.test_dir / "IdempotentRepo"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        git_dir.mkdir()

        # First install
        scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        # Second install
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("already installed", output)

        hook_file = git_dir / "hooks" / "pre-commit"
        hook_text = hook_file.read_text(encoding="utf-8")
        self.assertEqual(hook_text.count("SCS PRE-COMMIT GUARD START"), 1)

    def test_hook_install_fails_if_not_git_repo(self):
        """Verify scs hook install fails gracefully if target is not a git repository."""
        non_git_dir = self.test_dir / "NoGitDir"
        non_git_dir.mkdir()

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            rc = scs_cli.main(["hook", "install", "--git", "--path", str(non_git_dir)])

        self.assertEqual(rc, 1)
        err = stderr_buf.getvalue()
        self.assertIn("Not a Git repository", err)

    def test_hook_install_fails_without_git_flag(self):
        """Verify scs hook install requires --git flag to specify hook target."""
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            rc = scs_cli.main(["hook", "install"])

        self.assertEqual(rc, 1)
        err = stderr_buf.getvalue()
        self.assertIn("Target VCS hook not specified", err)

    # -------------------------------------------------------------------------
    # 2. Standalone Hook Script Verification (scripts/scs-pre-commit.py)
    # -------------------------------------------------------------------------

    def test_pre_commit_script_successful_validation(self):
        """Verify scs-pre-commit passes on intact canonical ledger and seal."""
        proj_dir = self.test_dir / "ValidProj"
        scs_cli.main(["new", "VAL", "Validation Project", "--path", str(proj_dir)])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_pre_commit.main(["--path", str(proj_dir)])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("SCS State Seal Intact: VAL", output)
        self.assertIn("Pre-commit verification passed", output)

    def test_pre_commit_script_seal_mismatch_rejection(self):
        """Verify scs-pre-commit fails closed (rc=1) when canonical ledger is tampered."""
        proj_dir = self.test_dir / "TamperProj"
        scs_cli.main(["new", "TAM", "Tamper Project", "--path", str(proj_dir)])

        # Tamper directly with canonical ledger without authorized sealing
        ledger_path = proj_dir / ".continuity" / "canonical" / "ledger.json"
        ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger_data["decisions"].append({
            "code": "DEC-TAMPERED",
            "statement": "Unauthorized decision injected bypassing custody gate",
            "is_active": True,
        })
        ledger_path.write_text(json.dumps(ledger_data, indent=2), encoding="utf-8")

        stderr_buf = io.StringIO()
        stdout_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf), patch("sys.stdout", stdout_buf):
            rc = scs_pre_commit.main(["--path", str(proj_dir)])

        self.assertEqual(rc, 1)
        err_out = stderr_buf.getvalue()
        self.assertIn("Cryptographic State Seal Mismatch", err_out)
        self.assertIn("scs rollback TAM", err_out)

    def test_pre_commit_script_corrupted_json_rejection(self):
        """Verify scs-pre-commit fails closed (rc=1) when canonical ledger has corrupted JSON."""
        proj_dir = self.test_dir / "CorruptProj"
        scs_cli.main(["new", "COR", "Corrupt Project", "--path", str(proj_dir)])

        # Corrupt JSON syntax
        ledger_path = proj_dir / ".continuity" / "canonical" / "ledger.json"
        ledger_path.write_text("{ unclosed bad json content ...", encoding="utf-8")

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            rc = scs_pre_commit.main(["--path", str(proj_dir)])

        self.assertEqual(rc, 1)
        err_out = stderr_buf.getvalue()
        self.assertIn("Corrupted JSON in canonical ledger", err_out)

    def test_pre_commit_script_missing_ledger_rejection(self):
        """Verify scs-pre-commit fails closed (rc=1) when canonical ledger file is missing."""
        proj_dir = self.test_dir / "MissingLedgerProj"
        scs_cli.main(["new", "MIS", "Missing Project", "--path", str(proj_dir)])

        # Delete canonical ledger
        ledger_path = proj_dir / ".continuity" / "canonical" / "ledger.json"
        ledger_path.unlink()

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            rc = scs_pre_commit.main(["--path", str(proj_dir)])

        self.assertEqual(rc, 1)
        err_out = stderr_buf.getvalue()
        self.assertIn("Missing canonical ledger", err_out)

    def test_pre_commit_script_no_vaults_non_strict_allowed(self):
        """Verify scs-pre-commit exits cleanly if no .continuity vaults are present."""
        empty_dir = self.test_dir / "EmptyDir"
        empty_dir.mkdir()

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_pre_commit.main(["--path", str(empty_dir)])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("No .continuity vaults found. Skipping state seal verification.", output)

    def test_pre_commit_script_staging_warning_is_advisory(self):
        """Verify pending proposals in staging emit an advisory notice without blocking commit."""
        proj_dir = self.test_dir / "StagingNoticeProj"
        scs_cli.main(["new", "STG", "Staging Project", "--path", str(proj_dir)])

        # Add pending proposal in staging
        staging_path = proj_dir / ".continuity" / "staging" / "pending_proposals.json"
        staging_data = {
            "protocol": "scs-staging/1.0",
            "proposals": [
                {
                    "id": "P01",
                    "proposal_type": "DECISION",
                    "statement": "Pending proposal awaiting human operator review",
                }
            ],
        }
        staging_path.write_text(json.dumps(staging_data, indent=2), encoding="utf-8")

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_pre_commit.main(["--path", str(proj_dir)])

        # Commit is allowed, but notice is emitted
        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("SCS State Seal Intact: STG", output)
        self.assertIn("[!] Notice: 1 unreviewed proposal(s) staged in quarantine", output)


    def test_hook_install_deploys_real_verification_script(self):
        """Verify scs hook install --git deploys the real state seal verification script, not a stub."""
        repo_dir = self.test_dir / "RealScriptRepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        self.assertEqual(rc, 0)
        target_script = repo_dir / "scripts" / "scs-pre-commit.py"
        self.assertTrue(target_script.exists())
        content = target_script.read_text(encoding="utf-8")
        self.assertIn("compute_sha256", content)
        self.assertIn("find_continuity_vaults", content)
        self.assertIn("verify_vault", content)
        self.assertNotIn("print(\"[SCS] Pre-commit verification passed.\")", content)

    def test_hook_install_upgrades_dummy_stub(self):
        """Verify scs hook install --git replaces an existing dummy stub with the real script."""
        repo_dir = self.test_dir / "UpgradeStubRepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        scripts_dir = repo_dir / "scripts"
        scripts_dir.mkdir()
        dummy_script = scripts_dir / "scs-pre-commit.py"
        dummy_script.write_text("#!/usr/bin/env python3\nimport sys\nprint(\"[SCS] Pre-commit verification passed.\")\nsys.exit(0)\n", encoding="utf-8")

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        self.assertEqual(rc, 0)
        content = dummy_script.read_text(encoding="utf-8")
        self.assertIn("compute_sha256", content)
        self.assertIn("find_continuity_vaults", content)

    def test_hook_install_template_fallback_without_repo_files(self):
        """Verify template fallback operates when filesystem candidate paths do not exist (pip install)."""
        repo_dir = self.test_dir / "TemplateFallbackRepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        # Mock bundled candidates as non-existent
        orig_exists = Path.exists
        def mock_exists(p):
            if "scs-pre-commit.py" in str(p) and "TemplateFallbackRepo" not in str(p):
                return False
            return orig_exists(p)

        with patch.object(Path, "exists", side_effect=mock_exists, autospec=True):
            stdout_buf = io.StringIO()
            with patch("sys.stdout", stdout_buf):
                rc = scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        self.assertEqual(rc, 0)
        target_script = repo_dir / "scripts" / "scs-pre-commit.py"
        self.assertTrue(target_script.exists())
        content = target_script.read_text(encoding="utf-8")
        self.assertIn("compute_sha256", content)
        self.assertIn("find_continuity_vaults", content)

    def test_pre_commit_git_commit_integration_block_and_pass(self):
        """End-to-end integration: git commit blocked on corrupted seal, succeeds on intact seal."""
        repo_dir = self.test_dir / "GitE2ERepo"
        repo_dir.mkdir()

        # Initialize actual git repo
        subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)

        # Create SCS vault
        scs_cli.main(["new", "E2E", "E2E Project", "--path", str(repo_dir)])
        scs_cli.main(["hook", "install", "--git", "--path", str(repo_dir)])

        # Stage and commit clean state
        (repo_dir / "file1.txt").write_text("clean", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
        res_clean = subprocess.run(["git", "commit", "-m", "initial clean commit"], cwd=str(repo_dir), capture_output=True, text=True)
        self.assertEqual(res_clean.returncode, 0)

        # Corrupt ledger
        ledger_path = repo_dir / ".continuity" / "canonical" / "ledger.json"
        ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger_data["decisions"].append({"code": "TAMPERED", "statement": "Unauthorized"})
        ledger_path.write_text(json.dumps(ledger_data, indent=2), encoding="utf-8")

        # Stage tampered ledger and try to commit
        subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
        res_corrupt = subprocess.run(["git", "commit", "-m", "corrupted commit"], cwd=str(repo_dir), capture_output=True, text=True)
        self.assertNotEqual(res_corrupt.returncode, 0)
        self.assertIn("Cryptographic State Seal Mismatch", res_corrupt.stderr + res_corrupt.stdout)

        # Rollback / restore clean state
        scs_cli.main(["rollback", "--project", str(repo_dir), "--snapshot", "SNP-20261106-001"])
        (repo_dir / "file2.txt").write_text("clean restored state", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
        res_restored = subprocess.run(["git", "commit", "-m", "restored commit"], cwd=str(repo_dir), capture_output=True, text=True)
        self.assertEqual(res_restored.returncode, 0, f"Git commit failed: {res_restored.stdout} {res_restored.stderr}")


if __name__ == "__main__":
    unittest.main()

