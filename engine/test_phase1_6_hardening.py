"""
Phase 1.6 Production Hardening Acceptance Test Suite (engine/test_phase1_6_hardening.py)
========================================================================================

Verifies the 5 Phase 1.6 quality invariants against production defects:
- Scenario A: Markdown Table Extraction Rejection (no table rows become decisions)
- Scenario B: Generic Word Filtering ('Adopt count', 'Use With failure' rejected)
- Scenario C: False Rejected-Option Prevention (system capabilities protected from rejection inversion)
- Scenario D: Completed Task Lifecycle Reconciliation (verified components marked COMPLETED with evidence)
- Scenario E: Handover Package Architecture Overview Presence (all 6 sections verified)
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project root & core/python to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if (CURRENT_DIR.parent / "core" / "python").exists():
    REPO_ROOT = CURRENT_DIR.parent
else:
    REPO_ROOT = CURRENT_DIR.parent.parent
CORE_PYTHON_DIR = REPO_ROOT / "core" / "python"

if str(CORE_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_PYTHON_DIR))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import core_adapter
import vault_store


class TestPhase16Hardening(unittest.TestCase):
    """Phase 1.6 Hardening verification test suite."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)
        self.vault_dir = Path(self.temp_dir) / ".continuity"
        vault_store.create_vault(
            project_dir=self.temp_dir,
            project_code="TEST_HARDEN",
            project_name="Phase 1.6 Hardening Test Project",
            objective="Verify continuity extraction quality and safety invariants",
            root_paths=[self.temp_dir],
        )

    # -----------------------------------------------------------------------
    # Scenario A: Markdown Table Extraction Rejection
    # -----------------------------------------------------------------------

    def test_scenario_a_markdown_table_rejection(self):
        """Markdown table headers, delimiters, and matrix rows must never become decisions."""
        table_dialogue = """
Human: Let's review the verification matrix.
AI: Here is the current test matrix:

| Component | Status | Test Result |
| :--- | :--- | :--- |
| Step 1.1: core_adapter.py | PASS | 13/13 passed |
| Step 1.2: vault_store.py | PASS | 8/8 passed |
| Step 1.3: transcript_reader.py | PASS | 10/10 passed |
| Step 1.4: scs_cli.py | PASS | 11/11 passed |
| Step 1.5: SKILL.md | PASS | 6/6 passed |

Human: Proceed with the rollout.
AI: Understood, proceeding with deployment.
"""
        extracted = core_adapter.extract_context(
            fragments=table_dialogue,
            project_code="TEST_HARDEN",
        )

        # 1. No decision title should contain pipe characters or table rows
        for d in extracted.decisions:
            self.assertNotIn("|", d.title, f"Decision title contains table syntax: {d.title}")
            self.assertFalse(
                any(d.title.lower().startswith(p) for p in ["step 1", "component", "status"]),
                f"Table row extracted as decision: {d.title}",
            )

        # 2. validate_decision_title invariant check
        self.assertFalse(core_adapter.validate_decision_title("| Component | Status |")[0])
        self.assertFalse(core_adapter.validate_decision_title("| :--- | :--- |")[0])
        self.assertFalse(core_adapter.validate_decision_title("| Step 1.1: core_adapter.py | PASS |")[0])

    # -----------------------------------------------------------------------
    # Scenario B: Generic Word Filtering
    # -----------------------------------------------------------------------

    def test_scenario_b_generic_word_filtering(self):
        """Generic words ('count', 'status', 'failure', etc.) must be rejected unless part of complete propositions."""
        # Test unit validator invariants
        bad_titles = [
            "Adopt count",
            "Adopt status",
            "Adopt result",
            "Adopt failure",
            "Use With failure",
            "Use failure",
            "Adopt check",
            "Adopt item",
            "Adopt test",
            "Adopt",
        ]
        for title in bad_titles:
            is_val, reason = core_adapter.validate_decision_title(title)
            self.assertFalse(is_val, f"Failed to reject generic title: '{title}' (reason: {reason})")

        # Complete architectural propositions containing words like 'count' or 'test' should be allowed
        good_titles = [
            "Adopt a Dual-Layer Staging Architecture",
            "Adopt a Standalone Zero-Dependency Python Sealing Helper",
            "Maintain session index in MANIFEST recording step end and turn hash",
            "Count database query latency with Prometheus metric exporter",
            "Use SQLite with WAL mode",
            "Use Windows Named Pipes",
        ]
        for title in good_titles:
            is_val, reason = core_adapter.validate_decision_title(title)
            self.assertTrue(is_val, f"Incorrectly rejected valid proposition: '{title}' (reason: {reason})")

        # Test full dialogue extraction with explicit decisions vs noisy lines
        dialogue = """
Human: We need to finalize the architecture decisions.
AI: Here is my report:
- [ ] Evidence/session count
- **/scs status** displays active decisions, rejected options, and pending proposal count.
Decision: Adopt a Dual-Layer Staging Architecture for human custody isolation.
Decision: Adopt a Standalone Zero-Dependency Python Sealing Helper utilizing hashlib and json.
Human: Approved.
"""
        extracted = core_adapter.extract_context(
            fragments=dialogue,
            project_code="TEST_HARDEN",
        )

        decision_titles = [d.title for d in extracted.decisions]
        self.assertNotIn("Adopt count", decision_titles)
        self.assertNotIn("count", [t.lower() for t in decision_titles])
        self.assertTrue(any("dual-layer staging architecture" in t.lower() for t in decision_titles))
        self.assertTrue(any("sealing helper" in t.lower() for t in decision_titles))

    # -----------------------------------------------------------------------
    # Scenario C: False Rejected-Option Prevention
    # -----------------------------------------------------------------------

    def test_scenario_c_rejected_option_protection(self):
        """System capabilities and safeguards must NEVER be classified as rejected options."""
        # Statements mentioning system capabilities that were previously misclassified
        misclassified_statements = [
            'options ("Do Not Repeat"), preventing models from cycling through previously discarded solutions',
            'Options ("Do Not Repeat")** register with failure rationales, models loop through identical dead ends',
            'options tracking',
            'options registry',
            'deterministic sealing of canonical state',
            'human custody gate before promotion',
            'staging quarantine buffer',
            'O_RDONLY low-level descriptors',
            'transcript reader streaming parser',
            'Workflow',
            'alternatives',
            'options',
        ]

        for stmt in misclassified_statements:
            is_val, reason = core_adapter.validate_rejected_option_statement(stmt)
            self.assertFalse(is_val, f"System capability or vague fragment not protected: '{stmt}' (reason: {reason})")

        # Genuine rejected options MUST be allowed
        genuine_rejected = [
            ("Direct SQLite database without staging", "Bypasses human custody gate"),
            ("In-repo continuity vault", "Pollutes application git repository history"),
            ("Parsing markdown back into state", "Violates machine SSOT authority"),
            ("Manual copy-paste workflow", "High human toil and error-prone"),
            ("PostgreSQL", "Requires running external daemon process"),
            ("Kafka", "Overkill for single-node assistant architecture"),
        ]

        for stmt, why in genuine_rejected:
            is_val, reason = core_adapter.validate_rejected_option_statement(stmt, why)
            self.assertTrue(is_val, f"Genuine rejected option incorrectly rejected: '{stmt}' (reason: {reason})")

        # Test recovery card generation: must not contain inverted warnings
        proj = {"code": "TEST", "name": "Test Project"}
        snap = {"snapshot_code": "SNP-001"}
        decisions = [
            {"code": "REJ-001", "record_kind": "REJECTED_OPTION", "statement": "Direct SQLite database without staging", "rationale_why": "Bypasses human custody gate"}
        ]
        res = core_adapter.generate_handover_context(
            project=proj,
            snapshot=snap,
            decisions=decisions,
            tasks=[],
            artifacts=[],
        )

        recovery_card = res["recovery_card_content"]
        self.assertNotIn("Do Not Repeat", recovery_card.split("## ⚠️ Remember")[-1].split("##")[0] if "## ⚠️ Remember" in recovery_card else "")
        self.assertIn("**Avoid:** Direct SQLite database without staging", recovery_card)

    # -----------------------------------------------------------------------
    # Scenario D: Completed Task Lifecycle Reconciliation
    # -----------------------------------------------------------------------

    def test_scenario_d_completed_task_reconciliation(self):
        """Verified on-disk components must be marked COMPLETED with evidence, not 0%."""
        # Create dummy implemented files in temp_dir
        engine_dir = Path(self.temp_dir) / "engine"
        engine_dir.mkdir(parents=True, exist_ok=True)
        (engine_dir / "core_adapter.py").write_text("# core_adapter stub", encoding="utf-8")
        (engine_dir / "vault_store.py").write_text("# vault_store stub", encoding="utf-8")
        (engine_dir / "transcript_reader.py").write_text("# transcript_reader stub", encoding="utf-8")
        (engine_dir / "scs_cli.py").write_text("# scs_cli stub", encoding="utf-8")

        skill_dir = Path(self.temp_dir) / ".agents" / "skills" / "scs"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("# skill stub", encoding="utf-8")

        tasks = [
            {"title": "Step 1.1 — Create Read-Only Core Adapter", "status": "PENDING"},
            {"title": "Step 1.2 — Implement vault_store.py", "status": "PENDING"},
            {"title": "Step 1.3 — Implement transcript_reader.py", "status": "PENDING"},
            {"title": "Step 1.4 — Implement Unified SCS CLI (engine/scs_cli.py)", "status": "PENDING"},
            {"title": "Step 1.5 — Antigravity Skill Packaging (SKILL.md)", "status": "PENDING"},
            {"title": "Future Phase 2 SQLite Indexer", "status": "PENDING"},
        ]

        reconciled = core_adapter.reconcile_task_lifecycle(tasks, root_paths=[self.temp_dir])
        completed = [t for t in reconciled if t.get("status") == "COMPLETED"]
        pending = [t for t in reconciled if t.get("status") == "PENDING"]

        self.assertEqual(len(completed), 5, f"Expected 5 completed tasks, got {len(completed)}")
        self.assertEqual(len(pending), 1, f"Expected 1 pending task, got {len(pending)}")

        for t in completed:
            self.assertTrue(t.get("completed_by_verification"), f"Task {t['title']} missing completed_by_verification")
            self.assertTrue(t.get("completed_evidence"), f"Task {t['title']} missing completed_evidence")

        # Test staging and promotion of reconciled tasks into canonical ledger
        staged_items = []
        for t in reconciled:
            staged_items.append({
                "proposal_type": "TASK",
                "statement": t["title"],
                "why": "Phase 1 implementation milestone",
                "task_status": t["status"],
                "completed_by_verification": t.get("completed_by_verification", False),
                "completed_evidence": t.get("completed_evidence", ""),
            })

        vault_store.append_staging_proposals(self.vault_dir, staged_items)
        promo_res = vault_store.promote_proposals(self.vault_dir, promote_all=True)
        self.assertEqual(promo_res["promoted_tasks"], 6)

        # Verify canonical ledger retains completed_by_verification and completed_evidence
        ledger = vault_store.read_ledger(self.vault_dir, verify_seal=True)
        canonical_tasks = ledger.get("tasks", [])
        c_completed = [t for t in canonical_tasks if t.get("status") == "COMPLETED"]
        self.assertEqual(len(c_completed), 5)
        for ct in c_completed:
            self.assertTrue(ct.get("completed_by_verification"))
            self.assertIn("Verified on disk", ct.get("completed_evidence", ""))

        # Verify generated canonical/TASKS.md contains evidence
        paths = vault_store.get_vault_paths(self.vault_dir)
        tasks_md = paths["tasks_md"].read_text(encoding="utf-8")
        self.assertIn("[x]", tasks_md)
        self.assertIn("Evidence: Verified on disk", tasks_md)
        self.assertIn("83%", tasks_md)  # 5/6 completed = 83%

    # -----------------------------------------------------------------------
    # Scenario E: Handover Package Architecture Overview Presence
    # -----------------------------------------------------------------------

    def test_scenario_e_handover_architecture_overview(self):
        """Master AI Handover Package must include the mandatory Architecture Overview section."""
        proj = {"code": "SCS_AG_V2", "name": "SCS_AG_v2 Engine"}
        snap = {"snapshot_code": "SNP-20261105-001"}
        decisions = [
            {"code": "DEC-001", "record_kind": "DECISION", "statement": "Adopt a Dual-Layer Staging Architecture", "rationale_why": "Human custody boundary"},
            {"code": "REJ-001", "record_kind": "REJECTED_OPTION", "statement": "Direct SQLite database without staging", "rationale_why": "Bypasses human custody gate"},
        ]
        tasks = [
            {"code": "TSK-001", "title": "Step 1.1 Read-Only Core Adapter", "status": "COMPLETED", "why_it_matters": "Bridge to upstream scs_core"}
        ]

        res = core_adapter.generate_handover_context(
            project=proj,
            snapshot=snap,
            decisions=decisions,
            tasks=tasks,
            artifacts=[],
        )

        handover_md = res["handover_content"]
        self.assertIn("## Architecture Overview", handover_md)
        self.assertIn("### 1. What It Is", handover_md)
        self.assertIn("### 2. Why It Exists", handover_md)
        self.assertIn("### 3. Core Architecture & Data Flow", handover_md)
        self.assertIn("### 4. Key Core Components", handover_md)
        self.assertIn("### 5. Governance Boundaries", handover_md)
        self.assertIn("### 6. Current Implementation State", handover_md)
        self.assertIn("core_adapter.py", handover_md)
        self.assertIn("vault_store.py", handover_md)
        self.assertIn("transcript_reader.py", handover_md)
        self.assertIn("scs_cli.py", handover_md)
        self.assertIn("SKILL.md", handover_md)

    # -----------------------------------------------------------------------
    # Scenario F: Canonical Proposal Deduplication on Promotion (DFG-003)
    # -----------------------------------------------------------------------

    def test_scenario_f_canonical_proposal_deduplication(self):
        """Promoting identical artifacts, decisions, constraints, or tasks must not create duplicates."""
        # 1. First promotion of items
        props_batch1 = [
            {"id": "P01", "proposal_type": "ARTIFACT", "name": "core_adapter.py", "relative_path": "engine/core_adapter.py"},
            {"id": "P02", "proposal_type": "CONSTRAINT", "statement": "All commands must respect sandbox", "why": "Security boundary"},
            {"id": "P03", "proposal_type": "DECISION", "statement": "Adopt standalone zero-dependency Python sealing", "why": "No external daemons"},
        ]
        vault_store.append_staging_proposals(self.vault_dir, props_batch1)
        r1 = vault_store.promote_proposals(self.vault_dir, promote_all=True)
        self.assertEqual(r1["promoted_artifacts"], 1)
        self.assertEqual(r1["promoted_constraints"], 1)
        self.assertEqual(r1["promoted_decisions"], 1)

        ledger1 = vault_store.read_ledger(self.vault_dir)
        self.assertEqual(len(ledger1["artifacts"]), 1)
        self.assertEqual(len(ledger1["constraints"]), 1)
        self.assertEqual(len(ledger1["decisions"]), 1)

        # 2. Second batch containing duplicate statements / paths
        props_batch2 = [
            {"id": "P01", "proposal_type": "ARTIFACT", "name": "core_adapter.py", "relative_path": "engine/core_adapter.py"},
            {"id": "P02", "proposal_type": "CONSTRAINT", "statement": "All commands must respect sandbox", "why": "Security boundary"},
            {"id": "P03", "proposal_type": "DECISION", "statement": "Adopt standalone zero-dependency Python sealing", "why": "Updated reason"},
            {"id": "P04", "proposal_type": "ARTIFACT", "name": "vault_store.py", "relative_path": "engine/vault_store.py"},
        ]
        vault_store.append_staging_proposals(self.vault_dir, props_batch2)
        r2 = vault_store.promote_proposals(self.vault_dir, promote_all=True)
        self.assertEqual(r2["promoted_artifacts"], 1)  # Only vault_store.py is new
        self.assertEqual(r2["promoted_constraints"], 0)  # Duplicate constraint updated in-place
        self.assertEqual(r2["promoted_decisions"], 0)  # Duplicate decision updated in-place

        ledger2 = vault_store.read_ledger(self.vault_dir)
        self.assertEqual(len(ledger2["artifacts"]), 2)
        self.assertEqual(len(ledger2["constraints"]), 1)
        self.assertEqual(len(ledger2["decisions"]), 1)
        self.assertEqual(ledger2["decisions"][0]["rationale_why"], "Updated reason")


if __name__ == "__main__":
    unittest.main()
