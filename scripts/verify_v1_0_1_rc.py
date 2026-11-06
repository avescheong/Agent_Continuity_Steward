#!/usr/bin/env python3
"""
verify_v1_0_1_rc.py — Clean-Room Release Candidate Verification for SCS v1.0.1
Tests clean wheel installation in an isolated virtual environment with no user site-packages.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import json
import hashlib
from pathlib import Path

# Console encoding safeguard
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RELEASE_REPO = Path(r"D:\000. GITHUB\Agent_Continuity_Steward")
WHEEL_PATH = RELEASE_REPO / "dist" / "agent_continuity_steward-1.0.1-py3-none-any.whl"

def run_cmd(cmd, cwd=None, env=None, check=True):
    print(f"\n[RUN] {cmd} (cwd={cwd})")
    res = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        print(res.stdout)
    except Exception:
        print(res.stdout.encode("ascii", errors="replace").decode("ascii"))
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed (exit code {res.returncode}):\n{res.stdout}")
    return res

def main():
    print("=" * 80)
    print("SCS v1.0.1-rc1 CLEAN-ROOM RELEASE CANDIDATE VERIFICATION")
    print(f"Repository: {RELEASE_REPO}")
    print(f"Wheel:      {WHEEL_PATH}")
    print("=" * 80)

    assert WHEEL_PATH.exists(), f"Wheel file missing at {WHEEL_PATH}!"
    wheel_bytes = WHEEL_PATH.read_bytes()
    wheel_sha256 = hashlib.sha256(wheel_bytes).hexdigest()
    wheel_size = len(wheel_bytes)
    print(f"Wheel Size:   {wheel_size} bytes")
    print(f"Wheel SHA256: {wheel_sha256}")

    work_dir = Path(tempfile.mkdtemp(prefix="scs_v101_rc_verify_"))
    try:
        user_home = work_dir / "clean_home"
        user_home.mkdir(parents=True, exist_ok=True)
        venv_dir = work_dir / "clean_venv"

        test_env = os.environ.copy()
        test_env["USERPROFILE"] = str(user_home)
        test_env["HOME"] = str(user_home)
        test_env["PYTHONNOUSERSITE"] = "1"
        test_env["PYTHONIOENCODING"] = "utf-8"

        print(f"\n1. Creating isolated virtualenv at: {venv_dir}")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, env=test_env)

        if os.name == "nt":
            py_exe = str(venv_dir / "Scripts" / "python.exe")
            pip_exe = str(venv_dir / "Scripts" / "pip.exe")
            scs_exe = str(venv_dir / "Scripts" / "scs.exe")
        else:
            py_exe = str(venv_dir / "bin" / "python")
            pip_exe = str(venv_dir / "bin" / "pip")
            scs_exe = str(venv_dir / "bin" / "scs")

        print("\n2. Verifying absence of third-party packages before install...")
        check_pydantic = subprocess.run([py_exe, "-c", "import pydantic"], env=test_env, capture_output=True)
        assert check_pydantic.returncode != 0, "pydantic must NOT be present!"
        check_starlette = subprocess.run([py_exe, "-c", "import starlette"], env=test_env, capture_output=True)
        assert check_starlette.returncode != 0, "starlette must NOT be present!"
        check_httpx = subprocess.run([py_exe, "-c", "import httpx"], env=test_env, capture_output=True)
        assert check_httpx.returncode != 0, "httpx must NOT be present!"
        print("[OK] Confirmed: No pydantic, starlette, or httpx in clean environment.")

        print("\n3. Installing ONLY the generated v1.0.1 wheel...")
        res_inst = run_cmd(f'"{pip_exe}" install "{WHEEL_PATH}"', env=test_env)
        # Check packaging warnings
        warnings = [line for line in res_inst.stdout.splitlines() if "warning" in line.lower() and "pip" not in line.lower()]
        print(f"Non-pip packaging warnings detected: {warnings}")
        assert len(warnings) == 0, f"Unexpected packaging warnings: {warnings}"

        print("\n4. Runtime dependency audit after wheel installation...")
        res_pip = run_cmd(f'"{pip_exe}" list', env=test_env)
        installed_pkgs = [l.split()[0].lower() for l in res_pip.stdout.strip().splitlines()[2:]]
        print(f"Installed packages: {installed_pkgs}")
        for p in installed_pkgs:
            assert p in ["pip", "setuptools", "wheel", "agent-continuity-steward"], f"Unexpected dependency installed: {p}"
        print("[OK] Runtime dependency audit passed: Zero external third-party dependencies!")

        print("\n5. Testing entrypoint: scs --help...")
        res_scs_help = run_cmd(f'"{scs_exe}" --help', env=test_env)
        assert "SCS_AG_v2" in res_scs_help.stdout
        assert "rollback" in res_scs_help.stdout
        print("[OK] scs --help verified!")

        print("\n6. Testing module entrypoint: python -m engine.scs_cli --help...")
        res_mod_help = run_cmd(f'"{py_exe}" -m engine.scs_cli --help', env=test_env)
        assert "SCS_AG_v2" in res_mod_help.stdout
        assert "rollback" in res_mod_help.stdout
        print("[OK] python -m engine.scs_cli --help verified!")

        print("\n7. Running verify_release.py with venv python in release repo...")
        res_verify = run_cmd(f'"{py_exe}" scripts/verify_release.py', cwd=str(RELEASE_REPO), env=test_env)
        assert "100% Test Conformance Achieved (134/134 tests passing)" in res_verify.stdout
        assert "RELEASE VERIFICATION SUCCESSFUL" in res_verify.stdout
        print("[OK] verify_release.py passed with 134/134 tests (100%)!")

        print("\n8. Running test_quickstart_e2e.py in release repo...")
        res_e2e = run_cmd(f'"{py_exe}" scripts/test_quickstart_e2e.py', cwd=str(RELEASE_REPO), env=test_env)
        assert "ALL 10 QUICKSTART E2E VERIFICATION STEPS COMPLETED WITH 100% SUCCESS" in res_e2e.stdout
        print("[OK] test_quickstart_e2e.py passed 10/10 steps!")

        # 9. Dedicated Rollback Syntax Test in Fresh External Workspace
        print("\n9. Testing Rollback CLI Ergonomics (Flag & Positional)...")
        ext_ws = work_dir / "rollback_test_workspace"
        ext_ws.mkdir(parents=True, exist_ok=True)
        vault_dir = user_home / "My_Project_Continuity" / "RBK"

        # Initialize vault
        run_cmd(f'"{scs_exe}" new RBK "Rollback Test" --path "{vault_dir}" --repo "{ext_ws}" --objective "Validate rollback"', cwd=str(ext_ws), env=test_env)

        # Stage proposal and promote to generate snapshot 2
        staging_file = vault_dir / ".continuity" / "staging" / "pending_proposals.json"
        staging_data = {
            "protocol": "scs-staging/1.0",
            "project_code": "RBK",
            "updated_at": "2026-11-06T12:00:00Z",
            "proposals": [
                {
                    "id": "P01",
                    "proposal_type": "DECISION",
                    "statement": "Adopt SQLite for local indexing",
                    "why": "Zero operational maintenance",
                    "status": "PENDING"
                }
            ]
        }
        with open(staging_file, "w", encoding="utf-8") as f:
            json.dump(staging_data, f, indent=2)

        run_cmd(f'"{scs_exe}" approve --all --project RBK', cwd=str(ext_ws), env=test_env)

        # Inspect snapshots
        snaps = sorted([p.stem for p in (vault_dir / ".continuity" / "snapshots").glob("SNP-*.json")])
        print(f"Snapshots present: {snaps}")
        assert len(snaps) == 2, f"Expected 2 snapshots, found: {snaps}"
        snp_base = snaps[0]
        snp_dec = snaps[1]

        # Test Flag Syntax: scs rollback --snapshot <CODE> --project RBK
        print(f"\n--> Testing rollback flag syntax to {snp_base}...")
        res_rb1 = run_cmd(f'"{scs_exe}" rollback --snapshot {snp_base} --project RBK', cwd=str(ext_ws), env=test_env)
        assert f"Successfully rolled back canonical memory to snapshot `{snp_base}`" in res_rb1.stdout
        assert "Decisions:     0" in res_rb1.stdout
        print("[OK] Rollback flag syntax verified!")

        # Test Positional Syntax: scs rollback <CODE> --project RBK
        print(f"\n--> Testing rollback positional syntax to {snp_dec}...")
        res_rb2 = run_cmd(f'"{scs_exe}" rollback {snp_dec} --project RBK', cwd=str(ext_ws), env=test_env)
        assert f"Successfully rolled back canonical memory to snapshot `{snp_dec}`" in res_rb2.stdout
        assert "Decisions:     1" in res_rb2.stdout
        print("[OK] Rollback positional syntax verified!")

        print("\n" + "=" * 80)
        print("ALL RELEASE CANDIDATE VERIFICATION CRITERIA MET (PASS 100%)")
        print("=" * 80)
        return {
            "wheel_size": wheel_size,
            "wheel_sha256": wheel_sha256,
            "wheel_filename": WHEEL_PATH.name,
            "tests_total": 134,
            "tests_passed": 134,
            "failures": 0,
            "errors": 0,
            "runtime_deps": installed_pkgs,
            "post_ga_status": "POST-GA-001 through POST-GA-004 CLOSED"
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

if __name__ == "__main__":
    res = main()
    print("\nResult summary:", json.dumps(res, indent=2))
