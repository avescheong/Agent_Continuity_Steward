"""Read-only SSOT filesystem observation and cryptographic SHA-256 reconciler.

CRITICAL ARCHITECTURAL INVARIANT:
This module contains ZERO write/modify/delete syscalls.
Files are inspected strictly with O_RDONLY descriptors.
"""

import os
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone
import json

from src.scs_core.db.database import VaultDatabase
from src.scs_core.models import ArtifactRecord, ArtifactCustodyState, ReconcileSummary, utc_now_iso


CHUNK_SIZE = 65536  # 64 KB read-only chunks


class ReadOnlyReconciler:
    def __init__(self, db: VaultDatabase):
        self.db = db

    def compute_sha256_readonly(self, file_path: Path) -> str:
        """Computes 64-char lowercase SHA-256 using low-level O_RDONLY descriptor."""
        hasher = hashlib.sha256()
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY

        fd = os.open(str(file_path), flags)
        try:
            with os.fdopen(fd, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    hasher.update(chunk)
        except Exception:
            # os.fdopen closes fd on exit if opened, but if fdopen fails ensure fd closed
            try:
                os.close(fd)
            except Exception:
                pass
            raise

        return hasher.hexdigest().lower()

    def check_markers_readonly(self, file_path: Path, markers: List[str]) -> List[str]:
        """Checks if required text markers are present in file. Returns list of missing markers.

        Supports ID markers like '#forecast-modal' matching id="forecast-modal" or id='forecast-modal'.
        """
        if not markers:
            return []

        try:
            if file_path.stat().st_size > 5 * 1024 * 1024:
                return []
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            missing = []
            for m in markers:
                matched = False
                if m in content:
                    matched = True
                elif m.startswith("#"):
                    # Check for DOM ID patterns: id="name" or id='name'
                    raw_id = m[1:]
                    if f'id="{raw_id}"' in content or f"id='{raw_id}'" in content or raw_id in content:
                        matched = True
                if not matched:
                    missing.append(m)
            return missing
        except Exception:
            return markers

    def resolve_file_location(
        self, relative_path: str, root_paths: List[str]
    ) -> Tuple[Optional[Path], bool]:
        """Resolves relative_path against configured root paths with path-traversal guard.

        Returns (resolved_path_if_found, is_traversal_violation).
        """
        for root in root_paths:
            try:
                root_dir = Path(root).resolve()
                if not root_dir.exists() or not root_dir.is_dir():
                    continue

                candidate = (root_dir / relative_path).resolve()
                # Hard Path-Traversal Guard
                if not candidate.is_relative_to(root_dir):
                    return None, True

                if candidate.exists() and candidate.is_file():
                    return candidate, False
            except Exception:
                continue

        return None, False

    def reconcile_artifact(
        self, artifact: ArtifactRecord, root_paths: List[str]
    ) -> ArtifactRecord:
        """Reconciles a single artifact against physical reality. Updates DB and returns updated record."""
        now = utc_now_iso()
        rel = artifact.relative_path
        ext = artifact.external_ref

        # Rule 1: No relative_path and no external_ref -> CONVERSATION_ONLY
        if not rel and not ext:
            new_state = ArtifactCustodyState.CONVERSATION_ONLY
            return self._update_artifact_state(artifact.id, new_state, None, None, None, [], now)

        # Rule 2: external_ref but no relative_path -> UNKNOWN
        if not rel and ext:
            new_state = ArtifactCustodyState.UNKNOWN
            return self._update_artifact_state(artifact.id, new_state, None, None, None, [], now)

        # Rule 3: relative_path set but root_paths empty -> UNKNOWN
        if not root_paths:
            new_state = ArtifactCustodyState.UNKNOWN
            return self._update_artifact_state(artifact.id, new_state, None, None, None, [], now)

        # Check physical existence
        resolved_file, is_traversal = self.resolve_file_location(rel, root_paths)

        if is_traversal:
            new_state = ArtifactCustodyState.UNKNOWN
            return self._update_artifact_state(artifact.id, new_state, None, None, None, [], now)

        # Rule 4: File not found under any root -> MISSING
        if not resolved_file:
            new_state = ArtifactCustodyState.MISSING
            return self._update_artifact_state(artifact.id, new_state, None, None, None, [], now)

        # File exists on disk -> compute SHA-256 and stat
        try:
            stat_info = resolved_file.stat()
            size_bytes = stat_info.st_size
            mtime_iso = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc).isoformat()
            observed_sha = self.compute_sha256_readonly(resolved_file)
            missing_m = self.check_markers_readonly(resolved_file, artifact.required_markers)

            if missing_m:
                new_state = ArtifactCustodyState.MODIFIED
            elif not artifact.baseline_sha256:
                new_state = ArtifactCustodyState.LOCAL_FILE_EXISTS
            elif observed_sha == artifact.baseline_sha256:
                new_state = ArtifactCustodyState.VERIFIED_MATCH
            else:
                new_state = ArtifactCustodyState.MODIFIED

            return self._update_artifact_state(
                artifact.id, new_state, observed_sha, size_bytes, mtime_iso, missing_m, now
            )
        except Exception:
            return self._update_artifact_state(
                artifact.id, ArtifactCustodyState.UNKNOWN, None, None, None, [], now
            )

    def reconcile_project(self, project_id: str) -> Tuple[List[ArtifactRecord], ReconcileSummary]:
        """Reconciles all artifacts for a project against its root_paths."""
        with self.db.transaction() as conn:
            proj_row = conn.execute("SELECT root_paths_json FROM projects WHERE id = ?;", (project_id,)).fetchone()
            if not proj_row:
                raise ValueError(f"Project not found: {project_id}")
            root_paths = json.loads(proj_row["root_paths_json"]) if proj_row["root_paths_json"] else []

            art_rows = conn.execute("SELECT * FROM artifacts WHERE project_id = ?;", (project_id,)).fetchall()

        reconciled_list = []
        summary = ReconcileSummary()

        for r in art_rows:
            req_m = json.loads(r["required_markers_json"]) if r["required_markers_json"] else []
            mis_m = json.loads(r["missing_markers_json"]) if r["missing_markers_json"] else []
            art = ArtifactRecord(
                id=r["id"],
                project_id=r["project_id"],
                name=r["name"],
                artifact_type=r["artifact_type"],
                conversation_note=r["conversation_note"] or "",
                relative_path=r["relative_path"],
                external_ref=r["external_ref"],
                custody_state=r["custody_state"],
                baseline_sha256=r["baseline_sha256"],
                observed_sha256=r["observed_sha256"],
                observed_size_bytes=r["observed_size_bytes"],
                observed_mtime_iso=r["observed_mtime_iso"],
                required_markers=req_m,
                missing_markers=mis_m,
                source_proposal_id=r["source_proposal_id"],
                last_reconciled_at=r["last_reconciled_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            updated = self.reconcile_artifact(art, root_paths)
            reconciled_list.append(updated)

            # Update summary
            summary.total += 1
            if updated.custody_state == ArtifactCustodyState.VERIFIED_MATCH:
                summary.verified_match += 1
            elif updated.custody_state == ArtifactCustodyState.LOCAL_FILE_EXISTS:
                summary.local_file_exists += 1
            elif updated.custody_state == ArtifactCustodyState.MODIFIED:
                summary.modified += 1
            elif updated.custody_state == ArtifactCustodyState.MISSING:
                summary.missing += 1
            elif updated.custody_state == ArtifactCustodyState.CONVERSATION_ONLY:
                summary.conversation_only += 1
            else:
                summary.unknown += 1

        return reconciled_list, summary

    def _update_artifact_state(
        self,
        artifact_id: str,
        state: ArtifactCustodyState,
        observed_sha: Optional[str],
        size_bytes: Optional[int],
        mtime_iso: Optional[str],
        missing_markers: List[str],
        reconciled_at: str,
    ) -> ArtifactRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE artifacts SET
                    custody_state = ?, observed_sha256 = ?, observed_size_bytes = ?,
                    observed_mtime_iso = ?, missing_markers_json = ?,
                    last_reconciled_at = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    state.value, observed_sha, size_bytes, mtime_iso,
                    json.dumps(missing_markers), reconciled_at, reconciled_at,
                    artifact_id,
                ),
            )
            r = conn.execute("SELECT * FROM artifacts WHERE id = ?;", (artifact_id,)).fetchone()
            req_m = json.loads(r["required_markers_json"]) if r["required_markers_json"] else []
            mis_m = json.loads(r["missing_markers_json"]) if r["missing_markers_json"] else []
            return ArtifactRecord(
                id=r["id"],
                project_id=r["project_id"],
                name=r["name"],
                artifact_type=r["artifact_type"],
                conversation_note=r["conversation_note"] or "",
                relative_path=r["relative_path"],
                external_ref=r["external_ref"],
                custody_state=ArtifactCustodyState(r["custody_state"]),
                baseline_sha256=r["baseline_sha256"],
                observed_sha256=r["observed_sha256"],
                observed_size_bytes=r["observed_size_bytes"],
                observed_mtime_iso=r["observed_mtime_iso"],
                required_markers=req_m,
                missing_markers=mis_m,
                source_proposal_id=r["source_proposal_id"],
                last_reconciled_at=r["last_reconciled_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
