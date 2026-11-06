"""
SCS_AG_v2 Unified Command-Line Interface (engine/scs_cli.py)
=============================================================

Governing Principles:
1. "Preserve the brain, replace the communication channel."
2. "Human custody authority — no unratified AI proposals bypass the staging gate."
3. "Fail-closed multi-project routing — never guess or contaminate projects."
4. "Cryptographic deterministic sealing with instant rollback."

This module is the unified entrypoint for all SCS operations in Antigravity:
  new, list, switch, record, status, approve, reject, handover, rollback, ui
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Import sibling modules
# ---------------------------------------------------------------------------

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import core_adapter
import vault_store
import transcript_reader

# ---------------------------------------------------------------------------
# Reconfigure stdout/stderr for Windows UTF-8 console safety
# ---------------------------------------------------------------------------

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OK_SYM = "[OK]"
ERR_SYM = "[X]"


def auto_detect_conversation_id(app_data_dir: Optional[Union[str, Path]] = None) -> str:
    """Auto-detects active conversation ID from environment or brain directory."""
    if "CONVERSATION_ID" in os.environ:
        return os.environ["CONVERSATION_ID"]

    app_data = Path(app_data_dir).resolve() if app_data_dir else transcript_reader.get_default_app_data_dir()
    brain_dir = app_data / "brain"
    if not brain_dir.exists():
        return ""

    accessible = []
    try:
        for d in brain_dir.iterdir():
            try:
                t_file = d / ".system_generated" / "logs" / "transcript.jsonl"
                if t_file.exists():
                    accessible.append((d.name, t_file.stat().st_mtime))
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    if accessible:
        accessible.sort(key=lambda x: x[1], reverse=True)
        return accessible[0][0]
    return ""


# ---------------------------------------------------------------------------
# CLI Command Handlers
# ---------------------------------------------------------------------------

def cmd_new(args: argparse.Namespace) -> int:
    """Scaffolds a new project continuity vault (.continuity/)."""
    target_dir = Path(args.path or Path.cwd()).resolve()

    # Dual syntax support: positional arguments OR --code / --name flags
    flag_code = getattr(args, "flag_code", None)
    flag_name = getattr(args, "flag_name", None)
    pos_code = getattr(args, "pos_code", None) or getattr(args, "code", None)
    pos_name = getattr(args, "pos_name", None) or getattr(args, "name", None)

    if flag_code and not flag_name and pos_code and not pos_name:
        code = flag_code
        name = pos_code
    elif flag_name and not flag_code and pos_code and not pos_name:
        code = pos_code
        name = flag_name
    else:
        code = flag_code or pos_code or ""
        name = flag_name or pos_name or ""

    code = str(code).strip().upper()
    name = str(name).strip()

    if not code or not name:
        print(f"{ERR_SYM} Error creating vault: Both project code and project name are required.", file=sys.stderr)
        print("Usage: scs new <CODE> \"<Name>\" OR scs new --code <CODE> --name \"<Name>\"", file=sys.stderr)
        return 1

    # Keep args attributes synchronized for downstream callers
    args.code = code
    args.name = name

    # Determine source repository roots (logically separated from vault)
    repo_dirs = None
    if getattr(args, "repo", None):
        repo_dirs = [str(Path(args.repo).resolve())]
    elif target_dir != Path.cwd().resolve():
        # Centralized vault architecture: target_dir is the vault, cwd is the repo!
        repo_dirs = [str(Path.cwd().resolve())]

    print(f"Creating continuity vault for {name} ({code}) at: {target_dir}...")
    try:
        vault_path = vault_store.create_vault(
            project_dir=target_dir,
            project_code=code,
            project_name=name,
            objective=args.objective or "",
            current_focus=args.focus or "",
            next_action=args.next_action or "",
            root_paths=repo_dirs,
        )
        is_valid, seal, _ = vault_store.verify_seal(vault_path)
        print(f"{OK_SYM} Successfully created {vault_path.name} vault.")
        print(f"  Project Code:  {code}")
        print(f"  Baseline Seal: {seal[:16]}... (Valid: {is_valid})")
        print(f"  Kickoff File:  {vault_path / 'BLUEPRINT.md'}")
        print(f"  Workspace Rule:{vault_path.parent / 'GEMINI.md'}")
        return 0
    except Exception as exc:
        print(f"{ERR_SYM} Error creating vault: {exc}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """Lists all discovered project continuity vaults."""
    search_roots = [Path(args.root).resolve()] if args.root else None
    discovered = vault_store.discover_vaults(search_roots)

    if not discovered:
        print("No .continuity/ vaults discovered in current workspace.")
        print("To create a project vault, run: /scs new <CODE> \"<Name>\"")
        return 0

    print(f"Discovered {len(discovered)} Continuity Vault(s):\n")
    print(f"{'CODE':<12} {'NAME':<24} {'LATEST SEAL':<18} {'VAULT PATH'}")
    print("-" * 80)
    for d in discovered:
        code = d["project_code"]
        name = d["project_name"][:22]
        snap = d["latest_snapshot"] or "BASELINE"
        p_path = d["project_dir"]
        print(f"{code:<12} {name:<24} {snap:<18} {p_path}")
    print()
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    """Binds active conversation to a specific project vault."""
    code = args.code.strip().upper()
    try:
        vault_path = vault_store.resolve_project_vault(project_arg=code)
        ledger = vault_store.read_ledger(vault_path, verify_seal=False)
        p = ledger.get("project", {})
        print(f"{OK_SYM} Switched active context to project: {p.get('name')} ({p.get('code')})")
        print(f"  Vault:         {vault_path}")
        print(f"  Current Focus: {p.get('current_focus', 'N/A')}")
        print(f"  Next Action:   👉 {p.get('next_action', 'N/A')}")
        return 0
    except vault_store.AmbiguousProjectError as exc:
        print(f"{ERR_SYM} Ambiguous project selection: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"{ERR_SYM} Could not switch project: {exc}", file=sys.stderr)
        return 1


def cmd_record(args: argparse.Namespace) -> int:
    """Captures conversation dialogue into an immutable SES file and stages Caveman proposals."""
    file_arg = getattr(args, "file_path", None)
    file_p = None
    if file_arg:
        file_p = Path(file_arg).resolve()
        if not file_p.exists() or not file_p.is_file():
            print(f"{ERR_SYM} Input file not found or not readable: {file_arg}", file=sys.stderr)
            return 1
        conv_id = getattr(args, "conv_id", None) or f"file-{hashlib.sha256(file_p.name.encode('utf-8')).hexdigest()[:12]}"
    else:
        conv_id = getattr(args, "conv_id", None) or auto_detect_conversation_id(args.app_data)
        if not conv_id:
            print(f"{ERR_SYM} Missing conversation ID. Provide via --conv-id <UUID>, --file <PATH>, or CONVERSATION_ID env var.", file=sys.stderr)
            return 1

    proj_arg = getattr(args, "project_flag", None) or getattr(args, "project", None)
    args.project = proj_arg

    try:
        vault_path = vault_store.resolve_project_vault(
            project_arg=proj_arg,
            conversation_id=conv_id,
        )
    except vault_store.AmbiguousProjectError as exc:
        print(f"{ERR_SYM} Ambiguous project routing:\n{exc}", file=sys.stderr)
        print("Please specify project via: /scs record <PROJECT_CODE>", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"{ERR_SYM} Error resolving project vault: {exc}", file=sys.stderr)
        return 1

    # 1. Capture session evidence & watermark slicing
    if file_p:
        print(f"Recording markdown session file `{file_p.name}` into vault: {vault_path.parent.name}...")
        capture_res = transcript_reader.capture_markdown_file_evidence(
            vault_dir=vault_path,
            file_path=file_p,
            conversation_id=conv_id,
        )
    else:
        print(f"Recording conversation `{conv_id[:8]}...` into vault: {vault_path.parent.name}...")
        capture_res = transcript_reader.capture_session_evidence(
            vault_dir=vault_path,
            conversation_id=conv_id,
            app_data_dir=args.app_data,
        )

    if not capture_res.get("captured"):
        print(f"ℹ No new dialogue turns recorded ({capture_res.get('reason')}).")
        return 0

    ses_id = capture_res["session_id"]
    turn_count = capture_res["turn_count"]
    print(f"{OK_SYM} Captured {turn_count} turns into raw evidence: {capture_res['file_name']}")

    # 2. Ingest dialogue with Caveman Context Extraction Engine
    dialogue = capture_res.get("dialogue_text", "")
    ledger = vault_store.read_ledger(vault_path, verify_seal=False)
    proj = ledger.get("project", {})
    proj_code = proj.get("code", "PROJ")
    root_paths = proj.get("root_paths", [str(vault_path.parent)])

    extracted = core_adapter.extract_context(
        fragments=dialogue,
        project_code=proj_code,
        active_focus=proj.get("current_focus", ""),
        active_next=proj.get("next_action", ""),
        session_codes=[ses_id],
        root_paths=root_paths,
    )

    # 3. Transform extracted items into candidate proposals for staging quarantine
    author_val = getattr(args, "author", None)
    candidate_proposals: List[Dict[str, Any]] = []

    # Decisions
    for d in extracted.decisions:
        p_dict = {
            "proposal_type": "DECISION",
            "statement": getattr(d, "title", str(d)),
            "why": getattr(d, "reasoning", "Extracted causal decision"),
            "impact_scope": getattr(d, "alternatives_considered", ""),
            "evidence_quote": getattr(d, "evidence_quote", ""),
            "source_session_code": ses_id,
        }
        if author_val:
            p_dict["author"] = author_val
        candidate_proposals.append(p_dict)

    # Constraints
    for c in extracted.constraints:
        candidate_proposals.append({
            "proposal_type": "CONSTRAINT",
            "statement": c,
            "why": "Governance constraint",
            "source_session_code": ses_id,
        })

    # Rejected options
    for r in extracted.rejected_options:
        candidate_proposals.append({
            "proposal_type": "REJECTED_OPTION",
            "statement": r.get("statement", ""),
            "why": r.get("why", "Rejected alternative"),
            "source_session_code": ses_id,
        })

    # Tasks (Pending & Verified Completed)
    for t in extracted.pending_tasks:
        candidate_proposals.append({
            "proposal_type": "TASK",
            "statement": t.get("title", ""),
            "why": t.get("why_it_matters", ""),
            "task_status": t.get("status") or t.get("task_status", "PENDING"),
            "priority": t.get("priority", "MEDIUM"),
            "completed_by_verification": t.get("completed_by_verification", False),
            "completed_evidence": t.get("completed_evidence", ""),
            "source_session_code": ses_id,
        })
    for t in extracted.completed_tasks:
        candidate_proposals.append({
            "proposal_type": "TASK",
            "statement": t.get("title", ""),
            "why": t.get("why_it_matters", ""),
            "task_status": "COMPLETED",
            "priority": t.get("priority", "MEDIUM"),
            "completed_by_verification": t.get("completed_by_verification", True),
            "completed_evidence": t.get("completed_evidence", "Verified completed on disk"),
            "source_session_code": ses_id,
        })

    # Artifacts
    for a in extracted.artifacts:
        candidate_proposals.append({
            "proposal_type": "ARTIFACT",
            "statement": a.get("path", ""),
            "name": a.get("path", "").split("/")[-1],
            "relative_path": a.get("path", ""),
            "source_session_code": ses_id,
        })

    staged_count = 0
    if candidate_proposals:
        staged_count = vault_store.append_staging_proposals(vault_path, candidate_proposals)
        print(f"{OK_SYM} Staged {staged_count} candidate proposal(s) in quarantine gate (.continuity/staging/).")
        print("  Run `/scs status` to inspect proposals, or `/scs approve --all` to ratify.")
    else:
        print("ℹ No new architectural proposals extracted from this session.")

    if capture_res.get("archive_triggered"):
        print(f"🎉 10-Session milestone reached! Consolidated archive generated: {capture_res.get('archive_file')}")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Displays comprehensive project health, seal verification, tasks, and ASCII flowcharts."""
    conv_id = args.conv_id or os.environ.get("CONVERSATION_ID", "")
    proj_arg = getattr(args, "project_flag", None) or getattr(args, "project", None)
    args.project = proj_arg
    try:
        vault_path = vault_store.resolve_project_vault(
            project_arg=proj_arg,
            conversation_id=conv_id,
        )
    except Exception as exc:
        print(f"{ERR_SYM} Error resolving project vault: {exc}", file=sys.stderr)
        return 1

    # 1. Cryptographic Seal Verification
    is_valid, computed_sha, expected_sha = vault_store.verify_seal(vault_path)
    ledger = vault_store.read_ledger(vault_path, verify_seal=False)
    proj = ledger.get("project", {})
    hist = ledger.get("history_summary", {})
    staging = vault_store.read_staging(vault_path)
    proposals = staging.get("proposals", [])

    seal_badge = f"{OK_SYM} [SEAL INTACT]" if is_valid else f"{ERR_SYM} [SEAL TAMPER DETECTED]"
    snap_code = hist.get("latest_snapshot_code", "SNP-BASELINE")

    print("=" * 80)
    print(f"🧭 SCS CONTINUITY STATUS — {proj.get('name')} ({proj.get('code')})")
    print("=" * 80)
    print(f"Status:            {seal_badge} (Snapshot: {snap_code})")
    print(f"SHA-256 Checksum:  {computed_sha[:16]}... (Expected: {expected_sha[:16]}...)")
    print(f"Primary Objective: {proj.get('objective', 'N/A')}")
    print(f"Current Focus:     {proj.get('current_focus', 'N/A')}")
    print(f"Next Action:       👉 {proj.get('next_action', 'N/A')}")
    print()

    # ASCII Workflow Diagram
    print("Continuity Workflow Engine:")
    print("  [Transcript] ──► [SES Evidence] ──► [Staging Quarantine] ──► [Human Custody] ──► [Canonical SSOT]")
    print(f"                   ({len(hist.get('total_sessions', 0) if isinstance(hist.get('total_sessions'), list) else [1])} sessions)         ({len(proposals)} pending items)         (Ratified)        (Sealed)")
    print()

    # 2. Pending Proposals in Staging Quarantine
    if proposals:
        print(f"⏳ Pending Proposals in Quarantine Gate ({len(proposals)} item(s) awaiting approval):")
        for p in proposals:
            pid = p.get("id")
            ptype = p.get("proposal_type", "DECISION")
            stmt = p.get("statement") or p.get("title") or ""
            print(f"  • [{pid}] [{ptype}] {stmt}")
        print("  👉 Action: Run `/scs approve --all` to ratify, or `/scs approve <ID>`.")
        print()

    # 3. Tasks Checklist
    tasks = ledger.get("tasks", [])
    completed_tasks = [t for t in tasks if t.get("status") == "COMPLETED"]
    active_tasks = [t for t in tasks if t.get("status") in ("PENDING", "IN_PROGRESS", "BLOCKED")]
    tot_t = len(tasks)
    pct = int((len(completed_tasks) / tot_t * 100)) if tot_t > 0 else 100
    bar_len = 20
    filled = int(bar_len * (pct / 100))
    bar_str = "[" + "=" * filled + " " * (bar_len - filled) + "]"

    print(f"📋 Task Checklist {bar_str} {pct}% ({len(completed_tasks)}/{tot_t} completed):")
    if active_tasks:
        for t in active_tasks:
            blk = f" — BLOCKER: {t.get('blocker_reason')}" if t.get("blocker_reason") else ""
            print(f"  [ ] [{t.get('code')}] {t.get('title')} ({t.get('status')}){blk}")
    else:
        print(f"  {OK_SYM} All active tasks completed.")
    if completed_tasks:
        print(f"  ✓ {len(completed_tasks)} task(s) verified completed on disk.")
    print()

    # 4. Ratified Decisions
    decisions = [d for d in ledger.get("decisions", []) if d.get("is_active", True)]
    print(f"📜 Ratified Decisions ({len(decisions)}):")
    if decisions:
        for d in decisions[:5]:
            print(f"  • [{d.get('code')}] {d.get('statement')}")
            print(f"    Why: {d.get('rationale_why')}")
        if len(decisions) > 5:
            print(f"    (+{len(decisions)-5} more in .continuity/canonical/DECISIONS.md)")
    else:
        print("  (None recorded yet)")
    print()

    # 5. Rejected Options
    rejected = [r for r in ledger.get("rejected_options", []) if r.get("is_active", True)]
    if rejected:
        print(f"⛔ Authoritative Do-Not-Repeat Registry ({len(rejected)}):")
        for r in rejected:
            print(f"  • ⛔ [{r.get('code')}] {r.get('statement')} (Why: {r.get('rationale_why')})")
        print()

    return 0 if is_valid else 2


def cmd_approve(args: argparse.Namespace) -> int:
    """Ratifies staged proposals and commits them to canonical SSOT memory."""
    try:
        conv_id = getattr(args, "conv_id", None) or auto_detect_conversation_id()
        project_flag = getattr(args, "project_flag", None) or getattr(args, "project", None)
        raw_proposals = list(getattr(args, "proposals", []) or [])
        is_all = getattr(args, "all", False)

        project_arg = project_flag
        p_ids = raw_proposals

        # If --project was not supplied, inspect first positional argument
        if not project_arg and raw_proposals:
            first_token = raw_proposals[0]
            if is_all:
                project_arg = first_token
                p_ids = []
            else:
                cand_path = Path(first_token).resolve()
                is_dir = cand_path.exists() and (cand_path.is_dir() or (cand_path / ".continuity").exists())
                known_codes = {d["project_code"].upper() for d in vault_store.discover_vaults()}
                if is_dir or first_token.upper() in known_codes:
                    project_arg = first_token
                    p_ids = raw_proposals[1:]

        args.project = project_arg
        args.proposals = p_ids

        vault_path = vault_store.resolve_project_vault(project_arg=project_arg, conversation_id=conv_id)
        staging = vault_store.read_staging(vault_path)
        staging_proposals = staging.get("proposals", [])

        # FDB-101-005: Expand comma-separated tokens (e.g. 1,2,3) and resolve 1-based numeric indices
        expanded_p_ids = []
        if p_ids:
            for item in p_ids:
                sub_tokens = [t.strip() for t in str(item).split(",") if t.strip()]
                for tok in sub_tokens:
                    matched_id = None
                    for p in staging_proposals:
                        if str(p.get("id", "")).strip().lower() == tok.lower():
                            matched_id = p.get("id")
                            break
                    if matched_id:
                        expanded_p_ids.append(matched_id)
                    elif tok.isdigit():
                        idx = int(tok) - 1
                        if 0 <= idx < len(staging_proposals):
                            expanded_p_ids.append(staging_proposals[idx].get("id", tok))
                        else:
                            expanded_p_ids.append(tok)
                    else:
                        expanded_p_ids.append(tok)
            p_ids = expanded_p_ids

        p_ids_to_promote = p_ids if not is_all else None
        force = getattr(args, "force", False)
        author_arg = getattr(args, "author", None)

        res = vault_store.promote_proposals(
            vault_dir=vault_path,
            proposal_ids=p_ids_to_promote,
            promote_all=is_all or (not p_ids_to_promote),
            label=args.label or "Human custody approval",
            allow_unverified=force,
            author=author_arg,
        )

        if res.get("blocked_count", 0) > 0:
            print(f"⚠️ {res['blocked_count']} proposal(s) blocked by Phase 1.6 quality invariants:")
            for b in res.get("blocked_items", []):
                stmt = b.get("statement") or b.get("title") or ""
                print(f"  • [{b.get('id')}] [{b.get('proposal_type')}] '{stmt[:60]}' — Reason: {b.get('blocked_reason')}")
            print("  👉 Use `/scs approve --force --all` if you explicitly intend to ratify these items.")

        if res.get("promoted_count", 0) == 0:
            print("ℹ No proposals were promoted.")
            return 0

        print(f"{OK_SYM} Ratified and promoted {res['promoted_count']} item(s) to canonical memory:")
        print(f"  Decisions:   +{res.get('promoted_decisions', 0)}")
        print(f"  Constraints: +{res.get('promoted_constraints', 0)}")
        print(f"  Tasks:       +{res.get('promoted_tasks', 0)}")
        print(f"  Rejected:    +{res.get('promoted_rejected', 0)}")
        print(f"  New Seal:    {res['snapshot_code']} (SHA: {res['checksum_sha256'][:16]}...)")
        print(f"  Updated:     .continuity/BLUEPRINT.md and .continuity/canonical/*.md")
        return 0
    except Exception as exc:
        print(f"{ERR_SYM} Error approving proposals: {exc}", file=sys.stderr)
        return 1


def cmd_reject(args: argparse.Namespace) -> int:
    """Discards a staged proposal, optionally recording it to Do-Not-Repeat memory."""
    try:
        conv_id = getattr(args, "conv_id", None) or auto_detect_conversation_id()
        project_flag = getattr(args, "project_flag", None) or getattr(args, "project", None)
        pos1 = getattr(args, "pos_arg1", None) or getattr(args, "proposal_id", None)
        pos2 = getattr(args, "pos_arg2", None)
        is_all = getattr(args, "all", False)
        is_yes = getattr(args, "yes", False)

        if pos1 and pos2:
            project_arg = project_flag or pos1
            p_id = str(pos2).strip()
        else:
            if is_all:
                project_arg = project_flag or pos1
                p_id = ""
            else:
                project_arg = project_flag
                p_id = str(pos1).strip() if pos1 else ""

        args.project = project_arg
        args.proposal_id = p_id

        if not is_all and not p_id:
            print(f"{ERR_SYM} Error rejecting proposal: Proposal ID or --all required.", file=sys.stderr)
            return 1

        vault_path = vault_store.resolve_project_vault(project_arg=project_arg, conversation_id=conv_id)
        staging = vault_store.read_staging(vault_path)
        staging_proposals = staging.get("proposals", [])

        # FDB-101-005: Bulk discard staged proposals
        if is_all:
            count = len(staging_proposals)
            if count == 0:
                print("ℹ Staging quarantine is already empty. No proposals to discard.")
                return 0

            if not is_yes:
                try:
                    answer = input(f"Are you sure you want to discard all {count} staged proposal(s)? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\nOperation cancelled.")
                    return 1
                if answer not in ("y", "yes"):
                    print("Operation cancelled.")
                    return 0

            if getattr(args, "record_why", False):
                recorded_count = 0
                for p in staging_proposals:
                    p_code = p.get("id")
                    if p_code:
                        vault_store.reject_proposal(
                            vault_dir=vault_path,
                            proposal_id=p_code,
                            why_rejected=args.why or "Bulk rejected by operator",
                            record_as_do_not_repeat=True,
                        )
                        recorded_count += 1
                print(f"{OK_SYM} Discarded and permanently recorded {recorded_count} proposal(s) into Do-Not-Repeat memory.")
                return 0
            else:
                staging["proposals"] = []
                staging["updated_at"] = vault_store.utc_now_iso()
                vault_store.write_staging(vault_path, staging)
                print(f"{OK_SYM} Discarded all {count} proposal(s) from staging quarantine.")
                return 0

        # Single proposal rejection: resolve exact ID or 1-based index
        matched_id = None
        for p in staging_proposals:
            if str(p.get("id", "")).strip().lower() == p_id.lower():
                matched_id = p.get("id")
                break
        if not matched_id and p_id.isdigit():
            idx = int(p_id) - 1
            if 0 <= idx < len(staging_proposals):
                p_id = staging_proposals[idx].get("id", p_id)
        elif matched_id:
            p_id = matched_id

        res = vault_store.reject_proposal(
            vault_dir=vault_path,
            proposal_id=p_id,
            why_rejected=args.why or "",
            record_as_do_not_repeat=args.record_why,
        )
        if res.get("status") == "NOT_FOUND":
            print(f"{ERR_SYM} Proposal {p_id} not found in staging quarantine.", file=sys.stderr)
            return 1

        if res.get("status") == "RECORDED_REJECTED":
            print(f"{OK_SYM} Discarded {p_id} and permanently recorded into Do-Not-Repeat memory:")
            print(f"  Code: {res.get('rejected_code')} (Recorded in .continuity/canonical/REJECTED_OPTIONS.md)")
        else:
            print(f"{OK_SYM} Discarded proposal {p_id} from staging quarantine.")
        return 0
    except Exception as exc:
        print(f"{ERR_SYM} Error rejecting proposal: {exc}", file=sys.stderr)
        return 1


def cmd_handover(args: argparse.Namespace) -> int:
    """Generates cross-AI restoration handover package and fast recovery card."""
    try:
        conv_id = getattr(args, "conv_id", None) or auto_detect_conversation_id()
        proj_arg = getattr(args, "project_flag", None) or getattr(args, "project", None)
        args.project = proj_arg
        vault_path = vault_store.resolve_project_vault(project_arg=proj_arg, conversation_id=conv_id)
        ledger = vault_store.read_ledger(vault_path, verify_seal=True)
        proj = ledger.get("project", {})
        proj_code = proj.get("code", "PROJ")

        # 1. Run physical artifact custody reconciliation
        artifacts = ledger.get("artifacts", [])
        configured_roots = proj.get("root_paths", [str(vault_path.parent)])
        all_roots = list(configured_roots)
        if str(vault_path) not in all_roots:
            all_roots.append(str(vault_path))
        if str(vault_path.parent) not in all_roots:
            all_roots.append(str(vault_path.parent))

        rec_summary = core_adapter.reconcile_artifacts(
            artifacts=artifacts,
            root_paths=all_roots,
        )

        # 2. Gather approved continuity chapter archives
        paths = vault_store.get_vault_paths(vault_path)
        manifest = {}
        if paths["manifest_json"].exists():
            manifest = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))

        chapters: List[Dict[str, Any]] = []
        for arch in manifest.get("archives", []):
            arch_file = paths["archives_dir"] / arch.get("file_name", "")
            if arch_file.exists():
                chapters.append({
                    "chapter_code": arch.get("archive_code"),
                    "markdown_content": arch_file.read_text(encoding="utf-8"),
                    "snapshot_code": "SEALED",
                    "created_at": arch.get("created_at"),
                })

        total_sessions = len(manifest.get("sessions", []))
        session_counts = {
            "total_sessions": total_sessions,
            "processed_sessions": total_sessions,
            "pending_sessions": 0,
        }

        # 3. Compile Master AI Handover Package
        snapshots = vault_store.list_snapshots(vault_path)
        latest_snap_code = snapshots[-1]["snapshot_code"] if snapshots else "SNP-BASELINE"
        latest_snap_sha = snapshots[-1]["checksum_sha256"] if snapshots else ("0" * 64)

        snapshot_mock = {
            "snapshot_code": latest_snap_code,
            "checksum_sha256": latest_snap_sha,
            "state_json": json.dumps(ledger, indent=2, sort_keys=True),
        }

        all_decision_records = (
            ledger.get("decisions", [])
            + ledger.get("constraints", [])
            + ledger.get("rejected_options", [])
        )

        handover_res = core_adapter.generate_handover_context(
            project=proj,
            snapshot=snapshot_mock,
            decisions=all_decision_records,
            tasks=ledger.get("tasks", []),
            artifacts=artifacts,
            chapters=chapters,
            session_counts=session_counts,
        )

        # 4. Save to .continuity/handover/
        handover_dir = paths["handover_dir"]
        handover_dir.mkdir(parents=True, exist_ok=True)

        ho_file = handover_dir / f"{proj_code}_AI_HANDOVER_PACKAGE.md"
        ho_file.write_text(handover_res["handover_content"], encoding="utf-8")

        rec_file = handover_dir / f"{proj_code}_PROJECT_RECOVERY_CARD.md"
        rec_file.write_text(handover_res["recovery_card_content"], encoding="utf-8")

        print(f"{OK_SYM} Generated Master AI Continuity Restoration Package:")
        print(f"  Package:       {ho_file} ({handover_res['protocol_version']})")
        print(f"  Recovery Card: {rec_file}")
        print(f"  Checksum SHA:  {handover_res['checksum_sha256'][:16]}...")
        print(f"  Artifacts:     {rec_summary['verified_count']}/{rec_summary['total_artifacts']} verified physically")
        return 0
    except Exception as exc:
        print(f"{ERR_SYM} Error generating handover package: {exc}", file=sys.stderr)
        return 1


def cmd_rollback(args: argparse.Namespace) -> int:
    """Restores canonical SSOT state from a previously sealed snapshot."""
    project_flag = getattr(args, "project_flag", None) or getattr(args, "project", None)
    snapshot_flag = getattr(args, "snapshot_flag", None)
    pos1 = getattr(args, "pos_arg1", None) or getattr(args, "snapshot_code", None)
    pos2 = getattr(args, "pos_arg2", None)

    snap_code = snapshot_flag
    project_arg = project_flag

    if pos1 and pos2:
        project_arg = project_arg or pos1
        snap_code = snap_code or pos2
    elif pos1:
        if snapshot_flag:
            project_arg = project_arg or pos1
        elif str(pos1).upper().startswith("SNP-"):
            snap_code = pos1
        else:
            if project_arg:
                snap_code = pos1
            else:
                snap_code = pos1

    snap_code = (snap_code or "").strip()
    if not snap_code:
        print(f"{ERR_SYM} Error executing rollback: Snapshot code required. Provide as positional argument or via `--snapshot <CODE>`.", file=sys.stderr)
        return 1

    args.project = project_arg
    args.snapshot_code = snap_code

    try:
        conv_id = getattr(args, "conv_id", None) or auto_detect_conversation_id()
        vault_path = vault_store.resolve_project_vault(project_arg=project_arg, conversation_id=conv_id)
        res = vault_store.rollback_to_snapshot(vault_dir=vault_path, snapshot_code=snap_code)
        print(f"{OK_SYM} Successfully rolled back canonical memory to snapshot `{snap_code}`:")
        print(f"  Restored Seal: {res['checksum_sha256'][:16]}... (Intact)")
        print(f"  Decisions:     {res['decisions_count']}")
        print(f"  Tasks:         {res['tasks_count']}")
        print(f"  Views:         Regenerated BLUEPRINT.md & canonical/*.md")
        return 0
    except Exception as exc:
        print(f"{ERR_SYM} Error executing rollback: {exc}", file=sys.stderr)
        return 1


def cmd_ui(args: argparse.Namespace) -> int:
    """Generates an Antigravity Generative UI HTML dashboard artifact."""
    active_vault = None
    conv_id = getattr(args, "conv_id", None) or auto_detect_conversation_id()
    proj_arg = getattr(args, "project_flag", None) or getattr(args, "project", None)
    args.project = proj_arg
    if proj_arg:
        p_path = Path(proj_arg).resolve()
        search_roots = [p_path] if p_path.exists() else None
        try:
            active_vault = vault_store.resolve_project_vault(
                project_arg=proj_arg,
                conversation_id=conv_id,
                search_roots=search_roots,
            )
        except Exception:
            pass
    elif conv_id:
        try:
            active_vault = vault_store.resolve_project_vault(conversation_id=conv_id)
        except Exception:
            pass

    if not active_vault:
        search_roots = [Path(args.root).resolve()] if args.root else [Path.cwd()]
        discovered = vault_store.discover_vaults(search_roots)
        if discovered:
            active_vault = Path(discovered[0]["vault_dir"])

    active_ledger = {}
    active_staging = {}
    is_valid = True
    active_code = "PROJ"
    active_name = "Continuity Dashboard"

    if active_vault:
        active_ledger = vault_store.read_ledger(active_vault, verify_seal=False)
        active_staging = vault_store.read_staging(active_vault)
        is_valid, _, _ = vault_store.verify_seal(active_vault)
        active_code = active_ledger.get("project", {}).get("code", "PROJ")
        active_name = active_ledger.get("project", {}).get("name", "Project")

    proj = active_ledger.get("project", {})
    decisions = [d for d in active_ledger.get("decisions", []) if d.get("is_active", True)]
    rejected = [r for r in active_ledger.get("rejected_options", []) if r.get("is_active", True)]
    tasks = active_ledger.get("tasks", [])
    proposals = active_staging.get("proposals", [])
    completed_tasks = [t for t in tasks if t.get("status") == "COMPLETED"]

    # Build standalone HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SCS Continuity Dashboard - {active_name}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 13px; }}
  </style>
</head>
<body class="bg-slate-900 text-slate-100 p-4">
  <div class="max-w-4xl mx-auto space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between border-b border-slate-700 pb-3">
      <div>
        <h1 class="text-lg font-bold text-white flex items-center gap-2">
          <span>🧭</span> {active_name} <span class="text-xs bg-indigo-900 text-indigo-300 px-2 py-0.5 rounded font-mono">{active_code}</span>
        </h1>
        <p class="text-xs text-slate-400 mt-1">{proj.get('objective', 'Continuity Steward')}</p>
      </div>
      <div class="text-right">
        <span class="inline-block px-2.5 py-1 rounded text-xs font-semibold {'bg-emerald-950 text-emerald-400 border border-emerald-800' if is_valid else 'bg-rose-950 text-rose-400 border border-rose-800'}">
          {'✔ SEAL INTACT' if is_valid else '✖ SEAL TAMPERED'}
        </span>
      </div>
    </div>

    <!-- Quick Action Copy Buttons -->
    <div class="flex flex-wrap gap-2 text-xs">
      <button onclick="copyCmd('/scs record')" class="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded text-slate-200 flex items-center gap-1.5 transition">
        <span>⏺</span> Record Session <code>/scs record</code>
      </button>
      <button onclick="copyCmd('/scs approve --all')" class="bg-emerald-900 hover:bg-emerald-800 border border-emerald-700 px-3 py-1.5 rounded text-emerald-200 flex items-center gap-1.5 transition">
        <span>✔</span> Approve Staging <code>/scs approve --all</code>
      </button>
      <button onclick="copyCmd('/scs status')" class="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded text-slate-200 flex items-center gap-1.5 transition">
        <span>🔍</span> Check Status <code>/scs status</code>
      </button>
      <button onclick="copyCmd('/scs handover')" class="bg-indigo-900 hover:bg-indigo-800 border border-indigo-700 px-3 py-1.5 rounded text-indigo-200 flex items-center gap-1.5 transition">
        <span>📦</span> Handover Package <code>/scs handover</code>
      </button>
    </div>

    <!-- Telemetry Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
      <div class="bg-slate-800/80 p-3 rounded-lg border border-slate-700">
        <div class="text-slate-400">Ratified Decisions</div>
        <div class="text-xl font-bold text-white mt-1">{len(decisions)}</div>
      </div>
      <div class="bg-slate-800/80 p-3 rounded-lg border border-slate-700">
        <div class="text-slate-400">Rejected Options</div>
        <div class="text-xl font-bold text-rose-400 mt-1">{len(rejected)}</div>
      </div>
      <div class="bg-slate-800/80 p-3 rounded-lg border border-slate-700">
        <div class="text-slate-400">Tasks Completed</div>
        <div class="text-xl font-bold text-emerald-400 mt-1">{len(completed_tasks)} / {len(tasks)}</div>
      </div>
      <div class="bg-slate-800/80 p-3 rounded-lg border border-slate-700">
        <div class="text-slate-400">Quarantine Gate</div>
        <div class="text-xl font-bold text-amber-400 mt-1">{len(proposals)} pending</div>
      </div>
    </div>

    <!-- Operational State -->
    <div class="bg-slate-800/50 p-3.5 rounded-lg border border-slate-700 text-xs space-y-2">
      <div><span class="text-slate-400 font-semibold">Current Focus:</span> <span class="text-slate-200">{proj.get('current_focus', 'N/A')}</span></div>
      <div><span class="text-slate-400 font-semibold">Immediate Next Action:</span> <span class="text-emerald-400 font-medium">👉 {proj.get('next_action', 'N/A')}</span></div>
    </div>

    <!-- Staging Gate Section -->
    <div class="bg-slate-800/50 p-4 rounded-lg border border-slate-700 text-xs">
      <h2 class="text-sm font-semibold text-white mb-2 flex items-center gap-1.5">
        <span>⏳</span> Staging Quarantine Gate ({len(proposals)} pending)
      </h2>
      <div class="space-y-1.5 max-h-40 overflow-y-auto">
        {''.join(f'<div class="bg-slate-900 p-2 rounded border border-slate-800 flex justify-between items-center"><span class="font-mono text-amber-400">[{p.get("id")}]</span> <span class="text-slate-200">{p.get("statement", "")}</span> <span class="text-slate-500 font-mono text-[11px]">{p.get("proposal_type")}</span></div>' for p in proposals) if proposals else '<div class="text-slate-500 italic">Quarantine gate is clear. No pending items.</div>'}
      </div>
    </div>
  </div>

  <script>
    function copyCmd(cmd) {{
      navigator.clipboard.writeText(cmd).then(() => {{
        alert('Copied to clipboard: ' + cmd);
      }});
    }}
  </script>
</body>
</html>
"""

    out_path = Path(args.output) if args.output else (active_vault.parent / "scs_dashboard.html" if active_vault else Path("scs_dashboard.html"))
    out_path.write_text(html_content, encoding="utf-8")
    print(f"{OK_SYM} Generated interactive dashboard artifact: {out_path.resolve()}")
    return 0


# ---------------------------------------------------------------------------
# Argument Parser Setup
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Builds the main argument parser for /scs commands."""
    parser = argparse.ArgumentParser(
        prog="scs",
        description="SCS_AG_v2 — Session Continuity Steward for Antigravity",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # new
    p_new = subparsers.add_parser("new", help="Scaffold a new project continuity vault")
    p_new.add_argument("pos_code", nargs="?", default=None, metavar="code", help="Short project code (e.g. RIE, HERO_KAI)")
    p_new.add_argument("pos_name", nargs="?", default=None, metavar="name", help="Full human-readable project name")
    p_new.add_argument("--code", dest="flag_code", help="Short project code (flag syntax, e.g. --code RIE)")
    p_new.add_argument("--name", dest="flag_name", help="Full human-readable project name (flag syntax, e.g. --name 'Project Name')")
    p_new.add_argument("--path", help="Target project root directory (default: CWD)")
    p_new.add_argument("--objective", help="Primary project objective")
    p_new.add_argument("--focus", help="Initial operational focus")
    p_new.add_argument("--next-action", help="Immediate next action")
    p_new.add_argument("--repo", help="Associated project source repository directory (default: CWD if vault is external)")
    p_new.set_defaults(func=cmd_new)

    # list
    p_list = subparsers.add_parser("list", help="List discovered project continuity vaults")
    p_list.add_argument("--root", help="Root search directory (default: CWD)")
    p_list.set_defaults(func=cmd_list)

    # switch
    p_switch = subparsers.add_parser("switch", help="Switch active project context")
    p_switch.add_argument("code", help="Target project code")
    p_switch.set_defaults(func=cmd_switch)

    # record
    p_record = subparsers.add_parser("record", help="Record incremental session evidence")
    p_record.add_argument("project", nargs="?", default=None, help="Optional project code or directory")
    p_record.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory (flag syntax)")
    p_record.add_argument("--file", dest="file_path", default=None, help="Direct markdown session file path to ingest (bypasses Antigravity UUID)")
    p_record.add_argument("--author", dest="author", default=None, help="Author/contributor attribution for recorded session")
    p_record.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_record.add_argument("--app-data", help="Custom Antigravity appData directory")
    p_record.set_defaults(func=cmd_record)

    # status
    p_status = subparsers.add_parser("status", help="Display project health and continuity status")
    p_status.add_argument("project", nargs="?", default=None, help="Optional project code or directory")
    p_status.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory (flag syntax)")
    p_status.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_status.set_defaults(func=cmd_status)

    # approve
    p_approve = subparsers.add_parser("approve", help="Ratify quarantined proposals into canonical memory")
    p_approve.add_argument("proposals", nargs="*", help="Specific proposal IDs to approve or project code (e.g. P01 P02)")
    p_approve.add_argument("--all", action="store_true", help="Approve all pending proposals")
    p_approve.add_argument("--force", action="store_true", help="Force promotion bypassing quality invariant warnings")
    p_approve.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory")
    p_approve.add_argument("--author", dest="author", default=None, help="Author/operator attribution identity (default: git/user identity)")
    p_approve.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_approve.add_argument("--label", help="Reason for approval update")
    p_approve.set_defaults(func=cmd_approve)

    # reject
    p_reject = subparsers.add_parser("reject", help="Discard a staged proposal")
    p_reject.add_argument("pos_arg1", nargs="?", default=None, metavar="proposal_id", help="Proposal ID/index to reject (or project code if 2 positional args)")
    p_reject.add_argument("pos_arg2", nargs="?", default=None, metavar="proposal_id", help="Proposal ID (if first arg is project)")
    p_reject.add_argument("--all", action="store_true", help="Discard all pending staged proposals")
    p_reject.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt for bulk discard")
    p_reject.add_argument("--why", help="Failure reason or rationale for rejection")
    p_reject.add_argument("--record-why", action="store_true", help="Permanently record in REJECTED_OPTIONS memory")
    p_reject.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory")
    p_reject.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_reject.set_defaults(func=cmd_reject)

    # handover
    p_handover = subparsers.add_parser("handover", help="Generate master AI handover restoration package")
    p_handover.add_argument("project", nargs="?", default=None, help="Optional project code or directory")
    p_handover.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory (flag syntax)")
    p_handover.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_handover.set_defaults(func=cmd_handover)

    # rollback
    p_rollback = subparsers.add_parser("rollback", help="Restore canonical memory from prior sealed snapshot")
    p_rollback.add_argument("pos_arg1", nargs="?", default=None, metavar="snapshot_code", help="Snapshot code to restore or project code")
    p_rollback.add_argument("pos_arg2", nargs="?", default=None, metavar="snapshot_code", help="Snapshot code to restore (if first arg is project)")
    p_rollback.add_argument("--snapshot", dest="snapshot_flag", help="Snapshot code to restore (flag alias, e.g. SNP-20261105-001)")
    p_rollback.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory")
    p_rollback.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_rollback.set_defaults(func=cmd_rollback)

    # ui
    p_ui = subparsers.add_parser("ui", help="Generate interactive Generative UI dashboard artifact")
    p_ui.add_argument("project", nargs="?", default=None, help="Optional project code or directory")
    p_ui.add_argument("--project", dest="project_flag", default=None, help="Target project code or directory (flag syntax)")
    p_ui.add_argument("--root", help="Root search directory")
    p_ui.add_argument("--output", help="Output HTML file path")
    p_ui.add_argument("--conv-id", help="Antigravity conversation UUID")
    p_ui.set_defaults(func=cmd_ui)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    raw_args = list(argv if argv is not None else sys.argv[1:])

    # Strip leading slash if user typed '/scs ...'
    if raw_args and raw_args[0].startswith("/scs"):
        raw_args[0] = raw_args[0][4:].lstrip()
        if not raw_args[0]:
            raw_args.pop(0)

    # If invoked with leading '/<command>'
    if raw_args and raw_args[0].startswith("/"):
        raw_args[0] = raw_args[0][1:]

    parser = build_parser()
    if not raw_args:
        parser.print_help()
        return 0

    parsed = parser.parse_args(raw_args)
    if hasattr(parsed, "func"):
        return parsed.func(parsed)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
