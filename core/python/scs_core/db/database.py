"""SQLite connection manager, migration runner, and code generators."""

import sqlite3
import json
from pathlib import Path
from typing import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
import re


SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


class VaultDatabase:
    """ACID SQLite Database Manager for the SCS Continuity Vault."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with Row factory and WAL enabled."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Transactional context manager with automatic rollback on error."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Applies schema.sql migrations."""
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        with self.transaction() as conn:
            conn.executescript(schema_sql)
            # Record initial migration
            row = conn.execute("SELECT version FROM schema_migrations WHERE version = 1;").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?);",
                    (datetime.now(timezone.utc).isoformat(),),
                )
            # Record migration 2: idx_artifacts_project_relpath
            row2 = conn.execute("SELECT version FROM schema_migrations WHERE version = 2;").fetchone()
            if not row2:
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (2, ?);",
                    (datetime.now(timezone.utc).isoformat(),),
                )
            # Record migration 3: conversation_sessions schema alignment with scs-session.v1.schema.json
            row3 = conn.execute("SELECT version FROM schema_migrations WHERE version = 3;").fetchone()
            if not row3:
                cols = [r["name"] for r in conn.execute("PRAGMA table_info(conversation_sessions);").fetchall()]
                for col_name, col_def in [
                    ("session_code", "session_code TEXT"),
                    ("session_num", "session_num INTEGER"),
                    ("content", "content TEXT NOT NULL DEFAULT ''"),
                    ("checksum_sha256", "checksum_sha256 TEXT NOT NULL DEFAULT ''"),
                    ("source", "source TEXT NOT NULL DEFAULT 'CLIPBOARD'"),
                    ("word_count", "word_count INTEGER NOT NULL DEFAULT 0"),
                    ("raw_file_path", "raw_file_path TEXT"),
                ]:
                    if col_name not in cols:
                        conn.execute(f"ALTER TABLE conversation_sessions ADD COLUMN {col_def};")

                # Backfill from fragments_json if present
                cur_rows = conn.execute("SELECT id, fragments_json FROM conversation_sessions WHERE content = '' AND fragments_json != '[]';").fetchall()
                for cr in cur_rows:
                    try:
                        parsed = json.loads(cr["fragments_json"])
                        if parsed and isinstance(parsed, list):
                            f0 = parsed[0]
                            conn.execute(
                                "UPDATE conversation_sessions SET session_code = ?, session_num = ?, content = ?, checksum_sha256 = ?, source = ?, word_count = ?, raw_file_path = ? WHERE id = ?;",
                                (
                                    f0.get("session_code"),
                                    f0.get("session_num"),
                                    f0.get("content", ""),
                                    f0.get("checksum_sha256", ""),
                                    f0.get("source", "CLIPBOARD"),
                                    f0.get("word_count", 0),
                                    f0.get("raw_file_path"),
                                    cr["id"],
                                ),
                            )
                    except Exception:
                        pass

                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_checksum ON conversation_sessions(project_id, checksum_sha256);")

                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (3, ?);",
                    (datetime.now(timezone.utc).isoformat(),),
                )


def next_entity_code(conn: sqlite3.Connection, table: str, project_id: str, prefix: str) -> str:
    """Generates the next sequential unique entity code for a project (e.g. TSK-001, DEC-001).

    Safely handles deletions and existing sequences by extracting the maximum numeric suffix.
    """
    column = "code" if table != "snapshots" else "snapshot_code"
    
    if table == "snapshots":
        # Format: SNP-YYYYMMDD-001
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        like_pattern = f"SNP-{today_str}-%"
        cursor = conn.execute(
            f"SELECT {column} FROM {table} WHERE project_id = ? AND {column} LIKE ?;",
            (project_id, like_pattern),
        )
        max_idx = 0
        for row in cursor.fetchall():
            m = re.search(r"(\d+)$", row[0])
            if m:
                max_idx = max(max_idx, int(m.group(1)))
        return f"SNP-{today_str}-{(max_idx + 1):03d}"
    else:
        # Standard: PREFIX-001 (e.g. TSK-001, DEC-001, CON-001, REJ-001, IDA-001)
        like_pattern = f"{prefix}-%"
        cursor = conn.execute(
            f"SELECT {column} FROM {table} WHERE project_id = ? AND {column} LIKE ?;",
            (project_id, like_pattern),
        )
        max_idx = 0
        for row in cursor.fetchall():
            m = re.search(r"(\d+)$", row[0])
            if m:
                max_idx = max(max_idx, int(m.group(1)))
        return f"{prefix}-{(max_idx + 1):03d}"
