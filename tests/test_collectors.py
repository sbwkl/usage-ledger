import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from src.usage_ledger.collectors import (scan_claude, scan_codex, scan_sqlite_agent,
                                       source_signatures)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class ClaudeTest(unittest.TestCase):
    def test_intermediate_rows_and_subagents(self):
        result = scan_claude(os.path.join(FIXTURES, "claude", "projects"))
        self.assertTrue(result.healthy)
        self.assertEqual(result.files, 2)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.dup_dropped, 1)
        self.assertEqual(result.key_kinds["skipped:intermediate"], 2)

        main = next(rec for rec in result.records if rec.key == "claude:m1")
        self.assertEqual((main.counts.input, main.counts.output, main.counts.cache_read,
                          main.counts.cache_write), (100, 20, 50, 10))
        self.assertEqual(main.model, "claude-sonnet-4")
        self.assertEqual(main.project, "proj-a")
        self.assertEqual(main.session, "s1")

        agent = next(rec for rec in result.records if rec.key == "claude:m2")
        self.assertEqual((agent.counts.input, agent.counts.output, agent.counts.cache_read,
                          agent.counts.cache_write), (10, 5, 2, 1))

    def test_missing_root_is_unavailable(self):
        result = scan_claude("/nonexistent/usage-ledger-test")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)
        self.assertEqual(result.records, [])


class CodexTest(unittest.TestCase):
    def test_cumulative_resume_and_model_attribution(self):
        result = scan_codex(os.path.join(FIXTURES, "codex", "sessions"),
                            os.path.join(FIXTURES, "codex", "archived_sessions"))
        self.assertTrue(result.healthy)
        self.assertEqual(result.files, 2)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.key_kinds["zero-usage"], 1)
        self.assertEqual(result.errors, [])

        by_key = {rec.key: rec for rec in result.records}
        first = by_key["codex:rollout-a:150"]
        second = by_key["codex:rollout-a:400"]
        resumed = by_key["codex:rollout-b:650"]

        self.assertEqual((first.counts.input, first.counts.output, first.counts.cache_read,
                          first.counts.reasoning), (60, 40, 40, 10))
        self.assertEqual((second.counts.input, second.counts.output, second.counts.cache_read,
                          second.counts.reasoning), (150, 40, 50, 10))
        self.assertEqual((resumed.counts.input, resumed.counts.output, resumed.counts.cache_read,
                          resumed.counts.reasoning), (10, 4, 10, 1))
        self.assertEqual(first.model, "gpt-5.6-terra")
        self.assertEqual(resumed.model, "gpt-5.5")

        totals = [sum(getattr(rec.counts, field) for rec in result.records)
                  for field in ("input", "output", "cache_read", "reasoning")]
        self.assertEqual(totals, [220, 84, 100, 21])

    def test_missing_both_roots_is_unavailable(self):
        result = scan_codex("/nonexistent/a", "/nonexistent/b")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)

    def test_duplicate_rollout_in_archived_is_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions = os.path.join(tmp, "sessions")
            archived = os.path.join(tmp, "archived_sessions")
            os.makedirs(sessions)
            os.makedirs(archived)
            source = os.path.join(FIXTURES, "codex", "sessions", "rollout-a.jsonl")
            shutil.copy(source, sessions)
            shutil.copy(source, archived)
            result = scan_codex(sessions, archived)
            self.assertEqual(len(result.records), 2)
            self.assertEqual(sum(rec.counts.total() for rec in result.records), 400)


class SignatureTest(unittest.TestCase):
    def test_latest_mtime_and_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".claude", "projects", "proj", "s.jsonl")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            signatures = source_signatures(tmp, ["claude", "kilo"])
            self.assertIsNotNone(signatures["claude"])
            self.assertIsNone(signatures["kilo"])

            first = signatures["claude"]
            bumped = (first + 1_000_000) * 1_000
            os.utime(path, ns=(bumped, bumped))
            self.assertGreater(source_signatures(tmp, ["claude"])["claude"], first)


class SqliteAgentTest(unittest.TestCase):
    def test_scan(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "x.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, "
                     "time_updated INTEGER, data TEXT)")
        data = {"role": "assistant", "modelID": "m", "providerID": "p",
                "path": {"cwd": "/tmp/proj"},
                "tokens": {"input": 1, "output": 2, "reasoning": 3,
                           "cache": {"read": 4, "write": 5}}}
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m1", "s1", 1700000000000, None, json.dumps(data)))
        zero = {"role": "assistant", "modelID": "m", "tokens": {}}
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m2", "s1", 1700000000000, None, json.dumps(zero)))
        user = {"role": "user", "tokens": {"input": 9}}
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m3", "s1", 1700000000000, None, json.dumps(user)))
        conn.commit()
        conn.close()

        result = scan_sqlite_agent(db, "opencode")
        self.assertTrue(result.healthy)
        self.assertEqual(len(result.records), 1)
        rec = result.records[0]
        self.assertEqual((rec.counts.input, rec.counts.output, rec.counts.reasoning,
                          rec.counts.cache_read, rec.counts.cache_write),
                         (1, 2, 3, 4, 5))
        self.assertEqual(rec.key, "opencode:m1")

    def test_scan_new_session_message_schema(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "x.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, "
                     "time_updated INTEGER, data TEXT)")
        conn.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, directory TEXT)")
        conn.execute("CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, "
                     "type TEXT, seq INTEGER, time_created INTEGER, time_updated INTEGER, "
                     "data TEXT)")
        conn.execute("INSERT INTO session_v2 VALUES ('s1', '/tmp/proj-new/')")
        new = {"model": {"id": "deepseek-v4.1-flash-free", "providerID": "opencode"},
               "tokens": {"input": 7, "output": 3, "reasoning": 1,
                          "cache": {"read": 5, "write": 2}}}
        conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
                     ("m1", "s1", "assistant", 1, 1700000000000, None, json.dumps(new)))
        conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
                     ("m2", "s1", "user", 2, 1700000000000, None,
                      json.dumps({"role": "user"})))
        legacy_same = {"role": "assistant", "modelID": "legacy-model",
                       "tokens": {"input": 1}}
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m1", "s1", 1700000000000, None, json.dumps(legacy_same)))
        legacy_only = {"role": "assistant", "modelID": "old-model",
                       "path": {"cwd": "/tmp/proj-old"},
                       "tokens": {"input": 2, "output": 1}}
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m0", "s0", 1700000000000, None, json.dumps(legacy_only)))
        conn.commit()
        conn.close()

        result = scan_sqlite_agent(db, "opencode")
        self.assertTrue(result.healthy)
        by_key = {rec.key: rec for rec in result.records}
        self.assertEqual(set(by_key), {"opencode:m1", "opencode:m0"})
        self.assertEqual(by_key["opencode:m1"].model, "deepseek-v4.1-flash-free")
        self.assertEqual(by_key["opencode:m1"].provider, "opencode")
        self.assertEqual(by_key["opencode:m1"].project, "proj-new")
        self.assertEqual((by_key["opencode:m1"].counts.input,
                          by_key["opencode:m1"].counts.output,
                          by_key["opencode:m1"].counts.reasoning,
                          by_key["opencode:m1"].counts.cache_read,
                          by_key["opencode:m1"].counts.cache_write), (7, 3, 1, 5, 2))
        self.assertEqual(by_key["opencode:m0"].model, "old-model")
        self.assertEqual(by_key["opencode:m0"].project, "proj-old")

    def test_missing_db_is_unavailable(self):
        result = scan_sqlite_agent("/nonexistent/x.db", "kilo")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)


if __name__ == "__main__":
    unittest.main()
