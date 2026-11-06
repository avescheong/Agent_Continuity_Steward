"""Project profile management, session mission state, and Continuity Snapshots."""

import json
import sqlite3
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any
from scs_core.db.database import VaultDatabase, next_entity_code
from scs_core.models import Project, SnapshotRecord, utc_now_iso


class ProjectSessionService:
    def __init__(self, db: VaultDatabase, snapshots_dir: Path | None = None):
        self.db = db
        self.snapshots_dir = snapshots_dir

    def ensure_default_project(self) -> Project:
        """Seeds a clean default starter project if projects table is empty."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM projects LIMIT 1;").fetchone()
            if not row:
                now = utc_now_iso()
                p = Project(
                    code="SCS_DEMO",
                    name="SCS Continuity Demo",
                    description="Default continuity project",
                    color="#6366F1",
                    objective="Establish session continuity between AI discussions and project files",
                    current_focus="Initial project setup and verification",
                    next_action="Capture initial architectural decisions and test bootstrap generation",
                    created_at=now,
                    updated_at=now,
                )
                conn.execute(
                    """
                    INSERT INTO projects (
                        id, code, name, description, color, root_paths_json,
                        objective, current_focus, next_action, is_archived,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        p.id, p.code, p.name, p.description, p.color,
                        json.dumps(p.root_paths), p.objective, p.current_focus,
                        p.next_action, 1 if p.is_archived else 0,
                        p.created_at, p.updated_at,
                    ),
                )
                return p

        # Retrieve first existing project
        return self.list_projects()[0]

    def create_project(
        self,
        code: str,
        name: str,
        description: str = "",
        color: str = "#6366F1",
        root_paths: Optional[List[str]] = None,
        objective: str = "",
        next_action: str = "",
    ) -> Project:
        clean_code = code.strip().upper()
        clean_name = name.strip()
        if not clean_code:
            raise ValueError("Project code cannot be empty.")
        if not clean_name:
            raise ValueError("Project name cannot be empty.")

        now = utc_now_iso()
        p = Project(
            code=clean_code,
            name=clean_name,
            description=description.strip(),
            color=color,
            root_paths=root_paths or [],
            objective=objective.strip(),
            next_action=next_action.strip(),
            created_at=now,
            updated_at=now,
        )
        with self.db.transaction() as conn:
            existing = conn.execute("SELECT id FROM projects WHERE code = ?;", (p.code,)).fetchone()
            if existing:
                raise ValueError(f"Project code '{p.code}' is already in use. Please choose a different code.")
            try:
                conn.execute(
                    """
                    INSERT INTO projects (
                        id, code, name, description, color, root_paths_json,
                        objective, current_focus, next_action, is_archived,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        p.id, p.code, p.name, p.description, p.color,
                        json.dumps(p.root_paths), p.objective, p.current_focus,
                        p.next_action, 0, p.created_at, p.updated_at,
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Project code '{p.code}' is already in use. Please choose a different code.")
        return p

    def get_project(self, project_id: str) -> Optional[Project]:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?;", (project_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_project(row)

    def get_project_by_code(self, code: str) -> Optional[Project]:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE code = ?;", (code.strip().upper(),)
            ).fetchone()
            if not row:
                return None
            return self._row_to_project(row)

    def list_projects(self, include_archived: bool = False) -> List[Project]:
        with self.db.transaction() as conn:
            query = "SELECT * FROM projects WHERE is_archived = 0 ORDER BY updated_at DESC;"
            if include_archived:
                query = "SELECT * FROM projects ORDER BY updated_at DESC;"
            rows = conn.execute(query).fetchall()
            return [self._row_to_project(r) for r in rows]

    def update_project_session(
        self,
        project_id: str,
        objective: Optional[str] = None,
        current_focus: Optional[str] = None,
        next_action: Optional[str] = None,
        description: Optional[str] = None,
        root_paths: Optional[List[str]] = None,
    ) -> Optional[Project]:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
            if not row:
                return None

            obj = objective if objective is not None else row["objective"]
            foc = current_focus if current_focus is not None else row["current_focus"]
            nxt = next_action if next_action is not None else row["next_action"]
            desc = description if description is not None else row["description"]
            r_paths = json.dumps(root_paths) if root_paths is not None else row["root_paths_json"]

            conn.execute(
                """
                UPDATE projects SET
                    objective = ?, current_focus = ?, next_action = ?,
                    description = ?, root_paths_json = ?, updated_at = ?
                WHERE id = ?;
                """,
                (obj, foc, nxt, desc, r_paths, now, project_id),
            )
        return self.get_project(project_id)

    def create_snapshot(self, project_id: str, label: str = "") -> SnapshotRecord:
        """Creates an immutable continuity snapshot with deterministic SHA-256 seal."""
        with self.db.transaction() as conn:
            proj_row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
            if not proj_row:
                raise ValueError(f"Project not found: {project_id}")
            proj = self._row_to_project(proj_row)

            # Gather all active decisions, tasks, and artifacts
            dec_rows = conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? ORDER BY code ASC;", (project_id,)
            ).fetchall()
            task_rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY code ASC;", (project_id,)
            ).fetchall()
            art_rows = conn.execute(
                "SELECT * FROM artifacts WHERE project_id = ? ORDER BY name ASC;", (project_id,)
            ).fetchall()

            # Build canonical state payload
            state_dict: Dict[str, Any] = {
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

            # Canonical sort-keys JSON serialization
            canonical_json = json.dumps(state_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

            snp_code = next_entity_code(conn, "snapshots", project_id, "SNP")
            now = utc_now_iso()
            snp_id = str(hashlib.md5(f"{project_id}_{snp_code}_{now}".encode()).hexdigest())

            mirror_path_str = None
            if self.snapshots_dir:
                self.snapshots_dir.mkdir(parents=True, exist_ok=True)
                mirror_file = self.snapshots_dir / f"{proj.code}_{snp_code}.json"
                mirror_file.write_text(json.dumps(state_dict, indent=2, ensure_ascii=False), encoding="utf-8")
                mirror_path_str = str(mirror_file)

            conn.execute(
                """
                INSERT INTO snapshots (
                    id, project_id, snapshot_code, label, state_json,
                    checksum_sha256, mirror_file_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (snp_id, project_id, snp_code, label.strip(), canonical_json, checksum, mirror_path_str, now),
            )

            # Update project reference
            conn.execute(
                "UPDATE projects SET latest_snapshot_id = ?, latest_snapshot_sha256 = ?, updated_at = ? WHERE id = ?;",
                (snp_id, checksum, now, project_id),
            )

            return SnapshotRecord(
                id=snp_id,
                project_id=project_id,
                snapshot_code=snp_code,
                label=label.strip(),
                state_json=canonical_json,
                checksum_sha256=checksum,
                mirror_file_path=mirror_path_str,
                created_at=now,
            )

    def list_snapshots(self, project_id: str) -> List[SnapshotRecord]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots WHERE project_id = ? ORDER BY created_at DESC;",
                (project_id,),
            ).fetchall()
            return [
                SnapshotRecord(
                    id=r["id"],
                    project_id=r["project_id"],
                    snapshot_code=r["snapshot_code"],
                    label=r["label"],
                    state_json=r["state_json"],
                    checksum_sha256=r["checksum_sha256"],
                    mirror_file_path=r["mirror_file_path"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def _row_to_project(self, row: Any) -> Project:
        r_paths = []
        try:
            r_paths = json.loads(row["root_paths_json"]) if row["root_paths_json"] else []
        except Exception:
            pass
        return Project(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            description=row["description"] or "",
            color=row["color"] or "#6366F1",
            root_paths=r_paths,
            objective=row["objective"] or "",
            current_focus=row["current_focus"] or "",
            next_action=row["next_action"] or "",
            latest_snapshot_id=row["latest_snapshot_id"],
            latest_snapshot_sha256=row["latest_snapshot_sha256"],
            is_archived=bool(row["is_archived"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
