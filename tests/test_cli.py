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
        self.assertEqual(payload["totals"]["credits"], 2.5)
        self.assertEqual(payload["totals"]["free_credits"], 1.0)
        self.assertEqual(payload["totals"]["requests"], 2)
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
        self.assertEqual(stateless["totals"]["credits"], 2.5)
        self.assertEqual(stateless["days"][0]["snapshots"], 1)

        shutil.rmtree(os.path.dirname(log_path(self.home)))
        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        store = SqliteStore(self.db_path)
        self.assertEqual(store.credit_count(), 2)
        self.assertEqual(store.quota_count(), 2)
        self.assertEqual(store.est_count(), 2)
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
        self.assertIn("credits: requests=2 quota_snapshots=2 est_rows=2 missing_ratio=0", out)
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


if __name__ == "__main__":
    unittest.main()
