"""
Unit and Integration Tests for Phase 14 Group 2 (Custody & Defensive DX Improvements)
====================================================================================

Covers:
1. FDB-101-013: Defensive staging normalization in vault_store.read_staging()
2. FDB-101-010: Extraction punctuation normalization in core_adapter.py and promote_proposals()
3. FDB-101-005: Batch custody shorthand (approve PROJECT 1,2,3 and reject --all [-y])
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

from engine import scs_cli, vault_store, core_adapter
from engine.core_adapter import CausalDecision


class TestGroup2CustodyDx(unittest.TestCase):
    """Test suite verifying Group 2 custody and normalization improvements."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="scs_group2_test_"))
        self.old_cwd = Path.cwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. FDB-101-013: Defensive Staging Normalization
    # -------------------------------------------------------------------------

    def test_staging_normalization_raw_list(self):
        """FDB-101-013: Verify raw JSON list is automatically wrapped into standard protocol dict."""
        vault_dir = vault_store.create_vault(self.test_dir / "ProjA", "PRJA", "Project A")
        staging_file = vault_store.get_vault_paths(vault_dir)["pending_proposals_json"]

        # Write raw list [...]
        raw_list = [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Raw decision 1", "status": "PENDING"},
            {"id": "P02", "proposal_type": "CONSTRAINT", "statement": "Raw constraint 2", "status": "PENDING"}
        ]
        staging_file.write_text(json.dumps(raw_list), encoding="utf-8")

        # read_staging should defensively normalize
        staging = vault_store.read_staging(vault_dir)
        self.assertIsInstance(staging, dict)
        self.assertEqual(staging.get("protocol"), "scs-staging/1.0")
        self.assertIn("updated_at", staging)
        self.assertEqual(len(staging.get("proposals", [])), 2)
        self.assertEqual(staging["proposals"][0]["id"], "P01")
        self.assertEqual(staging["proposals"][1]["id"], "P02")

    def test_staging_normalization_dict_preserved(self):
        """FDB-101-013: Verify existing protocol dict format is preserved intact."""
        vault_dir = vault_store.create_vault(self.test_dir / "ProjB", "PRJB", "Project B")
        staging_file = vault_store.get_vault_paths(vault_dir)["pending_proposals_json"]

        std_dict = {
            "protocol": "scs-staging/1.0",
            "updated_at": "2026-11-06T12:00:00Z",
            "proposals": [{"id": "PRP-01", "statement": "Test proposal", "status": "PENDING"}]
        }
        staging_file.write_text(json.dumps(std_dict), encoding="utf-8")

        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(staging["protocol"], "scs-staging/1.0")
        self.assertEqual(staging["updated_at"], "2026-11-06T12:00:00Z")
        self.assertEqual(len(staging["proposals"]), 1)

    def test_staging_normalization_corrupt_fallback(self):
        """FDB-101-013: Verify non-JSON or corrupted file falls back to empty protocol structure."""
        vault_dir = vault_store.create_vault(self.test_dir / "ProjC", "PRJC", "Project C")
        staging_file = vault_store.get_vault_paths(vault_dir)["pending_proposals_json"]

        staging_file.write_text("CORRUPTED NOT JSON {{{", encoding="utf-8")
        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(staging, {"protocol": "scs-staging/1.0", "proposals": []})

    # -------------------------------------------------------------------------
    # 2. FDB-101-010: Extraction Punctuation Normalization
    # -------------------------------------------------------------------------

    def test_normalize_decision_title_function(self):
        """FDB-101-010: Unit test normalize_decision_title helper function."""
        fn = core_adapter.normalize_decision_title
        self.assertEqual(fn("System reads"), "system reads")
        self.assertEqual(fn("System reads."), "system reads")
        self.assertEqual(fn("System reads..."), "system reads")
        self.assertEqual(fn("System reads:"), "system reads")
        self.assertEqual(fn("System reads;"), "system reads")
        self.assertEqual(fn("  System reads.*  "), "system reads")
        self.assertEqual(fn(""), "")
        self.assertEqual(fn(None), "")

    def test_extract_explicit_decisions_punctuation_dedup(self):
        """FDB-101-010: Verify explicit decisions with trailing punctuation are deduplicated."""
        dialogue = (
            "- Decision: Use PostgreSQL as primary datastore.\n"
            "- Architecture Decision: Use PostgreSQL as primary datastore\n"
        )
        decisions = core_adapter.extract_explicit_architectural_decisions(dialogue)
        self.assertEqual(len(decisions), 1)
        self.assertTrue("Use PostgreSQL as primary datastore" in decisions[0]["title"])

    def test_harden_extracted_context_dedup_with_punctuation(self):
        """FDB-101-010: Verify harden_extracted_context deduplicates decisions differing by punctuation."""
        existing_dec = CausalDecision(
            code="DEC-001",
            title="Use Redis for caching",
            reasoning="Low latency",
            evidence_quote="...",
        )
        ctx = core_adapter.ExtractedContext(decisions=[existing_dec])
        dialogue = "- Decision: Use Redis for caching.\n"
        hardened = core_adapter.harden_extracted_context(
            extracted=ctx,
            raw_text=dialogue,
        )
        # Should not append duplicate DEC-002
        self.assertEqual(len(hardened.decisions), 1)
        self.assertEqual(hardened.decisions[0].code, "DEC-001")

    def test_promote_proposals_punctuation_dedup(self):
        """FDB-101-010: Verify promote_proposals deduplicates decisions against canonical ledger differing by trailing punctuation."""
        vault_dir = vault_store.create_vault(self.test_dir / "ProjD", "PRJD", "Project D")

        # Promote baseline decision without period
        vault_store.append_staging_proposals(vault_dir, [{
            "id": "PRP-01",
            "proposal_type": "DECISION",
            "statement": "Enforce strict schema validation",
            "status": "PENDING"
        }])
        res1 = vault_store.promote_proposals(vault_dir=vault_dir, promote_all=True)
        self.assertEqual(res1["promoted_count"], 1)

        # Stage proposal with trailing period
        vault_store.append_staging_proposals(vault_dir, [{
            "id": "PRP-02",
            "proposal_type": "DECISION",
            "statement": "Enforce strict schema validation.",
            "status": "PENDING"
        }])
        res2 = vault_store.promote_proposals(vault_dir=vault_dir, promote_all=True)
        # Should detect existing decision and not create a duplicate
        self.assertEqual(res2["promoted_decisions"], 0)
        ledger = vault_store.read_ledger(vault_dir)
        self.assertEqual(len([d for d in ledger["decisions"] if d.get("is_active")]), 1)

    # -------------------------------------------------------------------------
    # 3. FDB-101-005: Batch Custody Shorthand
    # -------------------------------------------------------------------------

    def test_approve_comma_separated_indices(self):
        """FDB-101-005: Verify scs approve PROJECT 1,3 approves specific 1-based index proposals."""
        p_dir = self.test_dir / "ProjE"
        scs_cli.main(["new", "PRJE", "Project E", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        vault_store.append_staging_proposals(vault_dir, [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Decision One", "status": "PENDING"},
            {"id": "P02", "proposal_type": "CONSTRAINT", "statement": "Constraint Two", "status": "PENDING"},
            {"id": "P03", "proposal_type": "TASK", "statement": "Task Three", "status": "PENDING"},
        ])

        # Approve 1,3
        rc = scs_cli.main(["approve", "PRJE", "1,3"])
        self.assertEqual(rc, 0)

        # Staging should only have P02 left
        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(len(staging["proposals"]), 1)
        self.assertEqual(staging["proposals"][0]["id"], "P02")

        # Canonical ledger should have Decision One and Task Three
        ledger = vault_store.read_ledger(vault_dir)
        self.assertEqual(len(ledger["decisions"]), 1)
        self.assertEqual(len(ledger["tasks"]), 1)
        self.assertEqual(len(ledger["constraints"]), 0)

    def test_approve_comma_separated_ids(self):
        """FDB-101-005: Verify scs approve --project PROJECT P01,P02 approves comma-separated IDs."""
        p_dir = self.test_dir / "ProjF"
        scs_cli.main(["new", "PRJF", "Project F", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        vault_store.append_staging_proposals(vault_dir, [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Decision F1", "status": "PENDING"},
            {"id": "P02", "proposal_type": "DECISION", "statement": "Decision F2", "status": "PENDING"},
            {"id": "P03", "proposal_type": "DECISION", "statement": "Decision F3", "status": "PENDING"},
        ])

        rc = scs_cli.main(["approve", "--project", "PRJF", "P01,P02"])
        self.assertEqual(rc, 0)

        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(len(staging["proposals"]), 1)
        self.assertEqual(staging["proposals"][0]["id"], "P03")

    def test_reject_all_with_yes_bypass(self):
        """FDB-101-005: Verify scs reject PROJECT --all -y discards all staged proposals."""
        p_dir = self.test_dir / "ProjG"
        scs_cli.main(["new", "PRJG", "Project G", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        vault_store.append_staging_proposals(vault_dir, [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Decision G1", "status": "PENDING"},
            {"id": "P02", "proposal_type": "DECISION", "statement": "Decision G2", "status": "PENDING"},
        ])

        rc = scs_cli.main(["reject", "PRJG", "--all", "-y"])
        self.assertEqual(rc, 0)

        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(len(staging["proposals"]), 0)

    def test_reject_all_confirmation_prompt_declined(self):
        """FDB-101-005: Verify scs reject --all prompts operator and cancels when 'n' is given."""
        p_dir = self.test_dir / "ProjH"
        scs_cli.main(["new", "PRJH", "Project H", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        vault_store.append_staging_proposals(vault_dir, [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Decision H1", "status": "PENDING"},
        ])

        # Simulate user answering 'n'
        with patch("builtins.input", return_value="n"):
            rc = scs_cli.main(["reject", "--project", "PRJH", "--all"])
            self.assertEqual(rc, 0)

        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(len(staging["proposals"]), 1)

    def test_reject_all_confirmation_prompt_accepted(self):
        """FDB-101-005: Verify scs reject --all prompts operator and discards when 'y' is given."""
        p_dir = self.test_dir / "ProjI"
        scs_cli.main(["new", "PRJI", "Project I", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        vault_store.append_staging_proposals(vault_dir, [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Decision I1", "status": "PENDING"},
        ])

        with patch("builtins.input", return_value="y"):
            rc = scs_cli.main(["reject", "--project", "PRJI", "--all"])
            self.assertEqual(rc, 0)

        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(len(staging["proposals"]), 0)

    def test_reject_by_numeric_index(self):
        """FDB-101-005: Verify scs reject PROJECT 1 discards the first staged proposal by index."""
        p_dir = self.test_dir / "ProjJ"
        scs_cli.main(["new", "PRJJ", "Project J", "--path", str(p_dir)])
        vault_dir = p_dir / ".continuity"

        vault_store.append_staging_proposals(vault_dir, [
            {"id": "P01", "proposal_type": "DECISION", "statement": "Decision J1", "status": "PENDING"},
            {"id": "P02", "proposal_type": "DECISION", "statement": "Decision J2", "status": "PENDING"},
        ])

        rc = scs_cli.main(["reject", "PRJJ", "1"])
        self.assertEqual(rc, 0)

        staging = vault_store.read_staging(vault_dir)
        self.assertEqual(len(staging["proposals"]), 1)
        self.assertEqual(staging["proposals"][0]["id"], "P02")

    def test_reject_empty_staging_message(self):
        """FDB-101-005: Verify scs reject --all on empty staging exits cleanly with info message."""
        p_dir = self.test_dir / "ProjK"
        scs_cli.main(["new", "PRJK", "Project K", "--path", str(p_dir)])

        rc = scs_cli.main(["reject", "PRJK", "--all", "-y"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
