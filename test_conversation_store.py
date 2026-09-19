"""Tests for maya_conversation_store — stdlib only, pytest-compatible."""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

store: Any = importlib.import_module("maya_conversation_store")


class ConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = store.CONVERSATIONS_DIR
        self._orig_log = store.CONVERSATION_LOG
        store.CONVERSATIONS_DIR = Path(self._tmp.name) / "conversations"
        store.CONVERSATION_LOG = store.CONVERSATIONS_DIR / "maya_conversation_log.jsonl"

    def tearDown(self):
        store.CONVERSATIONS_DIR = self._orig_dir
        store.CONVERSATION_LOG = self._orig_log
        self._tmp.cleanup()

    def test_append_then_load_round_trip(self):
        self.assertEqual(store.load_recent(5), [])
        store.append_turn("user", "Hello Maya", "s1")
        store.append_turn("assistant", "Hi Andy", "s1")
        events = store.load_recent(10)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["role"], "user")
        self.assertEqual(events[0]["content"], "Hello Maya")
        self.assertEqual(events[1]["role"], "assistant")

    def test_append_creates_missing_directories(self):
        self.assertFalse(store.CONVERSATIONS_DIR.exists())
        self.assertIsNotNone(store.append_turn("user", "wake up", "s2"))
        self.assertTrue(store.CONVERSATION_LOG.exists())

    def test_malformed_lines_are_skipped(self):
        store.append_turn("user", "good line", "s3")
        with store.CONVERSATION_LOG.open("a", encoding="utf-8") as handle:
            handle.write("{not valid json\n")
            handle.write(json.dumps({"role": "not_a_role", "content": "x"}) + "\n")
            handle.write(json.dumps({"role": "user"}) + "\n")  # missing content
            handle.write("\n")
        store.append_turn("assistant", "recovered", "s3")
        events = store.load_recent(10)
        self.assertEqual(
            [(e["role"], e["content"]) for e in events],
            [("user", "good line"), ("assistant", "recovered")],
        )

    def test_missing_file_returns_empty(self):
        self.assertEqual(store.load_recent(5), [])

    def test_limit_returns_only_most_recent(self):
        for i in range(10):
            store.append_turn("user", f"msg {i}", "s4")
        events = store.load_recent(3)
        self.assertEqual([e["content"] for e in events], ["msg 7", "msg 8", "msg 9"])

    def test_empty_content_is_not_stored(self):
        self.assertIsNone(store.append_turn("user", "   ", "s5"))
        self.assertEqual(store.load_recent(5), [])


if __name__ == "__main__":
    unittest.main()