"""Long-Form Realistic Engineering Conversation Benchmarks.

Regression benchmark suite evaluating the Conversation Checkpoint Engine across
8 realistic multi-turn engineering scenarios:
1. Long multi-turn AI discussions.
2. Multiple rejected alternatives.
3. Decision reversals and superseding choices.
4. Partial agreements and hybrid decisions.
5. Ambiguous confirmations and provisional agreements.
6. Code blocks and verbatim file path preservation.
7. Constraints introduced early and referenced later (cross-fragment persistence & conflict detection).
8. Pure brainstorming / exploratory discussions with zero decisions.

Measures:
- False positive decisions (Target: 0)
- Missed decisions (Target: 0)
- Lost constraints (Target: 0)
- Incorrect task extraction (Target: 0)
- Incorrect rejected option handling (Target: 0)
- Bootstrap continuity quality (Target: Verified)
- Internal confidence classification (HIGH / MEDIUM / LOW)
"""

import unittest
from scs_core.modules.caveman_engine import CavemanContextExtractionEngine
from scs_core.modules.caveman_context_validator import CavemanContextValidator


class TestLongFormBenchmarks(unittest.TestCase):
    def setUp(self):
        self.engine = CavemanContextExtractionEngine()
        self.validator = CavemanContextValidator()

    def test_scenario_01_long_multiturn_architecture_discussion(self):
        """Scenario 1 — Multi-turn (10+ turns) conversation across multiple fragments.
        Verifies causal decision chain, constraint preservation, task separation,
        verbatim file paths, open questions, and confidence classification.
        """
        fragments = [
            # Fragment 1: Problem & Initial Options
            (
                "Human:\n"
                "We need to design the persistence and transaction boundary for SCS-HUD offline event vault.\n"
                "Current in-memory list risks data loss if the host crashes.\n\n"
                "AI:\n"
                "I evaluated two persistence backends:\n"
                "Option A: SQLite with Write-Ahead Logging (WAL) mode.\n"
                "Option B: Flat JSON files with append-only logs.\n"
                "I recommend SQLite with WAL mode because it provides atomic ACID transactions with minimal memory overhead."
            ),
            # Fragment 2: Human Decision & Constraint
            (
                "Human:\n"
                "Let's use SQLite with WAL mode because we need atomic ACID commits.\n"
                "Constraint: Database file size must strictly remain under 50MB.\n\n"
                "AI:\n"
                "Understood. I will configure pragmas for synchronous=NORMAL and journal_mode=WAL in src/scs_core/db/vault.py.\n"
                "Should we also compress historical snapshots with zstandard?"
            ),
            # Fragment 3: Tasks & Implementation Artifacts
            (
                "Human:\n"
                "Checklist for this sprint:\n"
                "- [ ] Implement schema migrations in src/scs_core/db/schema.sql\n"
                "- [ ] Add WAL pragma config to vault.py\n"
                "- [x] Initial write benchmark verified (15,000 ops/sec)\n\n"
                "AI:\n"
                "All items noted. The benchmark shows zero disk thrashing."
            )
        ]

        ctx = self.engine.extract(fragments, project_code="SCS", active_focus="Persistence Engine")

        # 1. Decisions: Exactly 1 decision, 0 false positives, 0 missed
        self.assertEqual(len(ctx.decisions), 1, "Must extract exactly 1 confirmed decision")
        dec = ctx.decisions[0]
        self.assertIn("sqlite with wal mode", dec.title.lower())
        self.assertEqual(dec.confidence, "HIGH", "Direct human decision must have HIGH confidence")
        self.assertIn("atomic acid commits", dec.reasoning.lower())
        self.assertEqual(dec.source_fragment_idx, 2)

        # 2. Constraints: Exactly 1 constraint preserved, 0 lost
        self.assertGreaterEqual(len(ctx.constraints), 1, "Must preserve the 50MB constraint")
        self.assertTrue(any("50mb" in c.lower() for c in ctx.constraints))

        # 3. Tasks: Clean separation of pending vs completed, questions NOT tasks
        self.assertEqual(len(ctx.completed_tasks), 1)
        self.assertIn("benchmark verified", ctx.completed_tasks[0]["title"].lower())
        self.assertGreaterEqual(len(ctx.pending_tasks), 2)
        pending_titles = [t["title"].lower() for t in ctx.pending_tasks]
        self.assertTrue(any("schema migrations" in t for t in pending_titles))
        self.assertTrue(any("wal pragma" in t for t in pending_titles))

        # 4. Open Question: Identified as question, not task
        self.assertTrue(any("zstandard" in q.lower() for q in ctx.open_questions))
        self.assertFalse(any("zstandard" in t["title"].lower() for t in ctx.pending_tasks))

        # 5. Artifacts: Verbatim paths preserved
        artifact_paths = [a["path"] for a in ctx.artifacts]
        self.assertTrue(any("src/scs_core/db/vault.py" in p for p in artifact_paths))
        self.assertTrue(any("src/scs_core/db/schema.sql" in p for p in artifact_paths))

        # 6. Bootstrap Markdown continuity check
        md = self.engine.compile_markdown_checkpoint(
            project_code="SCS",
            project_name="AI SCS HUD",
            session_id="bench_sess_01",
            snapshot_code="SNP-B01",
            checksum_sha256="abc123456",
            extracted=ctx,
            fragment_count=len(fragments),
        )
        self.assertIn("sqlite with wal mode", md.lower())
        self.assertIn("Next Session Bootstrap", md)
        self.assertIn("WHAT TO DO FIRST IN THIS SESSION", md)

    def test_scenario_02_multiple_rejected_alternatives(self):
        """Scenario 2 — Comparison of multiple alternatives with explicit rejections.
        Verifies rejection capture with reasons, do-not-repeat preservation, and ratified decision.
        """
        fragments = [
            (
                "Human:\n"
                "We need to select an IPC mechanism between the Windows desktop UI and Python core daemon.\n\n"
                "AI:\n"
                "Here are three candidates:\n"
                "1. Local HTTP REST on loopback port.\n"
                "2. Shared memory via memory-mapped files.\n"
                "3. Windows Named Pipes.\n\n"
                "Human:\n"
                "Do not use Local HTTP because port conflicts with existing developer servers.\n"
                "Do not use Shared Memory because mutex synchronization in Python is brittle.\n"
                "Let's use Windows Named Pipes because it is native and has zero port conflict."
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. Decision: Exactly 1 ratified decision
        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("named pipes", ctx.decisions[0].title.lower())
        self.assertEqual(ctx.decisions[0].confidence, "HIGH")

        # 2. Rejected Alternatives: Both rejected alternatives captured with reasons
        self.assertGreaterEqual(len(ctx.rejected_options), 2, "Must capture both rejected alternatives")
        rej_statements = [r["statement"].lower() for r in ctx.rejected_options]
        self.assertTrue(any("local http" in r for r in rej_statements))
        self.assertTrue(any("shared memory" in r for r in rej_statements))

        # Check reasoning preservation
        http_rej = next(r for r in ctx.rejected_options if "local http" in r["statement"].lower())
        self.assertIn("port conflict", http_rej["why"].lower())

        shm_rej = next(r for r in ctx.rejected_options if "shared memory" in r["statement"].lower())
        self.assertIn("mutex", shm_rej["why"].lower())

        # 3. Bootstrap Check: Appears under DO NOT REPEAT
        md = self.engine.compile_markdown_checkpoint(
            project_code="SCS",
            project_name="AI SCS HUD",
            session_id="bench_sess_02",
            snapshot_code="SNP-B02",
            checksum_sha256="abc123456",
            extracted=ctx,
            fragment_count=len(fragments),
        )
        self.assertIn("REJECTED OPTIONS (DO NOT REPEAT)", md)
        self.assertIn("local http", md.lower())
        self.assertIn("shared memory", md.lower())

    def test_scenario_03_decision_reversals_and_superseding(self):
        """Scenario 3 — Multi-turn decision reversal.
        Verifies superseded decision is removed from active decisions and added to rejected options.
        """
        fragments = [
            # Fragment 1: Initial decision
            (
                "AI:\n"
                "What database engine should we adopt?\n\n"
                "Human:\n"
                "Let's use PostgreSQL because we need rich relational SQL queries."
            ),
            # Fragment 2: Reversal to SQLite
            (
                "AI:\n"
                "Here is the PostgreSQL connection string template.\n\n"
                "Human:\n"
                "Change of plans: let's use SQLite instead of PostgreSQL because we must be single-binary offline."
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. Active Decisions: SQLite only, PostgreSQL MUST NOT be active
        self.assertEqual(len(ctx.decisions), 1, "Must have exactly 1 active decision after reversal")
        active_dec = ctx.decisions[0]
        self.assertIn("sqlite", active_dec.title.lower())
        self.assertNotIn("postgresql", active_dec.title.lower())
        self.assertEqual(active_dec.confidence, "HIGH")

        # 2. Rejected Options: PostgreSQL moved to rejected options
        self.assertGreaterEqual(len(ctx.rejected_options), 1)
        self.assertTrue(any("postgresql" in r["statement"].lower() for r in ctx.rejected_options))

    def test_scenario_04_partial_agreements_and_hybrid_decisions(self):
        """Scenario 4 — Partial agreement ('I agree with X, but do not use Y').
        Verifies ratified component is Decision, discarded component is Rejected Option.
        """
        fragments = [
            (
                "AI:\n"
                "For our analytics engine, I recommend using ClickHouse for aggregations and Apache Kafka for event bus.\n\n"
                "Human:\n"
                "I agree with using ClickHouse because column-oriented aggregation is fast, but do not use Apache Kafka because it requires JVM and is too heavy for desktop."
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. Decision: ClickHouse ratified (HIGH confidence)
        self.assertEqual(len(ctx.decisions), 1)
        self.assertIn("clickhouse", ctx.decisions[0].title.lower())
        self.assertEqual(ctx.decisions[0].confidence, "HIGH")

        # 2. Rejected: Apache Kafka rejected, NOT a decision
        self.assertFalse(any("kafka" in d.title.lower() for d in ctx.decisions))
        self.assertGreaterEqual(len(ctx.rejected_options), 1)
        self.assertTrue(any("kafka" in r["statement"].lower() for r in ctx.rejected_options))
        kafka_rej = next(r for r in ctx.rejected_options if "kafka" in r["statement"].lower())
        self.assertIn("jvm", kafka_rej["why"].lower())

    def test_scenario_05_ambiguous_confirmations_not_promoted(self):
        """Scenario 5 — Provisional/ambiguous human confirmations ('sleep on it', 'maybe').
        Verifies 0 false positive decisions are created from non-binding dialogue.
        """
        fragments = [
            (
                "AI:\n"
                "I recommend migrating our entire frontend from React to Svelte for smaller bundle size.\n\n"
                "Human:\n"
                "Sounds interesting, but let me sleep on it before making any big architectural changes.\n\n"
                "AI:\n"
                "Understood. We could also consider Preact as a lighter alternative.\n\n"
                "Human:\n"
                "Maybe, let's see how the benchmarks turn out next week."
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. False positive decisions: MUST BE EXACTLY 0
        self.assertEqual(len(ctx.decisions), 0, "Provisional hesitation must never create decisions (0 false positives)")

        # 2. Recommendations: AI proposal captured as awaiting decision
        self.assertGreaterEqual(len(ctx.recommendations), 1)
        rec = ctx.recommendations[0]
        self.assertIn("svelte", rec["statement"].lower())
        self.assertEqual(rec["status"], "Awaiting human decision")

    def test_scenario_06_code_blocks_and_verbatim_file_paths(self):
        """Scenario 6 — Fenced code blocks containing decision comments & file paths.
        Verifies comments inside code blocks do not create false decisions,
        while referenced file paths are preserved verbatim.
        """
        fragments = [
            (
                "Human:\n"
                "How should we implement the cache layer?\n\n"
                "AI:\n"
                "Here is an example implementation:\n"
                "```python\n"
                "# We decided to use Redis for all caching\n"
                "# Let's use AWS ElastiCache cluster\n"
                "import redis\n"
                "client = redis.Redis(host='localhost', port=6379)\n"
                "```\n"
                "Configure this in `src/scs_core/cache/manager.py` and `config/redis_settings.json`.\n\n"
                "Human:\n"
                "Do not use Redis. Let's use InMemoryCache because of zero external daemon dependencies."
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. Decisions: Exactly 1 decision (InMemoryCache), ZERO decisions from code comments
        self.assertEqual(len(ctx.decisions), 1)
        dec = ctx.decisions[0]
        self.assertIn("inmemorycache", dec.title.lower())
        self.assertFalse(any("redis" in d.title.lower() for d in ctx.decisions))
        self.assertFalse(any("aws" in d.title.lower() for d in ctx.decisions))

        # 2. Artifacts: Verbatim paths preserved from conversation
        artifact_paths = [a["path"] for a in ctx.artifacts]
        self.assertTrue(any("src/scs_core/cache/manager.py" in p for p in artifact_paths))
        self.assertTrue(any("config/redis_settings.json" in p for p in artifact_paths))

    def test_scenario_07_constraints_introduced_early_referenced_later(self):
        """Scenario 7 — Constraints introduced in fragment 1 persist across subsequent fragments.
        Verifies cross-fragment constraint retention and conflict detection against later contradictory tasks.
        """
        fragments = [
            # Fragment 1: Hard constraint
            (
                "Human:\n"
                "Constraint: The application must strictly operate 100% offline without remote network calls.\n\n"
                "AI:\n"
                "Understood. The architecture will operate fully air-gapped."
            ),
            # Fragment 2: Local logging
            (
                "Human:\n"
                "Let's use RotatingFileHandler for diagnostics.\n"
                "- [ ] Configure log rotation in src/scs_core/logging.py"
            ),
            # Fragment 3: Contradictory cloud task
            (
                "Human:\n"
                "Sprint checklist:\n"
                "- [ ] Deploy AWS Lambda telemetry sync"
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. Constraint retention: Early constraint persists
        self.assertGreaterEqual(len(ctx.constraints), 1)
        self.assertTrue(any("offline" in c.lower() for c in ctx.constraints))

        # 2. Conflict detection: Flags contradiction between offline constraint and AWS Lambda task
        self.assertGreaterEqual(len(ctx.conflicts), 1)
        conflict = ctx.conflicts[0]
        self.assertEqual(conflict["type"], "CONSTRAINT_TASK_CONTRADICTION")
        self.assertEqual(conflict["severity"], "WARNING")
        self.assertIn("offline", conflict["statement_a"].lower())
        self.assertIn("aws lambda", conflict["statement_b"].lower())

    def test_scenario_08_pure_brainstorming_zero_decisions(self):
        """Scenario 8 — Pure exploratory discussion with zero decisions made.
        Verifies 0 false positive decisions, 0 false rejected options, and clean open question capture.
        """
        fragments = [
            (
                "Human:\n"
                "What are the pros and cons of event sourcing versus CRUD for our state machine?\n\n"
                "AI:\n"
                "Event sourcing provides an immutable audit trail, whereas CRUD offers simpler data queries.\n\n"
                "Human:\n"
                "What if we consider CQRS? Could consider GraphQL or gRPC for query schemas.\n\n"
                "AI:\n"
                "Evaluating both: GraphQL has client-driven schema flexibility, whereas gRPC has high-throughput binary serialization.\n\n"
                "Human:\n"
                "Interesting trade-offs, let's revisit this next sprint after we write a prototype."
            )
        ]

        ctx = self.engine.extract(fragments)

        # 1. Decisions: EXACTLY 0 false positives
        self.assertEqual(len(ctx.decisions), 0, "Exploratory discussion must yield 0 decisions")

        # 2. Rejections: EXACTLY 0 false rejections
        self.assertEqual(len(ctx.rejected_options), 0, "No options were ratified or rejected")

        # 3. Tasks: EXACTLY 0 tasks
        self.assertEqual(len(ctx.pending_tasks), 0)
        self.assertEqual(len(ctx.completed_tasks), 0)

        # 4. Open Questions / Unclassified: Captured for future inquiry
        self.assertTrue(
            len(ctx.open_questions) > 0 or len(ctx.unclassified_context) > 0,
            "Exploratory queries must be retained in context"
        )


if __name__ == "__main__":
    unittest.main()
