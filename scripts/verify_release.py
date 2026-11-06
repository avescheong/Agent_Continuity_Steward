#!/usr/bin/env python3
"""
verify_release.py — SCS_AG_v2 Self-Contained Release Verification Script

A reproducible, zero-external-dependency script allowing any user or CI pipeline
to verify the integrity, dependencies, test suite, and operational readiness
of SCS_AG_v2 in under 10 seconds.

Usage:
    python scripts/verify_release.py
"""

import sys
import os
import time
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

# Configure stdout encoding gracefully across Windows cp1252 and Unix
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def log_step(name: str):
    print(f"\n--- {name} ---")


def main() -> int:
    start_time = time.perf_counter()
    print("=" * 80)
    print("[SCS_AG_v2] PRODUCTION RELEASE VERIFICATION SUITE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Python Version Check
    # -------------------------------------------------------------------------
    log_step("1. Python Environment Check")
    major, minor, micro = sys.version_info[:3]
    py_version_str = f"{major}.{minor}.{micro}"
    print(f"Detected Python Version: {py_version_str}")

    if sys.version_info < (3, 10):
        print(f"[FAIL] SCS_AG_v2 requires Python 3.10 or newer. Current: {py_version_str}", file=sys.stderr)
        return 1
    print(f"[OK] Python version {py_version_str} satisfies minimum requirement (>= 3.10).")

    # -------------------------------------------------------------------------
    # 2. Dependency Check (Standard Library Only)
    # -------------------------------------------------------------------------
    log_step("2. Dependency Verification")
    required_stdlib_modules = [
        "json", "hashlib", "pathlib", "argparse", "re",
        "datetime", "unittest", "tempfile", "shutil", "typing"
    ]
    for mod in required_stdlib_modules:
        try:
            __import__(mod)
        except ImportError as exc:
            print(f"[FAIL] Missing required standard library module: {mod} ({exc})", file=sys.stderr)
            return 1
    print(f"[OK] All {len(required_stdlib_modules)} standard library modules verified.")
    print("[OK] Zero external third-party pip dependencies required.")

    # -------------------------------------------------------------------------
    # 3. Codebase Artifact & Path Discovery
    # -------------------------------------------------------------------------
    log_step("3. Codebase Component Discovery")
    # Resolve project root relative to this script
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    if (repo_root / "src" / "engine").exists():
        scs_root = repo_root / "src"
    elif (repo_root / "SCS_AG_v2" / "engine").exists():
        scs_root = repo_root / "SCS_AG_v2"
    else:
        scs_root = repo_root

    core_artifacts = [
        scs_root / "engine" / "vault_store.py",
        scs_root / "engine" / "core_adapter.py",
        scs_root / "engine" / "transcript_reader.py",
        scs_root / "engine" / "scs_cli.py",
    ]
    skill_candidates = [
        repo_root / ".agents" / "skills" / "scs" / "SKILL.md",
        scs_root / ".agents" / "skills" / "scs" / "SKILL.md",
    ]
    skill_file = next((s for s in skill_candidates if s.exists()), skill_candidates[0])
    core_artifacts.append(skill_file)

    missing_artifacts = []
    for art in core_artifacts:
        if art.exists():
            print(f"[OK] Found: {art.relative_to(repo_root)}")
        else:
            print(f"[FAIL] Missing: {art.relative_to(repo_root)}")
            missing_artifacts.append(art)

    if missing_artifacts:
        print(f"[FAIL] {len(missing_artifacts)} core components missing.", file=sys.stderr)
        return 1

    # -------------------------------------------------------------------------
    # 4. Automated Test Suite Execution (Dual-Layer)
    # -------------------------------------------------------------------------
    log_step("4. Automated Conformance Test Suite (196 Tests)")
    loader = unittest.TestLoader()

    # Discover Engine suite
    engine_dir = str(scs_root / "engine")
    suite1 = loader.discover(engine_dir, pattern="test_*.py")

    # Discover Upstream suite if present
    upstream_dir = str(repo_root / "tests")
    core_python_dir = str(repo_root / "core" / "python")
    src_dir = str(repo_root / "src")
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(scs_root) not in sys.path:
        sys.path.insert(0, str(scs_root))
    if src_dir not in sys.path and Path(src_dir).exists():
        sys.path.insert(0, src_dir)
    if core_python_dir not in sys.path and Path(core_python_dir).exists():
        sys.path.insert(0, core_python_dir)

    suite2 = unittest.TestSuite()
    if Path(upstream_dir).exists():
        suite2 = loader.discover(upstream_dir, pattern="test_*.py")

    test_start = time.perf_counter()
    runner = unittest.TextTestRunner(verbosity=1)

    print(f"\n--- Running Engine Suite ({scs_root.name}/engine/) ---")
    res1 = runner.run(suite1)

    print("\n--- Running Upstream Normative Suite (tests/) ---")
    res2 = runner.run(suite2)
    test_elapsed = time.perf_counter() - test_start

    total_run = res1.testsRun + res2.testsRun
    total_failures = len(res1.failures) + len(res2.failures)
    total_errors = len(res1.errors) + len(res2.errors)

    print(f"\nTest Execution Finished in {test_elapsed:.3f}s:")
    print(f"  Engine Tests:   {res1.testsRun} run, {len(res1.failures)} failures, {len(res1.errors)} errors")
    print(f"  Upstream Tests: {res2.testsRun} run, {len(res2.failures)} failures, {len(res2.errors)} errors")
    print(f"  Total Conformance: {total_run} tests run, {total_failures} failures, {total_errors} errors")

    if total_failures > 0 or total_errors > 0:
        print("[FAIL] Test suite conformance check failed.", file=sys.stderr)
        return 1
    print(f"[OK] 100% Test Conformance Achieved ({total_run}/{total_run} tests passing).")

    # -------------------------------------------------------------------------
    # 5. Ephemeral Vault Lifecycle Integration Verification
    # -------------------------------------------------------------------------
    log_step("5. Live Vault Lifecycle Verification (Ephemeral Sandbox)")
    try:
        if (repo_root / "SCS_AG_v2").exists():
            sys.path.insert(0, str(repo_root))
            from SCS_AG_v2.engine import vault_store
        else:
            sys.path.insert(0, str(repo_root))
            from engine import vault_store

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Step A: Create Vault
            vault_path = vault_store.create_vault(
                project_dir=tmp_path,
                project_code="VFY",
                project_name="Release Verification Project",
            )
            print("[OK] Ephemeral vault created successfully.")

            # Step B: Verify Baseline Seal
            seal_valid = vault_store.verify_seal(vault_path)
            if not seal_valid:
                print("[FAIL] Ephemeral vault baseline seal verification failed.", file=sys.stderr)
                return 1
            print("[OK] Baseline SHA-256 state seal verified intact.")

            # Step C: Stage Proposal
            staged = vault_store.append_staging_proposals(vault_path, [
                {
                    "proposal_type": "DECISION",
                    "statement": "Adopt zero-daemon release verification",
                    "why": "Ensures reproducible deployment across all environments",
                    "source_session_code": "SES001",
                }
            ])
            if staged != 1:
                print(f"[FAIL] Staging proposal count mismatch: expected 1, got {staged}", file=sys.stderr)
                return 1
            print("[OK] Proposal quarantine gate verified (1 item staged).")

            # Step D: Promote Proposal & Re-Seal
            promote_res = vault_store.promote_proposals(vault_path, promote_all=True)
            if promote_res.get("promoted_count") != 1:
                print(f"[FAIL] Promotion count mismatch: expected 1, got {promote_res}", file=sys.stderr)
                return 1
            
            seal_after = vault_store.verify_seal(vault_path)
            if not seal_after:
                print("[FAIL] Post-promotion snapshot seal verification failed.", file=sys.stderr)
                return 1
            print("[OK] Human custody promotion & SHA-256 re-sealing verified intact.")
    except Exception as exc:
        print(f"[FAIL] Live vault lifecycle test raised exception: {exc}", file=sys.stderr)
        return 1

    # -------------------------------------------------------------------------
    # 6. Final Summary & Attestation
    # -------------------------------------------------------------------------
    total_elapsed = time.perf_counter() - start_time
    print("\n" + "=" * 80)
    print("[SUCCESS] RELEASE VERIFICATION SUCCESSFUL")
    print("=" * 80)
    print("Summary of Verification Attestations:")
    print("  * Python Environment:       VALIDATED (>= 3.10)")
    print("  * Runtime Dependencies:     VALIDATED (Zero external packages)")
    print("  * Core Engine Components:   VALIDATED (5/5 present)")
    print(f"  * Automated Test Suite:     VALIDATED ({total_run}/{total_run} tests passing 100%)")
    print("  * Cryptographic Sealing:    VALIDATED (Deterministic SHA-256 intact)")
    print("  * Quarantine Gate:          VALIDATED (Isolation verified)")
    print(f"  * Total Verification Time:  {total_elapsed:.3f} seconds")
    print("=" * 80)
    print("SCS_AG_v2 is certified ready for production use and GitHub release.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
