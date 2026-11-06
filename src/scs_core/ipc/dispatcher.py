"""Tauri-compatible IPC Command Dispatcher."""

from typing import Dict, Any, Optional, List
import traceback

from src.scs_core.db.database import VaultDatabase
from src.scs_core.models import (
    DashboardState, TaskStatus, TaskPriority, DecisionKind,
    ArtifactType, ProposalType, ProposalStatus
)
from src.scs_core.modules.mod04_projects_sessions import ProjectSessionService
from src.scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from src.scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from src.scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from src.scs_core.modules.mod03_approval_gate import ApprovalGateService
from src.scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from src.scs_core.modules.mod02_protocol_engine import ProtocolEngineService


class SCSDispatcher:
    """Central typed dispatcher routing JSON command envelopes.

    Envelope Contract:
    Success: {"ok": True, "data": ...}
    Error:   {"ok": False, "error": {"code": "...", "message": "..."}}
    """

    def __init__(
        self,
        db: VaultDatabase,
        project_svc: ProjectSessionService,
        decision_svc: DecisionLedgerService,
        checklist_svc: ChecklistEngineService,
        artifact_svc: ArtifactRegistryService,
        gate_svc: ApprovalGateService,
        reconciler_svc: ReadOnlyReconciler,
        protocol_svc: ProtocolEngineService,
    ):
        self.db = db
        self.project_svc = project_svc
        self.decision_svc = decision_svc
        self.checklist_svc = checklist_svc
        self.artifact_svc = artifact_svc
        self.gate_svc = gate_svc
        self.reconciler_svc = reconciler_svc
        self.protocol_svc = protocol_svc

    def invoke(self, command: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = payload or {}
        try:
            handler = getattr(self, f"cmd_{command}", None)
            if not handler:
                return {
                    "ok": False,
                    "error": {
                        "code": "UNKNOWN_COMMAND",
                        "message": f"Command '{command}' is not registered in SCSDispatcher.",
                    },
                }

            result = handler(p)
            return {"ok": True, "data": result}
        except ValueError as ve:
            return {"ok": False, "error": {"code": "VALIDATION_ERROR", "message": str(ve)}}
        except Exception as e:
            traceback.print_exc()
            return {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": str(e)}}

    # ---------------------------------------------------------------------------
    # Dashboard & Projects
    # ---------------------------------------------------------------------------

    def cmd_get_dashboard_state(self, p: Dict[str, Any]) -> Dict[str, Any]:
        all_projects = self.project_svc.list_projects()
        active_proj = None
        proj_id = p.get("project_id")

        if proj_id:
            active_proj = self.project_svc.get_project(proj_id)
        if not active_proj:
            if all_projects:
                active_proj = all_projects[0]
            else:
                active_proj = self.project_svc.ensure_default_project()
                all_projects = [active_proj]

        # Gather active data
        proposals = self.gate_svc.list_proposals(active_proj.id, ProposalStatus.PENDING)
        tasks = self.checklist_svc.list_tasks(active_proj.id)
        decisions = self.decision_svc.list_decisions(active_proj.id)
        artifacts = self.artifact_svc.list_artifacts(active_proj.id)
        snapshots = self.project_svc.list_snapshots(active_proj.id)

        # Run quick reconcile summary calculation
        _, summary = self.reconciler_svc.reconcile_project(active_proj.id)

        # Active conversation session & continuity chapter telemetry
        telemetry = self.protocol_svc.get_session_telemetry(active_proj.id)

        state = DashboardState(
            active_project=active_proj,
            all_projects=all_projects,
            proposals_pending=proposals,
            tasks=tasks,
            decisions=decisions,
            artifacts=artifacts,
            recent_snapshots=snapshots[:10],
            reconcile_summary=summary,
            active_session=telemetry["active_session"],
            fragment_count=telemetry["fragment_count"],
            total_sessions=telemetry["total_sessions"],
            processed_sessions=telemetry["processed_sessions"],
            pending_sessions=telemetry["pending_sessions"],
            continuity_md_count=telemetry["continuity_md_count"],
            continuity_chapters=telemetry["continuity_chapters"],
            session_records=telemetry["session_records"],
        )
        return state.model_dump(mode="json")

    def cmd_create_project(self, p: Dict[str, Any]) -> Dict[str, Any]:
        proj = self.project_svc.create_project(
            code=p["code"],
            name=p["name"],
            description=p.get("description", ""),
            color=p.get("color", "#6366F1"),
            root_paths=p.get("root_paths", []),
            objective=p.get("objective", ""),
            next_action=p.get("next_action", ""),
        )
        return proj.model_dump(mode="json")

    def cmd_update_project_session(self, p: Dict[str, Any]) -> Dict[str, Any]:
        proj = self.project_svc.update_project_session(
            project_id=p["project_id"],
            objective=p.get("objective"),
            current_focus=p.get("current_focus"),
            next_action=p.get("next_action"),
            description=p.get("description"),
            root_paths=p.get("root_paths"),
        )
        if not proj:
            raise ValueError(f"Project not found: {p.get('project_id')}")
        return proj.model_dump(mode="json")

    # ---------------------------------------------------------------------------
    # Capture & Approval Gate (Human Approval Boundary)
    # ---------------------------------------------------------------------------

    def cmd_stage_raw_capture(self, p: Dict[str, Any]) -> List[Dict[str, Any]]:
        staged = self.protocol_svc.parse_and_stage_capture(
            project_id=p["project_id"],
            raw_text=p["raw_text"],
            source_origin=p.get("source_origin", "MANUAL_CAPTURE"),
        )
        return staged

    def cmd_stage_proposal(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """Stages a single structured proposal into the quarantine inbox."""
        prop_type = ProposalType(p["proposal_type"])
        proj_id = p["project_id"]
        title = p["title"].strip()
        why = p.get("rationale_why", "").strip()
        payload = p.get("payload", {})
        if p.get("relative_path"):
            payload["relative_path"] = p["relative_path"].strip()

        prop = self.gate_svc.stage_proposal(
            project_id=proj_id,
            proposal_type=prop_type,
            title=title,
            rationale_why=why,
            source_excerpt=p.get("source_excerpt", f"Quick capture: {title}"),
            source_origin=p.get("source_origin", "QUICK_CAPTURE"),
            payload=payload,
        )
        return prop.model_dump(mode="json")

    def cmd_approve_proposal(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.gate_svc.approve_proposal(
            proposal_id=p["proposal_id"],
            overrides=p.get("overrides"),
        )

    def cmd_reject_proposal(self, p: Dict[str, Any]) -> Dict[str, Any]:
        ok = self.gate_svc.reject_proposal(p["proposal_id"])
        return {"rejected": ok, "proposal_id": p["proposal_id"]}

    def cmd_approve_all_proposals(self, p: Dict[str, Any]) -> Dict[str, Any]:
        count = self.gate_svc.approve_all(p["project_id"])
        return {"approved_count": count}

    def cmd_create_approved_item(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """Explicit human UI direct submission (skips quarantine since user directly hit Save/Add)."""
        prop_type = ProposalType(p["proposal_type"])
        proj_id = p["project_id"]
        title = p["title"].strip()
        why = p.get("rationale_why", "").strip()

        # Route directly
        if prop_type == ProposalType.TASK:
            t = self.checklist_svc.create_task(
                project_id=proj_id,
                title=title,
                priority=TaskPriority(p.get("priority", TaskPriority.MEDIUM.value)),
                why_it_matters=why,
            )
            return {"type": "TASK", "item": t.model_dump(mode="json")}
        elif prop_type in (ProposalType.DECISION, ProposalType.CONSTRAINT, ProposalType.REJECTED_OPTION, ProposalType.IDEA):
            kind_map = {
                ProposalType.DECISION: DecisionKind.DECISION,
                ProposalType.CONSTRAINT: DecisionKind.CONSTRAINT,
                ProposalType.REJECTED_OPTION: DecisionKind.REJECTED_OPTION,
                ProposalType.IDEA: DecisionKind.IDEA,
            }
            d = self.decision_svc.create_decision(
                project_id=proj_id,
                record_kind=kind_map[prop_type],
                statement=title,
                rationale_why=why,
            )
            return {"type": prop_type.value, "item": d.model_dump(mode="json")}
        elif prop_type == ProposalType.ARTIFACT:
            a = self.artifact_svc.register_artifact(
                project_id=proj_id,
                name=title,
                conversation_note=why,
                relative_path=p.get("relative_path"),
            )
            return {"type": "ARTIFACT", "item": a.model_dump(mode="json")}
        raise ValueError(f"Unsupported item type: {prop_type}")

    # ---------------------------------------------------------------------------
    # Checklist Tasks
    # ---------------------------------------------------------------------------

    def cmd_update_task_status(self, p: Dict[str, Any]) -> Dict[str, Any]:
        new_status = TaskStatus(p["status"])
        t = self.checklist_svc.update_task_status(
            task_id=p["task_id"],
            new_status=new_status,
            blocker_reason=p.get("blocker_reason"),
        )
        if not t:
            raise ValueError(f"Task not found: {p.get('task_id')}")
        return t.model_dump(mode="json")

    def cmd_cycle_task_status(self, p: Dict[str, Any]) -> Dict[str, Any]:
        t = self.checklist_svc.cycle_task_status(p["task_id"])
        if not t:
            raise ValueError(f"Task not found: {p.get('task_id')}")
        return t.model_dump(mode="json")

    def cmd_update_task(self, p: Dict[str, Any]) -> Dict[str, Any]:
        prio = TaskPriority(p["priority"]) if "priority" in p else None
        t = self.checklist_svc.update_task(
            task_id=p["task_id"],
            title=p.get("title"),
            priority=prio,
            why_it_matters=p.get("why_it_matters"),
            blocker_reason=p.get("blocker_reason"),
            related_decision_ids=p.get("related_decision_ids"),
        )
        if not t:
            raise ValueError(f"Task not found: {p.get('task_id')}")
        return t.model_dump(mode="json")

    def cmd_delete_task(self, p: Dict[str, Any]) -> Dict[str, Any]:
        ok = self.checklist_svc.delete_task(p["task_id"])
        return {"deleted": ok}

    # ---------------------------------------------------------------------------
    # Decisions & Constraints
    # ---------------------------------------------------------------------------

    def cmd_toggle_decision_active(self, p: Dict[str, Any]) -> Dict[str, Any]:
        d = self.decision_svc.toggle_decision_active(p["decision_id"])
        if not d:
            raise ValueError(f"Decision not found: {p.get('decision_id')}")
        return d.model_dump(mode="json")

    def cmd_delete_decision(self, p: Dict[str, Any]) -> Dict[str, Any]:
        ok = self.decision_svc.delete_decision(p["decision_id"])
        return {"deleted": ok}

    # ---------------------------------------------------------------------------
    # Artifacts & Reconciliation
    # ---------------------------------------------------------------------------

    def cmd_bind_artifact_path(self, p: Dict[str, Any]) -> Dict[str, Any]:
        a = self.artifact_svc.bind_path(
            artifact_id=p["artifact_id"],
            relative_path=p.get("relative_path"),
            external_ref=p.get("external_ref"),
        )
        if not a:
            raise ValueError(f"Artifact not found: {p.get('artifact_id')}")
        proj = self.project_svc.get_project(a.project_id)
        reconciled = self.reconciler_svc.reconcile_artifact(a, proj.root_paths if proj else [])
        return reconciled.model_dump(mode="json")

    def cmd_lock_artifact_baseline(self, p: Dict[str, Any]) -> Dict[str, Any]:
        a = self.artifact_svc.lock_baseline_checksum(p["artifact_id"])
        return a.model_dump(mode="json")

    def cmd_delete_artifact(self, p: Dict[str, Any]) -> Dict[str, Any]:
        ok = self.artifact_svc.delete_artifact(p["artifact_id"])
        return {"deleted": ok}

    def cmd_reconcile_project_artifacts(self, p: Dict[str, Any]) -> Dict[str, Any]:
        arts, summary = self.reconciler_svc.reconcile_project(p["project_id"])
        return {
            "artifacts": [a.model_dump(mode="json") for a in arts],
            "summary": summary.model_dump(mode="json"),
        }

    # ---------------------------------------------------------------------------
    # Continuity Outputs
    # ---------------------------------------------------------------------------

    def cmd_generate_bootstrap(self, p: Dict[str, Any]) -> Dict[str, Any]:
        res = self.protocol_svc.compile_bootstrap(
            project_id=p["project_id"],
            include_sync_footer=p.get("include_sync_footer", True),
        )
        return res.model_dump(mode="json")

    def cmd_create_snapshot(self, p: Dict[str, Any]) -> Dict[str, Any]:
        snp = self.project_svc.create_snapshot(
            project_id=p["project_id"],
            label=p.get("label", ""),
        )
        return snp.model_dump(mode="json")

    def cmd_generate_handover(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.generate_handover_package(
            project_id=p["project_id"],
            save_to_exports=p.get("save_to_exports", True),
        )

    def cmd_generate_human_briefing(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.generate_human_briefing(
            project_id=p["project_id"],
            save_to_exports=p.get("save_to_exports", True),
        )

    def cmd_generate_recovery_card(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.generate_recovery_card(
            project_id=p["project_id"],
            save_to_exports=p.get("save_to_exports", True),
        )

    # ---------------------------------------------------------------------------
    # Conversation Checkpoint Engine
    # ---------------------------------------------------------------------------

    def cmd_add_chat_fragment(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.add_chat_fragment(
            project_id=p["project_id"],
            text=p["text"],
            source=p.get("source", "CLIPBOARD"),
            prevent_duplicate=p.get("prevent_duplicate", False),
        )

    def cmd_get_conversation_session(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.get_conversation_session(
            project_id=p["project_id"]
        )

    def cmd_generate_checkpoint(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.generate_checkpoint(
            project_id=p["project_id"],
            last_n=p.get("last_n"),
            auto=p.get("auto", False),
            batch_size=p.get("batch_size"),
        )

    def cmd_approve_checkpoint(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.approve_checkpoint(
            project_id=p["project_id"],
            session_id=p.get("session_id"),
        )

    def cmd_clear_chat_fragments(self, p: Dict[str, Any]) -> Dict[str, Any]:
        return self.protocol_svc.clear_chat_fragments(
            project_id=p["project_id"]
        )
