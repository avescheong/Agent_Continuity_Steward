"""Normative Conformance Test Suite (RFC-0006 Tier 3 Conformance).

Executes the Causal Extraction Protocol against language-agnostic test vectors
located in test-vectors/ to mathematically verify RFC compliance.
"""

import unittest
import json
from pathlib import Path
from scs_core.modules.caveman_engine import CavemanContextExtractionEngine


class TestNormativeConformance(unittest.TestCase):
    """Verifies that the reference core implementation satisfies RFC-0006 Tier 3 conformance."""

    @classmethod
    def setUpClass(cls):
        cls.engine = CavemanContextExtractionEngine()
        # Find test-vectors directory relative to repo root
        current_file = Path(__file__).resolve()
        # core/python/tests/test_normative_conformance.py -> repo_root is 3 parents up
        repo_root = current_file.parent.parent.parent.parent
        cls.tv_dir = repo_root / "test-vectors"
        if not cls.tv_dir.exists():
            # Alternative: running from repo root or parent directory
            for candidate in [Path.cwd() / "test-vectors", Path.cwd().parent / "test-vectors"]:
                if candidate.exists():
                    cls.tv_dir = candidate
                    break

    def _split_fragments(self, text: str) -> list[str]:
        """Splits multi-turn markdown into sequential fragments."""
        if "## Fragment" in text:
            frags = [f.strip() for f in text.split("## Fragment")[1:] if f.strip()]
            return [f.split("\n", 1)[1].strip() if "\n" in f else f for f in frags]
        return [text.strip()]

    def test_conformance_scenario_01_multiturn_architecture(self):
        """RFC-0006 Scenario 1: Multi-turn architecture discussion, causal decisions, and tasks."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_01_multiturn_architecture.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_01_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments, project_code="SCS", active_focus="Persistence Engine")

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

    def test_conformance_scenario_02_multiple_rejected_alternatives(self):
        """RFC-0006 Scenario 2: Multiple candidate options with explicit rejections and rationale."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_02_multiple_rejected_alternatives.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_02_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # Decision
        self.assertEqual(len(ctx.decisions), len(expected["expected_decisions"]))
        self.assertIn("named pipes", ctx.decisions[0].title.lower())

        # Rejected Options
        self.assertGreaterEqual(len(ctx.rejected_options), len(expected["expected_rejected_options"]))
        rej_statements = [r["statement"].lower() for r in ctx.rejected_options]
        self.assertTrue(any("local http" in s for s in rej_statements))
        self.assertTrue(any("shared memory" in s for s in rej_statements))

    def test_conformance_scenario_03_decision_reversals(self):
        """RFC-0006 Scenario 3: Decision reversal superseding an earlier architectural choice."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_03_decision_reversals.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_03_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # Active decision must be SQLite
        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("sqlite", ctx.decisions[0].title.lower())
        self.assertNotIn("postgresql", ctx.decisions[0].title.lower())

        # PostgreSQL moved to rejected options
        self.assertTrue(any("postgresql" in r["statement"].lower() for r in ctx.rejected_options))

    def test_conformance_scenario_04_partial_agreements(self):
        """RFC-0006 Scenario 4: Compound utterance with partial agreement and partial rejection."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_04_partial_agreements.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_04_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # ClickHouse ratified
        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("clickhouse", ctx.decisions[0].title.lower())

        # Apache Kafka rejected
        self.assertTrue(any("kafka" in r["statement"].lower() for r in ctx.rejected_options))

    def test_conformance_scenario_05_ambiguous_confirmations(self):
        """RFC-0006 Scenario 5: Provisional hesitation ('sleep on it') yields zero false decisions."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_05_ambiguous_confirmations.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_05_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # Zero false-positive decisions
        self.assertEqual(len(ctx.decisions), 0)
        # Svelte proposal captured as awaiting decision
        self.assertGreaterEqual(len(ctx.recommendations), 1)
        self.assertIn("svelte", ctx.recommendations[0]["statement"].lower())

    def test_conformance_scenario_06_fenced_code_paths(self):
        """RFC-0006 Scenario 6: Fenced code block comments do not bleed into decisions."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_06_fenced_code_paths.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_06_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # Decision is InMemoryCache, not Redis
        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("inmemorycache", ctx.decisions[0].title.lower())
        self.assertFalse(any("redis" in d.title.lower() for d in ctx.decisions))

        # Paths preserved
        artifacts = [a["path"] for a in ctx.artifacts]
        self.assertTrue(any("src/scs_core/cache/manager.py" in p for p in artifacts))

    def test_conformance_scenario_07_pure_brainstorming(self):
        """RFC-0006 Scenario 7: Exploratory discussion yields zero decisions or rejections."""
        sc_file = self.tv_dir / "multi_turn_scenarios" / "scenario_07_pure_brainstorming.md"
        ex_file = self.tv_dir / "expected_extraction" / "scenario_07_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # Zero decisions, zero rejections, zero tasks
        self.assertEqual(len(ctx.decisions), 0)
        self.assertEqual(len(ctx.rejected_options), 0)
        self.assertEqual(len(ctx.pending_tasks), 0)

    def test_conformance_conflict_offline_vs_cloud(self):
        """RFC-0006 Conflict: Offline network constraint flags cloud service decision."""
        sc_file = self.tv_dir / "conflict_scenarios" / "conflict_offline_vs_cloud.md"
        ex_file = self.tv_dir / "conflict_scenarios" / "conflict_offline_vs_cloud_expected.json"

        fragments = self._split_fragments(sc_file.read_text(encoding="utf-8"))
        expected = json.loads(ex_file.read_text(encoding="utf-8"))

        ctx = self.engine.extract(fragments)

        # Conflict detected
        self.assertGreaterEqual(len(ctx.conflicts), 1)
        conflict = ctx.conflicts[0]
        self.assertIn("offline", conflict["statement_a"].lower())
        self.assertIn("aws", conflict["statement_b"].lower())


if __name__ == "__main__":
    unittest.main()
