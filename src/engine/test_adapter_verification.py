"""
Test Verification Suite for SCS_AG_v2 Read-Only Core Adapter
=============================================================

Executes automated verification of SCS_AG_v2/engine/core_adapter.py against:
1. RFC-0006 Normative Test Vectors (Scenario 01 through 07 + Conflict)
2. Incremental session YAML frontmatter stripping
3. Low-level read-only artifact reconciliation & path-traversal guard
4. Secret scrubber redaction
5. Master AI Handover Package, Executive Briefing & Recovery Card generation
"""

import sys
import os
import json
import unittest
from pathlib import Path

# Ensure SCS_AG_v2/engine is importable
ENGINE_DIR = Path(__file__).resolve().parent
if (ENGINE_DIR.parent / "test-vectors").exists():
    REPO_ROOT = ENGINE_DIR.parent
else:
    REPO_ROOT = ENGINE_DIR.parent.parent
sys.path.insert(0, str(ENGINE_DIR))

import core_adapter


class TestCoreAdapterVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tv_dir = REPO_ROOT / "test-vectors"
        if not cls.tv_dir.exists():
            raise FileNotFoundError(f"Test vectors not found at: {cls.tv_dir}")

    # -----------------------------------------------------------------------
    # 1. RFC-0006 Test Vectors (Scenario 01 to 07)
    # -----------------------------------------------------------------------

    def test_scenario_01_multiturn_architecture(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_01_multiturn_architecture.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_01_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(
            text,
            project_code="SCS",
            active_focus="Persistence Engine",
        )

        # 1. Decisions
        self.assertEqual(len(ctx.decisions), len(expected["expected_decisions"]))
        self.assertTrue(any("sqlite with wal" in d.title.lower() for d in ctx.decisions))
        self.assertEqual(ctx.decisions[0].confidence, "HIGH")

        # 2. Constraints
        self.assertGreaterEqual(len(ctx.constraints), 1)
        self.assertTrue(any("50mb" in c.lower() for c in ctx.constraints))

        # 3. Tasks
        completed = [t["title"].lower() for t in ctx.completed_tasks]
        self.assertTrue(any("benchmark verified" in t for t in completed))
        pending = [t["title"].lower() for t in ctx.pending_tasks]
        self.assertTrue(any("schema migrations" in t for t in pending))

        # 4. Artifacts
        artifacts = [a["path"] for a in ctx.artifacts]
        self.assertTrue(any("src/scs_core/db/vault.py" in p for p in artifacts))

    def test_scenario_02_multiple_rejected_alternatives(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_02_multiple_rejected_alternatives.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_02_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertEqual(len(ctx.decisions), len(expected["expected_decisions"]))
        self.assertIn("named pipes", ctx.decisions[0].title.lower())

        self.assertGreaterEqual(len(ctx.rejected_options), len(expected["expected_rejected_options"]))
        rej_statements = [r["statement"].lower() for r in ctx.rejected_options]
        self.assertTrue(any("local http" in s for s in rej_statements))
        self.assertTrue(any("shared memory" in s for s in rej_statements))

    def test_scenario_03_decision_reversals(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_03_decision_reversals.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_03_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("sqlite", ctx.decisions[0].title.lower())
        self.assertNotIn("postgresql", ctx.decisions[0].title.lower())
        self.assertTrue(any("postgresql" in r["statement"].lower() for r in ctx.rejected_options))

    def test_scenario_04_partial_agreements(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_04_partial_agreements.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_04_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("clickhouse", ctx.decisions[0].title.lower())
        self.assertTrue(any("kafka" in r["statement"].lower() for r in ctx.rejected_options))

    def test_scenario_05_ambiguous_confirmations(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_05_ambiguous_confirmations.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_05_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertEqual(len(ctx.decisions), 0)
        self.assertGreaterEqual(len(ctx.recommendations), 1)
        self.assertIn("svelte", ctx.recommendations[0]["statement"].lower())

    def test_scenario_06_fenced_code_paths(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_06_fenced_code_paths.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_06_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("inmemorycache", ctx.decisions[0].title.lower())
        self.assertFalse(any("redis" in d.title.lower() for d in ctx.decisions))

        artifacts = [a["path"] for a in ctx.artifacts]
        self.assertTrue(any("src/scs_core/cache/manager.py" in p for p in artifacts))

    def test_scenario_07_pure_brainstorming(self):
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_07_pure_brainstorming.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_07_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertEqual(len(ctx.decisions), 0)
        self.assertEqual(len(ctx.rejected_options), 0)
        self.assertEqual(len(ctx.pending_tasks), 0)

    def test_conflict_scenario_offline_vs_cloud(self):
        sc_file = self.tv_dir / "conflict_scenarios" / "conflict_offline_vs_cloud.md"
        ex_file = self.tv_dir / "conflict_scenarios" / "conflict_offline_vs_cloud_expected.json"

        text = sc_file.read_text(encoding="utf-8")
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = core_adapter.extract_context(text)

        self.assertGreaterEqual(len(ctx.conflicts), 1)
        conflict = ctx.conflicts[0]
        self.assertIn("offline", conflict["statement_a"].lower())
        self.assertIn("aws", conflict["statement_b"].lower())

    # -----------------------------------------------------------------------
    # 2. YAML Frontmatter Stripping for Incremental Session Logs
    # -----------------------------------------------------------------------

    def test_yaml_frontmatter_stripping(self):
        raw_session_md = (
            "---\n"
            "session_id: SES001_20261105_1300\n"
            "captured_at: '2026-11-05T13:00:00Z'\n"
            "active_project: SCS_AG_v2\n"
            "sha256: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069\n"
            "---\n\n"
            "AI:\n"
            "I recommend modular architecture.\n\n"
            "Human:\n"
            "Yes, proceed with this approach.\n"
        )

        ctx = core_adapter.extract_context(raw_session_md)

        # Must properly detect human confirmation as a Decision
        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("modular architecture", ctx.decisions[0].title.lower())

        # Also verify turn parsing cleanly has AI and HUMAN, without UNKNOWN speaker
        report = core_adapter.validate_context(fragments=raw_session_md)
        speakers = [t.speaker for t in report["turns"]]
        self.assertEqual(speakers, ["AI", "HUMAN"])
        self.assertNotIn("UNKNOWN", speakers)

    # -----------------------------------------------------------------------
    # 3. Context Validation (Authority, Acts, Turns & Conflicts)
    # -----------------------------------------------------------------------

    def test_validate_context_authority_and_conflicts(self):
        fragments = [
            "AI:\nI recommend Redis caching.\n\nHuman:\nNo, Redis is too heavy. Let's use SQLite memory cache instead."
        ]

        report = core_adapter.validate_context(
            fragments=fragments,
            constraints=["Must operate entirely offline with zero network."],
            rejected_options=[{"statement": "Redis caching", "why": "Too heavy"}],
        )

        self.assertIn("turns", report)
        self.assertIn("acts", report)
        self.assertEqual(len(report["turns"]), 2)
        # Human utterance must be recognized
        self.assertEqual(report["turns"][1].speaker, "HUMAN")
        # No severe conflict
        self.assertTrue(report["valid"])

    # -----------------------------------------------------------------------
    # 4. Read-Only Artifact Reconciliation & Path-Traversal Guard
    # -----------------------------------------------------------------------

    def test_reconcile_artifacts(self):
        # 1. Test existing file (README.md)
        artifacts = [
            {
                "name": "README",
                "relative_path": "README.md",
                "required_markers": ["SCS"],
            },
            {
                "name": "NonExistent",
                "relative_path": "does_not_exist_file.txt",
            },
            {
                "name": "TraversalAttack",
                "relative_path": "../../evil_outside.txt",
            },
        ]

        rec = core_adapter.reconcile_artifacts(artifacts, root_paths=[REPO_ROOT])

        self.assertEqual(rec["total_artifacts"], 3)
        self.assertEqual(rec["verified_count"], 1)
        self.assertEqual(rec["missing_count"], 1)
        self.assertEqual(rec["traversal_violations"], 1)
        self.assertFalse(rec["all_verified"])

        res_by_name = {r["name"]: r for r in rec["results"]}
        self.assertEqual(res_by_name["README"]["status"], "VERIFIED")
        self.assertIsNotNone(res_by_name["README"]["observed_sha256"])
        self.assertEqual(res_by_name["NonExistent"]["status"], "MISSING")
        self.assertEqual(res_by_name["TraversalAttack"]["status"], "TRAVERSAL_VIOLATION")

    # -----------------------------------------------------------------------
    # 5. Secret Scrubber Redaction
    # -----------------------------------------------------------------------

    def test_scrub_secrets(self):
        secret_sample = (
            "Connecting with api_key=sk-proj-1234567890abcdef1234567890abcdef and "
            "ghp_1234567890abcdef1234567890abcdef123456."
        )
        scrubbed, count = core_adapter.scrub_secrets(secret_sample)

        self.assertGreaterEqual(count, 1)
        self.assertNotIn("sk-proj-1234567890abcdef", scrubbed)
        self.assertNotIn("ghp_1234567890abcdef", scrubbed)
        self.assertIn("[REDACTED_SECRET]", scrubbed)

    # -----------------------------------------------------------------------
    # 6. AI Handover Package, Executive Briefing & Recovery Card Generation
    # -----------------------------------------------------------------------

    def test_generate_handover_context(self):
        proj = {
            "code": "SCS2",
            "name": "SCS_AG_v2",
            "objective": "Build Antigravity native continuity system",
            "current_focus": "Phase 1 Core Adapter",
            "next_action": "Complete Step 1.1 acceptance testing",
        }
        snap = {
            "snapshot_code": "SNP-001",
            "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "state_json": '{"schema_version": "1.0"}',
        }
        decisions = [
            {
                "code": "DEC-001",
                "record_kind": "DECISION",
                "statement": "Preserve upstream scs_core brain read-only",
                "rationale_why": "Guarantees zero regression on proven causal engine",
                "is_active": True,
            },
            {
                "code": "REJ-001",
                "record_kind": "REJECTED_OPTION",
                "statement": "Duplicate or rewrite caveman_engine in new repo",
                "rationale_why": "High risk of semantic drift and maintenance divergence",
                "is_active": True,
            },
        ]
        tasks = [
            {
                "code": "TSK-001",
                "title": "Implement core_adapter.py",
                "status": "COMPLETED",
                "priority": "HIGH",
                "why": "Adapter layer required for Phase 1",
            },
            {
                "code": "TSK-002",
                "title": "Implement vault_store.py",
                "status": "PENDING",
                "priority": "HIGH",
                "why": "Step 1.2 vault file storage",
            },
        ]
        artifacts = [
            {
                "name": "core_adapter.py",
                "relative_path": "SCS_AG_v2/engine/core_adapter.py",
                "custody_state": "VERIFIED_MATCH",
                "observed_sha256": "abc123def456",
            }
        ]

        result = core_adapter.generate_handover_context(
            project=proj,
            snapshot=snap,
            decisions=decisions,
            tasks=tasks,
            artifacts=artifacts,
        )

        # Handover verification
        self.assertEqual(result["protocol_version"], "scs-handover/1.0")
        self.assertEqual(result["file_name"], "SCS2_AI_HANDOVER_PACKAGE.md")
        self.assertIn("scs-handover/1.0", result["handover_content"])
        self.assertIn("Preserve upstream scs_core brain read-only", result["handover_content"])
        self.assertIn("Duplicate or rewrite caveman_engine", result["handover_content"])
        self.assertEqual(len(result["checksum_sha256"]), 64)

        # Human briefing verification
        self.assertIn("Human Operator Briefing", result["human_briefing_content"])
        self.assertEqual(len(result["human_checksum_sha256"]), 64)

        # Fast recovery card verification
        self.assertIn("Project Recovery Card", result["recovery_card_content"])
        self.assertEqual(len(result["recovery_checksum_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
