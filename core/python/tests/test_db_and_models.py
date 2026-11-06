"""Tests for database initialization, WAL mode, foreign keys, and models."""

import unittest
import tempfile
import sqlite3
from pathlib import Path
from scs_core.db.database import VaultDatabase, next_entity_code
from scs_core.models import (
    Project, Proposal, ProposalType, ProposalStatus,
    DecisionRecord, DecisionKind, TaskItem, TaskStatus,
    ArtifactRecord, ArtifactType, ArtifactCustodyState,
    compact_why,
)


class TestDBAndModels(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_vault.db"
        self.vault = VaultDatabase(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_wal_and_foreign_keys_enabled(self):
        with self.vault.transaction() as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            self.assertEqual(fk, 1)

    def test_foreign_key_cascade(self):
        with self.vault.transaction() as conn:
            # Create project
            conn.execute(
                "INSERT INTO projects (id, code, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                ("p1", "PRJ_1", "Project One", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z")
            )
            # Create task
            conn.execute(
                "INSERT INTO tasks (id, project_id, code, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
                ("t1", "p1", "TSK-001", "Task 1", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z")
            )
            # Delete project
            conn.execute("DELETE FROM projects WHERE id = 'p1';")
            # Verify task was deleted by cascade
            task_row = conn.execute("SELECT id FROM tasks WHERE id = 't1';").fetchone()
            self.assertIsNone(task_row)

    def test_next_entity_code_generation(self):
        with self.vault.transaction() as conn:
            code1 = next_entity_code(conn, "tasks", "p1", "TSK")
            self.assertEqual(code1, "TSK-001")
            
            conn.execute(
                "INSERT INTO projects (id, code, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                ("p1", "PRJ_1", "Project One", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z")
            )
            conn.execute(
                "INSERT INTO tasks (id, project_id, code, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
                ("t1", "p1", "TSK-001", "Task 1", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z")
            )
            code2 = next_entity_code(conn, "tasks", "p1", "TSK")
            self.assertEqual(code2, "TSK-002")

            # Check snapshot code formatting
            snp_code = next_entity_code(conn, "snapshots", "p1", "SNP")
            self.assertTrue(snp_code.startswith("SNP-"))
            self.assertTrue(snp_code.endswith("-001"))

    def test_compact_why_helper(self):
        self.assertEqual(compact_why("Because: we need stability"), "we need stability")
        self.assertEqual(compact_why("Why: performance"), "performance")
        self.assertEqual(compact_why("A" * 50, max_len=20), "A" * 17 + "...")

    def test_artifact_relative_path_partial_unique_index(self):
        with self.vault.transaction() as conn:
            conn.execute(
                "INSERT INTO projects (id, code, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                ("p1", "PRJ_1", "Project One", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z")
            )
            conn.execute(
                "INSERT INTO projects (id, code, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                ("p2", "PRJ_2", "Project Two", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z")
            )

            # Insert artifact in p1 with relative_path 'docs/spec.md'
            conn.execute(
                "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                "VALUES ('a1', 'p1', 'Spec', 'docs/spec.md', '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
            )

            # Different project p2 with same relative_path must succeed
            conn.execute(
                "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                "VALUES ('a2', 'p2', 'Spec', 'docs/spec.md', '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
            )

            # Same project p1 with duplicate relative_path must raise IntegrityError
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                    "VALUES ('a3', 'p1', 'Spec Duplicate', 'docs/spec.md', '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
                )

            # Same project p1 with NULL or empty relative_path must allow multiples
            conn.execute(
                "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                "VALUES ('a4', 'p1', 'Note 1', NULL, '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
            )
            conn.execute(
                "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                "VALUES ('a5', 'p1', 'Note 2', NULL, '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
            )
            conn.execute(
                "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                "VALUES ('a6', 'p1', 'Empty 1', '', '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
            )
            conn.execute(
                "INSERT INTO artifacts (id, project_id, name, relative_path, created_at, updated_at) "
                "VALUES ('a7', 'p1', 'Empty 2', '', '2026-10-30T00:00:00Z', '2026-10-30T00:00:00Z');"
            )


if __name__ == "__main__":
    unittest.main()
