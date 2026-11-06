"""Protocol engine: capture parsing, bootstrap prompt compilation, and handover export."""

import re
import json
import uuid
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from src.scs_core.db.database import VaultDatabase
from src.scs_core.models import (
    ProposalType, TaskStatus, TaskPriority, DecisionKind, ArtifactType, ArtifactCustodyState,
    BootstrapResult, ReconcileSummary, utc_now_iso, compact_why,
    ConversationSession, ChatFragment, CheckpointStatus
)
from src.scs_core.modules.scrubber import scrub_secrets
from src.scs_core.modules.caveman_engine import CavemanContextExtractionEngine, ExtractedContext
from src.scs_core.modules.mod04_projects_sessions import ProjectSessionService
from src.scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from src.scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from src.scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from src.scs_core.modules.mod03_approval_gate import ApprovalGateService
from src.scs_core.modules.mod07_reconciler import ReadOnlyReconciler


UNIVERSAL_SYNC_FOOTER = """
```scs-delta
{
  "protocol": "scs-delta/1.0",
  "decisions": [
    {"statement": "<Decision made>", "why": "<Rationale>"}
  ],
  "rejected_options": [
    {"statement": "<Rejected alternative>", "why": "<Why not chosen>"}
  ],
  "tasks": [
    {"title": "<Action item>", "status": "PENDING" | "IN_PROGRESS" | "COMPLETED" | "BLOCKED", "why": "<Why it matters>"}
  ],
  "artifacts": [
    {"name": "<file or doc>", "note": "<Status / description>"}
  ]
}
```
""".strip()


class ProtocolEngineService:
    def __init__(
        self,
        db: VaultDatabase,
        project_svc: ProjectSessionService,
        decision_svc: DecisionLedgerService,
        checklist_svc: ChecklistEngineService,
        artifact_svc: ArtifactRegistryService,
        gate_svc: ApprovalGateService,
        reconciler_svc: ReadOnlyReconciler,
        exports_dir: Optional[Path] = None,
    ):
        self.db = db
        self.project_svc = project_svc
        self.decision_svc = decision_svc
        self.checklist_svc = checklist_svc
        self.artifact_svc = artifact_svc
        self.gate_svc = gate_svc
        self.reconciler_svc = reconciler_svc
        self.exports_dir = exports_dir
        self.caveman_engine = CavemanContextExtractionEngine()
        self._active_sessions: Dict[str, ConversationSession] = {}
        self._extracted_cache: Dict[str, ExtractedContext] = {}
        self._draft_cache: Dict[str, Dict[str, Any]] = {}

    def parse_and_stage_capture(
        self, project_id: str, raw_text: str, source_origin: str = "MANUAL_CAPTURE"
    ) -> List[Dict[str, Any]]:
        """Parses multi-format captured text and stages into proposals table (PENDING).

        Tiers:
        1. Fenced scs-delta / scs-handover / TaskSyncPackage JSON
        2. Labeled Markdown lines & checklists
        3. Single quick-capture heuristic
        """
        text = raw_text.strip()
        if not text:
            return []

        staged = []

        # Tier 1: Fenced code blocks
        json_blocks = re.findall(
            r"```(?:scs-delta|scs-handover|scs-continuity-chapter|json)?\s*(\{[\s\S]*?\})\s*```",
            text,
            re.IGNORECASE,
        )
        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                    # Check for scs-delta or scs-handover
                    items = self._extract_from_json_dict(project_id, data, block, source_origin)
                    staged.extend(items)
            except Exception:
                pass

        if staged:
            return [self.gate_svc.stage_proposal(**item).model_dump(mode="json") for item in staged]

        # Tier 2: Labeled lines or markdown checkboxes
        lines = text.splitlines()
        extracted_lines = []

        md_check_pat = re.compile(r"^\s*[-*•]?\s*\[\s*([ xX])\s*\]\s*(.+)$")
        labeled_pat = re.compile(r"^(Decision|Constraint|Rejected|Blocker|Idea|Task|Artifact):\s*(.+)$", re.IGNORECASE)

        for line in lines:
            l_str = line.strip()
            if not l_str:
                continue

            m_lbl = labeled_pat.match(l_str)
            if m_lbl:
                kind_str = m_lbl.group(1).upper()
                content = m_lbl.group(2).strip()
                p_type = ProposalType.TASK
                if "DECISION" in kind_str:
                    p_type = ProposalType.DECISION
                elif "CONSTRAINT" in kind_str:
                    p_type = ProposalType.CONSTRAINT
                elif "REJECTED" in kind_str:
                    p_type = ProposalType.REJECTED_OPTION
                elif "BLOCKER" in kind_str:
                    p_type = ProposalType.BLOCKER
                elif "IDEA" in kind_str:
                    p_type = ProposalType.IDEA
                elif "ARTIFACT" in kind_str:
                    p_type = ProposalType.ARTIFACT

                why_str = ""
                why_match = re.search(r"\(Why:\s*(.*?)\)\s*$", content, re.IGNORECASE)
                if why_match:
                    why_str = why_match.group(1).strip()
                    content = content[:why_match.start()].strip()

                extracted_lines.append({
                    "project_id": project_id,
                    "proposal_type": p_type,
                    "title": content,
                    "rationale_why": why_str,
                    "source_excerpt": l_str,
                    "source_origin": source_origin,
                })
                continue

            m_chk = md_check_pat.match(l_str)
            if m_chk:
                is_done = m_chk.group(1).strip().lower() == "x"
                title = m_chk.group(2).strip()
                extracted_lines.append({
                    "project_id": project_id,
                    "proposal_type": ProposalType.TASK,
                    "title": title,
                    "rationale_why": "",
                    "source_excerpt": l_str,
                    "source_origin": source_origin,
                    "payload": {"status": "COMPLETED" if is_done else "PENDING"},
                })

        if extracted_lines:
            return [self.gate_svc.stage_proposal(**item).model_dump(mode="json") for item in extracted_lines]

        # Tier 3: Heuristic single item fallback
        single_item = self._extract_single_heuristic(project_id, text, source_origin)
        prop = self.gate_svc.stage_proposal(**single_item)
        return [prop.model_dump(mode="json")]

    def compile_bootstrap(
        self, project_id: str, include_sync_footer: bool = True
    ) -> BootstrapResult:
        """Compiles compact, secret-scrubbed context rehydration prompt."""
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        # Run fresh read-only reconciliation
        artifacts, summary = self.reconciler_svc.reconcile_project(project_id)

        decisions = self.decision_svc.list_decisions(project_id, active_only=True)
        tasks = self.checklist_svc.list_tasks(project_id)

        # Build prompt sections
        lines = [
            f"=== [SCS CONTINUITY BOOTSTRAP: {proj.code}] ===",
            f"Project: {proj.name} ({proj.code})",
        ]
        if proj.latest_snapshot_id:
            sha_pref = proj.latest_snapshot_sha256[:12] if proj.latest_snapshot_sha256 else "none"
            lines.append(f"Anchored Snapshot: {proj.latest_snapshot_id} (SHA: {sha_pref})")

        lines.append("")
        lines.append("1. OBJECTIVE & CURRENT FOCUS:")
        lines.append(f"   • Objective: {proj.objective or '(No objective specified)'}")
        lines.append(f"   • Current Focus: {proj.current_focus or '(Ready for task selection)'}")
        lines.append(f"   • Immediate Next Action: {proj.next_action or '(Define next action)'}")
        lines.append("")

        # Decisions & Constraints
        ratified_decs = [d for d in decisions if d.record_kind in (DecisionKind.DECISION, DecisionKind.CONSTRAINT)]
        if ratified_decs:
            lines.append(f"2. RATIFIED DECISIONS & CONSTRAINTS ({len(ratified_decs)}):")
            for d in ratified_decs:
                why = f" (Why: {d.rationale_why})" if d.rationale_why else ""
                lines.append(f"   • [{d.code}] {d.statement}{why}")
            lines.append("")

        # Rejected Options (Do Not Repeat)
        rejected = [d for d in decisions if d.record_kind == DecisionKind.REJECTED_OPTION]
        if rejected:
            lines.append(f"3. DO NOT REPEAT — REJECTED ALTERNATIVES ({len(rejected)}):")
            for r in rejected:
                why = f" (Why rejected: {r.rationale_why})" if r.rationale_why else ""
                lines.append(f"   • ⛔ [{r.code}] {r.statement}{why}")
            lines.append("")

        # Tasks
        in_prog = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
        blocked = [t for t in tasks if t.status == TaskStatus.BLOCKED]
        pending = [t for t in tasks if t.status == TaskStatus.PENDING]
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]

        lines.append(f"4. EXECUTION QUEUE (Active: {len(in_prog)}, Blocked: {len(blocked)}, Pending: {len(pending)}):")
        if in_prog:
            for t in in_prog:
                w = f" (Why: {t.compact_why})" if t.compact_why else ""
                lines.append(f"   • [IN_PROGRESS] {t.title}{w}")
        if blocked:
            for t in blocked:
                b = f" (Blocker: {t.blocker_reason})" if t.blocker_reason else ""
                lines.append(f"   • ⚠ [BLOCKED] {t.title}{b}")
        if pending:
            for t in pending[:5]:
                w = f" (Why: {t.compact_why})" if t.compact_why else ""
                lines.append(f"   • [ ] {t.title}{w}")
        if not (in_prog or blocked or pending):
            lines.append("   • (All tracked tasks completed)")
        lines.append("")

        # Artifact Reality Map
        verified = [a for a in artifacts if a.custody_state in (ArtifactCustodyState.VERIFIED_MATCH, ArtifactCustodyState.LOCAL_FILE_EXISTS)]
        drift = [a for a in artifacts if a.custody_state in (ArtifactCustodyState.MODIFIED, ArtifactCustodyState.MISSING)]
        chat_only = [a for a in artifacts if a.custody_state == ArtifactCustodyState.CONVERSATION_ONLY]

        lines.append("5. ARTIFACT REALITY MAP:")
        if verified:
            lines.append(f"   • Physical Files on Disk ({len(verified)}):")
            for a in verified:
                st = "Verified Match" if a.custody_state == ArtifactCustodyState.VERIFIED_MATCH else "Exists on Disk"
                lines.append(f"     - [🟢 {st}] {a.name} ({a.relative_path or 'root'})")
        if drift:
            lines.append(f"   • Diverged or Missing on Disk ({len(drift)}):")
            for a in drift:
                st = "Modified/Drift" if a.custody_state == ArtifactCustodyState.MODIFIED else "Missing on Disk"
                lines.append(f"     - [🟠 {st}] {a.name} ({a.relative_path or 'unbound'})")
        if chat_only:
            lines.append(f"   • Conversation Only — Not Saved to Disk ({len(chat_only)}):")
            for a in chat_only:
                lines.append(f"     - [💬 Chat Draft] {a.name} (Drafted in AI conversation)")
        if not (verified or drift or chat_only):
            lines.append("   • (No artifacts tracked yet)")
        lines.append("")

        lines.append("INSTRUCTIONS FOR THIS AI SESSION:")
        lines.append("Adopt this continuity state immediately. Focus on the current focus and next action.")
        lines.append("When we reach new decisions or finish tasks, please output your update in a ```scs-delta block.")

        if include_sync_footer:
            lines.append("")
            lines.append("OUTPUT PROTOCOL TEMPLATE:")
            lines.append(UNIVERSAL_SYNC_FOOTER)

        lines.append("=========================================")

        raw_prompt = "\n".join(lines)
        scrubbed_prompt, redacted_count = scrub_secrets(raw_prompt)
        approx_tokens = max(1, len(scrubbed_prompt) // 4)

        return BootstrapResult(
            project_code=proj.code,
            prompt_text=scrubbed_prompt,
            approx_tokens=approx_tokens,
            redacted_count=redacted_count,
            reconcile_summary=summary,
        )

    def generate_handover_package(
        self, project_id: str, save_to_exports: bool = False
    ) -> Dict[str, Any]:
        """Merges approved Continuity_MD chapters + canonical SQLite state into AI_HANDOVER_PACKAGE.md."""
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        # 1. Reconcile artifacts & gather canonical state
        artifacts, _ = self.reconciler_svc.reconcile_project(project_id)
        decisions = self.decision_svc.list_decisions(project_id, active_only=False)
        tasks = self.checklist_svc.list_tasks(project_id)

        # 2. Reuse existing snapshot if canonical state is unchanged; otherwise seal a new Snapshot
        snp = self._get_or_seal_handover_snapshot(project_id, proj)

        # 3. Load approved Continuity_MD_NN chapters & session counts
        chapters = self._list_continuity_chapters(project_id)
        session_counts = self._get_session_counts(project_id)

        raw_md = self.caveman_engine.compile_ai_handover_package(
            proj=proj,
            snapshot=snp,
            decisions=decisions,
            tasks=tasks,
            artifacts=artifacts,
            chapters=chapters,
            session_counts=session_counts,
            sync_footer=UNIVERSAL_SYNC_FOOTER,
        )
        scrubbed_md, redacted_count = scrub_secrets(raw_md)
        package_hash = hashlib.sha256(scrubbed_md.encode("utf-8")).hexdigest()

        # 4. Also compile Human Operator Briefing ({CODE}_HUMAN_BRIEFING.md)
        raw_human_md = self.caveman_engine.compile_human_briefing(
            proj=proj,
            snapshot=snp,
            decisions=decisions,
            tasks=tasks,
            artifacts=artifacts,
            chapters=chapters,
            session_counts=session_counts,
        )
        scrubbed_human_md, _ = scrub_secrets(raw_human_md)
        human_hash = hashlib.sha256(scrubbed_human_md.encode("utf-8")).hexdigest()

        # 5. Also compile Fast Project Recovery Card ({CODE}_PROJECT_RECOVERY_CARD.md)
        raw_recovery_md = self.caveman_engine.compile_project_recovery_card(
            proj=proj,
            snapshot=snp,
            decisions=decisions,
            tasks=tasks,
            artifacts=artifacts,
            chapters=chapters,
            session_counts=session_counts,
        )
        scrubbed_recovery_md, _ = scrub_secrets(raw_recovery_md)
        recovery_hash = hashlib.sha256(scrubbed_recovery_md.encode("utf-8")).hexdigest()

        now_str = utc_now_iso()
        file_name = f"{proj.code}_AI_HANDOVER_PACKAGE.md"
        human_file_name = f"{proj.code}_HUMAN_BRIEFING.md"
        recovery_file_name = f"{proj.code}_PROJECT_RECOVERY_CARD.md"
        exported_path_str = None
        exported_human_path_str = None
        exported_recovery_path_str = None
        if save_to_exports and self.exports_dir:
            self.exports_dir.mkdir(parents=True, exist_ok=True)
            out_file = self.exports_dir / file_name
            out_file.write_text(scrubbed_md, encoding="utf-8")
            exported_path_str = str(out_file)

            human_out_file = self.exports_dir / human_file_name
            human_out_file.write_text(scrubbed_human_md, encoding="utf-8")
            exported_human_path_str = str(human_out_file)

            recovery_out_file = self.exports_dir / recovery_file_name
            recovery_out_file.write_text(scrubbed_recovery_md, encoding="utf-8")
            exported_recovery_path_str = str(recovery_out_file)

        # Store in handover_packages table
        package_id = uuid.uuid4().hex
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO handover_packages (
                    id, project_id, snapshot_id, protocol_version,
                    markdown_content, checksum_sha256, exported_file_path,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    package_id, project_id, snp.id, "scs-handover/1.0",
                    scrubbed_md, package_hash, exported_path_str, now_str,
                ),
            )

        return {
            "handover_id": package_id,
            "file_name": file_name,
            "human_file_name": human_file_name,
            "recovery_file_name": recovery_file_name,
            "snapshot_id": snp.id,
            "snapshot_code": snp.snapshot_code,
            "markdown_content": scrubbed_md,
            "human_briefing_content": scrubbed_human_md,
            "recovery_card_content": scrubbed_recovery_md,
            "checksum_sha256": package_hash,
            "human_checksum_sha256": human_hash,
            "recovery_checksum_sha256": recovery_hash,
            "exported_file_path": exported_path_str,
            "exported_human_path": exported_human_path_str,
            "exported_recovery_path": exported_recovery_path_str,
            "human_briefing_file_path": exported_human_path_str,
            "recovery_card_file_path": exported_recovery_path_str,
            "chapters_merged": len(chapters),
            "total_sessions": session_counts["total_sessions"],
            "processed_sessions": session_counts["processed_sessions"],
            "pending_sessions": session_counts["pending_sessions"],
            "redacted_count": redacted_count,
            "created_at": now_str,
        }

    def generate_recovery_card(
        self, project_id: str, save_to_exports: bool = False
    ) -> Dict[str, Any]:
        """Compiles approved canonical SQLite state into a 30-60 second fast project recovery card ({CODE}_PROJECT_RECOVERY_CARD.md)."""
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        artifacts, _ = self.reconciler_svc.reconcile_project(project_id)
        decisions = self.decision_svc.list_decisions(project_id, active_only=False)
        tasks = self.checklist_svc.list_tasks(project_id)
        snp = self._get_or_seal_handover_snapshot(project_id, proj)
        chapters = self._list_continuity_chapters(project_id)
        session_counts = self._get_session_counts(project_id)

        raw_recovery_md = self.caveman_engine.compile_project_recovery_card(
            proj=proj,
            snapshot=snp,
            decisions=decisions,
            tasks=tasks,
            artifacts=artifacts,
            chapters=chapters,
            session_counts=session_counts,
        )
        scrubbed_recovery_md, _ = scrub_secrets(raw_recovery_md)
        recovery_hash = hashlib.sha256(scrubbed_recovery_md.encode("utf-8")).hexdigest()

        recovery_file_name = f"{proj.code}_PROJECT_RECOVERY_CARD.md"
        exported_recovery_path_str = None
        if save_to_exports and self.exports_dir:
            self.exports_dir.mkdir(parents=True, exist_ok=True)
            recovery_out_file = self.exports_dir / recovery_file_name
            recovery_out_file.write_text(scrubbed_recovery_md, encoding="utf-8")
            exported_recovery_path_str = str(recovery_out_file)

        return {
            "file_name": recovery_file_name,
            "snapshot_id": snp.id,
            "snapshot_code": snp.snapshot_code,
            "markdown_content": scrubbed_recovery_md,
            "recovery_card_content": scrubbed_recovery_md,
            "checksum_sha256": recovery_hash,
            "exported_file_path": exported_recovery_path_str,
            "chapters_merged": len(chapters),
            "total_sessions": session_counts["total_sessions"],
            "processed_sessions": session_counts["processed_sessions"],
            "pending_sessions": session_counts["pending_sessions"],
        }

    def generate_human_briefing(
        self, project_id: str, save_to_exports: bool = False
    ) -> Dict[str, Any]:
        """Compiles approved canonical SQLite state into a 3-minute executive human briefing ({CODE}_HUMAN_BRIEFING.md)."""
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        artifacts, _ = self.reconciler_svc.reconcile_project(project_id)
        decisions = self.decision_svc.list_decisions(project_id, active_only=False)
        tasks = self.checklist_svc.list_tasks(project_id)
        snp = self._get_or_seal_handover_snapshot(project_id, proj)
        chapters = self._list_continuity_chapters(project_id)
        session_counts = self._get_session_counts(project_id)

        raw_human_md = self.caveman_engine.compile_human_briefing(
            proj=proj,
            snapshot=snp,
            decisions=decisions,
            tasks=tasks,
            artifacts=artifacts,
            chapters=chapters,
            session_counts=session_counts,
        )
        scrubbed_human_md, _ = scrub_secrets(raw_human_md)
        human_hash = hashlib.sha256(scrubbed_human_md.encode("utf-8")).hexdigest()

        human_file_name = f"{proj.code}_HUMAN_BRIEFING.md"
        exported_human_path_str = None
        if save_to_exports and self.exports_dir:
            self.exports_dir.mkdir(parents=True, exist_ok=True)
            human_out_file = self.exports_dir / human_file_name
            human_out_file.write_text(scrubbed_human_md, encoding="utf-8")
            exported_human_path_str = str(human_out_file)

        return {
            "file_name": human_file_name,
            "snapshot_id": snp.id,
            "snapshot_code": snp.snapshot_code,
            "markdown_content": scrubbed_human_md,
            "human_briefing_content": scrubbed_human_md,
            "checksum_sha256": human_hash,
            "exported_file_path": exported_human_path_str,
            "chapters_merged": len(chapters),
            "total_sessions": session_counts["total_sessions"],
            "processed_sessions": session_counts["processed_sessions"],
            "pending_sessions": session_counts["pending_sessions"],
        }

    def _get_or_seal_handover_snapshot(self, project_id: str, proj: Any) -> Any:
        """Returns the latest SnapshotRecord if canonical state SHA-256 matches; else seals a new Snapshot."""
        if proj.latest_snapshot_id and proj.latest_snapshot_sha256:
            existing_snaps = self.project_svc.list_snapshots(project_id)
            latest_snp = next((s for s in existing_snaps if s.id == proj.latest_snapshot_id), None)
            if latest_snp:
                with self.db.transaction() as conn:
                    dec_rows = conn.execute(
                        "SELECT * FROM decisions WHERE project_id = ? ORDER BY code ASC;", (project_id,)
                    ).fetchall()
                    task_rows = conn.execute(
                        "SELECT * FROM tasks WHERE project_id = ? ORDER BY code ASC;", (project_id,)
                    ).fetchall()
                    art_rows = conn.execute(
                        "SELECT * FROM artifacts WHERE project_id = ? ORDER BY name ASC;", (project_id,)
                    ).fetchall()
                state_dict = {
                    "project": {
                        "code": proj.code,
                        "name": proj.name,
                        "objective": proj.objective,
                        "current_focus": proj.current_focus,
                        "next_action": proj.next_action,
                    },
                    "decisions": [
                        {
                            "code": r["code"],
                            "record_kind": r["record_kind"],
                            "statement": r["statement"],
                            "rationale_why": r["rationale_why"],
                            "is_active": bool(r["is_active"]),
                        }
                        for r in dec_rows
                    ],
                    "tasks": [
                        {
                            "code": r["code"],
                            "title": r["title"],
                            "status": r["status"],
                            "priority": r["priority"],
                            "why_it_matters": r["why_it_matters"],
                            "blocker_reason": r["blocker_reason"],
                        }
                        for r in task_rows
                    ],
                    "artifacts": [
                        {
                            "name": r["name"],
                            "artifact_type": r["artifact_type"],
                            "relative_path": r["relative_path"],
                            "custody_state": r["custody_state"],
                            "baseline_sha256": r["baseline_sha256"],
                        }
                        for r in art_rows
                    ],
                }
                canonical_json = json.dumps(state_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                current_sha = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
                if current_sha == latest_snp.checksum_sha256:
                    return latest_snp

        return self.project_svc.create_snapshot(project_id, label="AI Handover Package Seal")

    def _extract_from_json_dict(
        self, project_id: str, data: Dict[str, Any], raw_block: str, source_origin: str
    ) -> List[Dict[str, Any]]:
        staged = []

        # Decisions (handles both scs-delta format and snp.state_json record_kind format)
        for d in data.get("decisions", []):
            r_kind = str(d.get("record_kind", "DECISION")).upper()
            p_type = ProposalType.DECISION
            if r_kind == "CONSTRAINT":
                p_type = ProposalType.CONSTRAINT
            elif r_kind == "REJECTED_OPTION":
                p_type = ProposalType.REJECTED_OPTION
            elif r_kind == "IDEA":
                p_type = ProposalType.IDEA

            staged.append({
                "project_id": project_id,
                "proposal_type": p_type,
                "title": d.get("statement") or d.get("title") or "New Decision",
                "rationale_why": d.get("why") or d.get("rationale") or d.get("rationale_why") or "",
                "source_excerpt": raw_block[:200],
                "source_origin": source_origin,
            })

        # Rejected options
        for r in data.get("rejected_options", []):
            staged.append({
                "project_id": project_id,
                "proposal_type": ProposalType.REJECTED_OPTION,
                "title": r.get("statement") or r.get("title") or "Rejected Option",
                "rationale_why": r.get("why") or r.get("rationale") or "",
                "source_excerpt": raw_block[:200],
                "source_origin": source_origin,
            })

        # Constraints
        for c in data.get("constraints", []):
            staged.append({
                "project_id": project_id,
                "proposal_type": ProposalType.CONSTRAINT,
                "title": c.get("statement") or c.get("title") or "New Constraint",
                "rationale_why": c.get("why") or c.get("rationale") or "",
                "source_excerpt": raw_block[:200],
                "source_origin": source_origin,
            })

        # Tasks
        for t in data.get("tasks", []):
            title = t.get("title") if isinstance(t, dict) else str(t)
            why = t.get("why") or t.get("reason") or "" if isinstance(t, dict) else ""
            status = t.get("status", "PENDING") if isinstance(t, dict) else "PENDING"
            staged.append({
                "project_id": project_id,
                "proposal_type": ProposalType.TASK,
                "title": title,
                "rationale_why": why,
                "source_excerpt": raw_block[:200],
                "source_origin": source_origin,
                "payload": {"status": status},
            })

        # Artifacts
        for a in data.get("artifacts", []):
            name = a.get("name") if isinstance(a, dict) else str(a)
            note = a.get("note") or a.get("description") or "" if isinstance(a, dict) else ""
            rel = a.get("relative_path") if isinstance(a, dict) else None
            staged.append({
                "project_id": project_id,
                "proposal_type": ProposalType.ARTIFACT,
                "title": name,
                "rationale_why": note,
                "source_excerpt": raw_block[:200],
                "source_origin": source_origin,
                "payload": {"relative_path": rel},
            })

        return staged

    def _extract_single_heuristic(
        self, project_id: str, text: str, source_origin: str
    ) -> Dict[str, Any]:
        clean_text = text.strip()
        first_line = clean_text.splitlines()[0] if clean_text.splitlines() else clean_text
        lower_full = clean_text.lower()

        p_type = ProposalType.TASK
        if any(k in lower_full for k in ["blocker:", "blocked", "broken", "issue:", "fail"]):
            p_type = ProposalType.BLOCKER
        elif any(k in lower_full for k in ["decision:", "decided", "agreed"]):
            p_type = ProposalType.DECISION
        elif any(k in lower_full for k in ["rejected", "rejected option", "do not use"]):
            p_type = ProposalType.REJECTED_OPTION
        elif any(k in lower_full for k in ["idea:", "maybe we could", "explore"]):
            p_type = ProposalType.IDEA

        # Title
        title = first_line
        if len(title) > 60:
            title = title[:57].rstrip() + "..."

        # Why clause
        why = ""
        m_why = re.search(r"(?:because|why|since|in order to|so that)\s+([^,\.\n]{4,50})", clean_text, re.IGNORECASE)
        if m_why:
            why = m_why.group(1).strip()

        return {
            "project_id": project_id,
            "proposal_type": p_type,
            "title": title,
            "rationale_why": why,
            "source_excerpt": clean_text[:300],
            "source_origin": source_origin,
        }

    # ---------------------------------------------------------------------------
    # Conversation Session Custody & Continuity_MD Chapter Engine
    # ---------------------------------------------------------------------------

    def _load_session_rows(
        self, project_id: str, statuses: Optional[Tuple[str, ...]] = None
    ) -> List[Dict[str, Any]]:
        """Loads persisted raw conversation sessions from SQLite conversation_sessions."""
        with self.db.transaction() as conn:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                rows = conn.execute(
                    f"SELECT * FROM conversation_sessions WHERE project_id = ? AND checkpoint_status IN ({placeholders}) ORDER BY started_at ASC, rowid ASC;",
                    (project_id, *statuses),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversation_sessions WHERE project_id = ? ORDER BY started_at ASC, rowid ASC;",
                    (project_id,),
                ).fetchall()

        records: List[Dict[str, Any]] = []
        for idx, r in enumerate(rows, 1):
            frag_item: Dict[str, Any] = {}
            try:
                parsed = json.loads(r["fragments_json"]) if r["fragments_json"] else []
                if isinstance(parsed, list) and parsed:
                    frag_item = parsed[0]
            except Exception:
                frag_item = {}

            keys = r.keys()
            direct_content = r["content"] if "content" in keys else ""
            direct_sha = r["checksum_sha256"] if "checksum_sha256" in keys else ""
            direct_code = r["session_code"] if "session_code" in keys else None
            direct_num = r["session_num"] if "session_num" in keys else None
            direct_src = r["source"] if "source" in keys else None
            direct_words = r["word_count"] if "word_count" in keys else None
            direct_file = r["raw_file_path"] if "raw_file_path" in keys else None

            s_num = direct_num if direct_num is not None else int(frag_item.get("session_num") or frag_item.get("sequence_idx") or idx)
            s_code = direct_code or frag_item.get("session_code") or f"SES-{s_num:03d}"
            content = direct_content or frag_item.get("content", "")
            sha = direct_sha or frag_item.get("checksum_sha256", "")
            src = direct_src or frag_item.get("source", "CLIPBOARD")
            words = direct_words if direct_words else int(frag_item.get("word_count") or len(content.split()))
            raw_file = direct_file or frag_item.get("raw_file_path")

            records.append({
                "id": r["id"],
                "project_id": r["project_id"],
                "session_num": s_num,
                "session_code": s_code,
                "content": content,
                "source": src,
                "word_count": words,
                "checksum_sha256": sha,
                "raw_file_path": raw_file,
                "started_at": r["started_at"],
                "last_activity": r["last_activity"],
                "checkpoint_status": r["checkpoint_status"],
                "latest_checkpoint_path": r["latest_checkpoint_path"],
                "latest_checkpoint_sha256": r["latest_checkpoint_sha256"],
                "latest_snapshot_code": r["latest_snapshot_code"],
            })
        return records

    def _get_session_counts(self, project_id: str) -> Dict[str, int]:
        rows = self._load_session_rows(project_id)
        active_rows = [r for r in rows if r["checkpoint_status"] != CheckpointStatus.ARCHIVED.value]
        processed = sum(1 for r in active_rows if r["checkpoint_status"] == CheckpointStatus.APPROVED.value)
        pending = sum(
            1 for r in active_rows
            if r["checkpoint_status"] in (CheckpointStatus.DRAFT.value, CheckpointStatus.GENERATED.value)
        )
        return {
            "total_sessions": len(active_rows),
            "processed_sessions": processed,
            "pending_sessions": pending,
        }

    def _list_continuity_chapters(self, project_id: str) -> List[Dict[str, Any]]:
        """Lists approved Continuity_MD_NN chapters stored in handover_packages."""
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT hp.*, s.snapshot_code
                FROM handover_packages hp
                LEFT JOIN snapshots s ON hp.snapshot_id = s.id
                WHERE hp.project_id = ? AND hp.protocol_version = 'scs-continuity-md/1.0'
                ORDER BY hp.created_at ASC, hp.rowid ASC;
                """,
                (project_id,),
            ).fetchall()

        chapters: List[Dict[str, Any]] = []
        for idx, r in enumerate(rows, 1):
            md = r["markdown_content"] or ""
            meta = self.caveman_engine.parse_chapter_metadata(md)
            chapters.append({
                "id": r["id"],
                "snapshot_id": r["snapshot_id"],
                "snapshot_code": r["snapshot_code"] or meta.get("snapshot_code", "SEALED"),
                "chapter_code": meta.get("chapter_code") or f"Continuity_MD_{idx:02d}",
                "session_range": meta.get("session_range", "N/A"),
                "session_count": int(meta.get("session_count", 0)),
                "context_summary": meta.get("context_summary", ""),
                "markdown_content": md,
                "checksum_sha256": r["checksum_sha256"],
                "exported_file_path": r["exported_file_path"],
                "created_at": r["created_at"],
            })
        return chapters

    def get_session_telemetry(self, project_id: str) -> Dict[str, Any]:
        """Returns complete session & Continuity_MD telemetry for HUD DashboardState."""
        all_rows = [
            r for r in self._load_session_rows(project_id)
            if r["checkpoint_status"] != CheckpointStatus.ARCHIVED.value
        ]
        pending_rows = [
            r for r in all_rows
            if r["checkpoint_status"] in (CheckpointStatus.DRAFT.value, CheckpointStatus.GENERATED.value)
        ]
        processed_count = sum(
            1 for r in all_rows if r["checkpoint_status"] == CheckpointStatus.APPROVED.value
        )
        chapters = self._list_continuity_chapters(project_id)

        active_sess = self._build_active_session_view(project_id, pending_rows)

        chapter_summaries = [
            {
                "id": ch["id"],
                "chapter_code": ch["chapter_code"],
                "session_range": ch["session_range"],
                "session_count": ch["session_count"],
                "snapshot_code": ch["snapshot_code"],
                "context_summary": ch["context_summary"],
                "checksum_sha256": ch["checksum_sha256"],
                "exported_file_path": ch["exported_file_path"],
                "created_at": ch["created_at"],
            }
            for ch in chapters
        ]

        session_summaries = [
            {
                "id": r["id"],
                "session_num": r["session_num"],
                "session_code": r["session_code"],
                "word_count": r["word_count"],
                "checksum_sha256": r["checksum_sha256"],
                "checkpoint_status": r["checkpoint_status"],
                "latest_snapshot_code": r["latest_snapshot_code"],
                "latest_checkpoint_path": r["latest_checkpoint_path"],
                "raw_file_path": r["raw_file_path"],
                "started_at": r["started_at"],
                "preview": re.sub(r"\s+", " ", r["content"])[:160],
            }
            for r in reversed(all_rows)
        ]

        return {
            "active_session": active_sess,
            "fragment_count": len(pending_rows),
            "total_sessions": len(all_rows),
            "processed_sessions": processed_count,
            "pending_sessions": len(pending_rows),
            "continuity_md_count": len(chapters),
            "continuity_chapters": chapter_summaries,
            "session_records": session_summaries,
        }

    def _build_active_session_view(
        self, project_id: str, pending_rows: List[Dict[str, Any]]
    ) -> ConversationSession:
        """Synthesizes a ConversationSession view over pending raw sessions for backward compatibility."""
        fragments = [
            ChatFragment(
                id=r["id"],
                sequence_idx=idx,
                content=r["content"],
                timestamp=r["started_at"],
                source=r["source"],
                word_count=r["word_count"],
                checksum_sha256=r["checksum_sha256"],
            )
            for idx, r in enumerate(pending_rows, 1)
        ]
        status = CheckpointStatus.DRAFT
        if pending_rows and all(r["checkpoint_status"] == CheckpointStatus.GENERATED.value for r in pending_rows):
            status = CheckpointStatus.GENERATED

        sess = ConversationSession(
            session_id=pending_rows[0]["id"] if pending_rows else f"pending_{project_id[:8]}",
            project_id=project_id,
            fragments=fragments,
            started_at=pending_rows[0]["started_at"] if pending_rows else utc_now_iso(),
            last_activity=pending_rows[-1]["last_activity"] if pending_rows else utc_now_iso(),
            checkpoint_status=status,
        )
        self._active_sessions[project_id] = sess
        return sess

    def get_or_create_session(self, project_id: str) -> ConversationSession:
        """Retrieves a ConversationSession view of all pending sessions for the project."""
        pending_rows = self._load_session_rows(
            project_id,
            statuses=(CheckpointStatus.DRAFT.value, CheckpointStatus.GENERATED.value),
        )
        return self._build_active_session_view(project_id, pending_rows)

    def add_chat_fragment(
        self,
        project_id: str,
        text: str,
        source: str = "CLIPBOARD",
        prevent_duplicate: bool = False,
    ) -> Dict[str, Any]:
        """Stores one verbatim AI conversation session as raw evidence (no processing, no snapshot)."""
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Conversation session text cannot be empty.")

        sha = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        words = len(clean_text.split())

        all_rows = self._load_session_rows(project_id)
        if prevent_duplicate:
            dup = next(
                (
                    r for r in all_rows
                    if r["checkpoint_status"] != CheckpointStatus.ARCHIVED.value
                    and r["checksum_sha256"] == sha
                ),
                None,
            )
            if dup:
                raise ValueError(
                    f"Duplicate session ignored: identical conversation already stored as {dup['session_code']}."
                )

        session_num = max((r["session_num"] for r in all_rows), default=0) + 1
        session_code = f"SES-{session_num:03d}"
        now = utc_now_iso()
        row_id = str(uuid.uuid4())

        raw_file_str = None
        if self.exports_dir:
            sessions_dir = self.exports_dir / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            raw_file = sessions_dir / f"{proj.code}_{session_code}.md"
            raw_file.write_text(clean_text, encoding="utf-8")
            raw_file_str = str(raw_file)

        frag_payload = [{
            "id": row_id,
            "sequence_idx": session_num,
            "session_num": session_num,
            "session_code": session_code,
            "content": clean_text,
            "timestamp": now,
            "source": source,
            "word_count": words,
            "checksum_sha256": sha,
            "raw_file_path": raw_file_str,
        }]

        with self.db.transaction() as conn:
            cols = [col["name"] for col in conn.execute("PRAGMA table_info(conversation_sessions);").fetchall()]
            if "content" in cols:
                conn.execute(
                    """
                    INSERT INTO conversation_sessions (
                        id, project_id, session_code, session_num, content, checksum_sha256,
                        source, word_count, raw_file_path, fragments_json, started_at, last_activity, checkpoint_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        row_id, project_id, session_code, session_num, clean_text, sha,
                        source, words, raw_file_str, json.dumps(frag_payload, ensure_ascii=False),
                        now, now, CheckpointStatus.DRAFT.value
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO conversation_sessions (
                        id, project_id, fragments_json, started_at, last_activity, checkpoint_status
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (row_id, project_id, json.dumps(frag_payload, ensure_ascii=False), now, now, CheckpointStatus.DRAFT.value),
                )

        # Invalidate any unapproved draft cache since pending session buffer changed
        self._draft_cache.pop(project_id, None)

        counts = self._get_session_counts(project_id)
        return {
            "session_id": row_id,
            "session_code": session_code,
            "session_num": session_num,
            "word_count": words,
            "checksum_sha256": sha,
            "raw_file_path": raw_file_str,
            "total_sessions": counts["total_sessions"],
            "processed_sessions": counts["processed_sessions"],
            "pending_sessions": counts["pending_sessions"],
            "fragment_count": counts["pending_sessions"],
            "max_capacity": 10,
            "recommended_batch_ready": counts["pending_sessions"] >= 10,
            "auto_generated": False,
            "checkpoint": None,
        }

    def get_conversation_session(self, project_id: str) -> Dict[str, Any]:
        """Returns the pending conversation session view and session counts for a project."""
        telemetry = self.get_session_telemetry(project_id)
        return {
            "session": telemetry["active_session"].model_dump(mode="json"),
            "fragment_count": telemetry["pending_sessions"],
            "total_sessions": telemetry["total_sessions"],
            "processed_sessions": telemetry["processed_sessions"],
            "pending_sessions": telemetry["pending_sessions"],
            "continuity_md_count": telemetry["continuity_md_count"],
            "max_capacity": 10,
        }

    def generate_checkpoint(
        self,
        project_id: str,
        last_n: Optional[int] = None,
        auto: bool = False,
        batch_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Runs Caveman extraction on pending sessions to create an UNSEALED Continuity_MD_NN draft.

        Governance Custody Rule:
        - Does NOT seal a Snapshot yet.
        - Does NOT promote to canonical ledger yet.
        - Does NOT export final chapter file until human calls approve_checkpoint().
        """
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        pending_rows = self._load_session_rows(
            project_id,
            statuses=(CheckpointStatus.DRAFT.value, CheckpointStatus.GENERATED.value),
        )
        if not pending_rows:
            raise ValueError("No pending conversation sessions to process. Paste a session first.")

        target_rows = pending_rows
        if batch_size and batch_size > 0:
            target_rows = pending_rows[:batch_size]
        elif last_n and last_n > 0:
            target_rows = pending_rows[-last_n:]

        session_texts = [r["content"] for r in target_rows]
        session_codes = [r["session_code"] for r in target_rows]
        target_ids = [r["id"] for r in target_rows]
        session_range = (
            session_codes[0]
            if len(session_codes) == 1
            else f"{session_codes[0]}..{session_codes[-1]}"
        )

        existing_chapters = self._list_continuity_chapters(project_id)
        chapter_num = len(existing_chapters) + 1
        chapter_code = f"Continuity_MD_{chapter_num:02d}"
        file_name = f"{proj.code}_{chapter_code}.md"

        # 1. Run Caveman Context Extraction Engine
        extracted = self.caveman_engine.extract(
            fragments=session_texts,
            project_code=proj.code,
            active_focus=proj.current_focus,
            active_next=proj.next_action,
            session_codes=session_codes,
        )

        # 2. Cross-check conflicts against existing canonical constraints & rejected options in SQLite
        existing_decs = self.decision_svc.list_decisions(project_id, active_only=True)
        canonical_cons = [d.statement for d in existing_decs if d.record_kind == DecisionKind.CONSTRAINT]
        canonical_rejs = [
            {"code": d.code, "statement": d.statement, "why": d.rationale_why}
            for d in existing_decs
            if d.record_kind == DecisionKind.REJECTED_OPTION
        ]
        merged_cons = list(extracted.constraints)
        for cc in canonical_cons:
            if not any(cc.lower() == mc.lower() for mc in merged_cons):
                merged_cons.append(cc)
        merged_rejs = list(extracted.rejected_options)
        for cr in canonical_rejs:
            if not any(cr["statement"].lower() == mr["statement"].lower() for mr in merged_rejs):
                merged_rejs.append(cr)

        cross_conflicts = self.caveman_engine.validator.detect_conflicts(
            extracted.decisions, merged_cons, merged_rejs, extracted.pending_tasks
        )
        for cf in cross_conflicts:
            if cf not in extracted.conflicts:
                extracted.conflicts.append(cf)
        if extracted.conflicts:
            extracted.first_instruction_for_next_ai = self.caveman_engine._determine_next_ai_instruction(
                extracted, proj.next_action
            )

        # 3. Compile UNSEALED draft Continuity_MD (Snapshot is NOT created until human approval!)
        batch_id = target_ids[0]
        evidence_concat = "\n".join(r["checksum_sha256"] for r in target_rows)
        draft_evidence_sha = hashlib.sha256(evidence_concat.encode("utf-8")).hexdigest()

        md_content = self.caveman_engine.compile_markdown_checkpoint(
            project_code=proj.code,
            project_name=proj.name,
            session_id=batch_id,
            snapshot_code="PENDING_APPROVAL",
            checksum_sha256=draft_evidence_sha,
            extracted=extracted,
            fragment_count=len(target_rows),
            checkpoint_status=CheckpointStatus.GENERATED.value,
            chapter_code=chapter_code,
            session_range=session_range,
        )
        draft_md_sha = hashlib.sha256(md_content.encode("utf-8")).hexdigest()

        now = utc_now_iso()
        with self.db.transaction() as conn:
            placeholders = ",".join("?" for _ in target_ids)
            conn.execute(
                f"""
                UPDATE conversation_sessions
                SET checkpoint_status = ?, latest_checkpoint_sha256 = ?, last_activity = ?
                WHERE id IN ({placeholders});
                """,
                (CheckpointStatus.GENERATED.value, draft_md_sha, now, *target_ids),
            )

        self._draft_cache[project_id] = {
            "batch_id": batch_id,
            "target_ids": target_ids,
            "session_codes": session_codes,
            "session_range": session_range,
            "chapter_num": chapter_num,
            "chapter_code": chapter_code,
            "file_name": file_name,
            "extracted": extracted,
        }

        return {
            "session_id": batch_id,
            "session_ids": target_ids,
            "session_codes": session_codes,
            "session_range": session_range,
            "session_count": len(target_rows),
            "chapter_num": chapter_num,
            "chapter_code": chapter_code,
            "project_code": proj.code,
            "file_name": file_name,
            "file_path": None,
            "snapshot_code": "PENDING_APPROVAL",
            "checksum_sha256": draft_md_sha,
            "markdown_content": md_content,
            "status": CheckpointStatus.GENERATED.value,
            "auto_generated": auto,
            "extracted_summary": {
                "decisions_count": len(extracted.decisions),
                "rejected_count": len(extracted.rejected_options),
                "constraints_count": len(extracted.constraints),
                "tasks_count": len(extracted.pending_tasks),
                "completed_tasks_count": len(extracted.completed_tasks),
                "artifacts_count": len(extracted.artifacts),
                "open_questions_count": len(extracted.open_questions),
                "evolution_count": len(extracted.project_evolution),
                "conflicts_count": len(extracted.conflicts),
            },
        }

    def approve_checkpoint(
        self, project_id: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Human approval gate: promotes extracted continuity intelligence, seals Snapshot, and writes Continuity_MD_NN.md."""
        proj = self.project_svc.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        draft = self._draft_cache.get(project_id)
        if not draft:
            # Stateless recovery if host restarted after generate_checkpoint
            gen_rows = self._load_session_rows(project_id, statuses=(CheckpointStatus.GENERATED.value,))
            if not gen_rows:
                gen_rows = self._load_session_rows(project_id, statuses=(CheckpointStatus.DRAFT.value,))
            if not gen_rows:
                raise ValueError("No pending Continuity MD draft found to approve.")
            self.generate_checkpoint(project_id)
            draft = self._draft_cache[project_id]

        extracted: ExtractedContext = draft["extracted"]
        target_ids: List[str] = draft["target_ids"]
        chapter_code: str = draft["chapter_code"]
        session_range: str = draft["session_range"]
        file_name: str = draft["file_name"]
        batch_id: str = draft["batch_id"]

        promoted_decisions = 0
        promoted_tasks = 0
        promoted_artifacts = 0

        existing_decs = self.decision_svc.list_decisions(project_id, active_only=True)

        # 1. Cross-chapter Decision Evolution: retire active decisions superseded by new rejections/reversals
        for r in extracted.rejected_options:
            rej_core = re.sub(r"^(?:use|adopt|choose|select)\s+", "", r["statement"].lower()).strip()
            if len(rej_core) > 2:
                for ed in list(existing_decs):
                    if ed.record_kind == DecisionKind.DECISION and ed.is_active:
                        ed_core = re.sub(r"^(?:use|adopt|choose|select)\s+", "", ed.statement.lower()).strip()
                        if rej_core == ed_core or rej_core in ed_core:
                            self.decision_svc.toggle_decision_active(ed.id)
                            ed.is_active = False

        # 2. Promote Decisions (deduplicated)
        for d in extracted.decisions:
            if any(
                ed.is_active and ed.record_kind == DecisionKind.DECISION and ed.statement.lower() == d.title.lower()
                for ed in existing_decs
            ):
                continue
            created = self.decision_svc.create_decision(
                project_id=project_id,
                record_kind=DecisionKind.DECISION,
                statement=d.title,
                rationale_why=d.reasoning,
                impact_scope=d.alternatives_considered,
                source_excerpt=d.evidence_quote,
            )
            existing_decs.append(created)
            promoted_decisions += 1

        # 3. Promote Constraints (deduplicated with subsumption upgrade)
        for c in extracted.constraints:
            subsumed = [
                ed for ed in existing_decs
                if ed.is_active and ed.record_kind == DecisionKind.CONSTRAINT
                and ed.statement.lower() in c.lower() and ed.statement.lower() != c.lower()
            ]
            for old_c in subsumed:
                self.decision_svc.toggle_decision_active(old_c.id)
                old_c.is_active = False

            if any(
                ed.is_active and ed.record_kind == DecisionKind.CONSTRAINT and c.lower() in ed.statement.lower()
                for ed in existing_decs
            ):
                continue
            created_c = self.decision_svc.create_decision(
                project_id=project_id,
                record_kind=DecisionKind.CONSTRAINT,
                statement=c,
                rationale_why="Architectural boundary constraint",
            )
            existing_decs.append(created_c)
            promoted_decisions += 1

        # 4. Promote Rejected Options (deduplicated)
        for r in extracted.rejected_options:
            if any(
                ed.is_active and ed.record_kind == DecisionKind.REJECTED_OPTION
                and ed.statement.lower() == r["statement"].lower()
                for ed in existing_decs
            ):
                continue
            created_r = self.decision_svc.create_decision(
                project_id=project_id,
                record_kind=DecisionKind.REJECTED_OPTION,
                statement=r["statement"],
                rationale_why=r.get("why", ""),
                source_excerpt=r.get("quote", ""),
            )
            existing_decs.append(created_r)
            promoted_decisions += 1

        # 5. Promote Completed & Pending Tasks
        existing_tasks = self.checklist_svc.list_tasks(project_id)
        for ct in extracted.completed_tasks:
            match_t = next((et for et in existing_tasks if et.title.lower() == ct["title"].lower()), None)
            if match_t:
                if match_t.status != TaskStatus.COMPLETED:
                    self.checklist_svc.update_task_status(match_t.id, TaskStatus.COMPLETED)
                    promoted_tasks += 1
            else:
                new_ct = self.checklist_svc.create_task(
                    project_id=project_id,
                    title=ct["title"],
                    why_it_matters=ct.get("why", ""),
                )
                self.checklist_svc.update_task_status(new_ct.id, TaskStatus.COMPLETED)
                existing_tasks.append(new_ct)
                promoted_tasks += 1

        for t in extracted.pending_tasks:
            if any(et.title.lower() == t["title"].lower() for et in existing_tasks):
                continue
            new_t = self.checklist_svc.create_task(
                project_id=project_id,
                title=t["title"],
                why_it_matters=t.get("why", ""),
            )
            existing_tasks.append(new_t)
            promoted_tasks += 1

        # 6. Promote Artifacts (previously omitted — now registered with deduplication)
        existing_arts = self.artifact_svc.list_artifacts(project_id)
        for a in extracted.artifacts:
            rel_path = a.get("path", "").strip()
            if not rel_path:
                continue
            name = Path(rel_path).name
            if any(
                (ea.relative_path or "").replace("\\", "/").lower() == rel_path.lower()
                for ea in existing_arts
            ):
                continue
            ext = Path(rel_path).suffix.lower()
            art_type = ArtifactType.DOCUMENT
            if ext in (".py", ".js", ".ts", ".html", ".css", ".sql", ".sh", ".bat"):
                art_type = ArtifactType.CODE_FILE
            elif ext in (".json", ".yaml", ".yml"):
                art_type = ArtifactType.SPECIFICATION
            try:
                created_a = self.artifact_svc.register_artifact(
                    project_id=project_id,
                    name=name,
                    artifact_type=art_type,
                    conversation_note=f"Referenced in {chapter_code} ({session_range})",
                    relative_path=rel_path,
                )
                existing_arts.append(created_a)
                promoted_artifacts += 1
            except Exception:
                pass

        # 7. Update project operational state (next_action & current_focus if blank)
        next_act_update = extracted.first_instruction_for_next_ai or None
        focus_update = None
        if not proj.current_focus and extracted.session_themes:
            focus_update = extracted.session_themes[-1][:140]
        if next_act_update or focus_update:
            self.project_svc.update_project_session(
                project_id,
                current_focus=focus_update,
                next_action=next_act_update,
            )

        # 8. Seal immutable Snapshot POST-APPROVAL
        snp = self.project_svc.create_snapshot(
            project_id, label=f"{chapter_code} ({session_range})"
        )

        # 9. Compile sealed Continuity_MD_NN.md & export
        sealed_md = self.caveman_engine.compile_markdown_checkpoint(
            project_code=proj.code,
            project_name=proj.name,
            session_id=batch_id,
            snapshot_code=snp.snapshot_code,
            checksum_sha256=snp.checksum_sha256,
            extracted=extracted,
            fragment_count=len(target_ids),
            checkpoint_status=CheckpointStatus.APPROVED.value,
            chapter_code=chapter_code,
            session_range=session_range,
        )
        chapter_sha = hashlib.sha256(sealed_md.encode("utf-8")).hexdigest()

        out_path_str = None
        if self.exports_dir:
            self.exports_dir.mkdir(parents=True, exist_ok=True)
            out_file = self.exports_dir / file_name
            out_file.write_text(sealed_md, encoding="utf-8")
            out_path_str = str(out_file)

        now = utc_now_iso()
        chapter_pkg_id = uuid.uuid4().hex
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO handover_packages (
                    id, project_id, snapshot_id, protocol_version,
                    markdown_content, checksum_sha256, exported_file_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    chapter_pkg_id,
                    project_id,
                    snp.id,
                    "scs-continuity-md/1.0",
                    sealed_md,
                    chapter_sha,
                    out_path_str,
                    now,
                ),
            )
            placeholders = ",".join("?" for _ in target_ids)
            conn.execute(
                f"""
                UPDATE conversation_sessions
                SET checkpoint_status = ?,
                    latest_checkpoint_path = ?,
                    latest_checkpoint_sha256 = ?,
                    latest_snapshot_code = ?,
                    last_activity = ?
                WHERE id IN ({placeholders});
                """,
                (
                    CheckpointStatus.APPROVED.value,
                    out_path_str,
                    chapter_sha,
                    snp.snapshot_code,
                    now,
                    *target_ids,
                ),
            )

        self._draft_cache.pop(project_id, None)

        return {
            "approved": True,
            "session_id": batch_id,
            "session_ids": target_ids,
            "session_range": session_range,
            "chapter_code": chapter_code,
            "file_name": file_name,
            "file_path": out_path_str,
            "snapshot_id": snp.id,
            "snapshot_code": snp.snapshot_code,
            "checksum_sha256": snp.checksum_sha256,
            "chapter_sha256": chapter_sha,
            "markdown_content": sealed_md,
            "promoted_decisions": promoted_decisions,
            "promoted_tasks": promoted_tasks,
            "promoted_artifacts": promoted_artifacts,
            "new_session_id": f"pending_{project_id[:8]}",
        }

    def clear_chat_fragments(self, project_id: str) -> Dict[str, Any]:
        """Archives unapproved pending sessions while keeping approved raw evidence intact."""
        pending_rows = self._load_session_rows(
            project_id,
            statuses=(CheckpointStatus.DRAFT.value, CheckpointStatus.GENERATED.value),
        )
        if pending_rows:
            target_ids = [r["id"] for r in pending_rows]
            now = utc_now_iso()
            with self.db.transaction() as conn:
                placeholders = ",".join("?" for _ in target_ids)
                conn.execute(
                    f"UPDATE conversation_sessions SET checkpoint_status = ?, last_activity = ? WHERE id IN ({placeholders});",
                    (CheckpointStatus.ARCHIVED.value, now, *target_ids),
                )
        self._draft_cache.pop(project_id, None)
        return {"cleared": True, "count": len(pending_rows)}
