"""Dual-plane artifact registry service."""

import json
from typing import List, Optional, Any
from scs_core.db.database import VaultDatabase
from scs_core.models import ArtifactRecord, ArtifactType, ArtifactCustodyState, utc_now_iso


class ArtifactRegistryService:
    def __init__(self, db: VaultDatabase):
        self.db = db

    def register_artifact(
        self,
        project_id: str,
        name: str,
        artifact_type: ArtifactType = ArtifactType.DOCUMENT,
        conversation_note: str = "",
        relative_path: Optional[str] = None,
        external_ref: Optional[str] = None,
        source_proposal_id: Optional[str] = None,
        required_markers: Optional[List[str]] = None,
    ) -> ArtifactRecord:
        now = utc_now_iso()
        
        # State machine initial assignment
        rel = relative_path.strip() if relative_path else None
        ext = external_ref.strip() if external_ref else None
        
        custody = ArtifactCustodyState.CONVERSATION_ONLY
        if not rel and ext:
            custody = ArtifactCustodyState.UNKNOWN
        elif rel:
            custody = ArtifactCustodyState.UNKNOWN  # until reconciled against root

        art = ArtifactRecord(
            project_id=project_id,
            name=name.strip(),
            artifact_type=artifact_type,
            conversation_note=conversation_note.strip(),
            relative_path=rel,
            external_ref=ext,
            custody_state=custody,
            required_markers=required_markers or [],
            source_proposal_id=source_proposal_id,
            created_at=now,
            updated_at=now,
        )

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, project_id, name, artifact_type, conversation_note,
                    relative_path, external_ref, custody_state, baseline_sha256,
                    observed_sha256, observed_size_bytes, observed_mtime_iso,
                    required_markers_json, missing_markers_json, source_proposal_id,
                    last_reconciled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    art.id, art.project_id, art.name, art.artifact_type.value,
                    art.conversation_note, art.relative_path, art.external_ref,
                    art.custody_state.value, art.baseline_sha256, art.observed_sha256,
                    art.observed_size_bytes, art.observed_mtime_iso,
                    json.dumps(art.required_markers), json.dumps(art.missing_markers),
                    art.source_proposal_id, art.last_reconciled_at, art.created_at, art.updated_at,
                ),
            )
            return art

    def bind_path(
        self, artifact_id: str, relative_path: Optional[str] = None, external_ref: Optional[str] = None
    ) -> Optional[ArtifactRecord]:
        now = utc_now_iso()
        rel = relative_path.strip() if relative_path else None
        ext = external_ref.strip() if external_ref else None

        custody = ArtifactCustodyState.CONVERSATION_ONLY
        if not rel and ext:
            custody = ArtifactCustodyState.UNKNOWN
        elif rel:
            custody = ArtifactCustodyState.UNKNOWN

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE artifacts SET
                    relative_path = ?, external_ref = ?, custody_state = ?, updated_at = ?
                WHERE id = ?;
                """,
                (rel, ext, custody.value, now, artifact_id),
            )
        return self.get_artifact(artifact_id)

    def lock_baseline_checksum(self, artifact_id: str) -> Optional[ArtifactRecord]:
        """Locks current observed_sha256 as baseline_sha256, transitioning to VERIFIED_MATCH."""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT observed_sha256 FROM artifacts WHERE id = ?;", (artifact_id,)).fetchone()
            if not row or not row["observed_sha256"]:
                raise ValueError("Cannot lock baseline: no observed SHA-256 hash exists for this artifact.")

            hash_val = row["observed_sha256"]
            conn.execute(
                """
                UPDATE artifacts SET
                    baseline_sha256 = ?, custody_state = ?, updated_at = ?
                WHERE id = ?;
                """,
                (hash_val, ArtifactCustodyState.VERIFIED_MATCH.value, now, artifact_id),
            )
        return self.get_artifact(artifact_id)

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?;", (artifact_id,)).fetchone()
            if not row:
                return None
            return self._row_to_artifact(row)

    def list_artifacts(self, project_id: str) -> List[ArtifactRecord]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE project_id = ? ORDER BY name ASC;",
                (project_id,),
            ).fetchall()
            return [self._row_to_artifact(r) for r in rows]

    def delete_artifact(self, artifact_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM artifacts WHERE id = ?;", (artifact_id,))
            return cur.rowcount > 0

    def _row_to_artifact(self, row: Any) -> ArtifactRecord:
        req_m = []
        mis_m = []
        try:
            req_m = json.loads(row["required_markers_json"]) if row["required_markers_json"] else []
            mis_m = json.loads(row["missing_markers_json"]) if row["missing_markers_json"] else []
        except Exception:
            pass

        return ArtifactRecord(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            artifact_type=ArtifactType(row["artifact_type"]),
            conversation_note=row["conversation_note"] or "",
            relative_path=row["relative_path"],
            external_ref=row["external_ref"],
            custody_state=ArtifactCustodyState(row["custody_state"]),
            baseline_sha256=row["baseline_sha256"],
            observed_sha256=row["observed_sha256"],
            observed_size_bytes=row["observed_size_bytes"],
            observed_mtime_iso=row["observed_mtime_iso"],
            required_markers=req_m,
            missing_markers=mis_m,
            source_proposal_id=row["source_proposal_id"],
            last_reconciled_at=row["last_reconciled_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
