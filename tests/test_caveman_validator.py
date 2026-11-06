"""Unit test suite for Caveman Context Extraction Validator.

Regression tests covering:
1. AI recommendation vs Human Decision (Preserve conversation authority).
2. Human confirmation promotes recommendation to Decision.
3. Questions are classified as OPEN QUESTION, not TASK.
4. Incomplete constraints (e.g. 'Constraint: refactor:') rejected to UNCLASSIFIED_CONTEXT.
5. Exact technical identifiers (paths, files, symbols) preserved verbatim.
6. Open review questions and evaluation synthesis.
"""

import unittest
from scs_core.modules.caveman_engine import CavemanContextExtractionEngine
from scs_core.modules.caveman_context_validator import CavemanContextValidator


class TestCavemanContextValidator(unittest.TestCase):
    def setUp(self):
        self.engine = CavemanContextExtractionEngine()
        self.validator = CavemanContextValidator()

    def test_01_ai_recommendation_is_not_decision(self):
        """Test 1 — AI recommendation without human confirmation remains Recommendation, NOT Decision."""
        raw_fragment = (
            "AI:\n"
            "I recommend modular architecture."
        )
        ctx = self.engine.extract([raw_fragment])

        # Must NOT be a decision
        self.assertEqual(len(ctx.decisions), 0, "AI recommendation must not be promoted to decision without human confirmation")

        # Must be captured as a recommendation awaiting human decision
        self.assertGreaterEqual(len(ctx.recommendations), 1)
        rec = ctx.recommendations[0]
        self.assertIn("modular architecture", rec["statement"].lower())
        self.assertEqual(rec["status"], "Awaiting human decision")

    def test_02_human_confirmation_promotes_to_decision(self):
        """Test 2 — Human confirmation promotes AI recommendation to a full Causal Decision."""
        raw_fragments = [
            "AI:\nI recommend modular architecture.\n\nHuman:\nYes, proceed with this approach."
        ]
        ctx = self.engine.extract(raw_fragments)

        # Must be promoted to confirmed Decision
        self.assertGreaterEqual(len(ctx.decisions), 1, "AI recommendation + human confirmation must become a decision")
        dec = ctx.decisions[0]
        self.assertIn("modular architecture", dec.title.lower())
        self.assertIn("Confirmed", dec.human_decision)
        self.assertIn("modular architecture", dec.recommendation.lower())

    def test_03_question_detection_not_task(self):
        """Test 3 — Questions are detected as OPEN QUESTION, never as TASK."""
        raw_fragment = "What are the gaps?"
        ctx = self.engine.extract([raw_fragment])

        # Tasks must NOT contain the question
        self.assertEqual(len(ctx.pending_tasks), 0, "Questions must not be treated as tasks")
        self.assertEqual(len(ctx.completed_tasks), 0)

        # Must be in open questions
        self.assertGreaterEqual(len(ctx.open_questions), 1)
        self.assertTrue(any("gaps" in q.lower() for q in ctx.open_questions))

    def test_03b_checkbox_question_routed_to_open_questions(self):
        """Test 3b — Questions formatted as checkboxes (- [ ] Should we add multiplayer?) become questions, not tasks."""
        raw_fragment = "Checklist:\n- [ ] Should we add multiplayer?"
        ctx = self.engine.extract([raw_fragment])

        self.assertEqual(len(ctx.pending_tasks), 0, "Checkbox question must not become a task")
        self.assertGreaterEqual(len(ctx.open_questions), 1)
        self.assertTrue(any("multiplayer" in q.lower() for q in ctx.open_questions))
        # Formatted cleanly
        self.assertTrue(any("Evaluate whether multiplayer is required" in q for q in ctx.open_questions))

    def test_04_incomplete_constraint_rejection(self):
        """Test 4 — Incomplete constraint fragments (e.g. 'Constraint: refactor:') are rejected to UNCLASSIFIED_CONTEXT."""
        raw_fragment = (
            "Constraint:\n"
            "refactor:"
        )
        ctx = self.engine.extract([raw_fragment])

        # Must NOT be a constraint
        self.assertEqual(len(ctx.constraints), 0, "Incomplete fragment 'refactor:' must not be accepted as a constraint")

        # Must be preserved in unclassified context
        self.assertGreaterEqual(len(ctx.unclassified_context), 1)
        self.assertTrue(any("refactor" in u.lower() for u in ctx.unclassified_context))

    def test_04b_valid_constraint_accepted(self):
        """Test 4b — Substantive constraint with limitation rule is accepted."""
        raw_fragment = "Constraint: Frontend must remain modular."
        ctx = self.engine.extract([raw_fragment])

        self.assertEqual(len(ctx.constraints), 1)
        self.assertIn("frontend must remain modular", ctx.constraints[0].lower())

    def test_05_technical_preservation(self):
        """Test 5 — Technical paths and identifiers are preserved verbatim without simplification."""
        raw_fragment = "Modify src/scs_core/modules/caveman_engine.py to add validation layer."
        ctx = self.engine.extract([raw_fragment])

        # Exact path preserved
        self.assertGreaterEqual(len(ctx.artifacts), 1)
        artifact_paths = [a["path"] for a in ctx.artifacts]
        self.assertIn("src/scs_core/modules/caveman_engine.py", artifact_paths)
        # Not simplified to "caveman file"
        self.assertNotIn("caveman file", artifact_paths)

    def test_06_review_question_synthesis(self):
        """Test 6 — Multi-question review queries synthesize into sharp evaluation next action."""
        raw_fragment = "What is good? What is wrong? What are the gaps?"
        ctx = self.engine.extract([raw_fragment])

        self.assertEqual(len(ctx.pending_tasks), 0)
        self.assertTrue(any("strengths, weaknesses, and gaps" in q for q in ctx.open_questions))
        self.assertEqual(ctx.first_instruction_for_next_ai, "Evaluate current strengths, weaknesses, and gaps.")

    def test_07_speculative_brainstorming_rejected_from_decisions(self):
        """Test 7 — Speculative AI brainstorming with 'what if' / 'maybe' is NOT a decision."""
        raw_fragment = (
            "AI:\n"
            "What if we choose SQLite for local testing, or maybe PostgreSQL?\n"
            "Let's choose SQLite as an experiment."
        )
        ctx = self.engine.extract([raw_fragment])
        self.assertEqual(len(ctx.decisions), 0, "Speculative AI brainstorming must not become confirmed decisions")

    def test_08_comparison_rejected_from_decisions(self):
        """Test 8 — Comparison statements (choosing X provides Y whereas choosing Z provides W) are not decisions."""
        raw_fragment = (
            "AI:\n"
            "Choosing SQLite provides zero config, whereas choosing PostgreSQL provides better concurrency.\n"
            "Maybe we should consider SQLite."
        )
        ctx = self.engine.extract([raw_fragment])
        self.assertEqual(len(ctx.decisions), 0, "Comparison clauses must not be misclassified as decisions")

    def test_09_pronoun_resolution_preserves_human_decision(self):
        """Test 9 — Pronoun references ('Let's use it', 'Adopt this') resolve to preceding AI proposals."""
        raw_fragments = [
            "AI:\nWe could use PostgreSQL for relational storage.",
            "User:\nLet's use it because we have existing scripts."
        ]
        ctx = self.engine.extract(raw_fragments)
        self.assertGreaterEqual(len(ctx.decisions), 1, "Pronoun confirmation must resolve to subject and produce decision")
        dec = ctx.decisions[0]
        self.assertIn("postgresql", dec.title.lower())
        self.assertIn("existing scripts", dec.reasoning.lower())

    def test_10_decision_evolution_and_reversal(self):
        """Test 10 — Decision evolution correctly moves superseded choices to rejected options."""
        raw_fragments = [
            "User:\nLet's use MySQL because we know it well.",
            "User:\nActually, I changed my mind. Do not use MySQL. Let's use SQLite instead because of zero configuration."
        ]
        ctx = self.engine.extract(raw_fragments)
        # MySQL must be removed from active decisions
        self.assertFalse(any("mysql" in d.title.lower() for d in ctx.decisions), "Superseded decision must not remain active")
        # SQLite must be in active decisions
        self.assertTrue(any("sqlite" in d.title.lower() for d in ctx.decisions), "Latest ratified decision must be active")
        # MySQL must be in rejected options
        self.assertTrue(any("mysql" in r["statement"].lower() for r in ctx.rejected_options), "Superseded choice must be recorded in rejected options")

    def test_11_semantic_constraint_deduplication(self):
        """Test 11 — Subsumed/shorter duplicate constraints merge into the more descriptive version."""
        raw_fragments = [
            "Constraint: Must run completely offline.",
            "AI: Reminder: Must run completely offline without internet.",
            "Constraint: Frontend must remain modular."
        ]
        ctx = self.engine.extract(raw_fragments)
        # Should have 2 unique constraints, not 3
        self.assertEqual(len(ctx.constraints), 2)
        # Richer version retained
        self.assertTrue(any("without internet" in c.lower() for c in ctx.constraints))

    def test_12_conflict_detection_offline_vs_cloud(self):
        """Test 12 — Detects contradictory facts between offline constraints and cloud decisions."""
        raw_fragments = [
            "Constraint: The system must run 100% offline without remote cloud servers.",
            "User: Let's use Firebase Cloud database because of real-time sync."
        ]
        ctx = self.engine.extract(raw_fragments)
        self.assertGreaterEqual(len(ctx.conflicts), 1, "Contradiction between offline rule and cloud decision must be flagged")
        conflict = ctx.conflicts[0]
        self.assertEqual(conflict["type"], "CONSTRAINT_DECISION_CONTRADICTION")
        self.assertEqual(conflict["severity"], "WARNING")

    def test_13_evidence_traceability_populated(self):
        """Test 13 — Every decision and constraint has internal traceability to source fragment and turn."""
        raw_fragments = [
            "AI:\nConstraint: Must run 100% offline.",
            "User:\nLet's use SQLite because of zero configuration."
        ]
        ctx = self.engine.extract(raw_fragments)
        self.assertGreaterEqual(len(ctx.decisions), 1)
        dec = ctx.decisions[0]
        self.assertGreaterEqual(dec.source_fragment_idx, 1)
        self.assertGreaterEqual(dec.source_turn_idx, 1)
        self.assertIn("DEC-001", ctx.traceability_matrix)
        self.assertIn("CON-001", ctx.traceability_matrix)

    def test_14_bootstrap_contains_rejected_options_and_conflicts(self):
        """Test 14 — Bootstrap continuation prompt includes rejected options and conflict warnings."""
        raw_fragments = [
            "Constraint: The system must run 100% offline without remote cloud servers.",
            "User: Do not use MongoDB because of RAM footprint.",
            "User: Let's use Firebase Cloud database because of real-time sync."
        ]
        ctx = self.engine.extract(raw_fragments)
        md = self.engine.compile_markdown_checkpoint(
            project_code="TEST",
            project_name="Test Project",
            session_id="sess_123",
            snapshot_code="SNP-001",
            checksum_sha256="abc123456789",
            extracted=ctx,
            fragment_count=len(raw_fragments)
        )
        self.assertIn("REJECTED OPTIONS", md)
        self.assertIn("DO NOT REPEAT", md)
        self.assertIn("MongoDB", md)
        self.assertIn("ACTIVE CONFLICTS DETECTED", md)

    def test_15_human_speculative_question_not_decision(self):
        """Test 15 — Human brainstorming/questions ('Maybe let's use Redis, what do you think?') are not decisions."""
        raw_fragment = "User:\nMaybe let's use Redis for session caching, what do you think?"
        ctx = self.engine.extract([raw_fragment])
        self.assertEqual(len(ctx.decisions), 0, "Human brainstorming questions must not be classified as decisions")
        self.assertTrue(any("redis" in q.lower() for q in ctx.open_questions))

    def test_16_partial_agreement_and_instead_of(self):
        """Test 16 — Handles 'Instead of X, let's use Y' and partial agreement ('I agree with X, but do not use Y')."""
        # Case A: Instead of X, let's use Y
        ctx_a = self.engine.extract([
            "User:\nInstead of Redis, let's use Memcached because it is simpler."
        ])
        self.assertTrue(any("memcached" in d.title.lower() for d in ctx_a.decisions))
        self.assertTrue(any("redis" in r["statement"].lower() for r in ctx_a.rejected_options))

        # Case B: Partial agreement
        ctx_b = self.engine.extract([
            "User:\nI agree with using SQLite, but do not use Redis because we don't need caching."
        ])
        self.assertTrue(any("sqlite" in d.title.lower() for d in ctx_b.decisions))
        self.assertTrue(any("redis" in r["statement"].lower() for r in ctx_b.rejected_options))

    def test_17_constraint_task_conflict_detected(self):
        """Test 17 — Detects contradiction when a task attempts cloud deployment under an offline constraint."""
        raw_fragments = [
            "Constraint: System must run 100% offline without remote servers.",
            "Checklist:\n- [ ] Deploy AWS Lambda function"
        ]
        ctx = self.engine.extract(raw_fragments)
        self.assertGreaterEqual(len(ctx.conflicts), 1)
        conflict = ctx.conflicts[0]
        self.assertEqual(conflict["type"], "CONSTRAINT_TASK_CONTRADICTION")
        self.assertIn("offline", conflict["statement_a"].lower())
        self.assertIn("aws lambda", conflict["statement_b"].lower())

    def test_18_full_provenance_matrix_on_all_entities(self):
        """Test 18 — Full traceability matrix populated for decisions, constraints, tasks, and rejected options."""
        raw_fragments = [
            "Constraint: Must run offline.",
            "User:\nLet's use SQLite because of zero config.\n- [ ] Create schema migrations",
            "User:\nDo not use Redis because no memory cache needed."
        ]
        ctx = self.engine.extract(raw_fragments)
        # Check all categories exist in traceability matrix with fragment_idx and quote
        self.assertIn("DEC-001", ctx.traceability_matrix)
        self.assertIn("CON-001", ctx.traceability_matrix)
        self.assertIn("TSK-001", ctx.traceability_matrix)
        self.assertIn("REJ-001", ctx.traceability_matrix)

        for key, entry in ctx.traceability_matrix.items():
            self.assertIn("fragment_idx", entry, f"Missing fragment_idx in {key}")
            self.assertIn("quote", entry, f"Missing quote in {key}")


if __name__ == "__main__":
    unittest.main()
