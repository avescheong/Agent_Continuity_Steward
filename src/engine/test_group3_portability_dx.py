"""
Unit and Integration Tests for Phase 14 Group 3 (Portability & Ingestion Improvements)
=====================================================================================

Covers:
1. FDB-101-014: Standalone direct markdown file ingestion (scs record --file <PATH>)
2. FDB-101-006: Subagent progress chatter & heartbeat noise suppression
3. FDB-101-003: Multi-author attribution tracking across CLI, ledger, and Markdown views
"""

import io
import json
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine import scs_cli, vault_store, core_adapter, transcript_reader


class TestGroup3PortabilityDx(unittest.TestCase):
    """Test suite verifying Group 3 portability, noise suppression, and attribution."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="scs_group3_test_"))
        self.old_cwd = Path.cwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. FDB-101-014: Direct Markdown File Ingestion
    # -------------------------------------------------------------------------

    def test_parse_markdown_session_turns_with_speakers(self):
        """FDB-101-014: Verify parse_markdown_session_turns handles User and Assistant markers."""
        md_text = (
            "User: We need to decide on our cache architecture.\n"
            "Assistant: Decision: Use Redis Cluster with Sentinel.\n"
            "Constraint: Max memory must not exceed 8GB.\n"
            "User: Agreed, proceed.\n"
        )
        turns = transcript_reader.parse_markdown_session_turns(md_text)
        self.assertEqual(len(turns), 3)
        self.assertEqual(turns[0]["speaker"], "Human")
        self.assertIn("cache architecture", turns[0]["normalized_content"])
        self.assertEqual(turns[1]["speaker"], "AI")
        self.assertIn("Decision: Use Redis Cluster", turns[1]["normalized_content"])
        self.assertEqual(turns[2]["speaker"], "Human")
        self.assertIn("Agreed, proceed", turns[2]["normalized_content"])

    def test_parse_markdown_session_turns_plain_notes(self):
        """FDB-101-014: Verify raw notes without speaker markers are preserved intact."""
        md_text = (
            "# Architecture Review Notes\n"
            "- Decision: Use PostgreSQL as primary relational store.\n"
            "- Constraint: All API endpoints must enforce JWT authentication.\n"
        )
        turns = transcript_reader.parse_markdown_session_turns(md_text)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["speaker"], "AI")
        self.assertIn("Decision: Use PostgreSQL", turns[0]["normalized_content"])

    def test_record_from_markdown_file_direct(self):
        """FDB-101-014: Verify scs record --file <PATH> ingests session without Antigravity UUID."""
        p_dir = self.test_dir / "ProjFileIngest"
        scs_cli.main(["new", "PFIL", "Project File Ingest", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        session_md = self.test_dir / "session_notes.md"
        session_md.write_text(
            "User: Let's design the ingestion module.\n"
            "Assistant: Decision: Ingest external markdown sessions directly.\n"
            "Constraint: Do not depend on local Antigravity UUID when running in CI.\n"
            "Task: Add regression test suite for file ingestion.\n",
            encoding="utf-8",
        )

        rc = scs_cli.main(["record", "--project", "PFIL", "--file", str(session_md)])
        self.assertEqual(rc, 0)

        # Verify raw session captured in evidence/raw_sessions/
        raw_sessions = list((vault_dir / "evidence" / "raw_sessions").glob("SES*.md"))
        self.assertTrue(len(raw_sessions) >= 1)
        ses_content = raw_sessions[0].read_text(encoding="utf-8")
        self.assertIn("capture_source: DIRECT_FILE", ses_content)
        self.assertIn("source_file: session_notes.md", ses_content)

        # Verify proposals staged in quarantine
        staging = vault_store.read_staging(vault_dir)
        self.assertTrue(len(staging.get("proposals", [])) >= 1)
        stmt_list = [p.get("statement", "") for p in staging["proposals"]]
        self.assertTrue(any("Ingest external markdown sessions directly" in s for s in stmt_list))

    def test_record_missing_file_error(self):
        """FDB-101-014: Verify scs record --file with non-existent path reports error cleanly."""
        p_dir = self.test_dir / "ProjMissingFile"
        scs_cli.main(["new", "PMIS", "Project Missing", "--path", str(p_dir)])

        rc = scs_cli.main(["record", "--project", "PMIS", "--file", str(self.test_dir / "non_existent.md")])
        self.assertEqual(rc, 1)

    # -------------------------------------------------------------------------
    # 2. FDB-101-006: Extraction Noise Suppression
    # -------------------------------------------------------------------------

    def test_is_progress_chatter_detector(self):
        """FDB-101-006: Verify is_progress_chatter identifies subagent progress heartbeats."""
        fn = core_adapter.is_progress_chatter
        self.assertTrue(fn("[Progress: 3/10] Scanning directory"))
        self.assertTrue(fn("[Progress: 1/5]"))
        self.assertTrue(fn("Turn 4 of 12"))
        self.assertTrue(fn("Processing step 5"))
        self.assertTrue(fn("Step 2: running test"))
        self.assertTrue(fn("Step 1: searching files"))
        self.assertTrue(fn("Heartbeat: node worker active"))
        self.assertTrue(fn("[Heartbeat] ping"))

        # Crucial: Real architectural statements must NOT be flagged as chatter
        self.assertFalse(fn("Decision: Use PostgreSQL as primary datastore."))
        self.assertFalse(fn("Constraint: Limit execution time to 10 seconds."))
        self.assertFalse(fn("Task: Implement step 5 of the database migration."))
        self.assertFalse(fn("Process data in streaming batches"))

    def test_noise_suppression_in_extract_context(self):
        """FDB-101-006: Verify progress chatter is omitted from staged proposals."""
        dialogue = (
            "User: Begin subagent operation.\n"
            "Assistant: [Progress: 1/10] Initializing search index\n"
            "Turn 2 of 10\n"
            "Processing step 3\n"
            "Step 4: running test suites\n"
            "Heartbeat: alive\n"
            "Decision: Adopt event-driven microservices architecture.\n"
            "Constraint: Message payload size must not exceed 256KB.\n"
        )
        extracted = core_adapter.extract_context(
            fragments=dialogue,
            project_code="PNS",
            root_paths=[str(self.test_dir)],
        )

        dec_titles = [d.title for d in extracted.decisions]
        self.assertTrue(any("Adopt event-driven microservices architecture" in t for t in dec_titles))

        # Ensure no progress chatter turned into tasks
        all_task_titles = [t.get("title", "") for t in extracted.pending_tasks + extracted.completed_tasks]
        for t in all_task_titles:
            self.assertFalse(core_adapter.is_progress_chatter(t), f"Chatter leaked as task: '{t}'")

    # -------------------------------------------------------------------------
    # 3. FDB-101-003: Multi-Author Attribution
    # -------------------------------------------------------------------------

    def test_resolve_author_hierarchy(self):
        """FDB-101-003: Verify attribution resolution hierarchy."""
        # 1. Explicit CLI arg takes absolute priority
        self.assertEqual(vault_store.resolve_author("Custom-Agent-01"), "Custom-Agent-01")

        # 2. Environment fallback when git config is absent or mocked
        with patch.dict(os.environ, {"USER": "test_dev_alice"}, clear=False):
            with patch("subprocess.run", side_effect=Exception("No git")):
                self.assertEqual(vault_store.resolve_author(None), "test_dev_alice")

        # 3. Deterministic fallback when no env or git exists
        with patch.dict(os.environ, {"USER": "", "USERNAME": ""}, clear=False):
            with patch("subprocess.run", side_effect=Exception("No git")):
                self.assertEqual(vault_store.resolve_author(None), "human-operator")

    def test_attribution_persisted_in_ledger_and_markdown(self):
        """FDB-101-003: Verify author & approved_by are recorded in ledger.json and DECISIONS.md."""
        p_dir = self.test_dir / "ProjAttr"
        scs_cli.main(["new", "PATR", "Project Attribution", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        # Append staged proposals with author
        vault_store.append_staging_proposals(vault_dir, [
            {
                "id": "PRP-01",
                "proposal_type": "DECISION",
                "statement": "Use Ed25519 signatures for state sealing",
                "status": "PENDING",
                "author": "Security-Architect-AI",
            }
        ])

        # Approve with explicit author flag
        rc = scs_cli.main(["approve", "--project", "PATR", "--author", "Lead-Reviewer-Bob", "--all"])
        self.assertEqual(rc, 0)

        # Inspect canonical ledger.json
        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger["decisions"]), 1)
        dec = ledger["decisions"][0]
        self.assertEqual(dec.get("author"), "Security-Architect-AI")
        self.assertEqual(dec.get("approved_by"), "Lead-Reviewer-Bob")

        # Inspect generated canonical/DECISIONS.md
        dec_md = (vault_dir / "canonical" / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("**Author / Approved By:** Security-Architect-AI / Lead-Reviewer-Bob", dec_md)

    def test_legacy_ledger_backward_compatibility(self):
        """FDB-101-003: Verify legacy v1.0.1 ledgers without author keys read cleanly."""
        p_dir = self.test_dir / "ProjLegacy"
        scs_cli.main(["new", "PLEG", "Project Legacy", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        ledger_file = vault_store.get_vault_paths(vault_dir)["ledger_json"]
        ledger = json.loads(ledger_file.read_text(encoding="utf-8"))

        # Insert legacy decision without author or approved_by fields
        ledger["decisions"].append({
            "id": "legacy-id-123",
            "code": "DEC-001",
            "record_kind": "DECISION",
            "statement": "Legacy decision without author",
            "rationale_why": "Pre-v1.1.0 memory entry",
            "is_active": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
        ledger_file.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        # Update seal so verification passes
        new_hash = vault_store.compute_sha256(ledger)
        vault_store.get_vault_paths(vault_dir)["latest_seal"].write_text(f"{new_hash}\n", encoding="utf-8")

        # Re-render views should execute smoothly without crashing on missing keys
        vault_store.render_markdown_views(vault_dir, ledger)
        dec_md = (vault_dir / "canonical" / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("Legacy decision without author", dec_md)


if __name__ == "__main__":
    unittest.main()
