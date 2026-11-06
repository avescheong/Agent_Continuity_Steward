"""Human Approval Boundary & Proposal Quarantine Inbox service."""

import json
from typing import List, Optional, Dict, Any
from src.scs_core.db.database import VaultDatabase
from src.scs_core.models import (
    Proposal, ProposalType, ProposalStatus,
    TaskStatus, TaskPriority, DecisionKind, ArtifactType,
    utc_now_iso,
)
from src.scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from src.scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from src.scs_core.modules.mod06_artifact_registry import ArtifactRegistryService


class ApprovalGateService:
    def __init__(
        self,
        db: VaultDatabase,
        decision_service: DecisionLedgerService,
        checklist_service: ChecklistEngineService,
        artifact_service: ArtifactRegistryService,
    ):
        self.db = db
        self.decision_service = decision_service
        self.checklist_service = checklist_service
        self.artifact_service = artifact_service

    def stage_proposal(
        self,
        project_id: str,
        proposal_type: ProposalType,
        title: str,
        rationale_why: str = "",
        source_excerpt: str = "",
        source_origin: str = "MANUAL_CAPTURE",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Proposal:
        """Quarantines captured candidate item in proposals table with status = PENDING."""
        now = utc_now_iso()
        prop = Proposal(
            project_id=project_id,
            proposal_type=proposal_type,
            title=title.strip(),
            rationale_why=rationale_why.strip(),
            source_excerpt=source_excerpt.strip(),
            source_origin=source_origin.strip(),
            payload=payload or {},
            status=ProposalStatus.PENDING,
            created_at=now,
        )

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO proposals (
                    id, project_id, proposal_type, title, rationale_why,
                    source_excerpt, source_origin, payload_json, status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    prop.id, prop.project_id, prop.proposal_type.value,
                    prop.title, prop.rationale_why, prop.source_excerpt,
                    prop.source_origin, json.dumps(prop.payload),
                    prop.status.value, prop.created_at,
                ),
            )
        return prop

    def stage_batch(self, proposals_list: List[Dict[str, Any]]) -> List[Proposal]:
        results = []
        for item in proposals_list:
            p = self.stage_proposal(
                project_id=item["project_id"],
                proposal_type=item["proposal_type"],
                title=item["title"],
                rationale_why=item.get("rationale_why", ""),
                source_excerpt=item.get("source_excerpt", ""),
                source_origin=item.get("source_origin", "BATCH_CAPTURE"),
                payload=item.get("payload", {}),
            )
            results.append(p)
        return results

    def list_proposals(
        self, project_id: str, status_filter: Optional[ProposalStatus] = ProposalStatus.PENDING
    ) -> List[Proposal]:
        with self.db.transaction() as conn:
            query = "SELECT * FROM proposals WHERE project_id = ?"
            params = [project_id]
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter.value)
            query += " ORDER BY created_at ASC;"

            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def approve_proposal(
        self, proposal_id: str, overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ratifies a proposal and creates the canonical row. AI Proposes -> Human Decides."""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?;", (proposal_id,)).fetchone()
            if not row:
                raise ValueError(f"Proposal not found: {proposal_id}")
            if row["status"] != ProposalStatus.PENDING.value:
                raise ValueError(f"Proposal already resolved with status: {row['status']}")

            prop = self._row_to_proposal(row)

            # Apply user overrides if any
            title = overrides.get("title", prop.title).strip() if overrides and "title" in overrides else prop.title
            why = overrides.get("rationale_why", prop.rationale_why).strip() if overrides and "rationale_why" in overrides else prop.rationale_why
            p_type = ProposalType(overrides.get("proposal_type", prop.proposal_type.value)) if overrides and "proposal_type" in overrides else prop.proposal_type
            payload = overrides.get("payload", prop.payload) if overrides and "payload" in overrides else prop.payload

            was_edited = overrides is not None and bool(overrides)
            final_status = ProposalStatus.EDITED_APPROVED if was_edited else ProposalStatus.APPROVED

            created_entity_id = None

            # Route by type
            if p_type == ProposalType.TASK:
                prio = TaskPriority(payload.get("priority", TaskPriority.MEDIUM.value))
                t = self.checklist_service.create_task(
                    project_id=prop.project_id,
                    title=title,
                    status=TaskStatus.PENDING,
                    priority=prio,
                    why_it_matters=why,
                    source_excerpt=prop.source_excerpt,
                    source_proposal_id=prop.id,
                )
                created_entity_id = t.id

            elif p_type == ProposalType.BLOCKER:
                prio = TaskPriority(payload.get("priority", TaskPriority.HIGH.value))
                t = self.checklist_service.create_task(
                    project_id=prop.project_id,
                    title=title,
                    status=TaskStatus.BLOCKED,
                    priority=prio,
                    why_it_matters=why,
                    blocker_reason=why or title,
                    source_excerpt=prop.source_excerpt,
                    source_proposal_id=prop.id,
                )
                created_entity_id = t.id

            elif p_type in (ProposalType.DECISION, ProposalType.CONSTRAINT, ProposalType.REJECTED_OPTION, ProposalType.IDEA):
                kind_map = {
                    ProposalType.DECISION: DecisionKind.DECISION,
                    ProposalType.CONSTRAINT: DecisionKind.CONSTRAINT,
                    ProposalType.REJECTED_OPTION: DecisionKind.REJECTED_OPTION,
                    ProposalType.IDEA: DecisionKind.IDEA,
                }
                d = self.decision_service.create_decision(
                    project_id=prop.project_id,
                    record_kind=kind_map[p_type],
                    statement=title,
                    rationale_why=why,
                    impact_scope=payload.get("impact_scope", ""),
                    source_excerpt=prop.source_excerpt,
                    source_proposal_id=prop.id,
                )
                created_entity_id = d.id

            elif p_type == ProposalType.ARTIFACT:
                art_type = ArtifactType(payload.get("artifact_type", ArtifactType.DOCUMENT.value))
                rel_path = payload.get("relative_path")
                ext_ref = payload.get("external_ref")
                a = self.artifact_service.register_artifact(
                    project_id=prop.project_id,
                    name=title,
                    artifact_type=art_type,
                    conversation_note=why,
                    relative_path=rel_path,
                    external_ref=ext_ref,
                    source_proposal_id=prop.id,
                )
                created_entity_id = a.id

            conn.execute(
                """
                UPDATE proposals SET
                    status = ?, resolved_entity_id = ?, resolved_at = ?
                WHERE id = ?;
                """,
                (final_status.value, created_entity_id, now, prop.id),
            )

            return {
                "proposal_id": prop.id,
                "status": final_status.value,
                "created_entity_id": created_entity_id,
                "proposal_type": p_type.value,
            }

    def reject_proposal(self, proposal_id: str) -> bool:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE proposals SET status = ?, resolved_at = ? WHERE id = ? AND status = ?;",
                (ProposalStatus.REJECTED.value, now, proposal_id, ProposalStatus.PENDING.value),
            )
            return cur.rowcount > 0

    def approve_all(self, project_id: str) -> int:
        """Approves all pending proposals for a project."""
        pending = self.list_proposals(project_id, status_filter=ProposalStatus.PENDING)
        count = 0
        for p in pending:
            self.approve_proposal(p.id)
            count += 1
        return count

    def _row_to_proposal(self, row: Any) -> Proposal:
        payload = {}
        try:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        except Exception:
            pass
        return Proposal(
            id=row["id"],
            project_id=row["project_id"],
            proposal_type=ProposalType(row["proposal_type"]),
            title=row["title"],
            rationale_why=row["rationale_why"] or "",
            source_excerpt=row["source_excerpt"] or "",
            source_origin=row["source_origin"] or "",
            payload=payload,
            status=ProposalStatus(row["status"]),
            resolved_entity_id=row["resolved_entity_id"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )
