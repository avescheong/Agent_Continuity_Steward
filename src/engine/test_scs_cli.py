"""
Unit Test Suite for SCS_AG_v2 Unified CLI (engine/scs_cli.py)
=============================================================

Covers all Phase 1.4 requirements:
1. New project creation (`/scs new`)
2. Project listing (`/scs list`)
3. Project switching (`/scs switch`)
4. Ambiguous project failure (fail-closed routing)
5. Record workflow (`/scs record` -> transcript -> SES -> extraction -> staging quarantine)
6. Status command (`/scs status` -> ASCII flowchart, seal verification, tasks, decisions)
7. Approval workflow (`/scs approve` -> promotion -> canonical -> snapshot seal -> view update)
8. Reject workflow (`/scs reject` with Do-Not-Repeat memory)
9. Handover generation (`/scs handover` -> cross-AI package & recovery card)
10. Rollback recovery (`/scs rollback` -> state restoration & view regeneration)
11. Generative UI dashboard generation (`/scs ui`)
"""

import os
import sys
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

import scs_cli
import vault_store


class TestSCSCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.app_data_dir = self.base_dir / "app_data"
        self.app_data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_synthetic_transcript(self, conversation_id: str, steps: list):
        """Helper to create synthetic transcript logs."""
        log_dir = self.app_data_dir / "brain" / conversation_id / ".system_generated" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        trans_file = log_dir / "transcript.jsonl"
        with open(trans_file, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")
        trans_full_file = log_dir / "transcript_full.jsonl"
        with open(trans_full_file, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

    # -----------------------------------------------------------------------
    # 1. New project creation
    # -----------------------------------------------------------------------

    def test_01_cli_new_project(self):
        proj_dir = self.base_dir / "AlphaProj"
        exit_code = scs_cli.main([
            "new", "ALPHA", "Alpha Project",
            "--path", str(proj_dir),
            "--objective", "Deliver Alpha System",
            "--focus", "Architecture Baseline",
            "--next-action", "Run initial verification",
        ])

        self.assertEqual(exit_code, 0)
        vault_dir = proj_dir / ".continuity"
        self.assertTrue(vault_dir.exists())
        self.assertTrue((vault_dir / "BLUEPRINT.md").exists())
        self.assertTrue((vault_dir / "canonical" / "ledger.json").exists())
        self.assertTrue((vault_dir / "snapshots" / "LATEST_SEAL").exists())

    # -----------------------------------------------------------------------
    # 2. Project listing
    # -----------------------------------------------------------------------

    def test_02_cli_list_projects(self):
        # Create two projects
        p1 = self.base_dir / "ProjectOne"
        p2 = self.base_dir / "ProjectTwo"
        scs_cli.main(["new", "P1", "Project One", "--path", str(p1)])
        scs_cli.main(["new", "P2", "Project Two", "--path", str(p2)])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["list", "--root", str(self.base_dir)])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("P1", output)
        self.assertIn("P2", output)
        self.assertIn("Project One", output)
        self.assertIn("Project Two", output)

    # -----------------------------------------------------------------------
    # 3. Project switching
    # -----------------------------------------------------------------------

    def test_03_cli_switch_project(self):
        proj_dir = self.base_dir / "SwitchProj"
        scs_cli.main(["new", "SWP", "Switch Project", "--path", str(proj_dir), "--focus", "Testing switch command"])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            with patch("pathlib.Path.cwd", return_value=self.base_dir):
                code = scs_cli.main(["switch", "SWP"])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Switch Project (SWP)", output)
        self.assertIn("Testing switch command", output)

    # -----------------------------------------------------------------------
    # 4. Ambiguous project failure (fail closed)
    # -----------------------------------------------------------------------

    def test_04_cli_ambiguous_project_failure(self):
        p1 = self.base_dir / "ProjA"
        p2 = self.base_dir / "ProjB"
        scs_cli.main(["new", "PA", "Project A", "--path", str(p1)])
        scs_cli.main(["new", "PB", "Project B", "--path", str(p2)])

        stderr_buf = io.StringIO()
        # Running record without project argument in parent directory with multiple projects
        with patch("sys.stderr", stderr_buf):
            with patch("pathlib.Path.cwd", return_value=self.base_dir):
                code = scs_cli.main(["record", "--conv-id", "dummy-conv-id"])

        # Must fail closed with non-zero exit code
        self.assertNotEqual(code, 0)
        err = stderr_buf.getvalue()
        self.assertIn("Ambiguous project routing", err)

    # -----------------------------------------------------------------------
    # 5. Record workflow (transcript -> SES -> extraction -> staging)
    # -----------------------------------------------------------------------

    def test_05_cli_record_workflow(self):
        proj_dir = self.base_dir / "RecProj"
        scs_cli.main(["new", "REC", "Record Project", "--path", str(proj_dir)])

        conv_id = "test-conv-rec-001"
        steps = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>I need a database recommendation.</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "content": "I recommend adopting SQLite with WAL mode for local storage.",
            },
            {
                "step_index": 2,
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>Yes, proceed with SQLite with WAL mode.</USER_REQUEST>",
            },
        ]
        self._create_synthetic_transcript(conv_id, steps)

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main([
                "record", str(proj_dir),
                "--conv-id", conv_id,
                "--app-data", str(self.app_data_dir),
            ])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Captured 3 turns into raw evidence", output)
        self.assertIn("Staged", output)

        # Check raw SES evidence file
        vault_path = proj_dir / ".continuity"
        raw_files = list((vault_path / "evidence" / "raw_sessions").glob("SES*.md"))
        self.assertEqual(len(raw_files), 1)

        # Check staging proposals
        st = vault_store.read_staging(vault_path)
        self.assertGreaterEqual(len(st["proposals"]), 1)
        prop_types = [p["proposal_type"] for p in st["proposals"]]
        self.assertIn("DECISION", prop_types)

        # Check that CANONICAL ledger remains untouched (quarantine gate)
        ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        self.assertEqual(len(ledger["decisions"]), 0)

    # -----------------------------------------------------------------------
    # 6. Status command (ASCII flowchart, tasks, decisions)
    # -----------------------------------------------------------------------

    def test_06_cli_status(self):
        proj_dir = self.base_dir / "StatusProj"
        scs_cli.main(["new", "STAT", "Status Project", "--path", str(proj_dir)])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["status", str(proj_dir)])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("SCS CONTINUITY STATUS — Status Project (STAT)", output)
        self.assertIn("[SEAL INTACT]", output)
        self.assertIn("Continuity Workflow Engine:", output)
        self.assertIn("[Transcript] ──► [SES Evidence] ──► [Staging Quarantine]", output)
        self.assertIn("Task Checklist", output)

    # -----------------------------------------------------------------------
    # 7. Approval workflow (quarantine -> canonical -> snapshot seal)
    # -----------------------------------------------------------------------

    def test_07_cli_approve_workflow(self):
        proj_dir = self.base_dir / "ApproveProj"
        scs_cli.main(["new", "APPR", "Approve Project", "--path", str(proj_dir)])
        vault_path = proj_dir / ".continuity"

        # Stage candidate proposals
        proposals = [
            {
                "proposal_type": "DECISION",
                "statement": "Adopt zero-copy JSON parser",
                "why": "High performance",
            },
            {
                "proposal_type": "TASK",
                "statement": "Benchmark JSON parser",
                "priority": "HIGH",
                "why": "Performance verification",
            },
        ]
        vault_store.append_staging_proposals(vault_path, proposals)

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["approve", "--all", "--project", str(proj_dir)])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Ratified and promoted 2 item(s)", output)
        self.assertIn("New Seal:", output)

        # Canonical ledger must now hold the ratified decision and task
        ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        self.assertEqual(len(ledger["decisions"]), 1)
        self.assertEqual(ledger["decisions"][0]["statement"], "Adopt zero-copy JSON parser")
        self.assertEqual(len(ledger["tasks"]), 1)

        # Staging quarantine must now be empty
        st = vault_store.read_staging(vault_path)
        self.assertEqual(len(st["proposals"]), 0)

    # -----------------------------------------------------------------------
    # 8. Reject workflow (with Do-Not-Repeat memory)
    # -----------------------------------------------------------------------

    def test_08_cli_reject_workflow(self):
        proj_dir = self.base_dir / "RejectProj"
        scs_cli.main(["new", "REJ", "Reject Project", "--path", str(proj_dir)])
        vault_path = proj_dir / ".continuity"

        # Stage proposal
        vault_store.append_staging_proposals(vault_path, [
            {
                "proposal_type": "DECISION",
                "statement": "Use heavyweight Electron desktop shell",
                "why": "Web tech familiarity",
            }
        ])

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main([
                "reject", "P01",
                "--why", "Memory footprint exceeds 200MB budget",
                "--record-why",
                "--project", str(proj_dir),
            ])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("permanently recorded into Do-Not-Repeat memory", output)

        # Canonical REJECTED_OPTIONS.md must record Electron
        ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        self.assertEqual(len(ledger["rejected_options"]), 1)
        self.assertIn("Electron", ledger["rejected_options"][0]["statement"])

    # -----------------------------------------------------------------------
    # 9. Handover generation (cross-AI package & recovery card)
    # -----------------------------------------------------------------------

    def test_09_cli_handover(self):
        proj_dir = self.base_dir / "HandoverProj"
        scs_cli.main(["new", "HO", "Handover Project", "--path", str(proj_dir)])
        vault_path = proj_dir / ".continuity"

        # Add ratified decision
        ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        ledger["decisions"].append({
            "code": "DEC-001",
            "statement": "Use Antigravity native continuity skill",
            "rationale_why": "Full local sovereignty and fail-closed security",
            "is_active": True,
        })
        vault_store.write_ledger(vault_path, ledger, label="Ratified decision")

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["handover", str(proj_dir)])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Generated Master AI Continuity Restoration Package", output)
        self.assertIn("scs-handover/1.0", output)

        # Check files created in handover/
        ho_file = vault_path / "handover" / "HO_AI_HANDOVER_PACKAGE.md"
        rec_file = vault_path / "handover" / "HO_PROJECT_RECOVERY_CARD.md"
        self.assertTrue(ho_file.exists())
        self.assertTrue(rec_file.exists())

        ho_text = ho_file.read_text(encoding="utf-8")
        self.assertIn("scs-handover/1.0", ho_text)
        self.assertIn("Use Antigravity native continuity skill", ho_text)

    # -----------------------------------------------------------------------
    # 10. Rollback recovery
    # -----------------------------------------------------------------------

    def test_10_cli_rollback(self):
        proj_dir = self.base_dir / "RollbackProj"
        scs_cli.main(["new", "RB", "Rollback Project", "--path", str(proj_dir)])
        vault_path = proj_dir / ".continuity"

        # Check initial snapshot code
        initial_snap = vault_store.list_snapshots(vault_path)[0]["snapshot_code"]

        # Commit an erroneous decision
        ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        ledger["decisions"].append({
            "code": "DEC-BAD",
            "statement": "Faulty implementation approach",
            "rationale_why": "Unchecked experiment",
            "is_active": True,
        })
        vault_store.write_ledger(vault_path, ledger, label="Faulty commit")

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["rollback", initial_snap, "--project", str(proj_dir)])

        self.assertEqual(code, 0)
        output = stdout_buf.getvalue()
        self.assertIn(f"Successfully rolled back canonical memory to snapshot `{initial_snap}`", output)

        # Verify state is clean
        restored = vault_store.read_ledger(vault_path, verify_seal=True)
        self.assertEqual(len(restored["decisions"]), 0)

        # POST-GA-003: Verify --snapshot flag alias
        fresh_ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        fresh_ledger["decisions"].append({
            "code": "DEC-FLAG",
            "statement": "Decision to test flag rollback",
            "rationale_why": "Testing --snapshot flag",
            "is_active": True,
        })
        vault_store.write_ledger(vault_path, fresh_ledger, label="Flag commit")
        self.assertEqual(len(vault_store.read_ledger(vault_path)["decisions"]), 1)

        stdout_buf2 = io.StringIO()
        with patch("sys.stdout", stdout_buf2):
            code_flag = scs_cli.main(["rollback", "--snapshot", initial_snap, "--project", str(proj_dir)])
        self.assertEqual(code_flag, 0)
        self.assertIn(f"Successfully rolled back canonical memory to snapshot `{initial_snap}`", stdout_buf2.getvalue())
        self.assertEqual(len(vault_store.read_ledger(vault_path)["decisions"]), 0)

        # POST-GA-003: Missing snapshot argument should cleanly exit with code 1
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            code_missing = scs_cli.main(["rollback", "--project", str(proj_dir)])
        self.assertEqual(code_missing, 1)
        self.assertIn("Snapshot code required", stderr_buf.getvalue())

        # POST-GA-003: Invalid snapshot argument should cleanly exit with code 1
        stderr_buf2 = io.StringIO()
        with patch("sys.stderr", stderr_buf2):
            code_invalid = scs_cli.main(["rollback", "--snapshot", "SNP-NONEXISTENT", "--project", str(proj_dir)])
        self.assertEqual(code_invalid, 1)
        self.assertIn("Error executing rollback", stderr_buf2.getvalue())

    # -----------------------------------------------------------------------
    # 11. Generative UI dashboard generation
    # -----------------------------------------------------------------------

    def test_11_cli_ui_dashboard(self):
        proj_dir = self.base_dir / "UiProj"
        scs_cli.main(["new", "UIP", "UI Dashboard Project", "--path", str(proj_dir)])

        dash_file = proj_dir / "scs_dashboard.html"
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            code = scs_cli.main(["ui", str(proj_dir), "--output", str(dash_file)])

        self.assertEqual(code, 0)
        self.assertTrue(dash_file.exists())

        html_text = dash_file.read_text(encoding="utf-8")
        self.assertIn("UI Dashboard Project", html_text)
        self.assertIn("UIP", html_text)
        self.assertIn("/scs record", html_text)
        self.assertIn("/scs approve --all", html_text)
        self.assertIn("/scs status", html_text)


if __name__ == "__main__":
    unittest.main()
