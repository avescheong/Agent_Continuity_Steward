"""
SCS_AG_v2 Transcript Reader & Watermark Slicer (engine/transcript_reader.py)
============================================================================

Governing Principles:
1. "Preserve the brain, replace the communication channel."
2. "Automate the mechanical copying while preserving forensic evidence."
3. "Per-conversation watermarks — zero overlap, zero duplicate capture."
4. "Non-destructive evidence backbone — raw SES files are immutable."

This module implements Tier 1 (transcript.jsonl + transcript_full.jsonl)
evidence capture, XML tag normalization, per-conversation watermark slicing,
and immutable SES evidence generation for SCS_AG_v2.
"""

import os
import sys
import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    import vault_store
except ImportError:
    vault_store = None


# ---------------------------------------------------------------------------
# Default Antigravity Path Resolution
# ---------------------------------------------------------------------------

def get_default_app_data_dir() -> Path:
    """Returns the default Antigravity appData directory."""
    if "ANTIGRAVITY_APP_DATA" in os.environ:
        return Path(os.environ["ANTIGRAVITY_APP_DATA"]).resolve()
    if "APPDATA_DIR" in os.environ:
        return Path(os.environ["APPDATA_DIR"]).resolve()
    return (Path.home() / ".gemini" / "antigravity").resolve()


def get_transcript_paths(
    conversation_id: str,
    app_data_dir: Optional[Union[str, Path]] = None,
) -> Tuple[Path, Path]:
    """Returns (transcript.jsonl, transcript_full.jsonl) paths for a conversation."""
    base = Path(app_data_dir).resolve() if app_data_dir else get_default_app_data_dir()
    log_dir = base / "brain" / conversation_id / ".system_generated" / "logs"
    return log_dir / "transcript.jsonl", log_dir / "transcript_full.jsonl"


# ---------------------------------------------------------------------------
# Normalization Layer
# ---------------------------------------------------------------------------

def normalize_turn_text(text: str, is_human: bool = False) -> str:
    """Normalizes raw transcript text for Caveman CEE ingestion.

    Removes:
    - <ADDITIONAL_METADATA>...</ADDITIONAL_METADATA>
    - <USER_SETTINGS_CHANGE>...</USER_SETTINGS_CHANGE>
    - <SYSTEM_MESSAGE>...</SYSTEM_MESSAGE>
    - <SKILL>...</SKILL>
    - <CONTEXT_SUMMARY>...</CONTEXT_SUMMARY>
    - <USER_REQUEST> and </USER_REQUEST> tags
    - YAML frontmatter ('--- ... ---')
    - Excessive leading/trailing whitespace

    Does NOT modify original evidence files. Only normalizes the processing copy.
    """
    if not text:
        return ""

    cleaned = text

    # 1. Strip system and metadata XML wrapper blocks
    for tag in [
        "ADDITIONAL_METADATA",
        "USER_SETTINGS_CHANGE",
        "SYSTEM_MESSAGE",
        "SKILL",
        "CONTEXT_SUMMARY",
    ]:
        cleaned = re.sub(rf"<{tag}(?:\s+[^>]*)?>.*?</{tag}>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # 2. Extract or unwrap <USER_REQUEST>...</USER_REQUEST>
    req_match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if req_match:
        cleaned = req_match.group(1)
    else:
        # Strip any standalone <USER_REQUEST> or </USER_REQUEST> tags if unclosed
        cleaned = re.sub(r"</?USER_REQUEST>", "", cleaned, flags=re.IGNORECASE)

    # 3. Strip YAML frontmatter ('--- ... ---') if present
    stripped = cleaned.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            cleaned = parts[2]

    # 4. Normalize CRLF to LF and trim surrounding whitespace
    cleaned = cleaned.replace("\r\n", "\n").strip()

    return cleaned


def is_record_trigger_command(text: str) -> bool:
    """Returns True if the utterance is solely an /scs record command.

    Prevents recording trigger commands from polluting project memory.
    """
    if not text:
        return False
    t = text.strip().lower()
    return t in ("/scs record", "/scs record\n", "scs record", "record", "/scs record --all") or t.startswith("/scs record ")


def compute_turn_hash(speaker: str, content: str) -> str:
    """Computes a 64-char lowercase SHA-256 hash of a normalized turn."""
    payload = f"{speaker.strip()}:{content.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Tier 1: Transcript Reader & Truncation Resolver
# ---------------------------------------------------------------------------

def read_transcript_turns(
    conversation_id: str,
    app_data_dir: Optional[Union[str, Path]] = None,
    watermark: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Reads dialogue turns from transcript.jsonl and resolves truncated lines.

    Applies per-conversation watermark slicing:
    - Skips turns with step_index <= watermark['last_step_index']
    - Skips intermediate tool execution steps (type == 'GENERIC')
    - Skips tool-only planner steps (type == 'PLANNER_RESPONSE' with empty content)
    - Resolves lines with truncated_fields from transcript_full.jsonl

    Args:
        conversation_id: Antigravity conversation UUID.
        app_data_dir: Optional custom appData directory path.
        watermark: Optional dict with 'last_step_index' and 'last_turn_hash'.

    Returns:
        List of turn dictionaries:
        {
            "speaker": "Human" | "AI",
            "step_index": int,
            "created_at": str,
            "raw_content": str,
            "normalized_content": str,
            "turn_hash": str,
        }
    """
    trans_path, trans_full_path = get_transcript_paths(conversation_id, app_data_dir)

    if not trans_path.exists():
        raise FileNotFoundError(f"Transcript log not found at: {trans_path}")

    last_step_watermark = -1
    last_hash_watermark = ""
    if watermark:
        last_step_watermark = watermark.get("last_step_index", -1)
        last_hash_watermark = watermark.get("last_turn_hash", "")

    # Index full lines by step_index for quick O(1) resolution of truncated content
    full_by_step: Dict[int, Dict[str, Any]] = {}
    if trans_full_path.exists():
        with open(trans_full_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    step = d.get("step_index")
                    if step is not None:
                        full_by_step[step] = d
                except Exception:
                    continue

    turns: List[Dict[str, Any]] = []

    with open(trans_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue

            step = d.get("step_index", -1)
            # Watermark filter: only process steps strictly greater than watermark
            if step <= last_step_watermark:
                continue

            msg_type = d.get("type")
            if msg_type not in ("USER_INPUT", "PLANNER_RESPONSE"):
                continue

            raw_content = d.get("content") or ""
            # Resolve truncated content from transcript_full.jsonl
            trunc_fields = d.get("truncated_fields") or []
            if "content" in trunc_fields or not raw_content:
                full_obj = full_by_step.get(step)
                if full_obj and full_obj.get("content"):
                    raw_content = full_obj.get("content") or ""

            # Skip empty planner responses (tool-only intermediate steps)
            if msg_type == "PLANNER_RESPONSE" and not raw_content.strip():
                continue

            speaker = "Human" if msg_type == "USER_INPUT" else "AI"
            normalized = normalize_turn_text(raw_content, is_human=(speaker == "Human"))

            if not normalized.strip():
                continue

            turn_hash = compute_turn_hash(speaker, normalized)

            # Prevent duplicate capture if turn hash matches watermark
            if turn_hash == last_hash_watermark:
                continue

            turns.append({
                "speaker": speaker,
                "step_index": step,
                "created_at": d.get("created_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "raw_content": raw_content,
                "normalized_content": normalized,
                "turn_hash": turn_hash,
            })

    return turns


# ---------------------------------------------------------------------------
# Tier 2: Context Fallback Reader (Air-gapped / Non-Brain environments)
# ---------------------------------------------------------------------------

def read_fallback_turns(
    fallback_file: Union[str, Path],
) -> List[Dict[str, Any]]:
    """Reads dialogue turns from a fallback text file (.continuity/staging/context_capture.tmp)."""
    p = Path(fallback_file).resolve()
    if not p.exists():
        return []

    content = p.read_text(encoding="utf-8")
    lines = content.splitlines()

    turns: List[Dict[str, Any]] = []
    current_speaker = None
    current_lines: List[str] = []
    turn_idx = 0

    for line in lines:
        stripped = line.strip()
        if re.match(r"^(?:Human|User):", stripped, re.IGNORECASE):
            if current_speaker and current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    turns.append({
                        "speaker": current_speaker,
                        "step_index": turn_idx,
                        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "raw_content": body,
                        "normalized_content": normalize_turn_text(body, is_human=(current_speaker == "Human")),
                        "turn_hash": compute_turn_hash(current_speaker, body),
                    })
                    turn_idx += 1
            current_speaker = "Human"
            current_lines = [re.sub(r"^(?:Human|User):\s*", "", stripped, flags=re.IGNORECASE)]
        elif re.match(r"^(?:AI|Assistant|Model):", stripped, re.IGNORECASE):
            if current_speaker and current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    turns.append({
                        "speaker": current_speaker,
                        "step_index": turn_idx,
                        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "raw_content": body,
                        "normalized_content": normalize_turn_text(body, is_human=(current_speaker == "Human")),
                        "turn_hash": compute_turn_hash(current_speaker, body),
                    })
                    turn_idx += 1
            current_speaker = "AI"
            current_lines = [re.sub(r"^(?:AI|Assistant|Model):\s*", "", stripped, flags=re.IGNORECASE)]
        else:
            if current_speaker is not None:
                current_lines.append(line)

    if current_speaker and current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            turns.append({
                "speaker": current_speaker,
                "step_index": turn_idx,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "raw_content": body,
                "normalized_content": normalize_turn_text(body, is_human=(current_speaker == "Human")),
                "turn_hash": compute_turn_hash(current_speaker, body),
            })

    return turns


# ---------------------------------------------------------------------------
# Tier 4: SES Evidence Writer & Watermark Manager
# ---------------------------------------------------------------------------

def capture_session_evidence(
    vault_dir: Union[str, Path],
    conversation_id: str,
    app_data_dir: Optional[Union[str, Path]] = None,
    session_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Captures incremental conversation turns into an immutable SES file.

    1. Loads watermark for conversation_id from evidence/MANIFEST.json.
    2. Slices transcript.jsonl (Tier 1) or context_capture.tmp (Tier 2).
    3. Strips trailing '/scs record' trigger turn.
    4. Writes immutable SES{NNN}_{YYYYMMDD}_{HHMM}.md to evidence/raw_sessions/.
    5. Updates per-conversation watermark in MANIFEST.json.
    6. Checks 10-session trigger (SES010, SES020...) and invokes archive hook.

    Args:
        vault_dir: Path to project .continuity/ vault.
        conversation_id: Antigravity conversation UUID.
        app_data_dir: Optional custom Antigravity appData directory.
        session_time: Optional explicit timestamp (for testing).

    Returns:
        Session capture result dictionary:
        {
            "captured": bool,
            "session_id": str,
            "file_name": str,
            "file_path": str,
            "turn_count": int,
            "sha256": str,
            "first_step_index": int,
            "last_step_index": int,
            "first_turn_hash": str,
            "last_turn_hash": str,
            "archive_triggered": bool,
            "archive_file": Optional[str],
            "dialogue_text": str,
        }
    """
    v_paths = vault_store.get_vault_paths(vault_dir) if vault_store else {
        "vault_dir": Path(vault_dir).resolve(),
        "manifest_json": Path(vault_dir).resolve() / "evidence" / "MANIFEST.json",
        "raw_sessions_dir": Path(vault_dir).resolve() / "evidence" / "raw_sessions",
        "staging_dir": Path(vault_dir).resolve() / "staging",
    }

    # 1. Read MANIFEST.json
    manifest_file = v_paths["manifest_json"]
    manifest = {}
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": "scs-manifest/1.0",
            "project_code": "PROJ",
            "next_session_num": 1,
            "next_archive_num": 1,
            "watermarks_by_conversation": {},
            "sessions": [],
            "archives": [],
        }

    watermarks = manifest.setdefault("watermarks_by_conversation", {})
    conv_watermark = watermarks.get(conversation_id, {})

    # 2. Try Tier 1 Primary Capture
    turns: List[Dict[str, Any]] = []
    capture_source = "TIER1_BRAIN"

    try:
        turns = read_transcript_turns(
            conversation_id=conversation_id,
            app_data_dir=app_data_dir,
            watermark=conv_watermark,
        )
    except FileNotFoundError:
        # Tier 2 Fallback Capture
        fallback_file = v_paths["staging_dir"] / "context_capture.tmp"
        if fallback_file.exists():
            turns = read_fallback_turns(fallback_file)
            capture_source = "TIER2_FALLBACK"
            try:
                fallback_file.unlink()  # Remove tmp after reading
            except Exception:
                pass
        else:
            return {
                "captured": False,
                "reason": f"No transcript logs found for conversation {conversation_id} and no fallback tmp present.",
            }

    # 3. Strip trailing '/scs record' trigger turn if present
    if turns and turns[-1]["speaker"] == "Human":
        if is_record_trigger_command(turns[-1]["normalized_content"]):
            turns.pop()

    if not turns:
        return {
            "captured": False,
            "reason": "NO_NEW_TURNS",
            "last_step_index": conv_watermark.get("last_step_index", -1),
        }

    # 4. Compute session naming and metadata
    now_dt = session_time or datetime.now(timezone.utc)
    date_str = now_dt.strftime("%Y%m%d")
    time_str = now_dt.strftime("%H%M")
    dt_str = f"{date_str}_{time_str}"
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    next_num = manifest.get("next_session_num", 1)
    session_id = f"SES{next_num:03d}"
    filename = f"{session_id}_{dt_str}.md"
    ses_file = v_paths["raw_sessions_dir"] / filename

    first_step = turns[0]["step_index"]
    last_step = turns[-1]["step_index"]
    first_hash = turns[0]["turn_hash"]
    last_hash = turns[-1]["turn_hash"]

    # 5. Build dialogue text body
    dialogue_lines: List[str] = []
    for t in turns:
        dialogue_lines.append(f"{t['speaker']}:\n{t['normalized_content']}\n")
    dialogue_text = "\n".join(dialogue_lines).strip()

    # 6. Format SES markdown file with YAML frontmatter
    proj_code = manifest.get("project_code", "PROJ")

    # Preliminary frontmatter without sha256 to compute body hash
    frontmatter_template = (
        "---\n"
        f"session_id: {session_id}_{dt_str}\n"
        f"session_code: {session_id}\n"
        f"project_code: {proj_code}\n"
        f"conversation_id: {conversation_id}\n"
        f"captured_at: '{now_iso}'\n"
        f"capture_source: {capture_source}\n"
        f"turn_count: {len(turns)}\n"
        f"first_step_index: {first_step}\n"
        f"last_step_index: {last_step}\n"
        f"first_turn_hash: {first_hash}\n"
        f"last_turn_hash: {last_hash}\n"
        "sha256: {sha256_placeholder}\n"
        "---\n\n"
    )

    # Compute hash of the dialogue content payload
    content_sha256 = hashlib.sha256(dialogue_text.encode("utf-8")).hexdigest()
    full_ses_content = frontmatter_template.format(sha256_placeholder=content_sha256) + dialogue_text + "\n"

    # Write immutable SES file
    v_paths["raw_sessions_dir"].mkdir(parents=True, exist_ok=True)
    ses_file.write_text(full_ses_content, encoding="utf-8")

    # 7. Update MANIFEST.json watermarks
    watermarks[conversation_id] = {
        "last_step_index": last_step,
        "last_turn_hash": last_hash,
        "last_session_id": session_id,
        "updated_at": now_iso,
    }

    manifest.setdefault("sessions", []).append({
        "session_id": session_id,
        "file_path": f"evidence/raw_sessions/{filename}",
        "captured_at": now_iso,
        "conversation_id": conversation_id,
        "turn_count": len(turns),
        "first_step_index": first_step,
        "last_step_index": last_step,
        "sha256": content_sha256,
        "consolidated_in": None,
    })
    manifest["next_session_num"] = next_num + 1

    manifest_file.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # 8. Check 10-Session Archive Hook
    archive_triggered = False
    archive_file = None
    if next_num % 10 == 0 and vault_store:
        archive_file = vault_store.prepare_10_session_archive(
            vault_dir=v_paths["vault_dir"],
            archive_title=f"Consolidated archive for sessions through {session_id}",
        )
        archive_triggered = archive_file is not None

    return {
        "captured": True,
        "session_id": session_id,
        "file_name": filename,
        "file_path": str(ses_file),
        "turn_count": len(turns),
        "sha256": content_sha256,
        "first_step_index": first_step,
        "last_step_index": last_step,
        "first_turn_hash": first_hash,
        "last_turn_hash": last_hash,
        "archive_triggered": archive_triggered,
        "archive_file": archive_file,
        "dialogue_text": dialogue_text,
    }


def extract_session_dialogue(ses_content: str) -> str:
    """Extracts raw dialogue text from an SES markdown file by stripping YAML frontmatter."""
    if not ses_content:
        return ""
    stripped = ses_content.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return ses_content.strip()


# ---------------------------------------------------------------------------
# Tier 3: Direct Markdown File Ingestion (FDB-101-014)
# ---------------------------------------------------------------------------

def parse_markdown_session_turns(content: str) -> List[Dict[str, Any]]:
    """Parses speaker turns from a markdown session file.

    FDB-101-014: Recognizes common dialogue patterns:
    - Human / User / Operator: <text>
    - AI / Assistant / Model / Claude / Gemini: <text>
    - Markdown bold or header turns: **User:**, **AI:**, ### Human, ### AI
    - Blockquote markers: > User: ..., > AI: ...

    If no explicit speaker headers are matched, the content is preserved
    in its entirety as an AI dialogue turn so downstream Caveman extraction
    can process architectural propositions without loss.
    """
    if not content:
        return []

    lines = content.splitlines()
    turns: List[Dict[str, Any]] = []
    current_speaker: Optional[str] = None
    current_lines: List[str] = []
    turn_idx = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    human_pattern = re.compile(
        r"^(?:>\s*)?(?:#+\s*)?(?:\*\*)?(?:Human|User|Operator|Developer|Engineer)(?:\*\*)?:\s*(.*)$",
        re.IGNORECASE,
    )
    ai_pattern = re.compile(
        r"^(?:>\s*)?(?:#+\s*)?(?:\*\*)?(?:AI|Assistant|Model|Antigravity|Claude|Gemini)(?:\*\*)?:\s*(.*)$",
        re.IGNORECASE,
    )

    for line in lines:
        stripped = line.strip()
        m_human = human_pattern.match(stripped)
        m_ai = ai_pattern.match(stripped)

        if m_human:
            if current_speaker and current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    norm = normalize_turn_text(body, is_human=(current_speaker == "Human"))
                    turns.append({
                        "speaker": current_speaker,
                        "step_index": turn_idx,
                        "created_at": now_iso,
                        "raw_content": body,
                        "normalized_content": norm,
                        "turn_hash": compute_turn_hash(current_speaker, norm),
                    })
                    turn_idx += 1
            current_speaker = "Human"
            initial_text = m_human.group(1).strip()
            current_lines = [initial_text] if initial_text else []
        elif m_ai:
            if current_speaker and current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    norm = normalize_turn_text(body, is_human=(current_speaker == "Human"))
                    turns.append({
                        "speaker": current_speaker,
                        "step_index": turn_idx,
                        "created_at": now_iso,
                        "raw_content": body,
                        "normalized_content": norm,
                        "turn_hash": compute_turn_hash(current_speaker, norm),
                    })
                    turn_idx += 1
            current_speaker = "AI"
            initial_text = m_ai.group(1).strip()
            current_lines = [initial_text] if initial_text else []
        else:
            if current_speaker is not None:
                current_lines.append(line)
            else:
                current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            speaker = current_speaker or "AI"
            norm = normalize_turn_text(body, is_human=(speaker == "Human"))
            turns.append({
                "speaker": speaker,
                "step_index": turn_idx,
                "created_at": now_iso,
                "raw_content": body,
                "normalized_content": norm,
                "turn_hash": compute_turn_hash(speaker, norm),
            })

    return turns


def capture_markdown_file_evidence(
    vault_dir: Union[str, Path],
    file_path: Union[str, Path],
    conversation_id: Optional[str] = None,
    session_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Captures a standalone markdown session file directly into an immutable SES file.

    FDB-101-014: Allows headless/CI environments or external files without
    an active Antigravity conversation directory.

    Args:
        vault_dir: Path to project .continuity/ vault.
        file_path: Path to external markdown session file.
        conversation_id: Optional identifier (auto-generated if omitted).
        session_time: Optional explicit timestamp.

    Returns:
        Session capture result dictionary identical in structure to capture_session_evidence.
    """
    f_path = Path(file_path).resolve()
    if not f_path.exists() or not f_path.is_file():
        raise FileNotFoundError(f"Input markdown session file not found: {f_path}")

    raw_content = f_path.read_text(encoding="utf-8", errors="ignore")
    turns = parse_markdown_session_turns(raw_content)

    if not turns:
        return {
            "captured": False,
            "reason": "FILE_IS_EMPTY",
        }

    v_paths = vault_store.get_vault_paths(vault_dir) if vault_store else {
        "vault_dir": Path(vault_dir).resolve(),
        "manifest_json": Path(vault_dir).resolve() / "evidence" / "MANIFEST.json",
        "raw_sessions_dir": Path(vault_dir).resolve() / "evidence" / "raw_sessions",
        "staging_dir": Path(vault_dir).resolve() / "staging",
    }

    manifest_file = v_paths["manifest_json"]
    manifest = {}
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": "scs-manifest/1.0",
            "project_code": "PROJ",
            "next_session_num": 1,
            "next_archive_num": 1,
            "watermarks_by_conversation": {},
            "sessions": [],
            "archives": [],
        }

    conv_id = conversation_id or f"file-{hashlib.sha256(f_path.name.encode('utf-8')).hexdigest()[:12]}"
    watermarks = manifest.setdefault("watermarks_by_conversation", {})

    now_dt = session_time or datetime.now(timezone.utc)
    date_str = now_dt.strftime("%Y%m%d")
    time_str = now_dt.strftime("%H%M")
    dt_str = f"{date_str}_{time_str}"
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    next_num = manifest.get("next_session_num", 1)
    session_id = f"SES{next_num:03d}"
    filename = f"{session_id}_{dt_str}.md"
    ses_file = v_paths["raw_sessions_dir"] / filename

    first_step = turns[0]["step_index"]
    last_step = turns[-1]["step_index"]
    first_hash = turns[0]["turn_hash"]
    last_hash = turns[-1]["turn_hash"]

    dialogue_lines: List[str] = []
    for t in turns:
        dialogue_lines.append(f"{t['speaker']}:\n{t['normalized_content']}\n")
    dialogue_text = "\n".join(dialogue_lines).strip()

    proj_code = manifest.get("project_code", "PROJ")

    frontmatter_template = (
        "---\n"
        f"session_id: {session_id}_{dt_str}\n"
        f"session_code: {session_id}\n"
        f"project_code: {proj_code}\n"
        f"conversation_id: {conv_id}\n"
        f"captured_at: '{now_iso}'\n"
        f"capture_source: DIRECT_FILE\n"
        f"source_file: {f_path.name}\n"
        f"turn_count: {len(turns)}\n"
        f"first_step_index: {first_step}\n"
        f"last_step_index: {last_step}\n"
        f"first_turn_hash: {first_hash}\n"
        f"last_turn_hash: {last_hash}\n"
        "sha256: {sha256_placeholder}\n"
        "---\n\n"
    )

    content_sha256 = hashlib.sha256(dialogue_text.encode("utf-8")).hexdigest()
    full_ses_content = frontmatter_template.format(sha256_placeholder=content_sha256) + dialogue_text + "\n"

    v_paths["raw_sessions_dir"].mkdir(parents=True, exist_ok=True)
    ses_file.write_text(full_ses_content, encoding="utf-8")

    watermarks[conv_id] = {
        "last_step_index": last_step,
        "last_turn_hash": last_hash,
        "last_session_id": session_id,
        "updated_at": now_iso,
    }

    manifest.setdefault("sessions", []).append({
        "session_id": session_id,
        "file_path": f"evidence/raw_sessions/{filename}",
        "captured_at": now_iso,
        "conversation_id": conv_id,
        "turn_count": len(turns),
        "first_step_index": first_step,
        "last_step_index": last_step,
        "sha256": content_sha256,
        "consolidated_in": None,
    })
    manifest["next_session_num"] = next_num + 1

    manifest_file.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    archive_triggered = False
    archive_file = None
    if next_num % 10 == 0 and vault_store:
        archive_file = vault_store.prepare_10_session_archive(
            vault_dir=v_paths["vault_dir"],
            archive_title=f"Consolidated archive for sessions through {session_id}",
        )
        archive_triggered = archive_file is not None

    return {
        "captured": True,
        "session_id": session_id,
        "file_name": filename,
        "file_path": str(ses_file),
        "turn_count": len(turns),
        "sha256": content_sha256,
        "first_step_index": first_step,
        "last_step_index": last_step,
        "first_turn_hash": first_hash,
        "last_turn_hash": last_hash,
        "archive_triggered": archive_triggered,
        "archive_file": archive_file,
        "dialogue_text": dialogue_text,
    }
