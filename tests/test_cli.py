import contextlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.usage_ledger.cli import main
from src.usage_ledger.store import SqliteStore
from tests.antigravity_helpers import (CLI_APP, IDE_APP, model_step,
                                       write_summaries, write_transcript)
from tests.codebuddy_helpers import (DEFAULT_TRACE, metric_line, model_line,
                                     start_line, usage as cb_usage, write_genie,
                                     write_log)
from tests.minimax_helpers import (DEFAULT_SESSION, assistant_row, usage,
                                   write_messages, write_runtime_db)
from tests.qoder_helpers import (activity_path, create_activity_db, create_token_db,
                                 log_path, quota_line, token_path, transcript_path,
                                 write_jsonl, write_quota_log)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class CliConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        shutil.copytree(os.path.join(FIXTURES, "claude", "projects"),
                        os.path.join(self.home, ".claude", "projects"))
        os.makedirs(os.path.join(self.home, ".codex"), exist_ok=True)
        shutil.copytree(os.path.join(FIXTURES, "codex", "sessions"),
                        os.path.join(self.home, ".codex", "sessions"))
        shutil.copytree(os.path.join(FIXTURES, "codex", "archived_sessions"),
                        os.path.join(self.home, ".codex", "archived_sessions"))

        opencode_dir = os.path.join(self.home, ".local", "share", "opencode")
        os.makedirs(opencode_dir, exist_ok=True)
        self.opencode_db = os.path.join(opencode_dir, "opencode.db")
        conn = sqlite3.connect(self.opencode_db)
        conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, "
                     "time_updated INTEGER, data TEXT)")
        stamp = int(datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
        data = {"role": "assistant", "modelID": "deepseek-v4-flash", "providerID": "opencode",
                "path": {"cwd": "/tmp/proj-c"},
                "tokens": {"input": 1, "output": 2, "reasoning": 3,
                           "cache": {"read": 4, "write": 5}}}
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("om1", "os1", stamp, None, json.dumps(data)))
        conn.commit()
        conn.close()

        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_idempotent_and_report_consistency(self):
        code, _, _ = self.run_cli(["backfill"])
        self.assertEqual(code, 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 6)
        store.close()

        code, _, _ = self.run_cli(["backfill"])
        self.assertEqual(code, 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 6)
        store.close()

        code, db_json, _ = self.run_cli(["report", "--format", "json"])
        self.assertEqual(code, 0)
        code, source_json, _ = self.run_cli(["--stateless", "report", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(source_json))

        code, live_json, _ = self.run_cli(["report", "--live", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(live_json))

    def test_stateless_does_not_touch_db(self):
        self.run_cli(["backfill"])
        before = os.stat(self.db_path).st_mtime_ns
        code, _, _ = self.run_cli(["--stateless", "report", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(os.stat(self.db_path).st_mtime_ns, before)

    def test_report_grouping_and_filtering(self):
        self.run_cli(["backfill"])
        code, out, _ = self.run_cli(["report", "--group-by", "source", "--format", "json"])
        self.assertEqual(code, 0)
        rows = {row["source"]: row for row in json.loads(out)}
        self.assertEqual(rows["claude"]["input"], 110)
        self.assertEqual(rows["claude"]["output"], 25)
        self.assertEqual(rows["codex"]["input"], 220)
        self.assertEqual(rows["opencode"]["cache_read"], 4)

        code, out, _ = self.run_cli(["report", "--filter", "source=codex",
                                     "--format", "json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertTrue(rows)
        self.assertTrue(all(row["source"] == "codex" for row in rows))

    def test_report_auto_syncs_when_source_has_new_data(self):
        self.run_cli(["backfill"])
        path = os.path.join(self.home, ".claude", "projects", "proj-a", "session-1.jsonl")
        record = {
            "type": "assistant", "uuid": "u9", "sessionId": "s1",
            "timestamp": "2026-10-02T10:00:00Z", "cwd": "/tmp/proj-a",
            "message": {"id": "m9", "model": "claude-opus-4",
                        "usage": {"input_tokens": 7, "output_tokens": 3,
                                  "cache_read_input_tokens": 0,
                                  "cache_creation_input_tokens": 0,
                                  "iterations": [{"input_tokens": 7, "output_tokens": 3}]}},
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        stat = os.stat(path)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        code, out, err = self.run_cli(["report", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("auto-sync", err)
        rows = json.loads(out)
        self.assertEqual(sum(row["input"] for row in rows), 338)
        self.assertEqual(sum(row["output"] for row in rows), 114)

        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 7)
        store.close()

        code, out, err = self.run_cli(["report", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertNotIn("auto-sync", err)

    def test_auto_sync_only_checks_requested_source(self):
        self.run_cli(["backfill"])
        path = os.path.join(self.home, ".codex", "sessions", "rollout-a.jsonl")
        stat = os.stat(path)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        code, _, err = self.run_cli(["report", "--source", "claude", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertNotIn("auto-sync", err)

        code, _, err = self.run_cli(["report", "--source", "codex", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("auto-sync", err)

    def test_doctor_reports_gaps(self):
        self.run_cli(["backfill"])
        code, out, err = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("Qoder", out)
        self.assertIn("archived", out)
        self.assertIn("kilo", out)

    def test_archived_detection_skips_unavailable_source(self):
        self.run_cli(["backfill"])
        store = SqliteStore(self.db_path)
        self.assertEqual(store.archived_count(), 0)
        store.close()

        projects = os.path.join(self.home, ".claude", "projects")
        shutil.rmtree(projects)
        code, out, _ = self.run_cli(["sync", "--full"])
        self.assertEqual(code, 0)
        self.assertIn("status=unsupported", out)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.archived_count(), 0)
        store.close()

        os.makedirs(os.path.join(projects, "proj-a"))
        shutil.copy(os.path.join(FIXTURES, "claude", "projects", "proj-a", "session-1.jsonl"),
                    os.path.join(projects, "proj-a", "session-1.jsonl"))
        code, out, _ = self.run_cli(["sync", "--full"])
        self.assertEqual(code, 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.archived_count(), 1)
        self.assertEqual(store.turn_count(), 6)
        store.close()


class QoderCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.ts1 = int(datetime(2026, 10, 1, 12, 0).timestamp() * 1000)
        self.ts2 = int(datetime(2026, 10, 2, 12, 0).timestamp() * 1000)
        self.token_db = token_path(self.home)
        self.activity_db = activity_path(self.home)
        create_token_db(self.token_db, [
            ("m1", "s1", "assistant", self.ts1, '{"model_key":"qmodel"}',
             '{"prompt_tokens":1000,"completion_tokens":50,"cached_tokens":800}'),
            ("m2", "s2", "assistant", self.ts2, '{"model_key":"qmodel"}',
             '{"prompt_tokens":100,"completion_tokens":20,"cached_tokens":0}'),
        ], {
            "s1": {"project_name": "proj-x"},
            "s2": {"project_name": "proj-y"},
        })
        create_activity_db(self.activity_db, [
            ("u1", "s1", "user", {}, self.ts1, None),
            ("a1", "s1", "assistant", {"parts": [{"type": "tool"}],
                                       "turnMetrics": {"turnCount": 2, "durationMs": 1000}},
             self.ts1, None),
            ("u2", "s2", "user", {}, self.ts2, None),
            ("a2", "s2", "assistant", {"parts": [{"type": "tool"}, {"type": "tool"}]},
             self.ts2, None),
        ], {"s1": "/tmp/proj-x", "s2": "/tmp/proj-y"})
        base = datetime(2026, 10, 1, 12, 5, 0)
        self.credit_iso = base.isoformat()
        self.credit_iso2 = (base + timedelta(seconds=5)).isoformat()
        self.credit_iso3 = (base + timedelta(minutes=1)).isoformat()
        write_jsonl(transcript_path(self.home), [
            {"type": "user", "sessionId": "s1", "cwd": "/tmp/proj-x",
             "timestamp": self.credit_iso,
             "message": {"content": [{"type": "text", "text": "hello there"}]},
             "humanInput": {"text": "hello there"}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-x",
             "timestamp": self.credit_iso2,
             "message": {"model": "gfmodel",
                         "content": [{"type": "text", "text": "world"}],
                         "usage": {"request_id": "r1", "credits": 2.5,
                                   "billable": True, "context_usage_ratio": 0.25}}},
            {"type": "user", "sessionId": "s1", "cwd": "/tmp/proj-x",
             "timestamp": self.credit_iso3,
             "message": {"content": [{"type": "text", "text": "second prompt"}]}},
            {"type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-x",
             "timestamp": self.credit_iso3,
             "message": {"model": "gfmodel",
                         "content": [{"type": "text", "text": "answer here"}],
                         "usage": {"request_id": "r2", "credits": 1.0,
                                   "billable": False, "context_usage_ratio": 0.5}}},
        ])
        write_quota_log(log_path(self.home), [
            quota_line(self.credit_iso2, "q1", used=100, remaining=2200, pct=0.04),
        ])

        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_stores_tokens_and_activity(self):
        code, _, err = self.run_cli(["backfill"])
        self.assertEqual(code, 0, err)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        self.assertEqual(store.activity_count("qoder.activity"), 2)
        self.assertEqual(store.source_bounds("qoder"), ("2026-10-01", "2026-10-02"))
        self.assertEqual(store.activity_bounds("qoder.activity"),
                         ("2026-10-01", "2026-10-02"))
        store.close()

        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual(sum(row["input"] for row in rows), 300)
        self.assertEqual(sum(row["output"] for row in rows), 70)
        self.assertEqual(sum(row["cache_read"] for row in rows), 800)

        code, out, err = self.run_cli(["activity", "--format", "json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(len(rows), 2)
        by_day = {row["date"]: row for row in rows}
        self.assertEqual(by_day["2026-10-01"]["turns"], 2)
        self.assertEqual(by_day["2026-10-02"]["tool_calls"], 2)
        self.assertEqual(by_day["2026-10-02"]["duration_ms"], 0)
        self.assertIn("不可相加", err)

        code, out, _ = self.run_cli(["activity", "--source", "claude", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_backfill_stores_credits_and_estimates(self):
        code, _, err = self.run_cli(["backfill"])
        self.assertEqual(code, 0, err)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.credit_count(), 2)
        self.assertEqual(store.quota_count(), 2)
        self.assertEqual(store.est_count(), 2)
        self.assertEqual(store.est_missing_ratio(), 0)
        self.assertEqual(store.credit_bounds()[0:2], ("2026-10-01", "2026-10-01"))
        state = store.get_meta("transcript_files")
        self.assertIn("session-1.jsonl", state)
        store.close()

        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.credit_count(), 2)
        self.assertEqual(store.est_count(), 2)
        store.close()

        code, out, err = self.run_cli(["credits", "--format", "json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["totals"]["qoder"]["credits"], 2.5)
        self.assertEqual(payload["totals"]["qoder"]["free_credits"], 1.0)
        self.assertEqual(payload["totals"]["qoder"]["requests"], 2)
        self.assertEqual([row["day"] for row in payload["days"]], ["2026-10-01"])
        self.assertEqual(payload["days"][0]["credits"], 2.5)
        self.assertEqual(payload["days"][0]["requests"], 1)
        self.assertEqual(payload["days"][0]["free_credits"], 1.0)
        self.assertEqual(payload["days"][0]["snapshots"], 1)
        self.assertEqual(payload["quota"]["add_on"]["used"], 100)
        self.assertIn("非 token", err)
        self.assertIn("额度快照 add_on", err)

        code, out, err = self.run_cli(["est", "--format", "json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["day"], "2026-10-01")
        self.assertEqual(rows[0]["model"], "GLM-5.3-Flash")
        self.assertEqual(rows[0]["est_input"], 150_000)
        self.assertEqual(rows[0]["est_output"], 4)
        self.assertEqual(rows[0]["requests"], 2)
        self.assertIn("不可与真值/额度相加", err)

        code, out, err = self.run_cli(["--stateless", "credits", "--format", "json"])
        self.assertEqual(code, 0, err)
        stateless = json.loads(out)
        self.assertEqual(stateless["totals"]["qoder"]["credits"], 2.5)
        self.assertEqual(stateless["days"][0]["snapshots"], 1)

        shutil.rmtree(os.path.dirname(log_path(self.home)))
        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.credit_count(), 2)
        self.assertEqual(store.quota_count(), 2)
        self.assertEqual(store.est_count(), 2)
        store.close()

    def test_incremental_backfill_skips_turn_request_seen_in_transcript(self):
        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.credit_count(), 2)
        store.close()

        turn_ts = int(datetime(2026, 10, 1, 12, 5, 5).timestamp() * 1000)
        conn = sqlite3.connect(self.activity_db)
        conn.execute("ALTER TABLE chat_session_messages ADD COLUMN message_id TEXT")
        conn.execute("ALTER TABLE chat_session_messages ADD COLUMN turn_credits REAL")
        conn.execute(
            "ALTER TABLE chat_session_messages ADD COLUMN turn_credits_request_set_id TEXT")
        conn.execute(
            "INSERT INTO chat_session_messages "
            "(id, session_id, role, payload_json, created_at, updated_at, message_id, "
            "turn_credits, turn_credits_request_set_id) VALUES (?,?,?,?,?,?,?,?,?)",
            ("a3", "s1", "assistant", "{}", turn_ts, None, "m3", 2.5, "r1"))
        conn.commit()
        conn.close()

        store = SqliteStore(self.db_path)
        store.conn.execute(
            "INSERT INTO usage_credit "
            "(request_id, source, ts, day, project, model, session_id, credits, "
            "billable, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("qoder-turn:s1:m3", "qoder", turn_ts / 1000.0, "2026-10-01", "proj-x",
             "qmodel", "s1", 2.5, 1, turn_ts / 1000.0))
        store.conn.commit()
        self.assertEqual(store.credit_count(), 3)
        store.close()

        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        store = SqliteStore(self.db_path)
        ids = {row[0] for row in store.conn.execute("SELECT request_id FROM usage_credit")}
        self.assertEqual(store.credit_count(), 2)
        self.assertNotIn("qoder-turn:s1:m3", ids)
        self.assertEqual(store.credits_totals("2026-10-01", "2026-10-01")["qoder"]["credits"],
                         2.5)
        store.close()

    def test_model_labels_follow_qoder_display_names(self):
        self.run_cli(["backfill"])
        for name in ("Qwen3.7-Plus", "qmodel"):
            code, out, _ = self.run_cli(
                ["report", "--source", "qoder", "--format", "json", "--model", name])
            self.assertEqual(code, 0)
            rows = json.loads(out)
            self.assertTrue(rows)
            self.assertEqual({row["model"] for row in rows}, {"Qwen3.7-Plus"})

        code, out, _ = self.run_cli(["top", "models", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("Qwen3.7-Plus", {row["model"] for row in json.loads(out)})

    def test_sync_skips_token_scan_when_mtime_unchanged(self):
        self.run_cli(["backfill"])
        code, out, err = self.run_cli(["sync", "--source", "qoder"])
        self.assertEqual(code, 0, err)
        self.assertIn("token 库 mtime 未变化", out)
        self.assertIn("无新消息", out)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

    def test_activity_only_refresh_when_activity_db_touches(self):
        self.run_cli(["backfill"])
        os.utime(self.activity_db, ns=(os.stat(self.activity_db).st_atime_ns,
                                       os.stat(self.activity_db).st_mtime_ns + 1_000_000_000))
        with patch("src.usage_ledger.collectors.scan_qoder_tokens") as token_scan:
            code, _, err = self.run_cli(["report", "--source", "qoder", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("qoder.activity", err)
        token_scan.assert_not_called()

    def test_doctor_reports_both_ledgers(self):
        self.run_cli(["backfill"])
        with open(transcript_path(self.home), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "type": "assistant", "sessionId": "s1", "cwd": "/tmp/proj-x",
                "timestamp": (datetime.fromisoformat(self.credit_iso3)
                              + timedelta(minutes=1)).isoformat(),
                "message": {"model": "gfmodel",
                            "content": [{"type": "text", "text": "no ratio"}],
                            "usage": {"credits": 0.5, "billable": True}}}) + "\n")
        with open(log_path(self.home), "a", encoding="utf-8") as fh:
            fh.write('[2026-10-01T12:30:00] INFO 用量响应摘要 {"operation": broken\n')

        code, out, err = self.run_cli(["doctor", "--probe", "qoder"])
        self.assertEqual(code, 0, err)
        self.assertIn("qoder: files=1 records=2 tokens=1,170", out)
        self.assertIn("qoder.activity:", out)
        self.assertIn("token 覆盖 2026-10-01..2026-10-02", out)
        self.assertIn("活动覆盖 2026-10-01..2026-10-02", out)
        self.assertIn("credits: qoder_requests=2 trae_sessions=0 quota_snapshots=2 "
                      "est_rows=2 missing_ratio=0", out)
        self.assertIn("qoder.credits: files=1 credits=2 est=2 quota=2", out)
        self.assertIn("ratio 缺失响应 1", out)
        self.assertIn("warning: 额度日志解析失败 1 行", out)
        self.assertIn("warning: 额度快照已", out)
        self.assertIn(">24h", out)


class ClineCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        shutil.copytree(os.path.join(FIXTURES, "cline", "sessions"),
                        os.path.join(self.home, ".cline", "data", "sessions"))
        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_and_report_match_stateless(self):
        code, _, _ = self.run_cli(["backfill"])
        self.assertEqual(code, 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 3)
        store.close()

        code, db_json, _ = self.run_cli(
            ["report", "--source", "cline", "--format", "json"])
        self.assertEqual(code, 0)
        code, source_json, _ = self.run_cli(
            ["--stateless", "report", "--source", "cline", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(source_json))

        rows = json.loads(db_json)
        self.assertEqual(sum(row["input"] for row in rows), 450)
        self.assertEqual(sum(row["output"] for row in rows), 240)
        self.assertEqual(sum(row["cache_read"] for row in rows), 800)
        self.assertEqual(sum(row["cache_write"] for row in rows), 100)

    def test_report_auto_syncs_new_cline_messages(self):
        self.run_cli(["backfill"])
        path = os.path.join(self.home, ".cline", "data", "sessions",
                            "1787000000000_aaaa",
                            "1787000000000_aaaa.messages.json")
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        obj["messages"].append({
            "id": "msg_a9", "role": "assistant",
            "ts": max(msg["ts"] for msg in obj["messages"]) + 60000,
            "modelInfo": {"id": "anthropic/claude-sonnet-4", "provider": "anthropic"},
            "metrics": {"inputTokens": 70, "outputTokens": 7,
                        "cacheReadTokens": 0, "cacheWriteTokens": 0}})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        os.utime(path, ns=(os.stat(path).st_atime_ns,
                           os.stat(path).st_mtime_ns + 1_000_000_000))

        code, out, err = self.run_cli(["report", "--source", "cline", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertIn("auto-sync", err)
        rows = json.loads(out)
        self.assertEqual(sum(row["input"] for row in rows), 520)


class AntigravityCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        write_transcript(self.home, IDE_APP, "conv-ide", [
            model_step(0, input_tokens=100, output_tokens=20),
            model_step(1, input_tokens=30, output_tokens=5, cache_read_tokens=900,
                       created_at="2026-11-20T01:01:00Z"),
        ])
        write_summaries(self.home, IDE_APP,
                        [("conv-ide", '["file:///Users/wayne/workspace/alpha"]')])
        write_transcript(self.home, CLI_APP, "conv-cli", [
            model_step(0, model="gemini-3.8-flash-low", input_tokens=11,
                       output_tokens=2, created_at="2026-11-20T02:00:00Z"),
        ])
        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_and_report_match_stateless(self):
        code, _, err = self.run_cli(["backfill"])
        self.assertEqual(code, 0, err)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 3)
        store.close()

        code, db_json, _ = self.run_cli(
            ["report", "--source", "antigravity", "--format", "json"])
        self.assertEqual(code, 0)
        code, source_json, _ = self.run_cli(
            ["--stateless", "report", "--source", "antigravity", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(source_json))

        rows = json.loads(db_json)
        self.assertEqual(sum(row["input"] for row in rows), 141)
        self.assertEqual(sum(row["output"] for row in rows), 27)
        self.assertEqual(sum(row["cache_read"] for row in rows), 900)

    def test_backfill_is_idempotent(self):
        self.run_cli(["backfill"])
        self.run_cli(["backfill"])
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 3)
        store.close()

    def test_report_merges_ide_and_cli_into_one_source(self):
        self.run_cli(["backfill"])
        code, out, _ = self.run_cli(
            ["report", "--source", "antigravity", "--group-by", "source",
             "--format", "json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual({row["source"] for row in rows}, {"antigravity"})

    def test_doctor_reports_antigravity(self):
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("antigravity", out)


def write_codearts_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                 "time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, "
                 "data TEXT NOT NULL)")
    for mid, data in rows:
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     (mid, "s1", data["time"]["created"], data["time"]["created"],
                      json.dumps(data)))
    conn.commit()
    conn.close()


def codearts_message(stamp_ms, input=100, output=20, cache_read=900):
    return {"role": "assistant", "modelID": "glm-5.3-flash",
            "providerID": "inferhub-provider",
            "path": {"cwd": "/Users/wayne/workspace/playground"},
            "time": {"created": stamp_ms},
            "tokens": {"input": input, "output": output, "reasoning": 5,
                       "cache": {"read": cache_read, "write": 0}}}


class CodeArtsCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        db_dir = os.path.join(self.home, ".codeartsdoer", "codearts-data")
        os.makedirs(db_dir)
        self.codearts_db = os.path.join(db_dir, "opencode.db")
        stamp = int(datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
        write_codearts_db(self.codearts_db, [
            ("m1", codearts_message(stamp)),
            ("m2", codearts_message(stamp + 60_000, input=30, output=5, cache_read=0)),
        ])
        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_and_report_match_stateless(self):
        code, _, err = self.run_cli(["backfill"])
        self.assertEqual(code, 0, err)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

        code, db_json, _ = self.run_cli(
            ["report", "--source", "codearts", "--format", "json"])
        self.assertEqual(code, 0)
        code, source_json, _ = self.run_cli(
            ["--stateless", "report", "--source", "codearts", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(source_json))

        rows = json.loads(db_json)
        self.assertEqual(sum(row["input"] for row in rows), 130)
        self.assertEqual(sum(row["output"] for row in rows), 25)
        self.assertEqual(sum(row["cache_read"] for row in rows), 900)

    def test_backfill_is_idempotent(self):
        self.run_cli(["backfill"])
        self.run_cli(["backfill"])
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

    def test_report_auto_syncs_new_codearts_messages(self):
        self.run_cli(["backfill"])
        store = SqliteStore(self.db_path)
        stored_us = store.source_mtimes()["codearts"]
        store.close()

        stamp = stored_us // 1_000 + 1_000
        conn = sqlite3.connect(self.codearts_db)
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m3", "s1", stamp, stamp, json.dumps(codearts_message(stamp))))
        conn.commit()
        conn.close()
        bumped_ns = int((stored_us + 1_000_000) * 1_000)
        os.utime(self.codearts_db, ns=(bumped_ns, bumped_ns))

        code, out, _ = self.run_cli(
            ["report", "--source", "codearts", "--format", "json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual(sum(row["input"] for row in rows), 230)

    def test_doctor_reports_codearts(self):
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("codearts", out)


class MiniMaxCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        write_messages(self.home, [
            assistant_row("msg-a1", usage_value=usage(100, 20, 0, 0)),
            assistant_row("msg-a2", usage_value=usage(30, 5, 900, 0),
                          timestamp_ms=1795153671502),
        ])
        write_runtime_db(self.home, [
            (DEFAULT_SESSION, "/Users/wayne/workspace/playground", None),
        ])
        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_and_report_match_stateless(self):
        code, _, err = self.run_cli(["backfill", "--source", "minimax"])
        self.assertEqual(code, 0, err)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

        code, db_json, _ = self.run_cli(
            ["report", "--source", "minimax", "--format", "json"])
        self.assertEqual(code, 0)
        code, source_json, _ = self.run_cli(
            ["--stateless", "report", "--source", "minimax", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(source_json))

        rows = json.loads(db_json)
        self.assertEqual({row["source"] for row in rows}, {"minimax"})
        self.assertEqual(sum(row["input"] for row in rows), 130)
        self.assertEqual(sum(row["output"] for row in rows), 25)
        self.assertEqual(sum(row["cache_read"] for row in rows), 900)

    def test_backfill_is_idempotent(self):
        self.run_cli(["backfill", "--source", "minimax"])
        self.run_cli(["backfill", "--source", "minimax"])
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

    def test_report_auto_syncs_new_minimax_messages(self):
        self.run_cli(["backfill", "--source", "minimax"])
        path = write_messages(self.home, [
            assistant_row("msg-a1", usage_value=usage(100, 20, 0, 0)),
            assistant_row("msg-a2", usage_value=usage(30, 5, 900, 0),
                          timestamp_ms=1795153671502),
            assistant_row("msg-a3", usage_value=usage(70, 7, 0, 0),
                          timestamp_ms=1795153672502),
        ])
        os.utime(path, ns=(os.stat(path).st_atime_ns,
                           os.stat(path).st_mtime_ns + 1_000_000_000))
        code, out, err = self.run_cli(
            ["report", "--source", "minimax", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertIn("auto-sync", err)
        rows = json.loads(out)
        self.assertEqual(sum(row["input"] for row in rows), 200)

    def test_doctor_reports_minimax(self):
        self.run_cli(["backfill", "--source", "minimax"])
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("minimax", out)


class CodeBuddyCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        write_genie(self.home)
        self.log_path = write_log(self.home, [
            start_line(DEFAULT_TRACE),
            model_line(DEFAULT_TRACE),
            metric_line(DEFAULT_TRACE, 1, cb_usage()),
            metric_line(DEFAULT_TRACE, 2, cb_usage(output_tokens=5,
                                                   cache_tokens=900, cache_miss=100),
                        timestamp="2026-11-20 15:28:13.226"),
        ])
        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_backfill_and_report_match_stateless(self):
        code, _, err = self.run_cli(["backfill", "--source", "codebuddy"])
        self.assertEqual(code, 0, err)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

        code, db_json, _ = self.run_cli(
            ["report", "--source", "codebuddy", "--format", "json"])
        self.assertEqual(code, 0)
        code, source_json, _ = self.run_cli(
            ["--stateless", "report", "--source", "codebuddy", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(db_json), json.loads(source_json))

        rows = json.loads(db_json)
        self.assertEqual({row["source"] for row in rows}, {"codebuddy"})
        self.assertEqual(sum(row["input"] for row in rows), 700)
        self.assertEqual(sum(row["output"] for row in rows), 25)
        self.assertEqual(sum(row["cache_read"] for row in rows), 1300)

    def test_backfill_is_idempotent(self):
        self.run_cli(["backfill", "--source", "codebuddy"])
        self.run_cli(["backfill", "--source", "codebuddy"])
        store = SqliteStore(self.db_path)
        self.assertEqual(store.turn_count(), 2)
        store.close()

    def test_report_auto_syncs_new_codebuddy_steps(self):
        self.run_cli(["backfill", "--source", "codebuddy"])
        write_log(self.home, [
            start_line(DEFAULT_TRACE),
            model_line(DEFAULT_TRACE),
            metric_line(DEFAULT_TRACE, 1, cb_usage()),
            metric_line(DEFAULT_TRACE, 2, cb_usage(output_tokens=5,
                                                   cache_tokens=900, cache_miss=100),
                        timestamp="2026-11-20 15:28:13.226"),
            metric_line(DEFAULT_TRACE, 3, cb_usage(output_tokens=7,
                                                   cache_tokens=1200, cache_miss=80),
                        timestamp="2026-11-20 15:28:16.423"),
        ])
        stat = os.stat(self.log_path)
        os.utime(self.log_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        code, out, err = self.run_cli(
            ["report", "--source", "codebuddy", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertIn("auto-sync", err)
        self.assertEqual(sum(row["input"] for row in json.loads(out)), 780)

    def test_doctor_reports_codebuddy(self):
        self.run_cli(["backfill", "--source", "codebuddy"])
        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("codebuddy", out)


class QoderModelLabelCliTest(unittest.TestCase):
    """CHG-0021：报表用学习到的显示名，且首次自动同步即生效、可用显示名过滤。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.db_path = os.path.join(self.home, "usage.db")
        self.token_db = token_path(self.home)
        self.activity_db = activity_path(self.home)
        self.cache_dir = os.path.join(self.home, "cache")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": self.db_path,
            "USAGE_LEDGER_QODER_I18N": "",
            "USAGE_LEDGER_QODER_CACHE": self.cache_dir,
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _ts(self, day):
        return int(datetime(2026, 10, day, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)

    def _write_token_db(self, messages):
        if os.path.exists(self.token_db):
            os.remove(self.token_db)
        create_token_db(self.token_db, messages, {})

    def _write_activity_db(self, session_models, messages=None):
        if os.path.exists(self.activity_db):
            os.remove(self.activity_db)
        os.makedirs(os.path.dirname(self.activity_db), exist_ok=True)
        conn = sqlite3.connect(self.activity_db)
        conn.execute("CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, "
                     "cwd TEXT, model TEXT)")
        for sid, model in session_models.items():
            conn.execute("INSERT INTO chat_sessions VALUES (?,?,?)",
                         (sid, "/tmp/p", model))
        conn.execute(
            "CREATE TABLE chat_session_messages (session_id TEXT, message_id TEXT, "
            "role TEXT, payload_json TEXT, created_at INTEGER, updated_at INTEGER, "
            "turn_credits REAL, turn_credits_request_set_id TEXT)")
        for mid, sid, role, created in (messages or []):
            conn.execute(
                "INSERT INTO chat_session_messages VALUES (?,?,?,?,?,?,?,?)",
                (sid, mid, role, "{}", created, created, 0.0, None))
        conn.commit()
        conn.close()

    def _write_cache(self, name, entries):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(os.path.join(self.cache_dir, name), "w", encoding="utf-8") as fh:
            fh.write("1/0/https://openapi.qoder.sh/x" + json.dumps({"data": entries}))

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_report_shows_learned_display_name_and_filters(self):
        self._write_token_db([
            ("m1", "s1", "assistant", self._ts(1),
             '{"model_key":"qmodel_latest_preview"}',
             '{"prompt_tokens":100,"completion_tokens":10,"cached_tokens":0}'),
        ])
        self._write_activity_db({"s1": "qmodel_latest_preview"})
        self._write_cache("a_0", [{"session_id": "s1",
                                   "model_category": "Qwen4-Max-Preview"}])
        self.run_cli(["backfill"])

        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual({row["model"] for row in rows}, {"Qwen4-Max-Preview"})

        # 用显示名过滤
        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json",
                                     "--model", "Qwen4-Max-Preview"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out))
        # 原始键也能过滤
        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json",
                                     "--model", "qmodel_latest_preview"])
        self.assertTrue(json.loads(out))

    def test_auto_sync_first_appearance_shows_new_name_same_run(self):
        # issue 2：先 backfill（只有 qmodel），之后新模型只在新会话出现并触发自动同步；
        # 本次 report 必须用同步后重新构建的 labels，不能再用旧映射。
        self._write_token_db([
            ("m1", "s1", "assistant", self._ts(1), '{"model_key":"qmodel"}',
             '{"prompt_tokens":100,"completion_tokens":10,"cached_tokens":0}'),
        ])
        self._write_activity_db({"s1": "qmodel"})
        self.run_cli(["backfill"])

        # 新会话 s2 使用 qmodel_latest_preview，计费缓存给出显示名
        self._write_token_db([
            ("m1", "s1", "assistant", self._ts(1), '{"model_key":"qmodel"}',
             '{"prompt_tokens":100,"completion_tokens":10,"cached_tokens":0}'),
            ("m2", "s2", "assistant", self._ts(2),
             '{"model_key":"qmodel_latest_preview"}',
             '{"prompt_tokens":50,"completion_tokens":5,"cached_tokens":0}'),
        ])
        self._write_activity_db({"s1": "qmodel", "s2": "qmodel_latest_preview"})
        self._write_cache("a_0", [{"session_id": "s2",
                                   "model_category": "Qwen4-Max-Preview"}])
        bump = os.stat(self.activity_db).st_mtime_ns + 1_000_000_000
        os.utime(self.activity_db, ns=(bump, bump))

        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json"])
        self.assertEqual(code, 0)
        models = {row["model"] for row in json.loads(out)}
        self.assertIn("Qwen4-Max-Preview", models)
        self.assertNotIn("qmodel_latest_preview", models)

    def test_cache_only_change_learned_without_resync(self):
        # issue 3：缓存出现新映射、活动库 mtime 不变（不触发同步），实时学习仍生效。
        self._write_token_db([
            ("m1", "s1", "assistant", self._ts(1),
             '{"model_key":"qmodel_latest_preview"}',
             '{"prompt_tokens":100,"completion_tokens":10,"cached_tokens":0}'),
        ])
        self._write_activity_db({"s1": "qmodel_latest_preview"})
        # 先不放缓存，backfill 学不到，report 显示原始键
        self.run_cli(["backfill"])
        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json"])
        self.assertEqual({row["model"] for row in json.loads(out)},
                         {"qmodel_latest_preview"})

        mtime = os.stat(self.activity_db).st_mtime_ns
        self._write_cache("a_0", [{"session_id": "s1",
                                   "model_category": "Qwen4-Max-Preview"}])
        code, out, _ = self.run_cli(["report", "--source", "qoder", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual({row["model"] for row in json.loads(out)},
                         {"Qwen4-Max-Preview"})
        # 活动库 mtime 未变，说明没有触发同步，label 来自实时学习
        self.assertEqual(os.stat(self.activity_db).st_mtime_ns, mtime)


if __name__ == "__main__":
    unittest.main()
