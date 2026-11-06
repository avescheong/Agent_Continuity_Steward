"""Decision Ledger service (Decisions, Constraints, Rejected Options, Ideas)."""

import json
from typing import List, Optional
from src.scs_core.db.database import VaultDatabase, next_entity_code
from src.scs_core.models import DecisionRecord, DecisionKind, utc_now_iso


class DecisionLedgerService:
    def __init__(self, db: VaultDatabase):
        self.db = db

    def create_decision(
        self,
        project_id: str,
        record_kind: DecisionKind,
        statement: str,
        rationale_why: str = "",
        impact_scope: str = "",
        source_excerpt: str = "",
        source_proposal_id: Optional[str] = None,
    ) -> DecisionRecord:
        prefix_map = {
            DecisionKind.DECISION: "DEC",
            DecisionKind.CONSTRAINT: "CON",
            DecisionKind.REJECTED_OPTION: "REJ",
            DecisionKind.IDEA: "IDA",
        }
        prefix = prefix_map.get(record_kind, "DEC")
        now = utc_now_iso()

        with self.db.transaction() as conn:
            code = next_entity_code(conn, "decisions", project_id, prefix)
            dec = DecisionRecord(
                project_id=project_id,
                code=code,
                record_kind=record_kind,
                statement=statement.strip(),
                rationale_why=rationale_why.strip(),
                impact_scope=impact_scope.strip(),
                source_excerpt=source_excerpt.strip(),
                source_proposal_id=source_proposal_id,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            conn.execute(
                """
                INSERT INTO decisions (
                    id, project_id, code, record_kind, statement,
                    rationale_why, impact_scope, source_excerpt,
                    source_proposal_id, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    dec.id, dec.project_id, dec.code, dec.record_kind.value,
                    dec.statement, dec.rationale_why, dec.impact_scope,
                    dec.source_excerpt, dec.source_proposal_id, 1,
                    dec.created_at, dec.updated_at,
                ),
            )
            return dec

    def list_decisions(
        self, project_id: str, active_only: bool = False, kind: Optional[DecisionKind] = None
    ) -> List[DecisionRecord]:
        with self.db.transaction() as conn:
            query = "SELECT * FROM decisions WHERE project_id = ?"
            params = [project_id]
            if active_only:
                query += " AND is_active = 1"
            if kind:
                query += " AND record_kind = ?"
                params.append(kind.value)
            query += " ORDER BY code ASC;"

            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                DecisionRecord(
                    id=r["id"],
                    project_id=r["project_id"],
                    code=r["code"],
                    record_kind=DecisionKind(r["record_kind"]),
                    statement=r["statement"],
                    rationale_why=r["rationale_why"] or "",
                    impact_scope=r["impact_scope"] or "",
                    source_excerpt=r["source_excerpt"] or "",
                    source_proposal_id=r["source_proposal_id"],
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def toggle_decision_active(self, decision_id: str) -> Optional[DecisionRecord]:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM decisions WHERE id = ?;", (decision_id,)).fetchone()
            if not row:
                return None
            new_state = 0 if row["is_active"] else 1
            conn.execute(
                "UPDATE decisions SET is_active = ?, updated_at = ? WHERE id = ?;",
                (new_state, now, decision_id),
            )
            updated_row = conn.execute("SELECT * FROM decisions WHERE id = ?;", (decision_id,)).fetchone()
            return DecisionRecord(
                id=updated_row["id"],
                project_id=updated_row["project_id"],
                code=updated_row["code"],
                record_kind=DecisionKind(updated_row["record_kind"]),
                statement=updated_row["statement"],
                rationale_why=updated_row["rationale_why"] or "",
                impact_scope=updated_row["impact_scope"] or "",
                source_excerpt=updated_row["source_excerpt"] or "",
                source_proposal_id=updated_row["source_proposal_id"],
                is_active=bool(updated_row["is_active"]),
                created_at=updated_row["created_at"],
                updated_at=updated_row["updated_at"],
            )

    def delete_decision(self, decision_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM decisions WHERE id = ?;", (decision_id,))
            return cur.rowcount > 0
