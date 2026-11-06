"""
Unit Test Suite for SCS_AG_v2 Transcript Reader & Watermark Slicer
===================================================================

Covers all Step 1.3 acceptance requirements:
1. Read normal transcript.jsonl
2. Resolve truncated content from transcript_full.jsonl
3. Remove XML wrappers correctly (<USER_REQUEST>, <ADDITIONAL_METADATA>, etc.)
4. Remove YAML contamination
5. Preserve conversation ordering
6. Watermark prevents duplicate capture
7. Two conversations cannot overlap
8. SES file generation works & metadata fields exist
9. 10-session archive trigger works
10. Real Antigravity transcript compatibility verification
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

import transcript_reader
import vault_store


class TestTranscriptReader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.app_data_dir = self.base_dir / "app_data"
        self.app_data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_synthetic_transcript(
        self,
        conversation_id: str,
        steps: list,
        full_steps: list = None,
    ):
        """Helper to scaffold a synthetic brain transcript directory."""
        log_dir = self.app_data_dir / "brain" / conversation_id / ".system_generated" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        trans_file = log_dir / "transcript.jsonl"
        with open(trans_file, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        trans_full_file = log_dir / "transcript_full.jsonl"
        with open(trans_full_file, "w", encoding="utf-8") as f:
            for s in (full_steps or steps):
                f.write(json.dumps(s) + "\n")

        return log_dir

    # -----------------------------------------------------------------------
    # 1. Read normal transcript.jsonl
    # -----------------------------------------------------------------------

    def test_01_read_normal_transcript(self):
        conv_id = "test-conv-001"
        steps = [
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>Please design a modular storage layer.</USER_REQUEST>",
                "created_at": "2026-11-05T10:00:00Z",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "content": None,  # Tool call only — must be skipped
                "tool_calls": [{"name": "read_file"}],
            },
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "GENERIC",  # Tool output — must be skipped
                "content": "File content dummy",
            },
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "content": "I recommend adopting a file-first SQLite storage architecture.",
                "created_at": "2026-11-05T10:00:10Z",
            },
        ]
        self._create_synthetic_transcript(conv_id, steps)

        turns = transcript_reader.read_transcript_turns(
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
        )

        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["speaker"], "Human")
        self.assertEqual(turns[0]["step_index"], 0)
        self.assertEqual(turns[0]["normalized_content"], "Please design a modular storage layer.")

        self.assertEqual(turns[1]["speaker"], "AI")
        self.assertEqual(turns[1]["step_index"], 3)
        self.assertIn("file-first SQLite", turns[1]["normalized_content"])

    # -----------------------------------------------------------------------
    # 2. Resolve truncated transcript using transcript_full.jsonl
    # -----------------------------------------------------------------------

    def test_02_resolve_truncated_content(self):
        conv_id = "test-conv-trunc"
        short_preview = "Architecture summary truncated..."
        full_content = (
            "Complete Architectural Specification:\n"
            "1. Decision: Use SQLite with WAL mode.\n"
            "2. Rationale: Eliminates background daemon requirements.\n"
            "3. Governance constraint: Never exceed 50MB RAM.\n"
        )

        steps = [
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>Provide full spec.</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "content": short_preview,
                "truncated_fields": ["content"],
            },
        ]

        full_steps = [
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>Provide full spec.</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "content": full_content,
            },
        ]

        self._create_synthetic_transcript(conv_id, steps, full_steps)

        turns = transcript_reader.read_transcript_turns(
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
        )

        self.assertEqual(len(turns), 2)
        # Step 1 must have resolved the full content from transcript_full.jsonl
        self.assertEqual(turns[1]["step_index"], 1)
        self.assertEqual(turns[1]["raw_content"], full_content)
        self.assertIn("Eliminates background daemon requirements", turns[1]["normalized_content"])
        self.assertNotIn("truncated...", turns[1]["normalized_content"])

    # -----------------------------------------------------------------------
    # 3. Remove XML wrappers correctly
    # -----------------------------------------------------------------------

    def test_03_remove_xml_wrappers(self):
        raw_input = (
            "<CONTEXT_SUMMARY>\nOld compacted session context\n</CONTEXT_SUMMARY>\n"
            "<SKILL>agy-customizations</SKILL>\n"
            "<SYSTEM_MESSAGE>System instructions</SYSTEM_MESSAGE>\n"
            "<USER_SETTINGS_CHANGE>auto_approve=true</USER_SETTINGS_CHANGE>\n"
            "<USER_REQUEST>\n"
            "Yes, I approve adopting the new event queue.\n"
            "</USER_REQUEST>\n"
            "<ADDITIONAL_METADATA>\n"
            "The current local time is: 2026-11-05T13:45:00+08:00\n"
            "</ADDITIONAL_METADATA>"
        )

        normalized = transcript_reader.normalize_turn_text(raw_input, is_human=True)

        self.assertEqual(normalized, "Yes, I approve adopting the new event queue.")
        self.assertNotIn("<USER_REQUEST>", normalized)
        self.assertNotIn("ADDITIONAL_METADATA", normalized)
        self.assertNotIn("CONTEXT_SUMMARY", normalized)
        self.assertNotIn("USER_SETTINGS_CHANGE", normalized)
        self.assertNotIn("SYSTEM_MESSAGE", normalized)

    # -----------------------------------------------------------------------
    # 4. Remove YAML contamination
    # -----------------------------------------------------------------------

    def test_04_remove_yaml_contamination(self):
        text_with_yaml = (
            "---\n"
            "session_id: SES001_20261105_1200\n"
            "project_code: SCS2\n"
            "sha256: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069\n"
            "---\n\n"
            "Human:\n"
            "I approve adopting Redis caching.\n\n"
            "AI:\n"
            "Understood, proceeding."
        )

        cleaned = transcript_reader.extract_session_dialogue(text_with_yaml)

        self.assertTrue(cleaned.startswith("Human:\nI approve adopting Redis caching."))
        self.assertNotIn("session_id: SES001", cleaned)
        self.assertNotIn("---", cleaned)

    # -----------------------------------------------------------------------
    # 5. Preserve conversation ordering
    # -----------------------------------------------------------------------

    def test_05_preserve_conversation_ordering(self):
        conv_id = "test-conv-ordering"
        steps = [
            {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>Turn 1</USER_REQUEST>"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "Turn 2"},
            {"step_index": 2, "type": "USER_INPUT", "content": "<USER_REQUEST>Turn 3</USER_REQUEST>"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "content": "Turn 4"},
            {"step_index": 4, "type": "USER_INPUT", "content": "<USER_REQUEST>Turn 5</USER_REQUEST>"},
        ]
        self._create_synthetic_transcript(conv_id, steps)

        turns = transcript_reader.read_transcript_turns(
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
        )

        self.assertEqual(len(turns), 5)
        step_indices = [t["step_index"] for t in turns]
        self.assertEqual(step_indices, [0, 1, 2, 3, 4])
        contents = [t["normalized_content"] for t in turns]
        self.assertEqual(contents, ["Turn 1", "Turn 2", "Turn 3", "Turn 4", "Turn 5"])

    # -----------------------------------------------------------------------
    # 6. Watermark prevents duplicate capture
    # -----------------------------------------------------------------------

    def test_06_watermark_prevents_duplicate_capture(self):
        proj_dir = self.base_dir / "TestProj"
        vault_dir = vault_store.create_vault(proj_dir, "TEST", "Test Project")

        conv_id = "test-conv-watermark"
        steps = [
            {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>Hello</USER_REQUEST>"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "Hi there!"},
        ]
        self._create_synthetic_transcript(conv_id, steps)

        # 1. First capture -> creates SES001
        res1 = transcript_reader.capture_session_evidence(
            vault_dir=vault_dir,
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
        )
        self.assertTrue(res1["captured"])
        self.assertEqual(res1["session_id"], "SES001")
        self.assertEqual(res1["turn_count"], 2)

        # 2. Second capture immediately without new steps -> NO_NEW_TURNS
        res2 = transcript_reader.capture_session_evidence(
            vault_dir=vault_dir,
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
        )
        self.assertFalse(res2["captured"])
        self.assertEqual(res2["reason"], "NO_NEW_TURNS")

        # 3. Add Step 2 & Step 3 to the transcript
        steps.extend([
            {"step_index": 2, "type": "USER_INPUT", "content": "<USER_REQUEST>Add new feature</USER_REQUEST>"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "content": "Feature added."},
        ])
        self._create_synthetic_transcript(conv_id, steps)

        # 4. Third capture -> creates SES002 with ONLY the new turns (steps 2 & 3)
        res3 = transcript_reader.capture_session_evidence(
            vault_dir=vault_dir,
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
        )
        self.assertTrue(res3["captured"])
        self.assertEqual(res3["session_id"], "SES002")
        self.assertEqual(res3["first_step_index"], 2)
        self.assertEqual(res3["last_step_index"], 3)
        self.assertEqual(res3["turn_count"], 2)

    # -----------------------------------------------------------------------
    # 7. Two conversations cannot overlap
    # -----------------------------------------------------------------------

    def test_07_two_conversations_cannot_overlap(self):
        proj_dir = self.base_dir / "MultiConvProj"
        vault_dir = vault_store.create_vault(proj_dir, "MCONV", "Multi Conv Project")

        conv_a = "conv-alpha-111"
        conv_b = "conv-beta-222"

        steps_a = [
            {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>Conv A Step 0</USER_REQUEST>"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "Conv A Step 1"},
        ]
        steps_b = [
            {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>Conv B Step 0</USER_REQUEST>"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "Conv B Step 1"},
            {"step_index": 2, "type": "USER_INPUT", "content": "<USER_REQUEST>Conv B Step 2</USER_REQUEST>"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "content": "Conv B Step 3"},
        ]

        self._create_synthetic_transcript(conv_a, steps_a)
        self._create_synthetic_transcript(conv_b, steps_b)

        # Capture Conv A
        res_a = transcript_reader.capture_session_evidence(
            vault_dir=vault_dir,
            conversation_id=conv_a,
            app_data_dir=self.app_data_dir,
        )
        self.assertEqual(res_a["session_id"], "SES001")
        self.assertEqual(res_a["last_step_index"], 1)

        # Capture Conv B
        res_b = transcript_reader.capture_session_evidence(
            vault_dir=vault_dir,
            conversation_id=conv_b,
            app_data_dir=self.app_data_dir,
        )
        self.assertEqual(res_b["session_id"], "SES002")
        self.assertEqual(res_b["last_step_index"], 3)

        # Inspect MANIFEST.json watermarks
        paths = vault_store.get_vault_paths(vault_dir)
        man = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
        wm = man["watermarks_by_conversation"]

        self.assertIn(conv_a, wm)
        self.assertIn(conv_b, wm)
        self.assertEqual(wm[conv_a]["last_step_index"], 1)
        self.assertEqual(wm[conv_b]["last_step_index"], 3)

    # -----------------------------------------------------------------------
    # 8. SES file generation & metadata fields exist
    # -----------------------------------------------------------------------

    def test_08_ses_file_generation_and_metadata(self):
        proj_dir = self.base_dir / "MetaProj"
        vault_dir = vault_store.create_vault(proj_dir, "META", "Metadata Project")

        conv_id = "test-conv-meta"
        steps = [
            {"step_index": 10, "type": "USER_INPUT", "content": "<USER_REQUEST>Propose architecture</USER_REQUEST>"},
            {"step_index": 11, "type": "PLANNER_RESPONSE", "content": "I propose modular architecture."},
        ]
        self._create_synthetic_transcript(conv_id, steps)

        fixed_time = datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc)
        res = transcript_reader.capture_session_evidence(
            vault_dir=vault_dir,
            conversation_id=conv_id,
            app_data_dir=self.app_data_dir,
            session_time=fixed_time,
        )

        ses_file = Path(res["file_path"])
        self.assertTrue(ses_file.exists())
        self.assertIn("SES001_20261105_1430.md", ses_file.name)

        content = ses_file.read_text(encoding="utf-8")

        # Verify all required frontmatter metadata fields
        self.assertIn("session_id: SES001_20261105_1430", content)
        self.assertIn("session_code: SES001", content)
        self.assertIn("project_code: META", content)
        self.assertIn(f"conversation_id: {conv_id}", content)
        self.assertIn("captured_at: '2026-11-05T14:30:00Z'", content)
        self.assertIn("first_step_index: 10", content)
        self.assertIn("last_step_index: 11", content)
        self.assertIn("first_turn_hash:", content)
        self.assertIn("last_turn_hash:", content)
        self.assertIn("sha256:", content)

        # Verify dialogue text body
        dialogue = transcript_reader.extract_session_dialogue(content)
        self.assertIn("Human:\nPropose architecture", dialogue)
        self.assertIn("AI:\nI propose modular architecture.", dialogue)

    # -----------------------------------------------------------------------
    # 9. 10-Session archive trigger works
    # -----------------------------------------------------------------------

    def test_09_10_session_archive_trigger(self):
        proj_dir = self.base_dir / "TenSessionProj"
        vault_dir = vault_store.create_vault(proj_dir, "TEN", "Ten Session Project")

        conv_id = "test-conv-10"

        # Simulate 10 incremental recording cycles
        for i in range(1, 11):
            steps = [
                {"step_index": i * 2, "type": "USER_INPUT", "content": f"<USER_REQUEST>Discussion for session {i}</USER_REQUEST>"},
                {"step_index": i * 2 + 1, "type": "PLANNER_RESPONSE", "content": f"Decision ratified in session {i}."},
            ]
            self._create_synthetic_transcript(conv_id, steps)

            res = transcript_reader.capture_session_evidence(
                vault_dir=vault_dir,
                conversation_id=conv_id,
                app_data_dir=self.app_data_dir,
            )
            self.assertTrue(res["captured"])
            self.assertEqual(res["session_id"], f"SES{i:03d}")

            if i < 10:
                self.assertFalse(res["archive_triggered"])
            else:
                # 10th session MUST trigger the consolidation archiver!
                self.assertTrue(res["archive_triggered"])
                self.assertIsNotNone(res["archive_file"])
                self.assertTrue(Path(res["archive_file"]).exists())
                self.assertIn("MD001_", Path(res["archive_file"]).name)

        # Non-destructive backbone rule: ALL 10 raw SES files must still exist!
        paths = vault_store.get_vault_paths(vault_dir)
        raw_files = list(paths["raw_sessions_dir"].glob("SES*.md"))
        self.assertEqual(len(raw_files), 10)

    # -----------------------------------------------------------------------
    # 10. Real Antigravity transcript compatibility verification
    # -----------------------------------------------------------------------

    def test_10_real_antigravity_transcript(self):
        # Locate the real Antigravity transcript for this active conversation if present
        real_app_data = Path(os.environ.get("ANTIGRAVITY_APP_DATA", Path.home() / ".gemini" / "antigravity"))
        real_conv_id = "c00e503f-62af-46dc-8522-fb547b0bdcdc"
        real_trans_path = real_app_data / "brain" / real_conv_id / ".system_generated" / "logs" / "transcript.jsonl"

        if not real_trans_path.exists():
            self.skipTest("Real Antigravity transcript not found in environment; skipped.")

        turns = transcript_reader.read_transcript_turns(
            conversation_id=real_conv_id,
            app_data_dir=real_app_data,
        )

        self.assertGreater(len(turns), 10, "Must successfully extract dialogue turns from real conversation")
        # Verify first turn corresponds to initial human request
        first_turn = turns[0]
        self.assertEqual(first_turn["speaker"], "Human")
        self.assertIn("architecture evolution", first_turn["normalized_content"].lower())


if __name__ == "__main__":
    unittest.main()
