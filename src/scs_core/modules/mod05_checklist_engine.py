"""Reasoning-bound checklist and execution queue service."""

import json
from typing import List, Optional, Any
from scs_core.db.database import VaultDatabase, next_entity_code
from scs_core.models import TaskItem, TaskStatus, TaskPriority, utc_now_iso


class ChecklistEngineService:
    def __init__(self, db: VaultDatabase):
        self.db = db

    def create_task(
        self,
        project_id: str,
        title: str,
        status: TaskStatus = TaskStatus.PENDING,
        priority: TaskPriority = TaskPriority.MEDIUM,
        why_it_matters: str = "",
        source_excerpt: str = "",
        blocker_reason: str = "",
        related_decision_ids: Optional[List[str]] = None,
        depends_on_task_ids: Optional[List[str]] = None,
        source_proposal_id: Optional[str] = None,
    ) -> TaskItem:
        now = utc_now_iso()
        completed_at = now if status == TaskStatus.COMPLETED else None

        with self.db.transaction() as conn:
            code = next_entity_code(conn, "tasks", project_id, "TSK")
            t = TaskItem(
                project_id=project_id,
                code=code,
                title=title.strip(),
                status=status,
                priority=priority,
                why_it_matters=why_it_matters.strip(),
                source_excerpt=source_excerpt.strip(),
                blocker_reason=blocker_reason.strip(),
                related_decision_ids=related_decision_ids or [],
                depends_on_task_ids=depends_on_task_ids or [],
                source_proposal_id=source_proposal_id,
                created_at=now,
                updated_at=now,
                completed_at=completed_at,
            )
            conn.execute(
                """
                INSERT INTO tasks (
                    id, project_id, code, title, status, priority,
                    why_it_matters, source_excerpt, blocker_reason,
                    related_decision_ids_json, depends_on_task_ids_json,
                    source_proposal_id, sort_order, created_at, updated_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    t.id, t.project_id, t.code, t.title, t.status.value,
                    t.priority.value, t.why_it_matters, t.source_excerpt,
                    t.blocker_reason, json.dumps(t.related_decision_ids),
                    json.dumps(t.depends_on_task_ids), t.source_proposal_id,
                    t.sort_order, t.created_at, t.updated_at, t.completed_at,
                ),
            )
            return t

    def list_tasks(
        self, project_id: str, status_filter: Optional[TaskStatus] = None
    ) -> List[TaskItem]:
        with self.db.transaction() as conn:
            query = "SELECT * FROM tasks WHERE project_id = ?"
            params = [project_id]
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter.value)
            query += " ORDER BY sort_order ASC, code ASC;"

            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_task(r) for r in rows]

    def update_task_status(
        self, task_id: str, new_status: TaskStatus, blocker_reason: Optional[str] = None
    ) -> Optional[TaskItem]:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
            if not row:
                return None

            completed_at = now if new_status == TaskStatus.COMPLETED else None
            b_reason = blocker_reason if blocker_reason is not None else (row["blocker_reason"] if new_status == TaskStatus.BLOCKED else "")

            conn.execute(
                """
                UPDATE tasks SET
                    status = ?, blocker_reason = ?, completed_at = ?, updated_at = ?
                WHERE id = ?;
                """,
                (new_status.value, b_reason, completed_at, now, task_id),
            )
            updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
            return self._row_to_task(updated_row)

    def cycle_task_status(self, task_id: str) -> Optional[TaskItem]:
        """Cycles status: PENDING -> IN_PROGRESS -> COMPLETED -> PENDING (or unblocks)."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?;", (task_id,)).fetchone()
            if not row:
                return None
            current = TaskStatus(row["status"])
            cycle_map = {
                TaskStatus.PENDING: TaskStatus.IN_PROGRESS,
                TaskStatus.IN_PROGRESS: TaskStatus.COMPLETED,
                TaskStatus.COMPLETED: TaskStatus.PENDING,
                TaskStatus.BLOCKED: TaskStatus.PENDING,
            }
            nxt = cycle_map.get(current, TaskStatus.PENDING)
        return self.update_task_status(task_id, nxt)

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        priority: Optional[TaskPriority] = None,
        why_it_matters: Optional[str] = None,
        blocker_reason: Optional[str] = None,
        related_decision_ids: Optional[List[str]] = None,
    ) -> Optional[TaskItem]:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
            if not row:
                return None

            t_title = title.strip() if title is not None else row["title"]
            t_prio = priority.value if priority is not None else row["priority"]
            t_why = why_it_matters.strip() if why_it_matters is not None else row["why_it_matters"]
            t_block = blocker_reason.strip() if blocker_reason is not None else row["blocker_reason"]
            t_rel = json.dumps(related_decision_ids) if related_decision_ids is not None else row["related_decision_ids_json"]

            conn.execute(
                """
                UPDATE tasks SET
                    title = ?, priority = ?, why_it_matters = ?, blocker_reason = ?,
                    related_decision_ids_json = ?, updated_at = ?
                WHERE id = ?;
                """,
                (t_title, t_prio, t_why, t_block, t_rel, now, task_id),
            )
            updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
            return self._row_to_task(updated_row)

    def delete_task(self, task_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))
            return cur.rowcount > 0

    def _row_to_task(self, row: Any) -> TaskItem:
        rel_dec = []
        dep_tasks = []
        try:
            rel_dec = json.loads(row["related_decision_ids_json"]) if row["related_decision_ids_json"] else []
            dep_tasks = json.loads(row["depends_on_task_ids_json"]) if row["depends_on_task_ids_json"] else []
        except Exception:
            pass

        return TaskItem(
            id=row["id"],
            project_id=row["project_id"],
            code=row["code"],
            title=row["title"],
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            why_it_matters=row["why_it_matters"] or "",
            source_excerpt=row["source_excerpt"] or "",
            blocker_reason=row["blocker_reason"] or "",
            related_decision_ids=rel_dec,
            depends_on_task_ids=dep_tasks,
            source_proposal_id=row["source_proposal_id"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )
