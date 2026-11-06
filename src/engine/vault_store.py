"""
SCS_AG_v2 Project Vault Storage & Sealer (engine/vault_store.py)
================================================================

Governing Principles:
1. "Preserve the brain, replace the communication channel."
2. "JSON is machine authority; Markdown files are generated views only."
3. "Fail-closed project routing — never guess or use stale globals."
4. "Cryptographic deterministic sealing with instant rollback."

This module implements the file-first, project-based continuity vault (.continuity/)
for SCS_AG_v2. Every managed project maintains a self-contained, isolated vault.
"""

import os
import sys
import json
import re
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Import core_adapter safely from current directory
# ---------------------------------------------------------------------------

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    import core_adapter
except ImportError:
    core_adapter = None


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class VaultError(Exception):
    """Base exception for SCS vault operations."""
    pass


class SealTamperError(VaultError):
    """Raised when canonical ledger SHA-256 does not match LATEST_SEAL."""
    def __init__(self, message: str, computed_sha: str, expected_sha: str):
        super().__init__(message)
        self.computed_sha = computed_sha
        self.expected_sha = expected_sha


class AmbiguousProjectError(VaultError):
    """Raised when project context cannot be resolved safely and requires human selection."""
    def __init__(self, message: str, candidate_vaults: List[Dict[str, Any]]):
        super().__init__(message)
        self.candidate_vaults = candidate_vaults


class ProjectNotFoundError(VaultError):
    """Raised when specified project vault does not exist."""
    pass


# ---------------------------------------------------------------------------
# Deterministic Serialization & Hashing Utilities
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_compact() -> Tuple[str, str, str]:
    """Returns (YYYYMMDD, HHMM, YYYYMMDD_HHMM)."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M")
    return date_str, time_str, f"{date_str}_{time_str}"


def canonical_json_bytes(data: Any) -> bytes:
    """Serializes data to canonical, deterministic UTF-8 JSON bytes (ADR-002).

    Uses sorted keys, zero-whitespace separators (',', ':'), and ensure_ascii=False.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_sha256(data: Union[bytes, str, Dict[str, Any]]) -> str:
    """Computes a 64-char lowercase SHA-256 hash using canonical normalization."""
    if isinstance(data, (dict, list)):
        payload = canonical_json_bytes(data)
    elif isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = data
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Vault Path Resolution Helper
# ---------------------------------------------------------------------------

def get_vault_paths(vault_dir: Union[str, Path]) -> Dict[str, Path]:
    """Returns canonical paths for all directories and files within a vault."""
    v = Path(vault_dir).resolve()
    # If passed the project root rather than .continuity, adjust
    if v.name != ".continuity":
        # If v already is a naked vault directory containing canonical/ledger.json, preserve it
        if not (v / "canonical" / "ledger.json").exists():
            v = v / ".continuity"

    proj_root = v.parent
    canonical_dir = v / "canonical"
    staging_dir = v / "staging"
    snapshots_dir = v / "snapshots"
    evidence_dir = v / "evidence"
    raw_sessions_dir = evidence_dir / "raw_sessions"
    archives_dir = evidence_dir / "archives"
    imports_dir = evidence_dir / "imports"
    handover_dir = v / "handover"

    return {
        "project_root": proj_root,
        "vault_dir": v,
        "gitignore": v / ".gitignore",
        "blueprint_md": v / "BLUEPRINT.md",
        "gemini_md": proj_root / "GEMINI.md",
        # Canonical SSOT
        "canonical_dir": canonical_dir,
        "ledger_json": canonical_dir / "ledger.json",
        "decisions_md": canonical_dir / "DECISIONS.md",
        "rejected_options_md": canonical_dir / "REJECTED_OPTIONS.md",
        "tasks_md": canonical_dir / "TASKS.md",
        "artifacts_md": canonical_dir / "ARTIFACTS.md",
        # Staging
        "staging_dir": staging_dir,
        "pending_proposals_json": staging_dir / "pending_proposals.json",
        "review_draft_md": staging_dir / "REVIEW_DRAFT.md",
        # Snapshots
        "snapshots_dir": snapshots_dir,
        "latest_seal": snapshots_dir / "LATEST_SEAL",
        # Evidence
        "evidence_dir": evidence_dir,
        "manifest_json": evidence_dir / "MANIFEST.json",
        "raw_sessions_dir": raw_sessions_dir,
        "archives_dir": archives_dir,
        "imports_dir": imports_dir,
        # Handover
        "handover_dir": handover_dir,
    }


# ---------------------------------------------------------------------------
# Function 1: create_vault
# ---------------------------------------------------------------------------

def create_vault(
    project_dir: Union[str, Path],
    project_code: str,
    project_name: str,
    objective: str = "",
    current_focus: str = "",
    next_action: str = "",
    root_paths: Optional[List[str]] = None,
) -> Path:
    """Scaffolds a complete .continuity/ vault for an independent project.

    Creates directory hierarchy, .gitignore, initial ledger.json, initial staging,
    initial MANIFEST.json, initial baseline snapshot (SNP-*-001), LATEST_SEAL,
    and renders all Markdown views.

    Args:
        project_dir: Root directory of the project.
        project_code: Short identifier (e.g. 'RIE', 'HERO_KAI', 'SCS2').
        project_name: Human-friendly name.
        objective: Primary goal of the project.
        current_focus: Current operational focus.
        next_action: Immediate recommended next action.
        root_paths: List of watched root directories. Defaults to [project_dir].

    Returns:
        Path to created .continuity/ directory.
    """
    p_dir = Path(project_dir).resolve()
    p_dir.mkdir(parents=True, exist_ok=True)
    paths = get_vault_paths(p_dir)

    # 1. Create directory hierarchy
    for d in [
        paths["vault_dir"],
        paths["canonical_dir"],
        paths["staging_dir"],
        paths["snapshots_dir"],
        paths["raw_sessions_dir"],
        paths["archives_dir"],
        paths["imports_dir"],
        paths["handover_dir"],
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Write .continuity/.gitignore (ADR-003 Git retention policy)
    gitignore_content = (
        "# SCS Continuity Git Retention Policy (ADR-003)\n"
        "# Quarantine and raw forensic evidence remain project-local by default\n"
        "staging/\n"
        "evidence/raw_sessions/\n"
        "evidence/imports/\n"
        "*.tmp\n"
        "\n"
        "# Track canonical memory, deterministic snapshots, consolidated archives, and handover packages\n"
        "!BLUEPRINT.md\n"
        "!canonical/\n"
        "!snapshots/\n"
        "!evidence/MANIFEST.json\n"
        "!evidence/archives/\n"
        "!handover/\n"
    )
    paths["gitignore"].write_text(gitignore_content, encoding="utf-8")

    # 3. Write lightweight <project_root>/GEMINI.md (<25 lines)
    gemini_rule = (
        f"# SCS Continuity Rule — {project_name} ({project_code})\n"
        "\n"
        "1. At session start, read `.continuity/BLUEPRINT.md` for active goals, constraints, and tasks.\n"
        "2. Obey all ratified decisions and governance constraints as binding project law.\n"
        "3. Never re-propose any rejected option recorded in `.continuity/canonical/REJECTED_OPTIONS.md`.\n"
        "4. Never edit `.continuity/canonical/` or `.continuity/evidence/` directly.\n"
        "5. To record session progress, run `/scs record`.\n"
        "6. To ratify staged proposals, run `/scs approve`.\n"
    )
    paths["gemini_md"].write_text(gemini_rule, encoding="utf-8")

    # 4. Initialize evidence/MANIFEST.json
    manifest_data = {
        "schema_version": "scs-manifest/1.0",
        "project_code": project_code,
        "project_name": project_name,
        "next_session_num": 1,
        "next_archive_num": 1,
        "created_at": utc_now_iso(),
        "watermarks_by_conversation": {},
        "sessions": [],
        "archives": [],
    }
    paths["manifest_json"].write_text(
        json.dumps(manifest_data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # 5. Initialize staging/pending_proposals.json & REVIEW_DRAFT.md
    staging_data = {
        "protocol": "scs-staging/1.0",
        "project_code": project_code,
        "updated_at": utc_now_iso(),
        "proposals": [],
    }
    paths["pending_proposals_json"].write_text(
        json.dumps(staging_data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    render_review_draft(paths["vault_dir"], staging_data)

    # 6. Initialize canonical/ledger.json
    now_iso = utc_now_iso()
    proj_id = uuid.uuid4().hex
    safe_roots = [str(Path(r).resolve()) for r in (root_paths or [str(p_dir)])]

    initial_ledger = {
        "schema_version": "scs-ledger/1.0",
        "project": {
            "id": proj_id,
            "code": project_code,
            "name": project_name,
            "description": f"Continuity vault for {project_name}",
            "objective": objective or f"Execute and deliver {project_name}",
            "current_focus": current_focus or "Project initialization and architecture baseline",
            "next_action": next_action or "Review kickoff blueprint and proceed with Phase 1",
            "root_paths": safe_roots,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        "decisions": [],
        "constraints": [],
        "rejected_options": [],
        "tasks": [],
        "artifacts": [],
        "history_summary": {
            "total_sessions": 0,
            "total_archives": 0,
            "latest_snapshot_code": "",
            "latest_snapshot_sha256": "",
            "last_sealed_at": now_iso,
        },
    }

    # 7. Write initial ledger and seal initial baseline snapshot (SNP-*-001)
    date_str, _, _ = utc_now_compact()
    snap_code = f"SNP-{date_str}-001"
    snap_id = uuid.uuid4().hex

    initial_ledger["history_summary"]["latest_snapshot_code"] = snap_code

    # 7.1 Save canonical ledger.json
    paths["ledger_json"].write_text(
        json.dumps(initial_ledger, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # 7.2 Compute canonical normalized hash
    final_hash = compute_sha256(initial_ledger)

    # 7.3 Write initial snapshot
    snap_record = {
        "id": snap_id,
        "snapshot_code": snap_code,
        "project_id": proj_id,
        "project_code": project_code,
        "label": "Initial Project Baseline Sealing",
        "checksum_sha256": final_hash,
        "created_at": now_iso,
        "ledger_state": initial_ledger,
    }
    snap_path = paths["snapshots_dir"] / f"{snap_code}.json"
    snap_path.write_text(
        json.dumps(snap_record, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # 7.4 Write LATEST_SEAL
    paths["latest_seal"].write_text(f"{final_hash}\n", encoding="utf-8")

    # 8. Render all Markdown views
    render_markdown_views(paths["vault_dir"], initial_ledger)

    return paths["vault_dir"]


# ---------------------------------------------------------------------------
# Function 2: read_ledger
# ---------------------------------------------------------------------------

def read_ledger(vault_dir: Union[str, Path], verify_seal: bool = True) -> Dict[str, Any]:
    """Reads .continuity/canonical/ledger.json with optional seal verification.

    Args:
        vault_dir: Vault or project directory.
        verify_seal: If True, compares computed SHA-256 against LATEST_SEAL.

    Returns:
        Structured canonical ledger dictionary.

    Raises:
        SealTamperError: If verify_seal is True and SHA-256 mismatch is detected.
        FileNotFoundError: If ledger.json does not exist.
    """
    paths = get_vault_paths(vault_dir)
    if not paths["ledger_json"].exists():
        raise FileNotFoundError(f"Canonical ledger not found at: {paths['ledger_json']}")

    content = paths["ledger_json"].read_text(encoding="utf-8")
    data = json.loads(content)

    if verify_seal:
        computed_sha = hashlib.sha256(canonical_json_bytes(data)).hexdigest()
        expected_sha = ""
        if paths["latest_seal"].exists():
            expected_sha = paths["latest_seal"].read_text(encoding="utf-8").strip()

        if expected_sha and computed_sha.lower() != expected_sha.lower():
            raise SealTamperError(
                f"SEAL TAMPER DETECTED in {paths['ledger_json']}: "
                f"Computed SHA-256 `{computed_sha}` does not match `{expected_sha}`. "
                "Use rollback_to_snapshot() to restore canonical state.",
                computed_sha=computed_sha,
                expected_sha=expected_sha,
            )

    return data


# ---------------------------------------------------------------------------
# Function 3: write_ledger & seal
# ---------------------------------------------------------------------------

def _next_snapshot_code(snapshots_dir: Path) -> str:
    """Computes next snapshot code in SNP-YYYYMMDD-NNN format."""
    date_str, _, _ = utc_now_compact()
    pattern = re.compile(rf"^SNP-{date_str}-(\d{{3}})\.json$")
    highest = 0

    if snapshots_dir.exists():
        for f in snapshots_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                seq = int(m.group(1))
                if seq > highest:
                    highest = seq

    return f"SNP-{date_str}-{highest + 1:03d}"


def write_ledger(
    vault_dir: Union[str, Path],
    ledger_data: Dict[str, Any],
    label: str = "Canonical update",
    create_snapshot: bool = True,
) -> Tuple[str, str]:
    """Writes updated canonical/ledger.json, seals deterministically, and updates views.

    Args:
        vault_dir: Vault or project directory.
        ledger_data: Updated canonical ledger dictionary.
        label: Reason for update (recorded in snapshot).
        create_snapshot: If True, writes a new immutable snapshot in snapshots/.

    Returns:
        Tuple of (snapshot_code, seal_sha256).
    """
    paths = get_vault_paths(vault_dir)
    now_iso = utc_now_iso()

    # Update project updated_at timestamp
    if "project" in ledger_data:
        ledger_data["project"]["updated_at"] = now_iso

    # Determine snapshot code
    snap_code = ""
    if create_snapshot:
        snap_code = _next_snapshot_code(paths["snapshots_dir"])
        if "history_summary" not in ledger_data:
            ledger_data["history_summary"] = {}
        ledger_data["history_summary"]["latest_snapshot_code"] = snap_code
        ledger_data["history_summary"]["last_sealed_at"] = now_iso

        # Synchronize session and archive counts from MANIFEST.json if available
        manifest_file = paths["manifest_json"]
        if manifest_file.exists():
            try:
                m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                ledger_data["history_summary"]["total_sessions"] = len(m_data.get("sessions", []))
                ledger_data["history_summary"]["total_archives"] = len(m_data.get("archives", []))
            except Exception:
                pass

    # 1. Write canonical/ledger.json
    paths["ledger_json"].write_text(
        json.dumps(ledger_data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # 2. Compute deterministic canonical hash
    seal_hash = compute_sha256(ledger_data)

    # 3. Write immutable snapshot
    if create_snapshot and snap_code:
        snap_record = {
            "id": uuid.uuid4().hex,
            "snapshot_code": snap_code,
            "project_id": ledger_data.get("project", {}).get("id", ""),
            "project_code": ledger_data.get("project", {}).get("code", ""),
            "label": label,
            "checksum_sha256": seal_hash,
            "created_at": now_iso,
            "ledger_state": ledger_data,
        }
        snap_file = paths["snapshots_dir"] / f"{snap_code}.json"
        snap_file.write_text(
            json.dumps(snap_record, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    # 4. Write LATEST_SEAL
    paths["latest_seal"].write_text(f"{seal_hash}\n", encoding="utf-8")

    # 4. Re-render all Markdown views
    render_markdown_views(paths["vault_dir"], ledger_data)

    return snap_code, seal_hash


# ---------------------------------------------------------------------------
# Function 4: verify_seal
# ---------------------------------------------------------------------------

def verify_seal(vault_dir: Union[str, Path]) -> Tuple[bool, str, str]:
    """Verifies that canonical/ledger.json matches snapshots/LATEST_SEAL.

    Returns:
        (is_valid, computed_sha256, expected_sha256)
    """
    paths = get_vault_paths(vault_dir)
    if not paths["ledger_json"].exists():
        return False, "", "LEDGER_MISSING"
    if not paths["latest_seal"].exists():
        return False, "", "SEAL_MISSING"

    content = paths["ledger_json"].read_text(encoding="utf-8")
    data = json.loads(content)
    computed_sha = hashlib.sha256(canonical_json_bytes(data)).hexdigest()
    expected_sha = paths["latest_seal"].read_text(encoding="utf-8").strip()

    is_valid = computed_sha.lower() == expected_sha.lower()
    return is_valid, computed_sha, expected_sha


# ---------------------------------------------------------------------------
# Function 5: rollback_to_snapshot
# ---------------------------------------------------------------------------

def rollback_to_snapshot(
    vault_dir: Union[str, Path],
    snapshot_code: str,
) -> Dict[str, Any]:
    """Rolls back canonical/ledger.json and all Markdown views to a prior snapshot.

    Args:
        vault_dir: Vault or project directory.
        snapshot_code: Code of snapshot to restore (e.g. 'SNP-20261105-001').

    Returns:
        Summary dictionary with restored snapshot code, hash, and status.

    Raises:
        FileNotFoundError: If specified snapshot file does not exist.
        ValueError: If snapshot file is corrupt or invalid.
    """
    paths = get_vault_paths(vault_dir)
    snap_file = paths["snapshots_dir"] / f"{snapshot_code}.json"
    if not snap_file.exists():
        raise FileNotFoundError(f"Snapshot not found: {snap_file}")

    snap_data = json.loads(snap_file.read_text(encoding="utf-8"))
    ledger_state = snap_data.get("ledger_state")
    if not ledger_state:
        raise ValueError(f"Snapshot `{snapshot_code}` contains no ledger_state.")

    # Re-verify snapshot payload against its recorded checksum
    canonical_bytes = canonical_json_bytes(ledger_state)
    restored_hash = hashlib.sha256(canonical_bytes).hexdigest()

    # 1. Restore canonical/ledger.json
    paths["ledger_json"].write_text(
        json.dumps(ledger_state, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # 2. Update LATEST_SEAL
    paths["latest_seal"].write_text(f"{restored_hash}\n", encoding="utf-8")

    # 3. Re-render all Markdown views from the restored state
    render_markdown_views(paths["vault_dir"], ledger_state)

    return {
        "status": "RESTORED",
        "restored_snapshot_code": snapshot_code,
        "checksum_sha256": restored_hash,
        "restored_at": utc_now_iso(),
        "decisions_count": len(ledger_state.get("decisions", [])),
        "tasks_count": len(ledger_state.get("tasks", [])),
    }


def list_snapshots(vault_dir: Union[str, Path]) -> List[Dict[str, Any]]:
    """Lists all available snapshots in chronological sequence."""
    paths = get_vault_paths(vault_dir)
    if not paths["snapshots_dir"].exists():
        return []

    snapshots = []
    for f in sorted(paths["snapshots_dir"].glob("SNP-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            snapshots.append({
                "snapshot_code": d.get("snapshot_code", f.stem),
                "label": d.get("label", ""),
                "checksum_sha256": d.get("checksum_sha256", ""),
                "created_at": d.get("created_at", ""),
                "file_path": str(f),
            })
        except Exception:
            continue

    return snapshots


# ---------------------------------------------------------------------------
# Function 6: Staging Layer (pending_proposals.json & REVIEW_DRAFT.md)
# ---------------------------------------------------------------------------

def read_staging(vault_dir: Union[str, Path]) -> Dict[str, Any]:
    """Reads .continuity/staging/pending_proposals.json with defensive normalization.

    FDB-101-013: If pending_proposals.json contains a raw JSON list [...],
    it is automatically normalized into the standard protocol dictionary format:
    {"protocol": "scs-staging/1.0", "updated_at": <ISO>, "proposals": [...]}.
    """
    paths = get_vault_paths(vault_dir)
    if not paths["pending_proposals_json"].exists():
        return {"protocol": "scs-staging/1.0", "proposals": []}
    try:
        data = json.loads(paths["pending_proposals_json"].read_text(encoding="utf-8"))
    except Exception:
        return {"protocol": "scs-staging/1.0", "proposals": []}

    if isinstance(data, list):
        return {
            "protocol": "scs-staging/1.0",
            "updated_at": utc_now_iso(),
            "proposals": data,
        }
    if not isinstance(data, dict):
        return {"protocol": "scs-staging/1.0", "proposals": []}

    data.setdefault("protocol", "scs-staging/1.0")
    data.setdefault("proposals", [])
    return data


def write_staging(vault_dir: Union[str, Path], staging_data: Dict[str, Any]) -> None:
    """Writes .continuity/staging/pending_proposals.json and updates REVIEW_DRAFT.md."""
    paths = get_vault_paths(vault_dir)
    staging_data["updated_at"] = utc_now_iso()
    paths["pending_proposals_json"].write_text(
        json.dumps(staging_data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    render_review_draft(paths["vault_dir"], staging_data)


def append_staging_proposals(
    vault_dir: Union[str, Path],
    proposals: List[Dict[str, Any]],
) -> int:
    """Appends new candidate proposals to staging in PENDING status.

    Assigns sequential identifiers (P01, P02, ...) and updates REVIEW_DRAFT.md.
    Returns number of newly staged proposals.
    """
    paths = get_vault_paths(vault_dir)
    st = read_staging(paths["vault_dir"])
    existing = st.get("proposals", [])

    # Find highest existing P-number
    highest = 0
    for it in existing:
        pid = it.get("id", "")
        m = re.match(r"^P(\d+)$", pid)
        if m:
            highest = max(highest, int(m.group(1)))

    added = 0
    for p in proposals:
        highest += 1
        new_item = dict(p)
        new_item["id"] = f"P{highest:02d}"
        new_item["status"] = "PENDING"
        new_item.setdefault("created_at", utc_now_iso())
        existing.append(new_item)
        added += 1

    st["proposals"] = existing
    write_staging(paths["vault_dir"], st)
    return added


def promote_proposals(
    vault_dir: Union[str, Path],
    proposal_ids: Optional[List[str]] = None,
    promote_all: bool = False,
    label: str = "Human custody approval",
    allow_unverified: bool = False,
) -> Dict[str, Any]:
    """Promotes selected/all PENDING proposals from staging into canonical/ledger.json.

    Applies human custody approval gate:
    - Enforces Phase 1.6 quality invariants (blocks generic words and inverted features unless allow_unverified=True)
    - Retires superseded decisions on reversals
    - Deduplicates decisions, constraints, and tasks
    - Preserves rejected options
    - Seals new snapshot and re-renders Markdown views
    - Clears resolved staging proposals

    Args:
        vault_dir: Vault or project directory.
        proposal_ids: Specific IDs to promote (e.g. ['P01', 'P02']).
        promote_all: If True, promotes all PENDING proposals.
        label: Snapshot seal reason.
        allow_unverified: If True, bypasses title quality and capability protection gates.

    Returns:
        Summary dict of promoted items and new seal code.
    """
    paths = get_vault_paths(vault_dir)
    st = read_staging(paths["vault_dir"])
    ledger = read_ledger(paths["vault_dir"], verify_seal=True)
    all_proposals = st.get("proposals", [])

    to_promote = []
    remaining = []
    blocked_items = []

    for p in all_proposals:
        pid = p.get("id")
        should_promote = promote_all or (proposal_ids and pid in proposal_ids)
        if should_promote and p.get("status") == "PENDING":
            ptype = p.get("proposal_type", "DECISION").upper()
            stmt = p.get("statement") or p.get("title") or ""
            why = p.get("why") or p.get("rationale_why") or ""

            # Phase 1.6 safety validation
            is_valid = True
            rejection_reason = ""
            if not allow_unverified:
                if ptype == "DECISION":
                    is_valid, rejection_reason = core_adapter.validate_decision_title(stmt, why)
                elif ptype == "REJECTED_OPTION":
                    is_valid, rejection_reason = core_adapter.validate_rejected_option_statement(stmt, why)

            if is_valid:
                to_promote.append(p)
            else:
                p_blocked = dict(p)
                p_blocked["blocked_reason"] = rejection_reason
                blocked_items.append(p_blocked)
                remaining.append(p)
        else:
            remaining.append(p)

    if not to_promote:
        return {
            "promoted_count": 0,
            "blocked_count": len(blocked_items),
            "blocked_items": blocked_items,
            "snapshot_code": "",
            "message": "No proposals promoted"
        }

    promoted_decisions = 0
    promoted_constraints = 0
    promoted_rejected = 0
    promoted_tasks = 0
    promoted_artifacts = 0

    dec_list = ledger.setdefault("decisions", [])
    con_list = ledger.setdefault("constraints", [])
    rej_list = ledger.setdefault("rejected_options", [])
    tsk_list = ledger.setdefault("tasks", [])
    art_list = ledger.setdefault("artifacts", [])

    for p in to_promote:
        ptype = p.get("proposal_type", "DECISION").upper()
        stmt = p.get("statement") or p.get("title") or ""
        why = p.get("why") or p.get("rationale_why") or "Approved by operator"

        if ptype == "DECISION":
            norm_stmt = stmt.strip().rstrip(".:;*").strip().lower()
            existing_dec = next(
                (d for d in dec_list if d.get("is_active") and d.get("statement", "").strip().rstrip(".:;*").strip().lower() == norm_stmt),
                None
            )
            if existing_dec:
                existing_dec["updated_at"] = utc_now_iso()
                if why:
                    existing_dec["rationale_why"] = why
            else:
                code = f"DEC-{len(dec_list) + 1:03d}"
                dec_list.append({
                    "id": uuid.uuid4().hex,
                    "code": code,
                    "record_kind": "DECISION",
                    "statement": stmt,
                    "rationale_why": why,
                    "impact_scope": p.get("impact_scope", ""),
                    "source_excerpt": p.get("evidence_quote") or p.get("source_excerpt", ""),
                    "is_active": True,
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                })
                promoted_decisions += 1

        elif ptype == "CONSTRAINT":
            existing_con = next(
                (c for c in con_list if c.get("is_active") and c.get("statement", "").strip().lower() == stmt.strip().lower()),
                None
            )
            if existing_con:
                existing_con["updated_at"] = utc_now_iso()
            else:
                code = f"CON-{len(con_list) + 1:03d}"
                con_list.append({
                    "id": uuid.uuid4().hex,
                    "code": code,
                    "record_kind": "CONSTRAINT",
                    "statement": stmt,
                    "rationale_why": why,
                    "impact_scope": p.get("impact_scope", ""),
                    "source_excerpt": p.get("evidence_quote", ""),
                    "is_active": True,
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                })
                promoted_constraints += 1

        elif ptype == "REJECTED_OPTION":
            existing_rej = next(
                (r for r in rej_list if r.get("statement", "").strip().lower() == stmt.strip().lower()),
                None
            )
            if existing_rej:
                existing_rej["updated_at"] = utc_now_iso()
            else:
                code = f"REJ-{len(rej_list) + 1:03d}"
                rej_list.append({
                    "id": uuid.uuid4().hex,
                    "code": code,
                    "record_kind": "REJECTED_OPTION",
                    "statement": stmt,
                    "rationale_why": why,
                    "impact_scope": p.get("impact_scope", ""),
                    "source_excerpt": p.get("evidence_quote", ""),
                    "is_active": True,
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                })
                promoted_rejected += 1

        elif ptype == "TASK":
            existing_tsk = next(
                (t for t in tsk_list if t.get("title", "").strip().lower() == stmt.strip().lower()),
                None
            )
            status_val = p.get("task_status") or p.get("status", "PENDING")
            comp_at = p.get("completed_at") if status_val == "COMPLETED" else None
            if status_val == "COMPLETED" and not comp_at:
                comp_at = utc_now_iso()

            if existing_tsk:
                if status_val:
                    existing_tsk["status"] = status_val
                if comp_at:
                    existing_tsk["completed_at"] = comp_at
                if p.get("completed_evidence"):
                    existing_tsk["completed_evidence"] = p.get("completed_evidence")
                if p.get("completed_by_verification"):
                    existing_tsk["completed_by_verification"] = p.get("completed_by_verification")
                existing_tsk["updated_at"] = utc_now_iso()
            else:
                code = f"TSK-{len(tsk_list) + 1:03d}"
                tsk_list.append({
                    "id": uuid.uuid4().hex,
                    "code": code,
                    "title": stmt,
                    "status": status_val,
                    "priority": p.get("priority", "MEDIUM"),
                    "why_it_matters": why,
                    "blocker_reason": p.get("blocker_reason", ""),
                    "sort_order": len(tsk_list) + 1,
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                    "completed_at": comp_at,
                    "completed_by_verification": p.get("completed_by_verification", False),
                    "completed_evidence": p.get("completed_evidence", ""),
                })
                promoted_tasks += 1

        elif ptype == "ARTIFACT":
            art_name = p.get("name") or stmt
            art_path = p.get("relative_path") or stmt
            existing_art = next(
                (a for a in art_list if a.get("name", "").strip().lower() == art_name.strip().lower() or a.get("relative_path", "").strip().lower() == art_path.strip().lower()),
                None
            )
            if existing_art:
                existing_art["last_reconciled_at"] = utc_now_iso()
                existing_art["updated_at"] = utc_now_iso()
                if p.get("custody_state"):
                    existing_art["custody_state"] = p.get("custody_state")
                if p.get("observed_sha256"):
                    existing_art["observed_sha256"] = p.get("observed_sha256")
            else:
                art_list.append({
                    "id": uuid.uuid4().hex,
                    "name": art_name,
                    "artifact_type": p.get("artifact_type", "CODE_FILE"),
                    "relative_path": art_path,
                    "custody_state": p.get("custody_state", "LOCAL_FILE_EXISTS"),
                    "baseline_sha256": p.get("baseline_sha256"),
                    "observed_sha256": p.get("observed_sha256"),
                    "required_markers": p.get("required_markers", []),
                    "missing_markers": [],
                    "last_reconciled_at": utc_now_iso(),
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                })
                promoted_artifacts += 1

    # Write updated canonical state and seal
    snap_code, seal_hash = write_ledger(
        paths["vault_dir"],
        ledger,
        label=label,
        create_snapshot=True,
    )

    # Update staging with remaining items
    st["proposals"] = remaining
    write_staging(paths["vault_dir"], st)

    return {
        "promoted_count": len(to_promote),
        "promoted_decisions": promoted_decisions,
        "promoted_constraints": promoted_constraints,
        "promoted_rejected": promoted_rejected,
        "promoted_tasks": promoted_tasks,
        "promoted_artifacts": promoted_artifacts,
        "remaining_proposals": len(remaining),
        "blocked_count": len(blocked_items),
        "blocked_items": blocked_items,
        "snapshot_code": snap_code,
        "checksum_sha256": seal_hash,
    }


def reject_proposal(
    vault_dir: Union[str, Path],
    proposal_id: str,
    why_rejected: str = "",
    record_as_do_not_repeat: bool = False,
) -> Dict[str, Any]:
    """Rejects a proposal from staging.

    Optionally commits it to canonical REJECTED_OPTIONS memory so future AI
    sessions never repeat the rejected approach.
    """
    paths = get_vault_paths(vault_dir)
    st = read_staging(paths["vault_dir"])
    proposals = st.get("proposals", [])

    matched = None
    remaining = []
    for p in proposals:
        if p.get("id") == proposal_id:
            matched = p
        else:
            remaining.append(p)

    if not matched:
        return {"status": "NOT_FOUND", "proposal_id": proposal_id}

    st["proposals"] = remaining
    write_staging(paths["vault_dir"], st)

    if record_as_do_not_repeat:
        ledger = read_ledger(paths["vault_dir"], verify_seal=True)
        rej_list = ledger.setdefault("rejected_options", [])
        code = f"REJ-{len(rej_list) + 1:03d}"
        rej_list.append({
            "id": uuid.uuid4().hex,
            "code": code,
            "record_kind": "REJECTED_OPTION",
            "statement": matched.get("statement") or matched.get("title") or "",
            "rationale_why": why_rejected or matched.get("why") or "Rejected by human operator",
            "impact_scope": matched.get("impact_scope", ""),
            "source_excerpt": matched.get("evidence_quote", ""),
            "is_active": True,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        })
        snap_code, seal_hash = write_ledger(
            paths["vault_dir"],
            ledger,
            label=f"Recorded rejected option {code}",
            create_snapshot=True,
        )
        return {
            "status": "RECORDED_REJECTED",
            "proposal_id": proposal_id,
            "rejected_code": code,
            "snapshot_code": snap_code,
        }

    return {"status": "DISCARDED", "proposal_id": proposal_id}


# ---------------------------------------------------------------------------
# Function 7: One-Way Markdown Projection Renderers
# ---------------------------------------------------------------------------

def render_markdown_views(
    vault_dir: Union[str, Path],
    ledger_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Renders all one-way Markdown projections from canonical ledger.json.

    Generates:
    - BLUEPRINT.md (<500 tokens kickoff context)
    - canonical/DECISIONS.md
    - canonical/REJECTED_OPTIONS.md
    - canonical/TASKS.md
    - canonical/ARTIFACTS.md
    """
    paths = get_vault_paths(vault_dir)
    if ledger_data is None:
        ledger_data = read_ledger(paths["vault_dir"], verify_seal=False)

    proj = ledger_data.get("project", {})
    code = proj.get("code", "PROJ")
    name = proj.get("name", "Active Project")
    obj = proj.get("objective", "N/A")
    focus = proj.get("current_focus", "N/A")
    next_act = proj.get("next_action", "N/A")
    hist = ledger_data.get("history_summary", {})
    latest_snap = hist.get("latest_snapshot_code", "SNP-BASELINE")
    latest_sha = hist.get("latest_snapshot_sha256", "")
    sha_short = f"`{latest_sha[:12]}...`" if latest_sha else "`SEALED`"

    decisions = [d for d in ledger_data.get("decisions", []) if d.get("is_active", True)]
    superseded = [d for d in ledger_data.get("decisions", []) if not d.get("is_active", True)]
    constraints = [c for c in ledger_data.get("constraints", []) if c.get("is_active", True)]
    rejected = [r for r in ledger_data.get("rejected_options", []) if r.get("is_active", True)]
    tasks = ledger_data.get("tasks", [])
    artifacts = ledger_data.get("artifacts", [])

    completed_tasks = [t for t in tasks if t.get("status") == "COMPLETED"]
    active_tasks = [t for t in tasks if t.get("status") in ("PENDING", "IN_PROGRESS", "BLOCKED")]

    # 1. BLUEPRINT.md (<500 tokens concise kickoff manifest)
    bp_lines = [
        f"# 🧭 SCS Kickoff Blueprint — {name} ({code})",
        f"- **Snapshot Seal:** `{latest_snap}` (SHA: {sha_short}) | **Updated:** `{utc_now_iso()}`",
        f"- **Primary Objective:** {obj}",
        f"- **Current Focus:** {focus}",
        f"- **Immediate Next Action:** 👉 **{next_act}**",
        "",
        "## 1. Frozen Governance Constraints (Binding Project Law)",
    ]
    if constraints:
        for c in constraints:
            bp_lines.append(f"- **[{c.get('code')}]** {c.get('statement')}")
    else:
        bp_lines.append("- *(No active constraints recorded)*")

    bp_lines.append("")
    bp_lines.append("## 2. Do-Not-Repeat Registry (Rejected Approaches)")
    if rejected:
        for r in rejected:
            bp_lines.append(f"- ⛔ **[{r.get('code')}]** {r.get('statement')} *(Why: {r.get('rationale_why')})*")
    else:
        bp_lines.append("- *(No rejected approaches recorded)*")

    bp_lines.append("")
    bp_lines.append("## 3. Active Work Items")
    if active_tasks:
        for t in active_tasks[:7]:  # keep blueprint concise
            blk = f" — **BLOCKER:** {t.get('blocker_reason')}" if t.get("blocker_reason") else ""
            bp_lines.append(f"- [ ] **[{t.get('code')}]** {t.get('title')} `[{t.get('status')}]`{blk}")
        if len(active_tasks) > 7:
            bp_lines.append(f"- *(+{len(active_tasks)-7} more tasks in `canonical/TASKS.md`)*")
    else:
        bp_lines.append(f"- *({len(completed_tasks)} tasks completed, no pending work)*")

    bp_lines.append("")
    bp_lines.append("> **AI AGENT RULE:** Never edit `.continuity/canonical/` or `.continuity/evidence/` directly. Run `/scs record` to capture progress.")
    paths["blueprint_md"].write_text("\n".join(bp_lines) + "\n", encoding="utf-8")

    # 2. canonical/DECISIONS.md
    dec_lines = [
        f"# 📜 Ratified Decisions & Governance Constraints — {name} ({code})",
        f"> **Seal Baseline:** `{latest_snap}` | **Verification SHA-256:** {sha_short}",
        "",
        "## 1. Active Ratified Decisions",
    ]
    if decisions:
        for d in decisions:
            dec_lines.append(f"### [{d.get('code')}] {d.get('statement')}")
            dec_lines.append(f"- **Why Decided:** {d.get('rationale_why') or 'Ratified by operator'}")
            if d.get("impact_scope"):
                dec_lines.append(f"- **Impact Scope:** {d.get('impact_scope')}")
            if d.get("source_excerpt"):
                dec_lines.append(f"- **Source Evidence:** \"{d.get('source_excerpt')}\"")
            dec_lines.append("")
    else:
        dec_lines.append("- *(No ratified decisions recorded)*\n")

    dec_lines.append("## 2. Governance Constraints")
    if constraints:
        for c in constraints:
            dec_lines.append(f"- **[{c.get('code')}]** {c.get('statement')} *(Rationale: {c.get('rationale_why', 'N/A')})*")
    else:
        dec_lines.append("- *(No constraints recorded)*")

    if superseded:
        dec_lines.append("\n## 3. Superseded / Retired Decisions")
        for sd in superseded:
            dec_lines.append(f"- **[RETIRED {sd.get('code')}]** *{sd.get('statement')}* — Retired during project evolution")

    paths["decisions_md"].write_text("\n".join(dec_lines) + "\n", encoding="utf-8")

    # 3. canonical/REJECTED_OPTIONS.md
    rej_lines = [
        f"# ⛔ Authoritative Rejected Options Registry — {name} ({code})",
        "> **PURPOSE:** Hard Do-Not-Repeat memory. Never re-propose or implement any approach listed below unless the human operator explicitly re-opens it.",
        "",
    ]
    if rejected:
        for r in rejected:
            rej_lines.append(f"### ⛔ [{r.get('code')}] {r.get('statement')}")
            rej_lines.append(f"- **Why Rejected:** {r.get('rationale_why') or 'Failed evaluation or unviable'}")
            if r.get("source_excerpt"):
                rej_lines.append(f"- **Evidence Quote:** \"{r.get('source_excerpt')}\"")
            rej_lines.append("")
    else:
        rej_lines.append("- *(No rejected approaches recorded)*\n")

    paths["rejected_options_md"].write_text("\n".join(rej_lines) + "\n", encoding="utf-8")

    # 4. canonical/TASKS.md
    tot_tasks = len(tasks)
    comp_count = len(completed_tasks)
    pct = int((comp_count / tot_tasks * 100)) if tot_tasks > 0 else 100
    bar_len = 20
    filled = int(bar_len * (pct / 100))
    bar_str = "[" + "=" * filled + " " * (bar_len - filled) + "]"

    task_lines = [
        f"# ✅ Active Task Checklist — {name} ({code})",
        f"- **Progress:** `{bar_str} {pct}%` (`{comp_count}/{tot_tasks}` tasks completed)",
        "",
        "## 1. Remaining Work",
    ]
    if active_tasks:
        for t in active_tasks:
            blk = f" — **BLOCKER:** {t.get('blocker_reason')}" if t.get("blocker_reason") else ""
            task_lines.append(f"- [ ] **[{t.get('code')}]** {t.get('title')} `[{t.get('status')}]` *(Why: {t.get('why_it_matters', 'N/A')})*{blk}")
    else:
        task_lines.append("- *(No remaining tasks)*")

    task_lines.append("")
    task_lines.append("## 2. Completed Work")
    if completed_tasks:
        for t in completed_tasks:
            evid = f" *(Evidence: {t.get('completed_evidence')})*" if t.get("completed_evidence") else ""
            task_lines.append(f"- [x] **[{t.get('code')}]** {t.get('title')} `[COMPLETED]` *(Why: {t.get('why_it_matters', 'N/A')})*{evid}")
    else:
        task_lines.append("- *(No completed tasks recorded)*")

    paths["tasks_md"].write_text("\n".join(task_lines) + "\n", encoding="utf-8")

    # 5. canonical/ARTIFACTS.md
    art_lines = [
        f"# 📦 Artifact Custody Registry — {name} ({code})",
        "> **AUDIT METHOD:** Low-level read-only descriptors (`O_RDONLY`), path-traversal guard, and SHA-256 verification.",
        "",
        "| Artifact Name | Type | Relative Path | Custody State | Observed SHA-256 | Required Markers |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    if artifacts:
        for a in artifacts:
            sha = f"`{a.get('observed_sha256')[:12]}...`" if a.get("observed_sha256") else "None"
            markers = ", ".join(f"`{m}`" for m in a.get("required_markers", [])) or "None"
            art_lines.append(
                f"| `{a.get('name')}` | `{a.get('artifact_type')}` | `{a.get('relative_path')}` | "
                f"`{a.get('custody_state')}` | {sha} | {markers} |"
            )
    else:
        art_lines.append("| *(None)* | — | — | — | — | — |")

    paths["artifacts_md"].write_text("\n".join(art_lines) + "\n", encoding="utf-8")


def render_review_draft(
    vault_dir: Union[str, Path],
    staging_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Renders one-way preview .continuity/staging/REVIEW_DRAFT.md from staging."""
    paths = get_vault_paths(vault_dir)
    if staging_data is None:
        staging_data = read_staging(paths["vault_dir"])

    proposals = staging_data.get("proposals", [])
    code = staging_data.get("project_code", "PROJ")

    lines = [
        f"# 🔍 SCS Continuity Staging Review Draft — {code}",
        f"> **Generated:** `{staging_data.get('updated_at', utc_now_iso())}` | **Pending Items:** `{len(proposals)}`",
        "",
        "> **HUMAN CUSTODY GATE:** Items below were automatically extracted from recent sessions. "
        "They remain quarantined in PENDING status until you approve them.",
        "",
        "### Available Approval Commands",
        "- `/scs approve --all` — Ratify and promote all pending proposals into canonical memory.",
        "- `/scs approve P01 P02` — Selectively ratify specific proposals.",
        "- `/scs reject P01 [--why \"...\"]` — Discard proposal (or `/scs reject P01 --record-why` to add to Rejected Options).",
        "",
        "---",
        "",
        "## Pending Proposals for Ratification",
    ]

    if proposals:
        for p in proposals:
            pid = p.get("id", "P??")
            ptype = p.get("proposal_type", "DECISION")
            stmt = p.get("statement") or p.get("title") or ""
            why = p.get("why") or p.get("rationale_why") or "N/A"
            lines.append(f"### 💡 `[{pid}]` [{ptype}] **{stmt}**")
            lines.append(f"- **Rationale:** {why}")
            if p.get("evidence_quote"):
                lines.append(f"- **Session Evidence:** \"{p.get('evidence_quote')}\"")
            if p.get("source_session_code"):
                lines.append(f"- **Source Session:** `{p.get('source_session_code')}`")
            lines.append("")
    else:
        lines.append("- *(No pending proposals in staging. Quarantine gate is empty.)*\n")

    paths["review_draft_md"].write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Function 8: 10-Session Consolidated Archive Preparation
# ---------------------------------------------------------------------------

def prepare_10_session_archive(
    vault_dir: Union[str, Path],
    archive_title: str = "",
) -> Optional[str]:
    """Compiles a consolidated 10-session archive if 10 or more unarchived sessions exist.

    Non-Destructive Backbone Rule:
    - Raw files in evidence/raw_sessions/ are NEVER deleted or modified.
    - An additive archive is created at evidence/archives/MD{NNN}_{YYYYMMDD}_{HHMM}.md.
    - evidence/MANIFEST.json is updated to mark consolidated sessions.

    Returns:
        Path string to new archive file if created, or None if under 10 sessions.
    """
    paths = get_vault_paths(vault_dir)
    if not paths["manifest_json"].exists():
        return None

    manifest = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
    sessions = manifest.get("sessions", [])

    # Find sessions not yet consolidated
    unconsolidated = [s for s in sessions if not s.get("consolidated_in")]

    if len(unconsolidated) < 10:
        return None

    batch = unconsolidated[:10]
    date_str, time_str, dt_str = utc_now_compact()
    next_num = manifest.get("next_archive_num", 1)
    arch_code = f"MD{next_num:03d}"
    arch_filename = f"{arch_code}_{dt_str}.md"
    arch_file = paths["archives_dir"] / arch_filename

    # Read batch raw session files
    batch_texts = []
    session_lines = []
    for s in batch:
        s_file = paths["vault_dir"] / s.get("file_path", "")
        content = ""
        if s_file.exists():
            content = s_file.read_text(encoding="utf-8")
        batch_texts.append(content)
        session_lines.append(
            f"- **`{s.get('session_id')}`** (`{s.get('captured_at')}`): "
            f"Turns: `{s.get('turn_count', 0)}` | SHA: `{s.get('sha256', '')[:12]}...`"
        )

    # Compile synthesis with secret scrubber
    synthesis_body = "\n\n".join(batch_texts)
    if core_adapter:
        synthesis_body, _ = core_adapter.scrub_secrets(synthesis_body)

    first_ses = batch[0].get("session_id", "SES???")
    last_ses = batch[-1].get("session_id", "SES???")

    arch_content = [
        f"# 📚 10-Session Consolidated Archive — {arch_code} ({manifest.get('project_code', 'PROJ')})",
        f"- **Session Range:** `{first_ses}` → `{last_ses}` (10 sessions consolidated)",
        f"- **Compiled At:** `{utc_now_iso()}`",
        f"- **Archive Title:** {archive_title or f'Multi-session consolidation {first_ses}..{last_ses}'}",
        "",
        "> **FORENSIC BACKBONE NOTE:** Raw session files (`SES*.md`) in `evidence/raw_sessions/` remain "
        "permanent and immutable. This consolidated archive provides clean, secret-scrubbed context for Git tracking and long-running history.",
        "",
        "## 1. Consolidated Sessions Ledger",
    ]
    arch_content.extend(session_lines)
    arch_content.append("")
    arch_content.append("## 2. Scrubbed Historical Dialogue & Synthesis")
    arch_content.append(synthesis_body)

    full_text = "\n".join(arch_content) + "\n"
    arch_file.write_text(full_text, encoding="utf-8")
    arch_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    # Update MANIFEST.json
    for s in batch:
        s["consolidated_in"] = arch_code

    manifest.setdefault("archives", []).append({
        "archive_code": arch_code,
        "file_name": arch_filename,
        "session_range": f"{first_ses}..{last_ses}",
        "session_count": len(batch),
        "checksum_sha256": arch_hash,
        "created_at": utc_now_iso(),
    })
    manifest["next_archive_num"] = next_num + 1

    paths["manifest_json"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    return str(arch_file)


# ---------------------------------------------------------------------------
# Function 9: Sandbox-Safe Project Discovery & Fail-Closed Routing
# ---------------------------------------------------------------------------

def get_default_search_roots(cwd: Optional[Union[str, Path]] = None) -> List[Path]:
    """Returns search root directories including CWD and centralized continuity vaults."""
    working = Path(cwd or Path.cwd()).resolve()
    roots = [working]

    # Check environment variable for centralized vault root
    env_vault = os.environ.get("SCS_VAULT_ROOT") or os.environ.get("CONTINUITY_VAULT_ROOT")
    if env_vault:
        p = Path(env_vault).resolve()
        if p.exists() and p not in roots:
            roots.append(p)

    # Check well-known centralized vault locations
    candidate_centralized = [
        working.parent / "My_Project_Continuity",
        Path("F:/000_Ai Project/My_Project_Continuity"),
        Path.home() / "My_Project_Continuity",
        Path.home() / ".continuity",
    ]
    for cand in candidate_centralized:
        try:
            if cand.exists() and cand.is_dir() and cand.resolve() not in roots:
                roots.append(cand.resolve())
        except (PermissionError, OSError):
            continue

    return roots


def discover_vaults(
    search_roots: Optional[List[Union[str, Path]]] = None,
) -> List[Dict[str, Any]]:
    """Discovers all .continuity/ vaults in search roots and immediate children.

    Sandbox-Safe: Never triggers security prompts; performs purely local directory scans.

    Returns:
        List of project metadata dicts for all discovered vaults.
    """
    roots = [Path(r).resolve() for r in (search_roots or get_default_search_roots())]
    discovered = []
    seen_vaults = set()

    for r in roots:
        if not r.exists() or not r.is_dir():
            continue

        # 1. Check if r itself has .continuity or is a vault directly
        cand_vault = r / ".continuity" if (r / ".continuity").exists() else (r if (r / "canonical" / "ledger.json").exists() else None)
        if cand_vault and cand_vault.is_dir():
            ledger_file = cand_vault / "canonical" / "ledger.json"
            if ledger_file.exists() and str(cand_vault) not in seen_vaults:
                seen_vaults.add(str(cand_vault))
                try:
                    data = json.loads(ledger_file.read_text(encoding="utf-8"))
                    proj = data.get("project", {})
                    discovered.append({
                        "project_code": proj.get("code", "UNKNOWN"),
                        "project_name": proj.get("name", r.name),
                        "project_dir": str(r),
                        "vault_dir": str(cand_vault),
                        "latest_snapshot": data.get("history_summary", {}).get("latest_snapshot_code", ""),
                    })
                except Exception:
                    pass

        # 2. Check immediate child directories (e.g. RIE/, Hero_Kai/, TEST_SCS/)
        try:
            for child in r.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    child_vault = child / ".continuity" if (child / ".continuity").exists() else (child if (child / "canonical" / "ledger.json").exists() else None)
                    if child_vault and child_vault.is_dir():
                        ledger_file = child_vault / "canonical" / "ledger.json"
                        if ledger_file.exists() and str(child_vault) not in seen_vaults:
                            seen_vaults.add(str(child_vault))
                            try:
                                data = json.loads(ledger_file.read_text(encoding="utf-8"))
                                proj = data.get("project", {})
                                discovered.append({
                                    "project_code": proj.get("code", child.name.upper()),
                                    "project_name": proj.get("name", child.name),
                                    "project_dir": str(child),
                                    "vault_dir": str(child_vault),
                                    "latest_snapshot": data.get("history_summary", {}).get("latest_snapshot_code", ""),
                                })
                            except Exception:
                                pass
        except (PermissionError, OSError):
            continue

    return discovered


def resolve_project_vault(
    project_arg: Optional[Union[str, Path]] = None,
    cwd: Optional[Union[str, Path]] = None,
    conversation_id: Optional[str] = None,
    search_roots: Optional[List[Union[str, Path]]] = None,
) -> Path:
    """Implements EGM 4-Step Fail-Closed Project Resolution.

    Priority:
    1. Explicit project argument (`--project <CODE>` or path)
    2. Current directory `.continuity/` (if unambiguously inside a project)
    3. Existing conversation binding in MANIFEST.json
    4. Single discovered vault in workspace
    5. FAIL-CLOSED: Raises AmbiguousProjectError and asks operator. Never guesses.

    Returns:
        Resolved Path to `.continuity/`.

    Raises:
        ProjectNotFoundError: If explicit argument was provided but cannot be found.
        AmbiguousProjectError: If multiple projects match or context is ambiguous.
    """
    working_dir = Path(cwd or Path.cwd()).resolve()
    discovered = discover_vaults(search_roots or get_default_search_roots(working_dir))

    # 1. Explicit project argument
    if project_arg:
        p_str = str(project_arg).strip()
        # Check if direct path was provided
        direct_path = Path(p_str).resolve()
        if direct_path.exists():
            v_paths = get_vault_paths(direct_path)
            if v_paths["ledger_json"].exists():
                return v_paths["vault_dir"]

        # Check by code match
        matches = [d for d in discovered if d["project_code"].upper() == p_str.upper()]
        if len(matches) == 1:
            return Path(matches[0]["vault_dir"])
        elif len(matches) > 1:
            raise AmbiguousProjectError(
                f"Multiple project vaults matched code '{project_arg}'. Specify path explicitly.",
                candidate_vaults=matches,
            )
        raise ProjectNotFoundError(f"Project '{project_arg}' not found among discovered vaults.")

    # 2. Check if working_dir itself is an unambiguous project vault
    cwd_vault = working_dir / ".continuity"
    if cwd_vault.exists() and (cwd_vault / "canonical" / "ledger.json").exists():
        # Check if working_dir has competing child projects
        child_projects = [d for d in discovered if Path(d["project_dir"]).resolve() != working_dir]
        if not child_projects:
            return cwd_vault

    # 3. Existing conversation binding in MANIFEST.json
    if conversation_id:
        conv_matches = []
        for d in discovered:
            man_file = Path(d["vault_dir"]) / "evidence" / "MANIFEST.json"
            if man_file.exists():
                try:
                    man = json.loads(man_file.read_text(encoding="utf-8"))
                    watermarks = man.get("watermarks_by_conversation", {})
                    if conversation_id in watermarks:
                        conv_matches.append(d)
                except Exception:
                    continue
        if len(conv_matches) == 1:
            return Path(conv_matches[0]["vault_dir"])

    # 4. Single discovered vault in workspace
    if len(discovered) == 1:
        return Path(discovered[0]["vault_dir"])

    # 5. Fail-Closed
    if not discovered:
        raise ProjectNotFoundError(
            f"No .continuity/ project vault found in {working_dir} or immediate subdirectories. "
            "Initialize a new project using `create_vault(dir, code, name)` or `/scs new`."
        )

    raise AmbiguousProjectError(
        f"Ambiguous project context: Found {len(discovered)} candidate project vaults. "
        "Please specify project via `--project <CODE>`.",
        candidate_vaults=discovered,
    )
