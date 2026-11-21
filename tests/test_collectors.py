import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from src.usage_ledger.collectors import (codearts_db, learn_billing_labels,
                                       learn_qoder_model_labels,
                                       scan_antigravity, scan_claude,
                                       scan_cline, scan_codearts, scan_codebuddy,
                                       scan_codex, scan_minimax, scan_qoder_activity,
                                       scan_qoder_credit_sources, scan_qoder_quota,
                                       scan_qoder_tokens, scan_qoder_transcripts,
                                       scan_qoder_turn_credits,
                                       scan_sqlite_agent, source_signatures)
from tests.antigravity_helpers import (CLI_APP, IDE_APP, app_dir, logs_dir,
                                       model_step, user_step, write_raw,
                                       write_summaries, write_transcript)
from tests.codebuddy_helpers import (DEFAULT_CONVERSATION, DEFAULT_MODEL_ID,
                                     DEFAULT_TRACE, GENIE_REL, metric_line, model_line,
                                     start_line, summary_line, usage as cb_usage,
                                     write_genie, write_log)
from tests.minimax_helpers import (DEFAULT_SESSION, assistant_row, runtime_db_path,
                                   tool_row, usage, user_row, write_messages,
                                   write_runtime_db)
from tests.qoder_helpers import (activity_path, create_activity_db,
                                 create_token_db, create_turn_credit_db,
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


class ClineTest(unittest.TestCase):
    def test_metrics_mapping_and_fallbacks(self):
        result = scan_cline(os.path.join(FIXTURES, "cline", "sessions"))
        self.assertTrue(result.healthy)
        self.assertEqual(result.files, 2)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.key_kinds["assistant"], 5)
        self.assertEqual(result.key_kinds["skipped:no_metrics"], 1)
        self.assertEqual(result.key_kinds["zero-usage"], 1)

        by_key = {rec.key: rec for rec in result.records}
        first = by_key["cline:msg_a1"]
        self.assertEqual((first.counts.input, first.counts.output, first.counts.cache_read,
                          first.counts.cache_write), (300, 200, 600, 100))
        self.assertEqual(first.model, "anthropic/claude-sonnet-4")
        self.assertEqual(first.provider, "anthropic")
        self.assertEqual(first.project, "proj-cline")
        self.assertEqual(first.session, "1787000000000_aaaa")

        fallback = by_key["cline:msg_a2"]
        self.assertEqual((fallback.counts.input, fallback.counts.output), (50, 10))
        self.assertEqual(fallback.model, "cline-free/step-5-preview")
        self.assertEqual(fallback.provider, "cline")

        second = by_key["cline:msg_b1"]
        self.assertEqual(second.counts.input, 100)
        self.assertEqual(second.counts.cache_read, 200)
        self.assertEqual(second.project, "other-proj")
        self.assertEqual(second.model, "deepseek/deepseek-v4-flash")

        totals = [sum(getattr(rec.counts, field) for rec in result.records)
                  for field in ("input", "output", "cache_read", "cache_write")]
        self.assertEqual(totals, [450, 240, 800, 100])

    def test_missing_root_is_unavailable(self):
        result = scan_cline("/nonexistent/usage-ledger-cline")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)
        self.assertEqual(result.records, [])

    def test_broken_session_file_is_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad_session")
            os.makedirs(bad)
            with open(os.path.join(bad, "bad_session.messages.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{not json")
            result = scan_cline(tmp)
            self.assertTrue(result.available)
            self.assertFalse(result.healthy)
            self.assertEqual(len(result.errors), 1)
            self.assertEqual(result.records, [])


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

    def test_cline_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = os.path.join(tmp, ".cline", "data", "sessions", "s1")
            os.makedirs(session_dir)
            with open(os.path.join(session_dir, "s1.messages.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{}")
            self.assertIsNotNone(source_signatures(tmp, ["cline"])["cline"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(source_signatures(tmp, ["cline"])["cline"])


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


def write_codearts_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                 "time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, "
                 "data TEXT NOT NULL)")
    stamp = int(datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    for mid, data, offset in rows:
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     (mid, "s1", stamp + offset, stamp + offset, json.dumps(data)))
    conn.commit()
    conn.close()


def codearts_message(modelID="glm-5.3-flash", providerID="inferhub-provider",
                     cwd="/Users/wayne/workspace/proj-x", **tokens):
    data = {"role": "assistant", "modelID": modelID, "providerID": providerID,
            "path": {"cwd": cwd},
            "time": {"created": 1795000000000}}
    if tokens:
        data["tokens"] = tokens
    return data


class CodeArtsCollectorTest(unittest.TestCase):
    def test_maps_fields_and_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, ".codeartsdoer", "codearts-data", "opencode.db")
            os.makedirs(os.path.dirname(db))
            write_codearts_db(db, [
                ("m1", codearts_message(input=100, output=20, reasoning=7,
                                        cache={"read": 900, "write": 5}), 0),
                ("m2", codearts_message(modelID="kimi-k2", input=10, output=1), 1000),
            ])
            result = scan_codearts(home=tmp)
            self.assertTrue(result.healthy)
            self.assertEqual(len(result.records), 2)
            rec = result.records[0]
            self.assertEqual((rec.counts.input, rec.counts.output, rec.counts.reasoning,
                              rec.counts.cache_read, rec.counts.cache_write),
                             (100, 20, 7, 900, 5))
            self.assertEqual(rec.key, "codearts:m1")
            self.assertEqual(rec.model, "glm-5.3-flash")
            self.assertEqual(rec.provider, "inferhub-provider")
            self.assertEqual(rec.project, "proj-x")
            self.assertEqual(rec.source, "codearts")
            rec2 = result.records[1]
            self.assertEqual(rec2.model, "kimi-k2")
            self.assertEqual(rec2.project, "proj-x")

    def test_day_is_local_day_of_time_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = codearts_db(tmp)
            os.makedirs(os.path.dirname(db))
            data = codearts_message(input=1)
            data["time"] = {"created": 1795154953135}
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                         "time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, "
                         "data TEXT NOT NULL)")
            conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                         ("m1", "s1", 1795154953135, 1795154953135, json.dumps(data)))
            conn.commit()
            conn.close()
            result = scan_codearts(home=tmp)
            rec = result.records[0]
            self.assertEqual(rec.day, datetime.fromtimestamp(
                1795154953135 / 1000).strftime("%Y-%m-%d"))
            self.assertEqual(rec.ts, 1795154953135 / 1000)

    def test_skips_tokenless_and_zero_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = codearts_db(tmp)
            os.makedirs(os.path.dirname(db))
            write_codearts_db(db, [
                ("m1", codearts_message(input=5), 0),
                ("m2", codearts_message(), 1000),
                ("m3", {"role": "user", "tokens": {"input": 9}}, 2000),
                ("m4", codearts_message(input=0, output=0, reasoning=0,
                                        cache={"read": 0, "write": 0}), 3000),
            ])
            result = scan_codearts(home=tmp)
            self.assertEqual([rec.key for rec in result.records], ["codearts:m1"])
            # m2 无 tokens 字段：静默跳过；m4 全 0：计 zero-usage
            self.assertEqual(result.key_kinds.get("zero-usage"), 1)

    def test_broken_data_json_is_counted_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = codearts_db(tmp)
            os.makedirs(os.path.dirname(db))
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                         "time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, "
                         "data TEXT NOT NULL)")
            conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                         ("bad", "s1", 1795000000000, 1795000000000, "{not json"))
            conn.commit()
            conn.close()
            result = scan_codearts(home=tmp)
            self.assertFalse(result.healthy)
            self.assertEqual(result.records, [])
            self.assertEqual(len(result.errors), 1)

    def test_missing_db_is_unavailable(self):
        result = scan_codearts(home="/nonexistent-home")
        self.assertFalse(result.available)
        self.assertFalse(result.healthy)


class CodeArtsSignatureTest(unittest.TestCase):
    def test_signature_tracks_db_and_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(source_signatures(tmp, ["codearts"])["codearts"])
            db = codearts_db(tmp)
            os.makedirs(os.path.dirname(db))
            write_codearts_db(db, [("m1", codearts_message(input=1), 0)])
            first = source_signatures(tmp, ["codearts"])["codearts"]
            self.assertIsNotNone(first)
            wal = db + "-wal"
            with open(wal, "w", encoding="utf-8") as fh:
                fh.write("wal")
            bumped = (first + 1_000_000) * 1000
            os.utime(wal, ns=(bumped, bumped))
            self.assertGreater(source_signatures(tmp, ["codearts"])["codearts"], first)


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


class QoderTurnCreditsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        os.makedirs(os.path.join(self.home, ".qoder", "projects"), exist_ok=True)
        self.db = activity_path(self.home)
        self.ts = int(datetime(2026, 11, 14, 16, 25, 9).timestamp() * 1000)
        self.ts2 = int(datetime(2026, 11, 15, 8, 12, 12).timestamp() * 1000)
        create_turn_credit_db(self.db, [
            ("assistant:a1", "s1", "assistant", self.ts, 20.39, "r1"),
            ("assistant:a2", "s1", "assistant", self.ts + 1000, 0.0, "r2"),
            ("assistant:a3", "s2", "assistant", self.ts2, 1.83, None),
            ("assistant:a4", "s1", "assistant", self.ts + 2000, None, "r4"),
            ("assistant:a5", "s1", "assistant", 0, 9.9, "r5"),
        ], {
            "s1": {"cwd": "/Users/wayne/workspace/playground", "model": "dfmodel"},
            "s2": {"cwd": "/private/tmp", "model": None},
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_turn_credits_are_collected_and_mapped(self):
        result = scan_qoder_turn_credits(self.db)
        self.assertTrue(result.available)
        self.assertEqual(result.errors, [])
        by_id = {row.request_id: row for row in result.credits}
        self.assertEqual(set(by_id), {
            "qoder-turn:s1:assistant:a1",
            "qoder-turn:s1:assistant:a2",
            "qoder-turn:s2:assistant:a3",
        })
        first = by_id["qoder-turn:s1:assistant:a1"]
        self.assertEqual((first.day, first.project, first.model, first.credits),
                         ("2026-11-14", "playground", "dfmodel", 20.39))
        self.assertTrue(first.billable)
        self.assertEqual(first.session, "s1")
        zero = by_id["qoder-turn:s1:assistant:a2"]
        self.assertEqual(zero.credits, 0.0)
        self.assertTrue(zero.billable)
        other = by_id["qoder-turn:s2:assistant:a3"]
        self.assertEqual((other.day, other.project, other.model),
                         ("2026-11-15", "tmp", "unknown"))
        self.assertEqual(result.key_kinds["turn_credits"], 3)

    def test_merge_skips_transcript_request_set_duplicate(self):
        write_jsonl(transcript_path(self.home), [
            {"type": "user", "sessionId": "s1", "cwd": "/Users/wayne/workspace/playground",
             "timestamp": "2026-11-14T16:25:00", "message": {"content": []}},
            {"type": "assistant", "sessionId": "s1",
             "cwd": "/Users/wayne/workspace/playground",
             "timestamp": "2026-11-14T16:25:01",
             "message": {"model": "dfmodel", "content": [],
                         "usage": {"request_id": "r1", "credits": 2.5,
                                   "billable": True, "context_usage_ratio": 0.25}}},
        ])
        result = scan_qoder_credit_sources(self.home)
        by_id = {row.request_id: row for row in result.credits}
        self.assertIn("r1", by_id)
        self.assertNotIn("qoder-turn:s1:assistant:a1", by_id)
        self.assertIn("qoder-turn:s1:assistant:a2", by_id)
        self.assertEqual(result.key_kinds["turn_credits:duplicate"], 1)

    def test_old_schema_is_ignored(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".qoder", "projects"), exist_ok=True)
            old_db = activity_path(home)
            create_activity_db(old_db, [], {})
            result = scan_qoder_credit_sources(home)
            self.assertTrue(result.available)
            self.assertEqual(result.credits, [])
            self.assertTrue(any("turn_credits" in note for note in result.notes))

    def test_missing_db_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".qoder", "projects"), exist_ok=True)
            result = scan_qoder_credit_sources(home)
            self.assertTrue(result.available)
            self.assertEqual(result.credits, [])
            self.assertTrue(any("turn_credits" in note for note in result.notes))


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
            self.assertGreater(second["qoder.credits"], first["qoder.credits"])


class AntigravityTest(unittest.TestCase):
    def build_home(self):
        """一个 IDE 会话 + 一个 CLI 会话，含游离片段与 chunks 镜像。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)

        steps = [
            user_step(0),
            model_step(1, input_tokens=100, output_tokens=20, cache_read_tokens=0),
            model_step(2, input_tokens=30, output_tokens=5, cache_read_tokens=900,
                       created_at="2026-11-20T01:01:00Z"),
            # 没有 token 字段的 MODEL step：必须静默跳过，不能记为错误
            {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE",
             "status": "DONE", "content": "no usage here",
             "created_at": "2026-11-20T01:01:30Z"},
            model_step(4, input_tokens=7, output_tokens=3,
                       created_at="2026-11-20T01:02:00Z"),
        ]
        # 真实数据里出现过独立成行的 `}]}` 片段；chunks 与主转录内容一致
        write_raw(home, IDE_APP, "conv-ide", [
            json.dumps(s) for s in steps[:3]
        ] + ["]]}"] + [
            json.dumps(s) for s in steps[3:]
        ])
        chunk_dir = os.path.join(logs_dir(home, IDE_APP, "conv-ide"),
                                 "chunks", "transcript_full")
        os.makedirs(chunk_dir, exist_ok=True)
        with open(os.path.join(chunk_dir, "00000000.jsonl"), "w",
                  encoding="utf-8") as fh:
            for step in steps:
                fh.write(json.dumps(step) + "\n")
        write_summaries(home, IDE_APP, [
            ("conv-ide", '["file:///Users/wayne/workspace/alpha"]'),
        ])

        write_transcript(home, CLI_APP, "conv-cli", [
            model_step(0, model="gemini-3.8-flash-low", input_tokens=11,
                       output_tokens=2, created_at="2026-11-20T02:00:00Z"),
        ])
        # CLI 会话没有 summaries 记录 → 项目走默认兜底
        return home

    def test_maps_model_steps_and_skips_the_rest(self):
        result = scan_antigravity(self.build_home())
        self.assertTrue(result.healthy, result.errors)
        self.assertEqual(result.errors, [])
        # 游离片段只计数，不影响后续 step
        self.assertEqual(result.key_kinds["orphan-fragment"] >= 1, True)
        self.assertEqual(result.key_kinds["skipped:no-tokens"], 1)

        by_key = {rec.key: rec for rec in result.records}
        self.assertEqual(len(result.records), 4)

        first = by_key["antigravity:antigravity:conv-ide:1"]
        self.assertEqual((first.counts.input, first.counts.output,
                          first.counts.cache_read, first.counts.cache_write),
                         (100, 20, 0, 0))
        self.assertEqual(first.model, "gemini-3.8-flash-high")
        self.assertEqual(first.project, "alpha")
        self.assertEqual(first.session, "conv-ide")
        self.assertEqual(first.agent, "ide")

        cached = by_key["antigravity:antigravity:conv-ide:2"]
        self.assertEqual((cached.counts.input, cached.counts.cache_read), (30, 900))

        cli = by_key["antigravity:antigravity-cli:conv-cli:0"]
        self.assertEqual(cli.agent, "cli")
        self.assertEqual(cli.project, "default-cli-project")
        self.assertEqual(cli.model, "gemini-3.8-flash-low")

        totals = [sum(getattr(rec.counts, field) for rec in result.records)
                  for field in ("input", "output", "cache_read", "cache_write")]
        self.assertEqual(totals, [148, 30, 900, 0])

    def test_chunks_are_not_double_counted(self):
        home = self.build_home()
        with_chunks = scan_antigravity(home)
        # 去掉 chunks 镜像后结果必须一致
        shutil.rmtree(os.path.join(logs_dir(home, IDE_APP, "conv-ide"), "chunks"))
        without_chunks = scan_antigravity(home)
        self.assertEqual(len(without_chunks.records), len(with_chunks.records))
        self.assertEqual(without_chunks.key_kinds["skipped:duplicate-step"], 0)
        self.assertGreater(with_chunks.key_kinds["skipped:duplicate-step"], 0)

    def test_orphan_fragment_keeps_later_steps(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_raw(home, IDE_APP, "conv-frag", [
            json.dumps(model_step(0, input_tokens=5)),
            "}]}",
            json.dumps(model_step(1, input_tokens=6)),
            "available at: file:///tmp/task-1.log",
            json.dumps(model_step(2, input_tokens=7)),
        ])
        result = scan_antigravity(home)
        self.assertEqual(result.errors, [])
        self.assertEqual([rec.counts.input for rec in result.records], [5, 6, 7])

    def test_non_integer_step_index_is_dropped(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_transcript(home, IDE_APP, "conv-bad", [
            model_step(0, input_tokens=5),
            {"source": "MODEL", "type": "PLANNER_RESPONSE", "step_index": "x",
             "input_tokens": 9, "output_tokens": 9, "created_at": "2026-11-20T01:00:00Z"},
        ])
        result = scan_antigravity(home)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.key_kinds["skipped:bad-shape"], 1)

    def test_missing_root_degrades(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_transcript(home, CLI_APP, "conv-cli", [
            model_step(0, input_tokens=11),
        ])
        result = scan_antigravity(home)
        self.assertTrue(result.available)
        self.assertTrue(result.healthy)
        self.assertEqual([rec.agent for rec in result.records], ["cli"])
        self.assertTrue(any("antigravity" in note for note in result.notes))

        empty = scan_antigravity(os.path.join(home, "nope"))
        self.assertFalse(empty.available)
        self.assertEqual(empty.records, [])

    def test_zero_and_missing_timestamps_are_skipped(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_transcript(home, IDE_APP, "conv-zero", [
            model_step(0, input_tokens=5, output_tokens=1, cache_read_tokens=0),
            model_step(1, input_tokens=0, output_tokens=0, cache_read_tokens=0),
            model_step(2, input_tokens=8, created_at="not-a-timestamp"),
            model_step(3, input_tokens=9, created_at=""),
        ])
        result = scan_antigravity(home)
        self.assertEqual(result.errors, [])
        self.assertEqual([rec.counts.input for rec in result.records], [5])
        self.assertEqual(result.key_kinds["zero-usage"], 1)
        self.assertEqual(result.key_kinds["skipped:ts"], 2)

    def test_malformed_summaries_degrade(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_transcript(home, IDE_APP, "conv-a", [model_step(0, input_tokens=5)])
        write_transcript(home, IDE_APP, "conv-b", [model_step(0, input_tokens=7)])

        # workspace_uris 是垃圾值 → 项目回退默认
        db = os.path.join(app_dir(home, IDE_APP), "conversation_summaries.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE conversation_summaries ("
                     "conversation_id TEXT PRIMARY KEY, workspace_uris TEXT)")
        conn.executemany("INSERT INTO conversation_summaries VALUES (?,?)", [
            ("conv-a", ""),
            ("conv-b", "not json"),
        ])
        conn.commit()
        conn.close()
        result = scan_antigravity(home)
        self.assertEqual(result.errors, [])
        projects = {rec.session: rec.project for rec in result.records}
        self.assertEqual(projects["conv-a"], "default-cli-project")
        self.assertEqual(projects["conv-b"], "default-cli-project")

        # 摘要库损坏 → 记为错误，但不中断采集
        with open(db, "w", encoding="utf-8") as fh:
            fh.write("not a sqlite database")
        broken = scan_antigravity(home)
        self.assertEqual(len(broken.records), 2)
        self.assertEqual(len(broken.errors), 1)
        self.assertEqual(broken.errors[0][1].startswith("会话摘要读取失败"), True)

    def test_tokenless_copy_does_not_shadow_later_token_copy(self):
        """同一 step_index 先落无 token 形态、后补全时，必须取带 token 的副本。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_raw(home, IDE_APP, "conv-upgrade", [
            json.dumps({"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE",
                        "status": "RUNNING", "created_at": "2026-11-20T01:00:00Z"}),
            json.dumps(model_step(1, input_tokens=42, output_tokens=7,
                                  created_at="2026-11-20T01:00:05Z")),
        ])
        result = scan_antigravity(home)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].counts.input, 42)
        self.assertEqual(result.key_kinds["skipped:no-tokens"], 1)

    def test_duplicate_step_within_one_root_is_counted_once(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        step = model_step(0, input_tokens=5)
        write_transcript(home, IDE_APP, "conv-dup", [step])
        chunk_dir = os.path.join(logs_dir(home, IDE_APP, "conv-dup"),
                                 "chunks", "transcript_full")
        os.makedirs(chunk_dir, exist_ok=True)
        with open(os.path.join(chunk_dir, "00000000.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(step) + "\n")
            fh.write(json.dumps(step) + "\n")
        result = scan_antigravity(home)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].counts.input, 5)


class AntigravitySignatureTest(unittest.TestCase):
    def test_signature_tracks_both_roots(self):
        with tempfile.TemporaryDirectory() as home:
            first = source_signatures(home, ["antigravity"])
            self.assertIsNone(first["antigravity"])

            path = write_transcript(home, IDE_APP, "conv-ide", [model_step(0)])
            second = source_signatures(home, ["antigravity"])
            self.assertIsNotNone(second["antigravity"])

            stat = os.stat(path)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            third = source_signatures(home, ["antigravity"])
            self.assertGreater(third["antigravity"], second["antigravity"])

            cli_path = write_transcript(home, CLI_APP, "conv-cli", [model_step(0)])
            stat = os.stat(cli_path)
            os.utime(cli_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
            fourth = source_signatures(home, ["antigravity"])
            self.assertGreater(fourth["antigravity"], third["antigravity"])

    def test_signature_tracks_chunks_rotation(self):
        """主转录不变、chunks 增长时签名仍要推进，否则增量同步会漏。"""
        with tempfile.TemporaryDirectory() as home:
            main = write_transcript(home, IDE_APP, "conv-rot", [model_step(0)])
            first = source_signatures(home, ["antigravity"])

            chunk_dir = os.path.join(logs_dir(home, IDE_APP, "conv-rot"),
                                     "chunks", "transcript_full")
            os.makedirs(chunk_dir, exist_ok=True)
            chunk = os.path.join(chunk_dir, "00000000.jsonl")
            with open(chunk, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(model_step(0)) + "\n")
            stat = os.stat(chunk)
            os.utime(chunk, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            os.utime(main, ns=(stat.st_atime_ns, stat.st_mtime_ns))

            second = source_signatures(home, ["antigravity"])
            self.assertGreater(second["antigravity"], first["antigravity"])


class MiniMaxCollectorTest(unittest.TestCase):
    """MiniMax Code（`~/.minimax/v2/sessions`）的 token 真值采集。"""

    # 真实响应时间戳（毫秒）：2026-11-20T05:47:48Z
    ASSISTANT_TS_MS = 1795153668789

    def build_home(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [
            user_row(),
            assistant_row("msg-a1", usage_value=usage(100, 20, 0, 0)),
            assistant_row("msg-a2", usage_value=usage(30, 5, 900, 0),
                          timestamp_ms=1795153671502),
            tool_row(),
            # 没有 usage 的 assistant：跳过并计数，不能伪造 0
            assistant_row("msg-a3", usage_value=None),
            # 零 token：跳过
            assistant_row("msg-a4", usage_value=usage(0, 0, 0, 0)),
        ])
        write_runtime_db(home, [
            (DEFAULT_SESSION, "/Users/wayne/workspace/playground", None),
        ])
        return home

    def test_maps_assistant_usage_and_skips_the_rest(self):
        result = scan_minimax(self.build_home())
        self.assertTrue(result.healthy, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 2)

        by_key = {rec.key: rec for rec in result.records}
        first = by_key["minimax:%s:msg-a1" % DEFAULT_SESSION]
        self.assertEqual((first.counts.input, first.counts.output,
                          first.counts.cache_read, first.counts.cache_write,
                          first.counts.reasoning), (100, 20, 0, 0, 0))
        self.assertEqual(first.model, "MiniMax-M3.1-Flash")
        self.assertEqual(first.provider, "minimax")
        self.assertEqual(first.project, "playground")
        self.assertEqual(first.session, DEFAULT_SESSION)
        # 归属本地日：按毫秒时间戳换算，断言对时区不敏感
        self.assertAlmostEqual(first.ts, self.ASSISTANT_TS_MS / 1000.0, places=3)
        self.assertEqual(first.day,
                         datetime.fromtimestamp(self.ASSISTANT_TS_MS / 1000.0)
                         .strftime("%Y-%m-%d"))

        cached = by_key["minimax:%s:msg-a2" % DEFAULT_SESSION]
        self.assertEqual((cached.counts.input, cached.counts.output,
                          cached.counts.cache_read), (30, 5, 900))

        # 无 usage 与零 token 的 assistant 都被跳过，且分别计数
        self.assertEqual(result.key_kinds["skipped:no-usage"], 1)
        self.assertEqual(result.key_kinds["zero-usage"], 1)

    def test_input_excludes_cache_read(self):
        """口径：input 已排除 cache read，与 Claude / Codex 的非重叠口径一致。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [
            assistant_row("msg-a1", usage_value=usage(2697, 130, 32768, 0)),
        ])
        result = scan_minimax(home)
        self.assertEqual(len(result.records), 1)
        rec = result.records[0]
        # totalTokens = input + output + cacheRead → input 不含缓存
        self.assertEqual(rec.counts.input + rec.counts.output + rec.counts.cache_read,
                         35595)
        self.assertEqual(rec.counts.input, 2697)

    def test_broken_line_is_counted_not_fatal(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [
            json.dumps(assistant_row("msg-a1")),
            "{not json",
            json.dumps(assistant_row("msg-a2")),
        ])
        result = scan_minimax(home)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 2)
        self.assertGreaterEqual(result.key_kinds["skipped:bad-line"], 1)

    def test_duplicate_message_id_counted_once(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        row = assistant_row("msg-a1")
        write_messages(home, [row, row])
        result = scan_minimax(home)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.dup_dropped, 1)

    def test_session_id_falls_back_to_directory_name(self):
        """manifest.json 缺失时，用会话目录名后缀的 base64url 解码还原。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [assistant_row("msg-a1")], manifest=False)
        result = scan_minimax(home)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].session, DEFAULT_SESSION)
        self.assertEqual(result.records[0].key,
                         "minimax:%s:msg-a1" % DEFAULT_SESSION)

    def test_project_falls_back_to_project_workspace_dir(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [assistant_row("msg-a1")])
        write_runtime_db(home, [
            (DEFAULT_SESSION, None, "/Users/wayne/workspace/beta"),
        ])
        result = scan_minimax(home)
        self.assertEqual(result.records[0].project, "beta")

    def test_missing_runtime_db_degrades_to_no_project(self):
        """运行库缺失只影响项目维度，token 真值照常产出。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [assistant_row("msg-a1")])
        result = scan_minimax(home)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 1)
        self.assertIsNone(result.records[0].project)
        # 降级必须可见：状态 partial + note，而不是静默当成正常
        self.assertFalse(result.complete)
        self.assertTrue(any("项目维度" in note for note in result.notes), result.notes)

    def test_broken_runtime_db_does_not_break_collection(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_messages(home, [assistant_row("msg-a1")])
        path = runtime_db_path(home)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("not a sqlite database")
        result = scan_minimax(home)
        self.assertEqual(len(result.records), 1)
        self.assertIsNone(result.records[0].project)
        self.assertEqual(result.errors, [])
        self.assertFalse(result.complete)

    def test_missing_sessions_dir_is_unavailable(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        result = scan_minimax(home)
        self.assertFalse(result.available)
        self.assertEqual(result.records, [])


class MiniMaxSignatureTest(unittest.TestCase):
    def test_signature_tracks_messages_mtime(self):
        with tempfile.TemporaryDirectory() as home:
            first = source_signatures(home, ["minimax"])
            self.assertIsNone(first["minimax"])

            path = write_messages(home, [assistant_row("msg-a1")])
            second = source_signatures(home, ["minimax"])
            self.assertIsNotNone(second["minimax"])

            stat = os.stat(path)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            third = source_signatures(home, ["minimax"])
            self.assertGreater(third["minimax"], second["minimax"])


class CodeBuddyCollectorTest(unittest.TestCase):
    """腾讯 CodeBuddy CN（`codebuddy`）双目录日志镜像采集。"""

    def build_home(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_genie(home)
        write_log(home, [
            start_line(DEFAULT_TRACE),
            model_line(DEFAULT_TRACE),
            metric_line(DEFAULT_TRACE, 1, cb_usage()),
            metric_line(DEFAULT_TRACE, 2, cb_usage(output_tokens=5,
                                                   cache_tokens=900, cache_miss=100),
                        timestamp="2026-11-20 15:28:13.226"),
            summary_line(DEFAULT_TRACE, 1),
        ])
        return home

    def test_maps_step_usage_and_metadata(self):
        result = scan_codebuddy(self.build_home())
        self.assertTrue(result.healthy, (result.errors, result.notes))
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 2)

        first, second = result.records
        self.assertEqual(first.key, "codebuddy:%s:1" % DEFAULT_TRACE)
        self.assertEqual((first.counts.input, first.counts.output,
                          first.counts.cache_read, first.counts.cache_write,
                          first.counts.reasoning), (600, 20, 400, 0, 0))
        self.assertEqual((second.counts.input, second.counts.output,
                          second.counts.cache_read), (100, 5, 900))
        self.assertEqual(first.model, DEFAULT_MODEL_ID)
        self.assertEqual(first.model_raw, DEFAULT_MODEL_ID)
        self.assertEqual(first.session, DEFAULT_CONVERSATION)
        self.assertEqual(first.project, "playground")
        self.assertEqual(first.day, "2026-11-20")
        self.assertEqual(second.day, "2026-11-20")

    def test_input_tokens_including_cache_are_not_used(self):
        """日志的 inputTokens 含 cache read；直接采会重复计缓存。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_log(home, [metric_line(
            DEFAULT_TRACE, 1, cb_usage(input_tokens=999_999, cache_tokens=400,
                                       cache_miss=600))])
        rec = scan_codebuddy(home).records[0]
        self.assertEqual(rec.counts.input, 600)
        self.assertEqual(rec.counts.cache_read, 400)

    def test_mirrored_roots_are_deduplicated(self):
        home = self.build_home()
        write_log(home, [
            start_line(DEFAULT_TRACE, style="bracket"),
            model_line(DEFAULT_TRACE, style="bracket"),
            metric_line(DEFAULT_TRACE, 1, cb_usage(), style="bracket"),
            metric_line(DEFAULT_TRACE, 2, cb_usage(output_tokens=5,
                                                   cache_tokens=900, cache_miss=100),
                        style="bracket", timestamp="[11/20/2026, 3:28:13 PM.226]"),
        ], root="ide", name="playground__6b1eba.log")
        result = scan_codebuddy(home)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.dup_dropped, 2)
        self.assertEqual(result.records[0].day, "2026-11-20")

    def test_bad_lines_and_zero_usage_are_counted_not_fatal(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_log(home, [
            metric_line(DEFAULT_TRACE, 1, cb_usage()),
            metric_line(DEFAULT_TRACE, 2, cb_usage(output_tokens=0, cache_tokens=0,
                                                   cache_miss=0)),
            "2026-11-20 15:28:08.671 [info] [AgentReporter] [%s] "
            "Step execution metrics: step=3, duration=1ms, usage={not json}"
            % DEFAULT_TRACE,
            "2026-11-20 15:28:08.671 [info] [AgentReporter] [%s] "
            "Step execution metrics: step=abc, duration=1ms, usage={}"
            % DEFAULT_TRACE,
            summary_line(DEFAULT_TRACE, 1),
        ])
        result = scan_codebuddy(home)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.key_kinds["zero-usage"], 1)
        self.assertEqual(result.key_kinds["skipped:bad-usage"], 1)
        self.assertEqual(result.key_kinds["skipped:bad-step"], 1)
        self.assertEqual(result.key_kinds["skipped:no-usage"], 1)

    def test_metadata_fallbacks_when_logs_lack_context(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_log(home, [metric_line(DEFAULT_TRACE, 1, cb_usage())])
        result = scan_codebuddy(home)
        self.assertEqual(len(result.records), 1)
        rec = result.records[0]
        self.assertEqual(rec.session, DEFAULT_TRACE)
        self.assertEqual(rec.model, "unknown")
        self.assertIsNone(rec.project)
        self.assertFalse(result.complete)
        self.assertTrue(any("项目维度" in note for note in result.notes), result.notes)

    def test_bad_genie_entry_is_counted_not_fatal(self):
        home = self.build_home()
        bad_dir = os.path.join(home, GENIE_REL, "not_base64!")
        os.makedirs(bad_dir, exist_ok=True)
        with open(os.path.join(bad_dir, "current.json"), "w", encoding="utf-8") as fh:
            fh.write("[1, 2, 3]")
        result = scan_codebuddy(home)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0].project, "playground")
        self.assertGreaterEqual(result.key_kinds["skipped:bad-genie"], 1)

    def test_genie_padding_underscore_is_restored(self):
        """厂商把 base64 padding '=' 写成 '_'：tongxing-air 不能解成 'tongxing-air?'。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        workspace = "/Users/wayne/workspace/tongxing-air"
        write_genie(home, workspace=workspace)
        write_log(home, [start_line(DEFAULT_TRACE),
                         metric_line(DEFAULT_TRACE, 1, cb_usage())])
        result = scan_codebuddy(home)
        self.assertEqual(result.records[0].project, "tongxing-air")
        self.assertEqual(result.key_kinds["skipped:bad-genie"], 0)

    def test_genie_appended_suffix_is_restored(self):
        """无 padding 的时间戳工作区目录名尾部追加 '__'。"""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        write_genie(home, workspace="/Users/wayne/CodeBuddy/20260928133809",
                    suffix="__")
        write_log(home, [start_line(DEFAULT_TRACE),
                         metric_line(DEFAULT_TRACE, 1, cb_usage())])
        result = scan_codebuddy(home)
        self.assertEqual(result.records[0].project, "20260928133809")
        self.assertEqual(result.key_kinds["skipped:bad-genie"], 0)

    def test_missing_roots_is_unavailable(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        result = scan_codebuddy(home)
        self.assertFalse(result.available)
        self.assertEqual(result.records, [])


class CodeBuddySignatureTest(unittest.TestCase):
    def test_signature_tracks_both_roots(self):
        with tempfile.TemporaryDirectory() as home:
            first = source_signatures(home, ["codebuddy"])
            self.assertIsNone(first["codebuddy"])

            path = write_log(home, [metric_line(DEFAULT_TRACE, 1, cb_usage())])
            second = source_signatures(home, ["codebuddy"])
            self.assertIsNotNone(second["codebuddy"])

            stat = os.stat(path)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            third = source_signatures(home, ["codebuddy"])
            self.assertGreater(third["codebuddy"], second["codebuddy"])

            write_log(home, [metric_line(DEFAULT_TRACE, 1, cb_usage())],
                      root="ide", name="playground__hash.log")
            fourth = source_signatures(home, ["codebuddy"])
            self.assertGreaterEqual(fourth["codebuddy"], third["codebuddy"])


class QoderModelLabelLearningTest(unittest.TestCase):
    def _write_cache(self, cache_dir, name, entries):
        os.makedirs(cache_dir, exist_ok=True)
        payload = json.dumps({"data": entries})
        with open(os.path.join(cache_dir, name), "w", encoding="utf-8") as fh:
            fh.write("1/0/https://openapi.qoder.sh/x" + payload)

    def _write_activity_db(self, path, session_models):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, "
                     "cwd TEXT, model TEXT)")
        for sid, model in session_models.items():
            conn.execute("INSERT INTO chat_sessions VALUES (?,?,?)",
                         (sid, "/tmp/p", model))
        conn.commit()
        conn.close()

    def test_unambiguous_sessions_learn_key_to_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, "cache")
            db = activity_path(tmp)
            self._write_activity_db(db, {"s1": "qmodel_latest_preview",
                                         "s2": "dfmodel",
                                         "s3": "qmodel_latest_preview"})
            self._write_cache(cache_dir, "a_0", [
                # s1 全部是 Qwen4 → 无歧义，采纳
                {"session_id": "s1", "model_category": "Qwen4-Max-Preview"},
                {"session_id": "s1", "model_category": "Qwen4-Max-Preview"},
                # s2 全部是 DeepSeek → 无歧义，采纳
                {"session_id": "s2", "model_category": "DeepSeek-Flash"},
                # s3 全部是 Qwen4 → 无歧义，采纳（与 s1 同键，多数票）
                {"session_id": "s3", "model_category": "Qwen4-Max-Preview"},
            ])
            old = os.environ.get("USAGE_LEDGER_QODER_CACHE")
            os.environ["USAGE_LEDGER_QODER_CACHE"] = cache_dir
            try:
                labels = learn_qoder_model_labels(tmp)
            finally:
                if old is None:
                    os.environ.pop("USAGE_LEDGER_QODER_CACHE", None)
                else:
                    os.environ["USAGE_LEDGER_QODER_CACHE"] = old
            self.assertEqual(labels["qmodel_latest_preview"], "Qwen4-Max-Preview")
            self.assertEqual(labels["dfmodel"], "DeepSeek-Flash")

    def test_session_switching_models_is_skipped(self):
        # 同一会话先 A 后 B：计费条目混入两个 category，归属不唯一 → 整段跳过，
        # 不能把任一模型误标成另一个。
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, "cache")
            self._write_cache(cache_dir, "a_0", [
                {"session_id": "s1", "model_category": "DeepSeek-Flash"},
                {"session_id": "s1", "model_category": "DeepSeek-Flash"},
                {"session_id": "s1", "model_category": "Qwen4-Max-Preview"},
            ])
            labels = learn_billing_labels(cache_dir, {"s1": "qmodel_latest_preview"})
            self.assertEqual(labels, {})

    def test_tie_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, "cache")
            self._write_cache(cache_dir, "a_0", [
                {"session_id": "s1", "model_category": "A"},
                {"session_id": "s1", "model_category": "B"},
            ])
            labels = learn_billing_labels(cache_dir, {"s1": "somekey"})
            self.assertEqual(labels, {})

    def test_missing_sources_return_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(learn_qoder_model_labels(tmp), {})

    def test_corrupt_cache_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, "cache")
            os.makedirs(cache_dir)
            with open(os.path.join(cache_dir, "junk"), "wb") as fh:
                fh.write(b"\x00\x01not a cache")
            self.assertEqual(learn_billing_labels(cache_dir, {"s1": "k"}), {})


if __name__ == "__main__":
    unittest.main()
