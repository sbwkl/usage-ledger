import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from src.usage_ledger.collectors import (scan_claude, scan_codex, scan_qoder_activity,
                                       scan_qoder_credit_sources, scan_qoder_quota,
                                       scan_qoder_tokens, scan_qoder_transcripts,
                                       scan_sqlite_agent, source_signatures)
from tests.qoder_helpers import (activity_path, create_activity_db, create_token_db,
                                 log_path, quota_line, token_path, transcript_path,
                                 write_jsonl, write_quota_log)

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


class QoderTokenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.db = token_path(self.home)
        self.ts = int(datetime(2026, 10, 1, 12, 0).timestamp() * 1000)
        create_token_db(self.db, [
            ("m1", "s1", "assistant", self.ts, '{"model_key":"qmodel"}',
             '{"prompt_tokens":1000,"completion_tokens":50,"cached_tokens":800}'),
            ("m2", "s2", "assistant", self.ts, "",
             '{"prompt_tokens":100,"completion_tokens":0,"cached_tokens":500}'),
            ("m3", "s1", "assistant", self.ts, '{"model_key":"qmodel"}',
             '{"prompt_tokens":0,"completion_tokens":0,"cached_tokens":0}'),
            ("m4", "s1", "assistant", self.ts, '{"model_key":"qmodel"}', "{broken"),
            ("m5", "s1", "assistant", self.ts, '{"model_key":"qmodel"}', "{}"),
            ("m6", "s1", "user", self.ts, '{"model_key":"qmodel"}',
             '{"prompt_tokens":9,"completion_tokens":9}'),
            ("m7", "s3", "assistant", self.ts, '{"model_key":""}',
             '{"prompt_tokens":10,"completion_tokens":5,"cached_tokens":0}'),
            ("m8", "s4", "assistant", self.ts, "",
             '{"prompt_tokens":10,"completion_tokens":0,"cached_tokens":0}'),
        ], {
            "s1": {"project_name": "proj-a", "project_uri": "/tmp/proj-a",
                   "session_type": "agent"},
            "s2": {"project_uri": "/tmp/proj-b/",
                   "preferred_model_info": '{"preferred_model":"fallback-model"}'},
            "s3": {"project_name": "", "project_uri": "/tmp/foo/bar/",
                   "preferred_model_info": "legacy-string"},
            "s4": {},
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_mapping_fallbacks_and_skips(self):
        result = scan_qoder_tokens(self.db)
        self.assertTrue(result.healthy)
        self.assertEqual(result.files, 1)
        self.assertEqual(result.key_kinds["zero-usage"], 2)
        by_key = {rec.key: rec for rec in result.records}
        self.assertEqual(set(by_key), {"qoder:m1", "qoder:m2", "qoder:m7", "qoder:m8"})

        main = by_key["qoder:m1"]
        self.assertEqual((main.counts.input, main.counts.output, main.counts.cache_read),
                         (200, 50, 800))
        self.assertEqual(main.counts.total(), 1050)
        self.assertEqual(main.model, "qmodel")
        self.assertEqual(main.project, "proj-a")
        self.assertEqual(main.provider, "qoder")
        self.assertEqual(main.agent, "agent")

        clamped = by_key["qoder:m2"]
        self.assertEqual((clamped.counts.input, clamped.counts.output,
                          clamped.counts.cache_read), (0, 0, 500))
        self.assertEqual(clamped.model, "fallback-model")
        self.assertEqual(clamped.project, "proj-b")

        legacy = by_key["qoder:m7"]
        self.assertEqual(legacy.model, "legacy-string")
        self.assertEqual(legacy.project, "bar")

        missing = by_key["qoder:m8"]
        self.assertEqual(missing.model, "unknown")
        self.assertIsNone(missing.project)

    def test_duplicate_id_keeps_largest(self):
        db = os.path.join(self.tmp.name, "dup.db")
        create_token_db(db, [
            ("m1", "s1", "assistant", self.ts, "", '{"prompt_tokens":100}'),
            ("m1", "s1", "assistant", self.ts, "", '{"prompt_tokens":300}'),
        ], {"s1": {}})
        result = scan_qoder_tokens(db)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.dup_dropped, 1)
        self.assertEqual(result.records[0].counts.input, 300)

    def test_missing_db_is_unavailable(self):
        result = scan_qoder_tokens("/nonexistent/qoder-local.db")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)


class QoderActivityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.db = activity_path(self.home)
        self.day = date(2020, 1, 1)
        self.next_day = date(2020, 1, 2)
        self.ts = int(datetime(2020, 1, 1, 0, 5).timestamp() * 1000)
        self.late_ts = int(datetime(2020, 1, 1, 12, 0).timestamp() * 1000)
        self.ts2 = int(datetime(2020, 1, 2, 12, 0).timestamp() * 1000)
        self.messages = [
            ("u1", "s1", None, {"role": "user"}, self.ts, None),
            ("a1", "s1", None, {"role": "assistant", "parts": [
                {"type": "tool"}, {"type": "tool"}, {"type": "text"}]}, self.ts, None),
            ("a2", "s1", "assistant", {"parts": [{"type": "tool"}],
                                       "turnMetrics": {"turnCount": 5, "durationMs": 1000}},
             self.ts, None),
            ("u2", "s2", "user", {}, self.ts, None),
            ("a3", "s2", "assistant", {"parts": [{"type": "tool"}],
                                       "turnMetrics": {"turnCount": 2, "durationMs": 500}},
             self.ts, None),
            ("sys", "s2", "system", {"role": "system"}, self.ts, None),
            ("late", "s2", "system", {"role": "system"}, self.late_ts, None),
            ("bad", "s1", None, "{broken", self.ts, None),
        ]
        self.sessions = {"s1": "/tmp/proj-x", "s2": "/tmp/proj-x"}
        create_activity_db(self.db, self.messages, self.sessions)

    def tearDown(self):
        self.tmp.cleanup()

    def test_metrics_and_role_fallback(self):
        result = scan_qoder_activity(self.db)
        self.assertTrue(result.healthy)
        self.assertEqual(result.files, 1)
        self.assertEqual(len(result.activities), 1)
        act = result.activities[0]
        self.assertEqual(act.day, "2020-01-01")
        self.assertEqual(act.project, "proj-x")
        self.assertEqual(act.sessions, 2)
        self.assertEqual(act.prompts, 2)
        self.assertEqual(act.assistant_calls, 3)
        self.assertEqual(act.assistant_with_metrics, 2)
        self.assertEqual(act.turns, 7)
        self.assertEqual(act.tool_calls, 4)
        self.assertEqual(act.duration_ms, 1500)
        self.assertEqual(act.source, "qoder.activity")
        self.assertEqual(result.cursor_ms, self.late_ts)
        self.assertEqual(result.key_kinds["messages"], len(self.messages))

    def test_incremental_recomputes_only_touched_day(self):
        first = scan_qoder_activity(self.db)
        cursor = first.cursor_ms
        self.assertIsNotNone(cursor)

        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO chat_session_messages VALUES (?,?,?,?,?,?)",
            ("a4", "s2", "assistant",
             json.dumps({"turnMetrics": {"turnCount": 1, "durationMs": 100}}),
             self.ts2, self.ts2))
        conn.commit()
        conn.close()

        result = scan_qoder_activity(self.db, cursor_ms=cursor)
        self.assertTrue(result.healthy)
        today = date.today()
        extra = result.affected_days - {today.isoformat(),
                                        (today - timedelta(days=1)).isoformat()}
        self.assertEqual(extra, {"2020-01-01", "2020-01-02"})
        by_day = {act.day: act for act in result.activities}
        self.assertEqual(set(by_day), {"2020-01-01", "2020-01-02"})
        self.assertEqual(by_day["2020-01-02"].assistant_calls, 1)
        self.assertEqual(by_day["2020-01-02"].turns, 1)

        repeat = scan_qoder_activity(self.db, cursor_ms=result.cursor_ms)
        self.assertEqual(repeat.activities, [])
        self.assertTrue(any("无新消息" in note for note in repeat.notes))
        self.assertEqual(repeat.key_kinds["messages"], len(self.messages) + 1)

    def test_missing_db_is_unavailable(self):
        result = scan_qoder_activity("/nonexistent/qoder-activity.sqlite")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)


class QoderCreditsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.base = datetime(2026, 10, 30, 12, 0, 0)
        self.iso = self.base.isoformat()
        self.iso2 = (self.base + timedelta(seconds=5)).isoformat()
        self.iso3 = (self.base + timedelta(minutes=5)).isoformat()
        self.iso4 = (self.base + timedelta(minutes=6)).isoformat()
        self.iso5 = (self.base + timedelta(minutes=7)).isoformat()
        self.path = transcript_path(self.home)
        write_jsonl(self.path, [
            {"type": "user", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso,
             "message": {"content": [{"type": "text", "text": "hello there"}]},
             "humanInput": {"text": "hello there"}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso2,
             "message": {"model": "gfmodel",
                         "content": [{"type": "text", "text": "world"}],
                         "usage": {"request_id": "r1", "credits": 2.5,
                                   "original_credits": 5, "billable": True,
                                   "context_usage_ratio": 0.25}}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso2,
             "message": {"model": "gfmodel",
                         "content": [{"type": "text", "text": "!!"}]}},
            {"type": "user", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso3,
             "message": {"content": [{"type": "text", "text": "second prompt"}]}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso3,
             "message": {"model": "gfmodel",
                         "content": [{"type": "text", "text": "answer here"}],
                         "usage": {"request_id": "r2", "credits": 1.0,
                                   "billable": False, "context_usage_ratio": 0.5}}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso4,
             "message": {"model": "gfmodel",
                         "content": [{"type": "text", "text": "old"}]}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-a",
             "timestamp": self.iso5,
             "message": {"model": "dfmodel",
                         "content": [{"type": "text", "text": "no rid"}],
                         "usage": {"credits": 0.5, "billable": True,
                                   "context_usage_ratio": 0.1}}},
        ])
        write_quota_log(log_path(self.home), [
            quota_line(self.iso, "q1", used=100, remaining=2200, pct=0.04),
            quota_line(self.iso2, "q2", used=120, remaining=2180, pct=0.05),
            quota_line(self.iso3, "q3", used=90, remaining=2210, pct=0.03),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_credits_and_estimates(self):
        result = scan_qoder_credit_sources(self.home)
        self.assertTrue(result.available)
        self.assertEqual(result.files, 1)

        by_rid = {row.request_id: row for row in result.credits}
        self.assertEqual(set(by_rid), {"r1", "r2"})
        self.assertEqual(by_rid["r1"].credits, 2.5)
        self.assertTrue(by_rid["r1"].billable)
        self.assertEqual(by_rid["r1"].project, "proj-a")
        self.assertEqual(by_rid["r1"].model, "gfmodel")
        self.assertFalse(by_rid["r2"].billable)

        self.assertEqual(len(result.estimates), 3)
        self.assertEqual(result.key_kinds["missing:ratio"], 1)
        estimates = {row.request_id: row for row in result.estimates}
        first = estimates["s1:%s" % self.iso2]
        self.assertEqual((first.chars_in, first.chars_out), (11, 7))
        self.assertEqual(first.est_input, 50_000)
        self.assertEqual(first.est_output, 2)
        second = estimates["s1:%s" % self.iso3]
        self.assertEqual((second.chars_in, second.chars_out), (13, 11))
        self.assertEqual(second.est_input, 100_000)
        self.assertEqual(second.est_output, 3)
        no_rid = estimates["s1:%s" % self.iso5]
        self.assertEqual(no_rid.model, "dfmodel")
        self.assertEqual(no_rid.est_input, 20_000)
        self.assertEqual(no_rid.est_output, 1)
        self.assertNotIn("hello there", repr(result.estimates))
        self.assertNotIn("second prompt", repr(result.estimates))

        snapshots = {(row.request_id, row.quota_kind): row for row in result.quota}
        self.assertEqual(len(snapshots), 6)
        add_on = snapshots[("q3", "add_on")]
        self.assertEqual((add_on.total, add_on.used, add_on.remaining), (2300, 90, 2210))
        self.assertAlmostEqual(add_on.raw_pct, 0.03)
        self.assertEqual(add_on.unit, "credits")

    def test_incremental_rescan_is_idempotent(self):
        root = os.path.dirname(self.path)
        first = scan_qoder_transcripts(root)
        self.assertEqual(len(first.credits), 2)
        state = first.transcript_state
        self.assertTrue(state)

        repeat = scan_qoder_transcripts(root, file_state=state)
        self.assertEqual(repeat.credits, [])
        self.assertEqual(repeat.estimates, [])
        self.assertEqual(repeat.files, 1)

        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-a",
                "timestamp": (self.base + timedelta(minutes=9)).isoformat(),
                "message": {"model": "gfmodel",
                            "content": [{"type": "text", "text": "new"}],
                            "usage": {"request_id": "r3", "credits": 3.0,
                                      "billable": True,
                                      "context_usage_ratio": 0.4}},
            }) + "\n")

        third = scan_qoder_transcripts(root, file_state=state)
        self.assertEqual({row.request_id for row in third.credits}, {"r1", "r2", "r3"})
        self.assertEqual(len(third.estimates), 4)
        added = max(third.estimates, key=lambda row: row.ts)
        self.assertEqual(added.est_input, 80_000)
        self.assertGreater(third.transcript_state[self.path]["offset"],
                           state[self.path]["offset"])

    def test_signatures_track_transcripts_and_logs(self):
        first = source_signatures(self.home, ["qoder"])
        path = transcript_path(self.home)
        stat = os.stat(path)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        second = source_signatures(self.home, ["qoder"])
        self.assertGreater(second["qoder.credits"], first["qoder.credits"])
        self.assertGreater(second["qoder.est"], first["qoder.est"])

    def test_missing_transcript_and_log_roots(self):
        with tempfile.TemporaryDirectory() as empty:
            result = scan_qoder_credit_sources(empty)
            self.assertFalse(result.available)
            self.assertEqual(result.credits, [])
            self.assertEqual(result.estimates, [])
            self.assertTrue(any("目录不存在" in note for note in result.notes))
            self.assertTrue(any("日志目录不存在" in note for note in result.notes))
            quota = scan_qoder_quota(log_path(empty, bucket="none"))
            self.assertEqual(quota.quota, [])


class QoderSignatureTest(unittest.TestCase):
    def test_token_and_activity_signatures_are_independent(self):
        with tempfile.TemporaryDirectory() as home:
            token_db = token_path(home)
            activity_db = activity_path(home)
            create_token_db(token_db, [], {})
            create_activity_db(activity_db, [], {})

            first = source_signatures(home, ["qoder"])
            stat = os.stat(activity_db)
            os.utime(activity_db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            second = source_signatures(home, ["qoder"])

            self.assertEqual(second["qoder"], first["qoder"])
            self.assertGreater(second["qoder.activity"], first["qoder.activity"])


if __name__ == "__main__":
    unittest.main()
