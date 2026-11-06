"""
SCS Pre-Commit Hook Template & Packaging Module (src/engine/pre_commit_template.py)
==================================================================================

Provides the authoritative, zero-dependency pre-commit verification script
as an embedded template. Ensures that `scs hook install --git` can deploy the
full verification guard even when installed in a clean environment via pip/wheel,
without relying on source-tree relative paths.
"""

PRE_COMMIT_SCRIPT_CONTENT = '''#!/usr/bin/env python3
"""
SCS_AG_v2 — Git Pre-Commit State Seal Verification Hook (scripts/scs-pre-commit.py)
==================================================================================

Governing Invariant: "Never allow a git commit with a corrupted or tampered state seal."
Zero runtime dependencies (Python standard library only).

Validation Routine:
1. Locates active .continuity project vault(s) in repository.
2. Validates canonical/ledger.json existence and JSON syntax.
3. Computes deterministic canonical SHA-256 digest across ledger state.
4. Validates hash against snapshots/LATEST_SEAL.
5. Emits warnings for unratified proposals in staging quarantine.
6. Fails closed (exit code 1) on any corruption or seal mismatch.
7. Exits 0 on clean verification to allow Git commit.
"""

import sys
import os
import json
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


def canonical_json_bytes(data: Any) -> bytes:
    """Serializes data to canonical, deterministic UTF-8 JSON bytes (ADR-002).

    Uses sorted keys, zero-whitespace separators (',', ':'), and ensure_ascii=False.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_sha256(data: Any) -> str:
    """Computes a 64-char lowercase SHA-256 hash using canonical normalization."""
    payload = canonical_json_bytes(data)
    return hashlib.sha256(payload).hexdigest()


def find_continuity_vaults(start_path: Path) -> List[Path]:
    """Finds .continuity vault directories at start_path, in parents, or in subdirectories."""
    vaults: List[Path] = []
    seen = set()

    def add_vault(v: Path):
        resolved = v.resolve()
        if resolved not in seen and resolved.is_dir():
            seen.add(resolved)
            vaults.append(resolved)

    # 1. Direct check at start_path
    if (start_path / ".continuity").is_dir():
        add_vault(start_path / ".continuity")
    elif start_path.name == ".continuity" and start_path.is_dir():
        add_vault(start_path)

    # 2. Check parents up to filesystem root or git root
    curr = start_path.resolve()
    while curr.parent != curr:
        if (curr / ".continuity").is_dir():
            add_vault(curr / ".continuity")
        if (curr / ".git").exists():
            # Stop searching parents once git boundary reached
            break
        curr = curr.parent

    # 3. Search children (up to 3 levels deep, skipping common non-project dirs)
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox"}
    try:
        for root, dirs, files in os.walk(start_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            if ".continuity" in dirs:
                add_vault(Path(root) / ".continuity")
            # Limit depth
            depth = len(Path(root).relative_to(start_path).parts)
            if depth >= 3:
                dirs.clear()
    except Exception:
        pass

    return vaults


def verify_vault(vault_dir: Path) -> Tuple[bool, str]:
    """Verifies ledger integrity, schema invariants, and SHA-256 state seal for a vault.

    Returns:
        (is_valid, message)
    """
    ledger_path = vault_dir / "canonical" / "ledger.json"
    latest_seal_path = vault_dir / "snapshots" / "LATEST_SEAL"

    # 1. Physical existence check
    if not ledger_path.exists():
        return False, f"Missing canonical ledger: {ledger_path}"

    # 2. JSON parsing & corruption check
    try:
        content = ledger_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as exc:
        return False, f"Corrupted JSON in canonical ledger: {exc}"

    if not isinstance(data, dict):
        return False, "Canonical ledger must be a JSON object dictionary."

    # 3. Schema invariant verification
    proj = data.get("project")
    if not isinstance(proj, dict) or not proj.get("code"):
        return False, "Ledger missing mandatory project metadata or project code."

    proj_code = proj.get("code", "UNKNOWN")
    proj_name = proj.get("name", "Unnamed Project")

    # 4. State seal verification
    computed_sha = compute_sha256(data)

    if not latest_seal_path.exists():
        return False, f"Missing state seal anchor: {latest_seal_path}"

    try:
        expected_sha = latest_seal_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        return False, f"Unable to read LATEST_SEAL: {exc}"

    if computed_sha.lower() != expected_sha.lower():
        msg = (
            f"Cryptographic State Seal Mismatch for {proj_name} ({proj_code})!\\n"
            f"  Vault:        {vault_dir}\\n"
            f"  Computed SHA: {computed_sha}\\n"
            f"  Expected SHA: {expected_sha}\\n"
            f"  Cause:        ledger.json modified without authorized custody ratification.\\n"
            f"  Remediation:  Restore canonical state using: scs rollback {proj_code}"
        )
        return False, msg

    # 5. Non-blocking check for staged proposals
    staging_path = vault_dir / "staging" / "pending_proposals.json"
    unreviewed_count = 0
    if staging_path.exists():
        try:
            st_content = staging_path.read_text(encoding="utf-8").strip()
            if st_content:
                st_data = json.loads(st_content)
                if isinstance(st_data, list):
                    unreviewed_count = len(st_data)
                elif isinstance(st_data, dict):
                    unreviewed_count = len(st_data.get("proposals", []))
        except Exception:
            pass

    status_msg = f"[OK] SCS State Seal Intact: {proj_code} (SHA: {computed_sha[:16]}...)"
    if unreviewed_count > 0:
        status_msg += f"\\n     [!] Notice: {unreviewed_count} unreviewed proposal(s) staged in quarantine."

    return True, status_msg


def main(argv: Optional[List[str]] = None) -> int:
    """CLI Entry point for Git pre-commit verification."""
    parser = argparse.ArgumentParser(description="SCS Pre-Commit State Seal Verification Guard")
    parser.add_argument("--path", default=None, help="Repository or vault directory to verify (default: current directory)")
    parser.add_argument("--strict", action="store_true", help="Fail if no SCS vaults are detected")
    args = parser.parse_args(argv)

    target_dir = Path(args.path) if args.path else Path.cwd()
    vaults = find_continuity_vaults(target_dir)

    if not vaults:
        if args.strict:
            print("[X] SCS Pre-Commit Error: No .continuity vaults found (--strict mode).", file=sys.stderr)
            return 1
        print("[SCS] No .continuity vaults found. Skipping state seal verification.")
        return 0

    has_errors = False
    for v in vaults:
        is_valid, msg = verify_vault(v)
        if not is_valid:
            print(f"[X] SCS PRE-COMMIT BLOCKED:\\n{msg}", file=sys.stderr)
            has_errors = True
        else:
            print(msg)

    if has_errors:
        print("\\n[X] Commit aborted by SCS Pre-Commit Guard. Fix state seal violations before committing.", file=sys.stderr)
        return 1

    print("[SCS] Pre-commit verification passed. State seals intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
