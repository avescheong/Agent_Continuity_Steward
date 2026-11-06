"""
SCS_AG_v2 Phase 1.5 End-to-End Acceptance Tests (engine/test_phase1_5_e2e.py)
=============================================================================

Comprehensive acceptance test suite verifying real operator and AI workflows:
- Scenario A: New Project creation (.continuity/ hierarchy, SSOT, baseline seal)
- Scenario B: AI Session Capture (/scs record, SES file, watermark, duplicate prevention, raw immutability)
- Scenario C: Governance Gate (proposals -> staging quarantine -> human custody gate -> /scs approve -> canonical SSOT)
- Scenario D: Multi-Project Isolation (RIE, Hero_Kai, Python_Playground, SCS_AG_v2, fail-closed routing)
- Scenario E: Handover (/scs handover -> AI_HANDOVER_PACKAGE.md, PROJECT_RECOVERY_CARD.md, context reconstruction)
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import vault_store
import transcript_reader
import core_adapter
import scs_cli


class TestPhase15EndToEnd(unittest.TestCase):
    """End-to-End acceptance test suite covering Scenarios A through E."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="scs_e2e_")
        self.workspace_dir = Path(self.temp_dir) / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.app_data_dir = Path(self.temp_dir) / "app_data"
        self.app_data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_conversation(
        self,
        conv_id: str,
        turns: list,
    ) -> Path:
        """Helper to create a synthetic Antigravity transcript."""
        logs_dir = self.app_data_dir / "brain" / conv_id / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        transcript_file = logs_dir / "transcript.jsonl"
        full_file = logs_dir / "transcript_full.jsonl"

        with open(transcript_file, "w", encoding="utf-8") as f_c, open(full_file, "w", encoding="utf-8") as f_f:
            for step_idx, role, content in turns:
                record = {
                    "step_index": step_idx,
                    "source": "USER_EXPLICIT" if role == "USER" else "MODEL",
                    "type": "USER_INPUT" if role == "USER" else "PLANNER_RESPONSE",
                    "status": "DONE",
                    "created_at": "2026-11-05T10:00:00Z",
                    "content": content,
                }
                line = json.dumps(record) + "\n"
                f_c.write(line)
                f_f.write(line)

        return transcript_file

    def _run_cli(self, args: list) -> tuple:
        """Runs the CLI entrypoint capturing stdout and stderr."""
        stdout_buf = StringIO()
        stderr_buf = StringIO()
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            ret = scs_cli.main(args)
        return ret, stdout_buf.getvalue(), stderr_buf.getvalue()

    # -----------------------------------------------------------------------
    # Scenario A: New Project
    # -----------------------------------------------------------------------
    def test_scenario_a_new_project(self):
        """Scenario A — Verify new project creation, .continuity/ structure, and baseline seal."""
        proj_dir = self.workspace_dir / "alpha_project"
        proj_dir.mkdir(parents=True, exist_ok=True)

        ret, out, err = self._run_cli([
            "new", "ALPHA", "Alpha Continuity Project",
            "--path", str(proj_dir),
            "--objective", "Preserve multi-session engineering continuity",
            "--focus", "Implement resilient adapter layer",
            "--next-action", "Author end-to-end integration tests",
        ])
        self.assertEqual(ret, 0, f"scs new failed with error: {err}")
        self.assertIn("[OK] Successfully created .continuity vault", out)

        # 1. Verify directory hierarchy
        vault_dir = proj_dir / ".continuity"
        self.assertTrue(vault_dir.exists())
        self.assertTrue((vault_dir / "canonical").is_dir())
        self.assertTrue((vault_dir / "staging").is_dir())
        self.assertTrue((vault_dir / "evidence").is_dir())
        self.assertTrue((vault_dir / "snapshots").is_dir())
        self.assertTrue((vault_dir / "handover").is_dir())

        # 2. Verify machine SSOT authority
        ledger_file = vault_dir / "canonical" / "ledger.json"
        self.assertTrue(ledger_file.exists())
        ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
        self.assertEqual(ledger["project"]["code"], "ALPHA")
        self.assertEqual(ledger["project"]["name"], "Alpha Continuity Project")
        self.assertEqual(ledger["project"]["objective"], "Preserve multi-session engineering continuity")
        self.assertEqual(ledger["project"]["current_focus"], "Implement resilient adapter layer")

        # 3. Verify deterministic SHA-256 baseline seal
        seal_file = vault_dir / "snapshots" / "LATEST_SEAL"
        self.assertTrue(seal_file.exists())
        seal_sha = seal_file.read_text(encoding="utf-8").strip()
        self.assertEqual(len(seal_sha), 64)
        computed_sha = vault_store.compute_sha256(ledger)
        self.assertEqual(seal_sha, computed_sha)

        is_valid, c_sha, e_sha = vault_store.verify_seal(vault_dir)
        self.assertTrue(is_valid)

        # 4. Verify generated views and workspace rules
        self.assertTrue((vault_dir / "BLUEPRINT.md").exists())
        self.assertTrue((proj_dir / "GEMINI.md").exists())
        self.assertTrue((vault_dir / "canonical" / "DECISIONS.md").exists())
        self.assertTrue((vault_dir / "canonical" / "TASKS.md").exists())

    # -----------------------------------------------------------------------
    # Scenario B: AI Session Capture
    # -----------------------------------------------------------------------
    def test_scenario_b_ai_session_capture(self):
        """Scenario B — Verify AI dialogue capture, immutable SES evidence, and duplicate prevention."""
        proj_dir = self.workspace_dir / "capture_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        vault_dir = vault_store.create_vault(proj_dir, "CAP", "Capture Project")

        conv_id = "test-conv-uuid-1111"
        turns = [
            (1, "USER", "Let's discuss database storage options."),
            (2, "AI", "I recommend SQLite for local storage.\nConstraint: Frontend must remain modular.\nNext action: Setup migration files."),
            (3, "USER", "Yes, proceed with this approach."),
            (4, "AI", "Confirmed. Proceeding with SQLite setup."),
        ]
        self._create_mock_conversation(conv_id, turns)

        # 1. Run /scs record
        ret, out, err = self._run_cli([
            "record", str(proj_dir),
            "--conv-id", conv_id,
            "--app-data", str(self.app_data_dir),
        ])
        self.assertEqual(ret, 0, f"scs record failed: {err}")
        self.assertIn("[OK] Captured", out)
        self.assertIn("turns into raw evidence: SES001_", out)

        # 2. Verify SES file created and immutable
        evidence_dir = vault_dir / "evidence"
        ses_files = list(evidence_dir.rglob("SES001_*.md"))
        self.assertEqual(len(ses_files), 1)
        ses_content = ses_files[0].read_text(encoding="utf-8")
        self.assertIn("test-conv-uuid-1111", ses_content)
        self.assertIn("I recommend SQLite for local storage", ses_content)
        self.assertIn("Yes, proceed with this approach", ses_content)

        # 3. Verify watermark tracking in MANIFEST.json
        manifest = json.loads((evidence_dir / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn(conv_id, manifest["watermarks_by_conversation"])
        self.assertEqual(manifest["watermarks_by_conversation"][conv_id]["last_step_index"], 4)
        self.assertGreaterEqual(len(manifest["sessions"]), 1)
        self.assertEqual(manifest["sessions"][-1]["turn_count"], 4)
        self.assertEqual(len(manifest["watermarks_by_conversation"][conv_id]["last_turn_hash"]), 64)

        # 4. Verify duplicate capture prevention on rerun
        ret2, out2, err2 = self._run_cli([
            "record", str(proj_dir),
            "--conv-id", conv_id,
            "--app-data", str(self.app_data_dir),
        ])
        self.assertEqual(ret2, 0)
        self.assertIn("No new dialogue turns recorded", out2)

        # Verify no second SES file created
        all_ses = list(evidence_dir.rglob("SES*.md"))
        self.assertEqual(len(all_ses), 1)

    # -----------------------------------------------------------------------
    # Scenario C: Governance Gate
    # -----------------------------------------------------------------------
    def test_scenario_c_governance_gate(self):
        """Scenario C — Verify staging quarantine, human custody gate, and canonical promotion."""
        proj_dir = self.workspace_dir / "gov_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        vault_dir = vault_store.create_vault(proj_dir, "GOV", "Governance Project")

        baseline_seal = (vault_dir / "snapshots" / "LATEST_SEAL").read_text(encoding="utf-8").strip()

        conv_id = "test-conv-uuid-2222"
        turns = [
            (1, "AI", "I recommend modular architecture.\nConstraint: No external daemons.\nNext action: Build client interface."),
            (2, "USER", "Yes, proceed with this approach."),
        ]
        self._create_mock_conversation(conv_id, turns)

        # 1. AI Extraction captures into staging
        ret, out, err = self._run_cli([
            "record", str(proj_dir),
            "--conv-id", conv_id,
            "--app-data", str(self.app_data_dir),
        ])
        self.assertEqual(ret, 0)

        # 2. Verify proposals are quarantined in staging
        staging = vault_store.read_staging(vault_dir)
        proposals = staging.get("proposals", [])
        self.assertGreaterEqual(len(proposals), 1, "Candidate proposals should be in staging")
        for p in proposals:
            self.assertEqual(p["status"], "PENDING", "All staged proposals must have PENDING status")

        # 3. Verify CANONICAL SSOT is NOT mutated before human approval
        ledger_before = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertEqual(len(ledger_before.get("decisions", [])), 0, "Canonical ledger must not contain unapproved decisions")
        seal_before = (vault_dir / "snapshots" / "LATEST_SEAL").read_text(encoding="utf-8").strip()
        self.assertEqual(seal_before, baseline_seal, "Seal must remain unchanged before approval")

        # 4. Verify human custody gate via /scs approve --all
        ret_appr, out_appr, err_appr = self._run_cli([
            "approve", "--all",
            "--project", str(proj_dir),
            "--label", "Human operator approval of modular architecture",
        ])
        self.assertEqual(ret_appr, 0, f"Approval failed: {err_appr}")
        self.assertIn("[OK] Ratified and promoted", out_appr)

        # 5. Verify CANONICAL SSOT is now updated with verified decisions and new seal
        ledger_after = vault_store.read_ledger(vault_dir, verify_seal=True)
        self.assertGreaterEqual(len(ledger_after.get("decisions", [])), 1)
        dec = ledger_after["decisions"][0]
        self.assertIn("modular architecture", dec.get("statement", "").lower())

        seal_after = (vault_dir / "snapshots" / "LATEST_SEAL").read_text(encoding="utf-8").strip()
        self.assertNotEqual(seal_after, baseline_seal, "Seal must update after promotion")
        self.assertEqual(seal_after, vault_store.compute_sha256(ledger_after))

        # 6. Verify one-way generated markdown projections are updated
        decisions_md = (vault_dir / "canonical" / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("modular architecture", decisions_md.lower())
        blueprint_md = (vault_dir / "BLUEPRINT.md").read_text(encoding="utf-8")
        self.assertIn("snp-", blueprint_md.lower())

        # 7. Verify tamper detection — direct mutation of canonical/ledger.json breaks seal
        ledger_after["tampered_field"] = "hacked_value"
        with open(vault_dir / "canonical" / "ledger.json", "w", encoding="utf-8") as f:
            json.dump(ledger_after, f)

        is_valid_tampered, _, _ = vault_store.verify_seal(vault_dir)
        self.assertFalse(is_valid_tampered, "Seal verification must fail if ledger is tampered directly")

    # -----------------------------------------------------------------------
    # Scenario D: Multi-Project Isolation
    # -----------------------------------------------------------------------
    def test_scenario_d_multi_project_isolation(self):
        """Scenario D — Verify RIE, Hero_Kai, Python_Playground, SCS_AG_v2 isolation and fail-closed routing."""
        projects = {
            "RIE": self.workspace_dir / "RIE",
            "Hero_Kai": self.workspace_dir / "Hero_Kai",
            "Python_Playground": self.workspace_dir / "Python_Playground",
            "SCS_AG_v2": self.workspace_dir / "SCS_AG_v2",
        }

        created_vaults = {}
        for code, pdir in projects.items():
            pdir.mkdir(parents=True, exist_ok=True)
            v = vault_store.create_vault(pdir, code, f"Project {code}")
            created_vaults[code] = v

        # 1. Verify separate .continuity vaults exist
        for code, pdir in projects.items():
            v_dir = pdir / ".continuity"
            self.assertTrue(v_dir.exists())
            l = json.loads((v_dir / "canonical" / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(l["project"]["code"], code)

        # 2. Test fail-closed routing from parent directory with ambiguous context
        with self.assertRaises(vault_store.AmbiguousProjectError):
            vault_store.resolve_project_vault(
                cwd=self.workspace_dir,
                conversation_id="unbound-session-uuid",
                search_roots=[self.workspace_dir],
            )

        # 3. Test explicit routing succeeds unambiguously
        resolved_hero = vault_store.resolve_project_vault(
            project_arg="HERO_KAI",
            cwd=self.workspace_dir,
            search_roots=[self.workspace_dir],
        )
        self.assertEqual(resolved_hero.resolve(), (projects["Hero_Kai"] / ".continuity").resolve())

        # 4. Test conversation binding: record a conversation into RIE
        conv_rie = "rie-conversation-uuid-9999"
        turns = [
            (1, "USER", "RIE project focus: real-time telemetry."),
            (2, "AI", "Acknowledged. Next action: Setup sensor pipeline."),
        ]
        self._create_mock_conversation(conv_rie, turns)

        ret, out, err = self._run_cli([
            "record", str(projects["RIE"]),
            "--conv-id", conv_rie,
            "--app-data", str(self.app_data_dir),
        ])
        self.assertEqual(ret, 0)

        # 5. Subsequent resolution using conv_rie resolves to RIE automatically
        resolved_auto = vault_store.resolve_project_vault(
            cwd=self.workspace_dir,
            conversation_id=conv_rie,
            search_roots=[self.workspace_dir],
        )
        self.assertEqual(resolved_auto.resolve(), (projects["RIE"] / ".continuity").resolve())

        # 6. Verify zero contamination of other projects
        for other_code in ["Hero_Kai", "Python_Playground", "SCS_AG_v2"]:
            other_manifest_file = created_vaults[other_code] / "evidence" / "MANIFEST.json"
            other_man = json.loads(other_manifest_file.read_text(encoding="utf-8"))
            self.assertNotIn(conv_rie, other_man["watermarks_by_conversation"])

    # -----------------------------------------------------------------------
    # Scenario E: Handover
    # -----------------------------------------------------------------------
    def test_scenario_e_handover(self):
        """Scenario E — Verify /scs handover creates AI_HANDOVER_PACKAGE.md and PROJECT_RECOVERY_CARD.md."""
        proj_dir = self.workspace_dir / "handover_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        vault_dir = vault_store.create_vault(
            proj_dir,
            "RESTORE",
            "Restoration Project",
            objective="Zero context loss cross-AI handover",
            current_focus="Execute Phase 1.5 testing",
            next_action="Run acceptance benchmarks",
        )

        # Add a verified decision and task to ledger
        ledger = vault_store.read_ledger(vault_dir, verify_seal=False)
        ledger["decisions"].append({
            "code": "DEC-RESTORE-001",
            "title": "Use Deterministic SHA-256 Sealing",
            "recommendation": "Hash canonical ledger JSON with sorted keys",
            "human_decision": "Confirmed",
            "session_code": "SES001",
            "timestamp": "2026-11-05T12:00:00Z",
            "is_active": True,
        })
        ledger["tasks"].append({
            "code": "TSK-001",
            "statement": "Run full test regression",
            "status": "COMPLETED",
            "is_completed": True,
            "session_code": "SES001",
        })
        ledger["tasks"].append({
            "code": "TSK-002",
            "statement": "Deliver Phase 1.5 verification report",
            "status": "PENDING",
            "is_completed": False,
            "session_code": "SES001",
        })
        vault_store.write_ledger(vault_dir, ledger, label="Add confirmed decisions and tasks")

        # Run /scs handover
        ret, out, err = self._run_cli(["handover", str(proj_dir)])
        self.assertEqual(ret, 0, f"scs handover failed: {err}")
        self.assertIn("[OK] Generated Master AI Continuity Restoration Package", out)

        handover_dir = vault_dir / "handover"
        package_files = list(handover_dir.glob("*AI_HANDOVER_PACKAGE.md"))
        recovery_files = list(handover_dir.glob("*PROJECT_RECOVERY_CARD.md"))

        self.assertEqual(len(package_files), 1)
        self.assertEqual(len(recovery_files), 1)

        package_file = package_files[0]
        recovery_file = recovery_files[0]

        pkg_text = package_file.read_text(encoding="utf-8")
        rec_text = recovery_file.read_text(encoding="utf-8")

        # Verify package contents for incoming AI
        self.assertIn("RESTORE", pkg_text)
        self.assertIn("Use Deterministic SHA-256 Sealing", pkg_text)
        self.assertIn("Execute Phase 1.5 testing", pkg_text)
        self.assertIn("Deliver Phase 1.5 verification report", pkg_text)
        self.assertIn("scs-handover/1.0", pkg_text)

        # Verify recovery card is concise (< 120 lines)
        self.assertIn("Project Recovery Card", rec_text)
        self.assertIn("Run acceptance benchmarks", rec_text)
        self.assertLess(len(rec_text.splitlines()), 120)

    # -----------------------------------------------------------------------
    # Task 2 Verification: Automatic Context Injection
    # -----------------------------------------------------------------------
    def test_auto_detect_conversation_id(self):
        """Verify automatic conversation ID discovery from brain directory."""
        # Create two conversation directories with different timestamps
        self._create_mock_conversation("older-conv-id", [(1, "USER", "Old turn")])
        self._create_mock_conversation("newer-conv-id", [(1, "USER", "New turn")])

        # Touch newer transcript to ensure higher mtime
        newer_file = self.app_data_dir / "brain" / "newer-conv-id" / ".system_generated" / "logs" / "transcript.jsonl"
        os.utime(newer_file, (1800000000, 1800000000))

        detected = scs_cli.auto_detect_conversation_id(app_data_dir=self.app_data_dir)
        self.assertEqual(detected, "newer-conv-id")

        # Verify environment variable override takes precedence
        with patch.dict(os.environ, {"CONVERSATION_ID": "env-override-uuid"}):
            self.assertEqual(scs_cli.auto_detect_conversation_id(self.app_data_dir), "env-override-uuid")


if __name__ == "__main__":
    unittest.main()
