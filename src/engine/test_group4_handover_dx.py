"""
Unit and Integration Tests for Phase 14 Group 4 (Handover Synthesis & Density Controls)
========================================================================================

Covers:
1. FDB-101-011: Handover output ergonomics
   - scs handover PROJECT --stdout / --print: Print generated package directly to stdout.
   - scs handover PROJECT --card-only: Print only Fast Recovery Card directly to stdout.
   - Clean stdout: Informational banner/logs must not pollute stdout stream.
   - Backward compatibility: scs handover PROJECT without flags creates files on disk.

2. FDB-101-002: Handover depth profiles
   - scs handover PROJECT --profile compact: Minimal restart context (~300 words).
   - scs handover PROJECT --profile standard: Default baseline (~1,000 words).
   - scs handover PROJECT --profile deep: Extended forensic audit package (~2,000+ words).
   - Author, approver, evidence quotes, completed task verification, and chapter histories.
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


class TestGroup4HandoverDx(unittest.TestCase):
    """Test suite verifying Group 4 Handover ergonomics and depth profiles."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="scs_group4_test_"))
        self.old_cwd = Path.cwd()
        os.chdir(self.test_dir)

        # Create a populated project for rich handover generation
        self.proj_dir = self.test_dir / "RichHandoverProj"
        scs_cli.main(["new", "RHO", "Rich Handover Project", "--path", str(self.proj_dir)])
        self.vault_path = self.proj_dir / ".continuity"

        # Populate ledger with decisions, constraints, rejected options, tasks, and artifacts
        ledger = vault_store.read_ledger(self.vault_path, verify_seal=True)
        ledger["project"]["objective"] = "Validate multi-profile handover generation and stdout piping"
        ledger["project"]["current_focus"] = "Verifying Group 4 density profiles"
        ledger["project"]["next_action"] = "Execute automated conformance test suite"

        ledger["decisions"].append({
            "code": "DEC-001",
            "statement": "Adopt Dual-Layer Verification Architecture",
            "rationale_why": "Guarantees zero-drift integrity across sessions",
            "impact_scope": "Core engine and test pipelines",
            "author": "lead-architect",
            "approved_by": "human-operator",
            "source_excerpt": "We must enforce a dual-layer verification architecture.",
            "is_active": True,
        })
        ledger["decisions"].append({
            "code": "DEC-002",
            "statement": "Legacy SQLite Storage Backend",
            "rationale_why": "Deprecated in favor of transparent flat-file JSON",
            "impact_scope": "Persistence layer",
            "author": "junior-agent",
            "approved_by": "human-operator",
            "is_active": False,  # Superseded decision
        })

        ledger["constraints"].append({
            "code": "CON-001",
            "statement": "Zero external runtime dependencies permitted (Python stdlib only)",
            "rationale_why": "Ensure absolute air-gapped portability and instant bootstrap",
            "is_active": True,
        })

        ledger["rejected_options"].append({
            "code": "REJ-001",
            "statement": "Use third-party cryptography packages (e.g. pycryptodome)",
            "rationale_why": "Violates zero external runtime dependency constraint",
            "impact_scope": "Hashing and seal calculation",
            "source_excerpt": "Do not install pycryptodome; hashlib in stdlib is sufficient.",
            "is_active": True,
        })

        ledger["tasks"].append({
            "code": "TSK-001",
            "title": "Implement CLI argument parser for depth profiles",
            "status": "COMPLETED",
            "priority": "HIGH",
            "why_it_matters": "Enables user-selectable handover density",
            "completed_evidence": "scs_cli.py supports --profile flag with choices",
            "completed_by_verification": True,
            "completed_at": "2026-11-06T20:00:00Z",
        })
        ledger["tasks"].append({
            "code": "TSK-002",
            "title": "Verify stdout piping without banner contamination",
            "status": "IN_PROGRESS",
            "priority": "HIGH",
            "why_it_matters": "Allows clean piping to clipboard or AI prompt context",
            "blocker_reason": "",
        })

        # Add physical artifact
        sample_doc = self.proj_dir / "ARCHITECTURE.md"
        sample_doc.write_text("# Project Architecture\nAll components strictly modular.", encoding="utf-8")
        ledger["artifacts"].append({
            "name": "ARCHITECTURE.md",
            "relative_path": "ARCHITECTURE.md",
            "custody_state": "PRESENT",
            "observed_sha256": "abcdef1234567890",
        })

        vault_store.write_ledger(self.vault_path, ledger, label="Populated rich ledger")

        # Create a mock chapter archive in MANIFEST.json
        paths = vault_store.get_vault_paths(self.vault_path)
        manifest_path = paths["manifest_json"]
        archives_dir = paths["archives_dir"]
        archives_dir.mkdir(parents=True, exist_ok=True)
        chapter_file = archives_dir / "ARCH-001.md"
        chapter_file.write_text(
            "# Chapter 1: Genesis & Bootstrap\nInitial architecture established with zero external dependencies.",
            encoding="utf-8",
        )
        manifest = {
            "archives": [
                {
                    "archive_code": "ARCH-001",
                    "file_name": "ARCH-001.md",
                    "created_at": "2026-11-06T18:00:00Z",
                }
            ],
            "sessions": ["session-001", "session-002"],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. FDB-101-011: Handover Output Ergonomics (--stdout, --print, --card-only)
    # -------------------------------------------------------------------------

    def test_handover_default_file_generation_backward_compat(self):
        """FDB-101-011: Default scs handover PROJECT generates files on disk and outputs summary."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir)])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Generated Master AI Continuity Restoration Package", output)
        self.assertIn("RHO_AI_HANDOVER_PACKAGE.md", output)
        self.assertIn("Profile:       standard", output)

        ho_file = self.vault_path / "handover" / "RHO_AI_HANDOVER_PACKAGE.md"
        rec_file = self.vault_path / "handover" / "RHO_PROJECT_RECOVERY_CARD.md"
        self.assertTrue(ho_file.exists())
        self.assertTrue(rec_file.exists())

    def test_handover_stdout_flag_outputs_content_cleanly(self):
        """FDB-101-011: scs handover PROJECT --stdout prints full package with zero banner noise."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir), "--stdout"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()

        # Must contain package content
        self.assertIn("AI HANDOVER PACKAGE", output)
        self.assertIn("Master AI Continuity Restoration Package", output)
        self.assertIn("Rich Handover Project", output)
        self.assertIn("Adopt Dual-Layer Verification Architecture", output)
        self.assertIn("scs-handover/1.0", output)

        # Must NOT contain CLI banner or logging messages
        self.assertNotIn("Generated Master AI Continuity Restoration Package", output)
        self.assertNotIn("[OK]", output)

    def test_handover_print_flag_alias(self):
        """FDB-101-011: scs handover PROJECT --print is supported as an alias for --stdout."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir), "--print"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("AI HANDOVER PACKAGE", output)
        self.assertIn("Master AI Continuity Restoration Package", output)
        self.assertNotIn("[OK] Generated Master AI Continuity Restoration Package", output)

    def test_handover_card_only_flag_outputs_recovery_card_cleanly(self):
        """FDB-101-011: scs handover PROJECT --card-only outputs only fast recovery card with zero banners."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir), "--card-only"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()

        # Must contain Fast Recovery Card content
        self.assertIn("Project Recovery Card", output)
        self.assertIn("Fast Project Recovery Card", output)
        self.assertIn("Execute automated conformance test suite", output)

        # Must NOT contain the full handover package or status banners
        self.assertNotIn("Master AI Continuity Restoration Package", output)
        self.assertNotIn("[OK] Generated Master AI Continuity Restoration Package", output)

    def test_handover_flag_project_dual_syntax_with_stdout(self):
        """FDB-101-012 & FDB-101-011: scs handover --project <DIR> --stdout works consistently."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", "--project", str(self.proj_dir), "--stdout"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()
        self.assertIn("AI HANDOVER PACKAGE", output)
        self.assertIn("Master AI Continuity Restoration Package", output)
        self.assertNotIn("[OK]", output)

    # -------------------------------------------------------------------------
    # 2. FDB-101-002: Handover Depth Profiles (compact, standard, deep)
    # -------------------------------------------------------------------------

    def test_profile_compact_density_and_content(self):
        """FDB-101-002: --profile compact produces a high-density restart package (~300 words)."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir), "--profile", "compact", "--stdout"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()

        # Check protocol and profile identification
        self.assertIn("AI REHYDRATION BRIEFING (COMPACT)", output)
        self.assertIn("profile: `compact`", output)

        # Check essential content presence
        self.assertIn("Operational Focus & Immediate Action", output)
        self.assertIn("Active Governance Constraints & Boundaries", output)
        self.assertIn("Essential Architectural Decisions", output)
        self.assertIn("Immediate Pending Tasks", output)
        self.assertIn("Authoritative Do-Not-Repeat Registry", output)
        self.assertIn("Execute automated conformance test suite", output)
        self.assertIn("Zero external runtime dependencies", output)
        self.assertIn("Adopt Dual-Layer Verification Architecture", output)
        self.assertIn("Use third-party cryptography packages", output)

        # Compact profile should exclude heavy historical chapters or artifact manifest tables
        self.assertNotIn("Artifact Physical Custody Manifest", output)
        self.assertNotIn("Project Evolution & Continuity Chapter History", output)

        # Word count check: compact package should be dense (under 600 words)
        word_count = len(output.split())
        self.assertLess(word_count, 600, f"Compact package word count was {word_count}, expected high density < 600 words")

    def test_profile_standard_baseline_compatibility(self):
        """FDB-101-002: --profile standard produces current v1.0.1 certified baseline."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir), "--profile", "standard", "--stdout"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()

        # Check standard sections
        self.assertIn("AI HANDOVER PACKAGE", output)
        self.assertIn("Master AI Continuity Restoration Package", output)
        self.assertIn("Architecture Overview", output)
        self.assertIn("Decision History (What Was Decided & Why)", output)
        self.assertIn("Immediate Next Action", output)
        self.assertIn("Artifact Custody Registry", output)

    def test_profile_deep_forensic_completeness(self):
        """FDB-101-002: --profile deep produces exhaustive forensic audit package."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            rc = scs_cli.main(["handover", str(self.proj_dir), "--profile", "deep", "--stdout"])

        self.assertEqual(rc, 0)
        output = stdout_buf.getvalue()

        # Check deep profile indicators
        self.assertIn("MASTER AI HANDOVER & AUDIT PACKAGE (DEEP)", output)
        self.assertIn("profile: `deep`", output)
        self.assertIn("EXHAUSTIVE AUDIT PURPOSE", output)

        # 1. Forensic attribution & evidence quotes
        self.assertIn("Detailed Decision History & Forensic Attribution", output)
        self.assertIn("- **Author / Approved By:** lead-architect / human-operator", output)
        self.assertIn("- **Forensic Source Evidence:** \"We must enforce a dual-layer verification architecture.\"", output)

        # 2. Superseded decisions
        self.assertIn("Superseded & Retired Decisions", output)
        self.assertIn("Legacy SQLite Storage Backend", output)

        # 3. Rejected options with failure analysis & quotes
        self.assertIn("- **Evidence Quote:** \"Do not install pycryptodome; hashlib in stdlib is sufficient.\"", output)
        self.assertIn("- **Scope Evaluated:** Hashing and seal calculation", output)

        # 4. Completed task verification logs
        self.assertIn("Verified Completed Tasks", output)
        self.assertIn("[VERIFIED ON DISK]", output)
        self.assertIn("- **Why It Mattered:** Enables user-selectable handover density", output)
        self.assertIn("- **Verification Evidence:** scs_cli.py supports --profile flag with choices", output)

        # 5. Chapter archive history & artifact manifest with SHA-256
        self.assertIn("Continuity Chapter Archives & Historical Evolution", output)
        self.assertIn("Chapter `ARCH-001`", output)
        self.assertIn("Artifact Physical Custody Manifest", output)
        self.assertIn("ARCHITECTURE.md", output)
        self.assertIn("SHA-256", output)

        # Deep package should be substantially richer than compact
        word_count = len(output.split())
        self.assertGreater(word_count, 400, f"Deep package word count was {word_count}")

    # -------------------------------------------------------------------------
    # 3. Programmatic API and Error Handling
    # -------------------------------------------------------------------------

    def test_vault_store_generate_handover_package_api(self):
        """Verify vault_store.generate_handover_package supports all profiles programmatically."""
        for prof in ["compact", "standard", "deep"]:
            res = vault_store.generate_handover_package(self.vault_path, profile=prof)
            self.assertEqual(res["protocol_version"], "scs-handover/1.0")
            self.assertEqual(res["profile"], prof)
            self.assertTrue(Path(res["handover_file"]).exists())
            self.assertTrue(Path(res["recovery_file"]).exists())
            self.assertIn("checksum_sha256", res)

    def test_core_adapter_unknown_profile_fallback(self):
        """Verify core_adapter.generate_handover_context falls back safely to standard profile."""
        ledger = vault_store.read_ledger(self.vault_path, verify_seal=True)
        res = core_adapter.generate_handover_context(
            project=ledger["project"],
            snapshot={"snapshot_code": "SNP-TEST", "checksum_sha256": "0" * 64, "state_json": "{}"},
            decisions=[],
            tasks=[],
            artifacts=[],
            profile="nonexistent_profile",
        )
        self.assertEqual(res["profile"], "nonexistent_profile")
        self.assertIn("Master AI Continuity Restoration Package", res["handover_content"])

    def test_cli_invalid_profile_rejected(self):
        """Verify argparse rejects unsupported profile values with error exit code."""
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            with self.assertRaises(SystemExit) as cm:
                scs_cli.main(["handover", str(self.proj_dir), "--profile", "ultra_deep"])
            self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
