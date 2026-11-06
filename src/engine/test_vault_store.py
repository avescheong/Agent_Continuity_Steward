"""
Unit Test Suite for SCS_AG_v2 Vault Store & Sealer
==================================================

Covers all Phase 1.2 acceptance requirements:
1. Vault Creation Test (.continuity/ structure, BLUEPRINT.md, directories, gitignore, initial seal)
2. Ledger Write/Read Test (JSON machine authority, deterministic formatting)
3. Markdown Rendering Test (One-way projections: BLUEPRINT.md, DECISIONS.md, REJECTED_OPTIONS.md, TASKS.md, ARTIFACTS.md)
4. Seal Verification Test (SHA-256 match vs tamper detection)
5. Rollback Test (Deterministic rollback from snapshot, LATEST_SEAL restoration, view updates)
6. Project Isolation Test (Multi-project independence, zero cross-contamination, fail-closed discovery)
7. Staging & Human Custody Gate Test (Pending quarantine, selective/all promotion, rejection memory)
8. 10-Session Archive Preparation Test (Non-destructive backbone, additive MD archives, manifest updates)
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

import vault_store


class TestVaultStore(unittest.TestCase):
    def setUp(self):
        # Create a fresh temporary directory for each test
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -----------------------------------------------------------------------
    # 1. Vault Creation Test
    # -----------------------------------------------------------------------

    def test_01_vault_creation(self):
        proj_dir = self.base_dir / "TestProject"
        vault_dir = vault_store.create_vault(
            project_dir=proj_dir,
            project_code="TEST_PROJ",
            project_name="Test Project",
            objective="Deliver verified continuity engine",
            current_focus="Phase 1.2 vault testing",
            next_action="Run test suite",
        )

        paths = vault_store.get_vault_paths(vault_dir)

        # Directory structure checks
        self.assertTrue(paths["vault_dir"].exists())
        self.assertTrue(paths["canonical_dir"].exists())
        self.assertTrue(paths["staging_dir"].exists())
        self.assertTrue(paths["snapshots_dir"].exists())
        self.assertTrue(paths["raw_sessions_dir"].exists())
        self.assertTrue(paths["archives_dir"].exists())
        self.assertTrue(paths["imports_dir"].exists())
        self.assertTrue(paths["handover_dir"].exists())

        # File checks
        self.assertTrue(paths["gitignore"].exists())
        self.assertTrue(paths["blueprint_md"].exists())
        self.assertTrue(paths["gemini_md"].exists())
        self.assertTrue(paths["ledger_json"].exists())
        self.assertTrue(paths["decisions_md"].exists())
        self.assertTrue(paths["rejected_options_md"].exists())
        self.assertTrue(paths["tasks_md"].exists())
        self.assertTrue(paths["artifacts_md"].exists())
        self.assertTrue(paths["pending_proposals_json"].exists())
        self.assertTrue(paths["review_draft_md"].exists())
        self.assertTrue(paths["manifest_json"].exists())
        self.assertTrue(paths["latest_seal"].exists())

        # Baseline snapshot exists
        snapshots = vault_store.list_snapshots(vault_dir)
        self.assertEqual(len(snapshots), 1)
        self.assertTrue(snapshots[0]["snapshot_code"].endswith("-001"))

        # Verify initial seal
        is_valid, computed_sha, expected_sha = vault_store.verify_seal(vault_dir)
        self.assertTrue(is_valid)
        self.assertEqual(computed_sha, expected_sha)
        self.assertEqual(len(computed_sha), 64)

    # -----------------------------------------------------------------------
    # 2. Ledger Write & Read Test
    # -----------------------------------------------------------------------

    def test_02_ledger_write_read(self):
        proj_dir = self.base_dir / "RIE"
        vault_dir = vault_store.create_vault(proj_dir, "RIE", "RIE Core")

        # Read initial ledger
        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(ledger["project"]["code"], "RIE")
        self.assertEqual(len(ledger["decisions"]), 0)

        # Modify ledger in-memory
        ledger["decisions"].append({
            "id": "dec_001",
            "code": "DEC-001",
            "record_kind": "DECISION",
            "statement": "Use pure file-first architecture",
            "rationale_why": "Eliminates daemon/network dependencies",
            "impact_scope": "Storage layer",
            "source_excerpt": "Human agreed",
            "is_active": True,
            "created_at": vault_store.utc_now_iso(),
            "updated_at": vault_store.utc_now_iso(),
        })

        snap_code, seal_hash = vault_store.write_ledger(
            vault_dir,
            ledger,
            label="Added DEC-001",
            create_snapshot=True,
        )

        self.assertTrue(snap_code.endswith("-002"))
        self.assertEqual(len(seal_hash), 64)

        # Read back with verification
        updated = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(updated["decisions"]), 1)
        self.assertEqual(updated["decisions"][0]["statement"], "Use pure file-first architecture")

        # Check that 2 snapshots now exist
        snaps = vault_store.list_snapshots(vault_dir)
        self.assertEqual(len(snaps), 2)

    # -----------------------------------------------------------------------
    # 3. Markdown Rendering Test
    # -----------------------------------------------------------------------

    def test_03_markdown_rendering(self):
        proj_dir = self.base_dir / "HeroKai"
        vault_dir = vault_store.create_vault(proj_dir, "HERO_KAI", "Hero Kai")

        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        ledger["decisions"].append({
            "code": "DEC-001",
            "statement": "Adopt WebGL renderer",
            "rationale_why": "60fps requirement",
            "is_active": True,
        })
        ledger["constraints"].append({
            "code": "CON-001",
            "statement": "Zero external cloud telemetry",
            "rationale_why": "Strict offline policy",
            "is_active": True,
        })
        ledger["rejected_options"].append({
            "code": "REJ-001",
            "statement": "Three.js heavy bundle",
            "rationale_why": "Exceeds 50MB budget",
            "is_active": True,
        })
        ledger["tasks"].append({
            "code": "TSK-001",
            "title": "Set up WebGL context",
            "status": "COMPLETED",
            "why_it_matters": "Rendering foundation",
        })
        ledger["tasks"].append({
            "code": "TSK-002",
            "title": "Shader pipeline integration",
            "status": "IN_PROGRESS",
            "why_it_matters": "Visual effects",
        })

        vault_store.write_ledger(vault_dir, ledger, label="Populated core entries")

        paths = vault_store.get_vault_paths(vault_dir)

        # 1. BLUEPRINT.md
        bp_content = paths["blueprint_md"].read_text(encoding="utf-8")
        self.assertIn("Hero Kai (HERO_KAI)", bp_content)
        self.assertIn("CON-001", bp_content)
        self.assertIn("Zero external cloud telemetry", bp_content)
        self.assertIn("REJ-001", bp_content)
        self.assertIn("Three.js heavy bundle", bp_content)
        self.assertIn("TSK-002", bp_content)

        # 2. DECISIONS.md
        dec_content = paths["decisions_md"].read_text(encoding="utf-8")
        self.assertIn("DEC-001", dec_content)
        self.assertIn("Adopt WebGL renderer", dec_content)
        self.assertIn("60fps requirement", dec_content)
        self.assertIn("CON-001", dec_content)

        # 3. REJECTED_OPTIONS.md
        rej_content = paths["rejected_options_md"].read_text(encoding="utf-8")
        self.assertIn("REJ-001", rej_content)
        self.assertIn("Three.js heavy bundle", rej_content)
        self.assertIn("Exceeds 50MB budget", rej_content)

        # 4. TASKS.md
        tasks_content = paths["tasks_md"].read_text(encoding="utf-8")
        self.assertIn("[x] **[TSK-001]**", tasks_content)
        self.assertIn("[ ] **[TSK-002]**", tasks_content)
        self.assertIn("50%", tasks_content)  # 1 of 2 completed

    # -----------------------------------------------------------------------
    # 4. Seal Verification & Tamper Detection Test
    # -----------------------------------------------------------------------

    def test_04_seal_verification_and_tamper(self):
        proj_dir = self.base_dir / "TGL"
        vault_dir = vault_store.create_vault(proj_dir, "TGL", "TGL Game")
        paths = vault_store.get_vault_paths(vault_dir)

        # Initial seal is valid
        is_valid, comp, exp = vault_store.verify_seal(vault_dir)
        self.assertTrue(is_valid)

        # Simulate unauthorized manual tampering of ledger.json
        raw_json = json.loads(paths["ledger_json"].read_text(encoding="utf-8"))
        raw_json["project"]["name"] = "HACKED_NAME"
        paths["ledger_json"].write_text(json.dumps(raw_json), encoding="utf-8")

        # Verification must fail
        is_valid_after, comp_after, exp_after = vault_store.verify_seal(vault_dir)
        self.assertFalse(is_valid_after)
        self.assertNotEqual(comp_after, exp_after)

        # read_ledger with verify_seal must raise SealTamperError
        with self.assertRaises(vault_store.SealTamperError):
            vault_store.read_ledger(vault_dir, verify_seal=True)

    # -----------------------------------------------------------------------
    # 5. Rollback Test
    # -----------------------------------------------------------------------

    def test_05_rollback(self):
        proj_dir = self.base_dir / "Playground"
        vault_dir = vault_store.create_vault(proj_dir, "PLAY", "Playground")
        paths = vault_store.get_vault_paths(vault_dir)

        # Initial baseline snapshot
        baseline_snaps = vault_store.list_snapshots(vault_dir)
        initial_snap_code = baseline_snaps[0]["snapshot_code"]

        # Add a bad change in a new snapshot
        ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        ledger["decisions"].append({
            "code": "DEC-999",
            "statement": "Accidental bad decision",
            "rationale_why": "Mistake",
            "is_active": True,
        })
        bad_snap, _ = vault_store.write_ledger(vault_dir, ledger, label="Bad commit")

        # Check bad decision is present
        ledger_bad = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger_bad["decisions"]), 1)

        # Perform rollback to initial snapshot
        res = vault_store.rollback_to_snapshot(vault_dir, initial_snap_code)
        self.assertEqual(res["status"], "RESTORED")
        self.assertEqual(res["restored_snapshot_code"], initial_snap_code)

        # Verify restored ledger
        restored_ledger = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(restored_ledger["decisions"]), 0)

        # Verify seal is valid again
        is_valid, _, _ = vault_store.verify_seal(vault_dir)
        self.assertTrue(is_valid)

        # Verify Markdown views were regenerated cleanly
        dec_text = paths["decisions_md"].read_text(encoding="utf-8")
        self.assertNotIn("Accidental bad decision", dec_text)

    # -----------------------------------------------------------------------
    # 6. Project Isolation & Fail-Closed Discovery Test
    # -----------------------------------------------------------------------

    def test_06_project_isolation_and_discovery(self):
        # Create 3 independent projects in workspace
        rie_dir = self.base_dir / "RIE"
        hero_dir = self.base_dir / "Hero_Kai"
        scs_dir = self.base_dir / "SCS_AG_v2"

        vault_store.create_vault(rie_dir, "RIE", "RIE Project")
        vault_store.create_vault(hero_dir, "HERO_KAI", "Hero Kai Project")
        vault_store.create_vault(scs_dir, "SCS2", "SCS v2 Project")

        # Discover all vaults in workspace
        discovered = vault_store.discover_vaults([self.base_dir])
        self.assertEqual(len(discovered), 3)
        codes = {d["project_code"] for d in discovered}
        self.assertEqual(codes, {"RIE", "HERO_KAI", "SCS2"})

        # Priority 1: Explicit project argument resolution
        res_rie = vault_store.resolve_project_vault(project_arg="RIE", search_roots=[self.base_dir])
        self.assertEqual(res_rie, rie_dir / ".continuity")

        res_hero = vault_store.resolve_project_vault(project_arg="HERO_KAI", search_roots=[self.base_dir])
        self.assertEqual(res_hero, hero_dir / ".continuity")

        # Priority 2: Inside single project directory (CWD resolution)
        res_cwd = vault_store.resolve_project_vault(cwd=rie_dir, search_roots=[rie_dir])
        self.assertEqual(res_cwd, rie_dir / ".continuity")

        # Priority 3: Conversation binding resolution
        # Simulate conversation bound in Hero Kai's MANIFEST.json
        hero_manifest_file = hero_dir / ".continuity" / "evidence" / "MANIFEST.json"
        man = json.loads(hero_manifest_file.read_text(encoding="utf-8"))
        conv_id = "test-conv-uuid-1234"
        man["watermarks_by_conversation"][conv_id] = {
            "last_step_index": 10,
            "last_session_id": "SES001",
        }
        hero_manifest_file.write_text(json.dumps(man), encoding="utf-8")

        res_conv = vault_store.resolve_project_vault(
            conversation_id=conv_id,
            search_roots=[self.base_dir],
        )
        self.assertEqual(res_conv, hero_dir / ".continuity")

        # Priority 4: Fail closed when ambiguous
        # Running from base_dir with no project arg, no conversation binding
        with self.assertRaises(vault_store.AmbiguousProjectError) as ctx:
            vault_store.resolve_project_vault(cwd=self.base_dir, search_roots=[self.base_dir])
        self.assertEqual(len(ctx.exception.candidate_vaults), 3)

    # -----------------------------------------------------------------------
    # 7. Staging Layer & Human Custody Promotion Test
    # -----------------------------------------------------------------------

    def test_07_staging_and_human_approval(self):
        proj_dir = self.base_dir / "StagingProj"
        vault_dir = vault_store.create_vault(proj_dir, "STG", "Staging Project")
        paths = vault_store.get_vault_paths(vault_dir)

        # 1. Append proposals to staging
        proposals = [
            {
                "proposal_type": "DECISION",
                "statement": "Use Ed25519 signing",
                "why": "High security, small signature size",
                "evidence_quote": "Human: Yes, proceed with Ed25519",
            },
            {
                "proposal_type": "CONSTRAINT",
                "statement": "Never allow unencrypted tokens",
                "why": "Security policy",
            },
            {
                "proposal_type": "TASK",
                "statement": "Implement Ed25519 key generator",
                "priority": "HIGH",
                "why": "Prerequisite for auth",
            },
            {
                "proposal_type": "DECISION",
                "statement": "Use RSA 2048",
                "why": "Legacy compatibility",
            },
        ]

        count = vault_store.append_staging_proposals(vault_dir, proposals)
        self.assertEqual(count, 4)

        # Check REVIEW_DRAFT.md generated
        draft = paths["review_draft_md"].read_text(encoding="utf-8")
        self.assertIn("Ed25519 signing", draft)
        self.assertIn("Never allow unencrypted tokens", draft)
        self.assertIn("[P01]", draft)
        self.assertIn("[P04]", draft)

        # Canonical ledger MUST remain untouched (quarantine gate)
        ledger_before = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger_before["decisions"]), 0)

        # 2. Selectively approve P01, P02, P03
        promo_res = vault_store.promote_proposals(
            vault_dir,
            proposal_ids=["P01", "P02", "P03"],
            label="Approved core cryptography architecture",
        )
        self.assertEqual(promo_res["promoted_count"], 3)
        self.assertEqual(promo_res["promoted_decisions"], 1)
        self.assertEqual(promo_res["promoted_constraints"], 1)
        self.assertEqual(promo_res["promoted_tasks"], 1)
        self.assertEqual(promo_res["remaining_proposals"], 1)

        # Canonical ledger updated & sealed
        ledger_after = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger_after["decisions"]), 1)
        self.assertEqual(ledger_after["decisions"][0]["statement"], "Use Ed25519 signing")
        self.assertEqual(len(ledger_after["constraints"]), 1)
        self.assertEqual(len(ledger_after["tasks"]), 1)

        # 3. Reject P04 and record to REJECTED_OPTIONS
        rej_res = vault_store.reject_proposal(
            vault_dir,
            proposal_id="P04",
            why_rejected="RSA 2048 is too slow and deprecated",
            record_as_do_not_repeat=True,
        )
        self.assertEqual(rej_res["status"], "RECORDED_REJECTED")

        # Staging is now empty
        st_after = vault_store.read_staging(vault_dir)
        self.assertEqual(len(st_after["proposals"]), 0)

        # Canonical REJECTED_OPTIONS contains RSA 2048
        ledger_final = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger_final["rejected_options"]), 1)
        self.assertIn("RSA 2048", ledger_final["rejected_options"][0]["statement"])
        self.assertIn("too slow", ledger_final["rejected_options"][0]["rationale_why"])

        # Check REJECTED_OPTIONS.md view
        rej_md = paths["rejected_options_md"].read_text(encoding="utf-8")
        self.assertIn("RSA 2048", rej_md)

    # -----------------------------------------------------------------------
    # 8. 10-Session Archive Non-Destructive Preparation Test
    # -----------------------------------------------------------------------

    def test_08_10_session_archive_preparation(self):
        proj_dir = self.base_dir / "ArchiveProj"
        vault_dir = vault_store.create_vault(proj_dir, "ARCH", "Archive Project")
        paths = vault_store.get_vault_paths(vault_dir)

        # Simulate 12 incremental session files
        manifest = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
        for i in range(1, 13):
            ses_id = f"SES{i:03d}"
            ses_file = paths["raw_sessions_dir"] / f"{ses_id}_20261105_1200.md"
            content = (
                f"---\nsession_id: {ses_id}\n---\n"
                f"Human: Session {i} discussion.\n"
                f"AI: Session {i} response with decision {i}."
            )
            ses_file.write_text(content, encoding="utf-8")
            manifest["sessions"].append({
                "session_id": ses_id,
                "file_path": f"evidence/raw_sessions/{ses_file.name}",
                "captured_at": vault_store.utc_now_iso(),
                "turn_count": 2,
                "sha256": vault_store.compute_sha256(content),
                "consolidated_in": None,
            })

        paths["manifest_json"].write_text(json.dumps(manifest), encoding="utf-8")

        # Prepare archive (should batch exactly 10 sessions)
        arch_file = vault_store.prepare_10_session_archive(vault_dir, archive_title="First 10 sessions")
        self.assertIsNotNone(arch_file)
        self.assertTrue(Path(arch_file).exists())
        self.assertIn("MD001_", Path(arch_file).name)

        # Non-Destructive Backbone Rule: ALL 12 raw session files still exist
        raw_files = list(paths["raw_sessions_dir"].glob("SES*.md"))
        self.assertEqual(len(raw_files), 12)

        # Manifest check: exactly 10 sessions marked consolidated in MD001
        updated_man = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
        consolidated = [s for s in updated_man["sessions"] if s.get("consolidated_in") == "MD001"]
        self.assertEqual(len(consolidated), 10)
        remaining = [s for s in updated_man["sessions"] if not s.get("consolidated_in")]
        self.assertEqual(len(remaining), 2)

        # Archives ledger has MD001 entry
        self.assertEqual(len(updated_man["archives"]), 1)
        self.assertEqual(updated_man["archives"][0]["archive_code"], "MD001")


if __name__ == "__main__":
    unittest.main()
