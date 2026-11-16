import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.usage_ledger import __version__, cli, scheduler
from src.usage_ledger.models import (Activity, Counts, Credit, Estimate,
                                     QuotaSnapshot, Record, SourceResult)
from src.usage_ledger.store import SqliteStore
from tests.qoder_helpers import (activity_path, create_activity_db, create_token_db,
                                 log_path, quota_line, token_path, transcript_path,
                                 write_jsonl, write_quota_log)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def capture(func, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = func(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


def make_record(source="claude", day="2026-10-01", model="claude-opus-4",
                project="/tmp/proj-a", session="s1", key=None, input_tokens=10):
    stamp = datetime.fromisoformat(day + "T12:00:00+00:00").timestamp()
    return Record(source=source, day=day, model=model, project=project,
                  session=session, key=key or "%s:%s:%s" % (source, day, session),
                  counts=Counts(input=input_tokens, output=2), ts=stamp)


class SourceHomeFixture(unittest.TestCase):
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
        conn = sqlite3.connect(os.path.join(opencode_dir, "opencode.db"))
        conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, "
                     "time_updated INTEGER, data TEXT)")
        stamp = int(datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
        data = {"role": "assistant", "modelID": "deepseek-v4-flash",
                "providerID": "opencode", "path": {"cwd": "/tmp/proj-c"},
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


class QoderHomeFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.ts1 = int(datetime(2026, 10, 1, 12, 0).timestamp() * 1000)
        self.ts2 = int(datetime(2026, 10, 2, 12, 0).timestamp() * 1000)
        create_token_db(token_path(self.home), [
            ("m1", "s1", "assistant", self.ts1, '{"model_key":"qmodel"}',
             '{"prompt_tokens":1000,"completion_tokens":50,"cached_tokens":800}'),
            ("m2", "s2", "assistant", self.ts2, '{"model_key":"qmodel"}',
             '{"prompt_tokens":100,"completion_tokens":20,"cached_tokens":0}'),
        ], {"s1": {"project_name": "proj-x"}, "s2": {"project_name": "proj-y"}})
        create_activity_db(activity_path(self.home), [
            ("u1", "s1", "user", {}, self.ts1, None),
            ("a1", "s1", "assistant",
             {"parts": [{"type": "tool"}],
              "turnMetrics": {"turnCount": 2, "durationMs": 1000}}, self.ts1, None),
            ("u2", "s2", "user", {}, self.ts2, None),
            ("a2", "s2", "assistant",
             {"parts": [{"type": "tool"}, {"type": "tool"}]}, self.ts2, None),
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


class LiveCommandTest(SourceHomeFixture):
    def test_live_reads_sources_without_db_writes(self):
        code, out, err = run_cli(["live"])
        self.assertEqual(code, 0, err)
        self.assertIn("today:", out)
        self.assertIn("qoder: 本地无 token 数据", out)
        self.assertIn("无 token 真值", out)
        self.assertFalse(os.path.exists(self.db_path))

    def test_live_session_filter_and_watch_loop(self):
        code, out, _ = run_cli(["live", "--source", "claude", "--session", "s1"])
        self.assertEqual(code, 0)
        self.assertIn("s1", out)
        with patch("src.usage_ledger.cli.time.sleep", side_effect=KeyboardInterrupt):
            code, out, _ = run_cli(["live", "--watch", "1"])
        self.assertEqual(code, 0)
        self.assertIn("today:", out)

    def test_live_with_qoder_token_coverage(self):
        create_token_db(token_path(self.home), [
            ("m1", "s1", "assistant", 1700000000000, '{"model_key":"qmodel"}',
             '{"prompt_tokens":5,"completion_tokens":1,"cached_tokens":0}'),
        ], {"s1": {"project_name": "proj"}})
        code, out, err = run_cli(["live", "--source", "qoder"])
        self.assertEqual(code, 0, err)
        self.assertIn("qoder: token 覆盖", out)


class ReportOutputTest(SourceHomeFixture):
    def test_report_formats_and_export(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        code, out, err = run_cli(["report", "--format", "csv"])
        self.assertEqual(code, 0, err)
        header = out.splitlines()[0]
        self.assertEqual(header, "date,source,model,input,output,cache_read,"
                                 "cache_write,reasoning,cost_equiv_usd,cost_source,turns")
        self.assertIn("cost_equiv_usd 为按 API 价折算", err)

        code, out, _ = run_cli(["export"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], header)

        code, out, _ = run_cli(["report", "--weekly", "--format", "csv"])
        self.assertEqual(code, 0)
        self.assertIn("2026-W40", out)

        code, out, _ = run_cli(["report", "--monthly", "--format", "csv"])
        self.assertEqual(code, 0)
        self.assertIn("2026-10", out)

        code, out, _ = run_cli(["report", "--format", "table"])
        self.assertEqual(code, 0)
        self.assertIn("cost_equiv_usd", out)
        self.assertIn("claude-sonnet-4", out)

    def test_report_flags_and_missing_days(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        code, out, err = run_cli([
            "report", "--source", "claude", "--project", "proj-a",
            "--model", "claude-sonnet-4", "--since", "2026-10-01",
            "--until", "2026-10-05", "--group-by", "project,session",
            "--format", "json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertTrue(rows)
        self.assertTrue(all(row["project"] == "proj-a" for row in rows))
        self.assertIn("no data: 2026-10-02", err)

    def test_report_without_db_falls_back_to_sources(self):
        code, out, err = run_cli(["report", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("自动降级为 --stateless", err)
        self.assertTrue(json.loads(out))
        self.assertFalse(os.path.exists(self.db_path))

    def test_report_invalid_inputs(self):
        cases = [
            (["report", "--range", "bad"], "--range"),
            (["report", "--range", "2026-10-02..2026-10-01"], "起始日期"),
            (["report", "--filter", "bad"], "--filter"),
            (["report", "--filter", "nope=1"], "未知过滤字段"),
            (["report", "--group-by", "nope"], "未知分组维度"),
        ]
        for argv, needle in cases:
            code, _, err = run_cli(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(needle, err, argv)

    def test_top_variants(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        code, out, _ = run_cli(["top", "sources", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual({row["source"] for row in json.loads(out)},
                         {"claude", "codex", "opencode"})
        code, out, _ = run_cli(["top", "models", "--limit", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        code, out, _ = run_cli(["top", "projects", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out))
        code, out, _ = run_cli(["top", "sessions", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out))

    def test_pricing_list_known_and_unknown(self):
        code, out, _ = run_cli(["pricing"])
        self.assertEqual(code, 0)
        self.assertIn("->", out)
        code, out, _ = run_cli(["pricing", "claude-opus-4"])
        self.assertEqual(code, 0)
        self.assertIn("normalized:", out)
        code, out, _ = run_cli(["pricing", "definitely-not-a-model"])
        self.assertEqual(code, 0)
        self.assertIn("unknown", out)

    def test_prune_dry_run_then_delete(self):
        store = SqliteStore(self.db_path)
        store.upsert_records([make_record(day="2020-01-01")])
        store.close()
        code, out, _ = run_cli(["prune", "--keep-days", "30", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run: cutoff=", out)
        self.assertIn("candidate=1 deleted=0", out)
        code, out, _ = run_cli(["prune", "--keep-days", "30"])
        self.assertEqual(code, 0)
        self.assertIn("candidate=1 deleted=1", out)
        code, _, err = run_cli(["--stateless", "prune"])
        self.assertEqual(code, 2)
        self.assertIn("不能与 --stateless", err)

    def test_schedule_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            with patch.object(scheduler, "LAUNCH_AGENTS", target), \
                    patch.object(scheduler, "_launchctl",
                                 return_value=SimpleNamespace(returncode=1)):
                code, out, _ = run_cli(["schedule", "status"])
                self.assertEqual(code, 0)
                self.assertIn("installed=False", out)
                self.assertIn("loaded=False", out)
                code, out, _ = run_cli(["schedule", "uninstall"])
                self.assertEqual(code, 0)
                self.assertEqual(out, "")
        code, out, _ = run_cli(["schedule", "install", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run: would write", out)
        self.assertIn("dry-run: 未写入、未加载", out)

    def test_hooks_status_install_and_uninstall_dry_run(self):
        code, out, _ = run_cli(["hooks", "status", "trae-cn"])
        self.assertEqual(code, 0)
        self.assertIn("source: trae-cn", out)
        self.assertIn("hint: usage hooks install", out)
        code, out, _ = run_cli(["hooks", "install", "trae-cn", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("installed:", out)
        self.assertIn("dry-run: 未写入 hooks.json", out)
        code, out, _ = run_cli(["hooks", "uninstall", "trae-cn", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("removed groups: 0", out)
        self.assertIn("dry-run: 未修改 hooks.json", out)

    def test_html_source_qoder_and_error_paths(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        output = os.path.join(self.home, "report.html")
        code, out, err = run_cli(["html", "--source", "qoder", "--offline",
                                  "--output", output])
        self.assertEqual(code, 0, err)
        self.assertIn("wrote ", out)
        self.assertTrue(os.path.getsize(output) > 0)
        missing = os.path.join(self.home, "missing", "report.html")
        code, _, err = run_cli(["html", "--source", "qoder", "--output", missing])
        self.assertEqual(code, 2)
        self.assertIn("输出目录不存在", err)

    def test_html_strict_refresh_without_db_exits_nonzero(self):
        output = os.path.join(self.home, "report.html")
        code, out, err = run_cli(["html", "--source", "trae-cn", "--strict-refresh",
                                  "--output", output])
        self.assertEqual(code, 1, err)
        self.assertIn("refresh failed, using cached data", err)
        self.assertTrue(os.path.exists(output))

    def test_sync_dry_run_paths(self):
        code, out, _ = run_cli(["sync", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("records,", out)
        code, out, err = run_cli(["sync", "--source", "claude", "--remote", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("--remote 仅影响 trae-cn", err)
        code, out, _ = run_cli(["sync", "--source", "trae-cn", "--remote", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("remote plan", out)
        code, _, err = run_cli(["--stateless", "sync"])
        self.assertEqual(code, 2)
        self.assertIn("不能与 --stateless", err)
        code, _, err = run_cli(["sync", "--remote", "--source", "trae-cn",
                                "--since", "2026-10-01", "--full", "--dry-run"])
        self.assertEqual(code, 2)
        self.assertIn("--since 不能与", err)

    def test_version_exits(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("usage-ledger %s" % __version__, out.getvalue())


class QoderOutputTest(QoderHomeFixture):
    def test_activity_stateless_table_and_formats(self):
        code, out, err = run_cli(["activity"])
        self.assertEqual(code, 0, err)
        self.assertIn("date", out)
        self.assertIn("qoder", out)
        self.assertIn("2026-10-01", out)
        self.assertIn("不可相加", err)
        self.assertIn("turnMetrics 覆盖 1/2 assistant", err)
        self.assertIn("Qoder 活动覆盖 2026-10-01 ~ 2026-10-02", err)

        code, out, _ = run_cli(["activity", "--group-by", "month", "--format", "csv"])
        self.assertEqual(code, 0)
        self.assertIn("2026-10", out)

        code, out, _ = run_cli(["activity", "--group-by", "week", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["week"], "2026-W40")

        code, out, _ = run_cli(["activity", "--source", "claude", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

        code, out, _ = run_cli(["activity", "--project", "proj-x",
                                "--since", "2026-10-01", "--until", "2026-10-01",
                                "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 1)

    def test_activity_db_path_after_backfill(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        code, out, err = run_cli(["activity", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(json.loads(out)), 2)
        self.assertNotIn("自动降级", err)

    def test_credits_table_and_trae_stateless(self):
        code, out, err = run_cli(["--stateless", "credits", "--format", "table"])
        self.assertEqual(code, 0, err)
        self.assertIn("credits", out)
        self.assertIn("total qoder: 2.50 credits / 2 requests", out)
        self.assertIn("额度快照 add_on", err)

        code, out, err = run_cli(["--stateless", "credits", "--source", "trae-cn"])
        self.assertEqual(code, 0)
        self.assertIn("SQLite 缓存", err)
        self.assertIn("no credits data in range", err)
        self.assertEqual(out, "")

    def test_credits_table_from_db(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        code, out, err = run_cli(["credits", "--format", "table"])
        self.assertEqual(code, 0, err)
        self.assertIn("snapshots", out)
        self.assertIn("total qoder:", out)

    def test_est_stateless_and_db_formats(self):
        code, out, err = run_cli(["--stateless", "est", "--format", "csv"])
        self.assertEqual(code, 0, err)
        self.assertIn("date,model,est_input,est_output,requests", out)
        self.assertIn("估算覆盖 2 请求", err)

        code, out, _ = run_cli(["--stateless", "est", "--group-by",
                                "project,session", "--format", "table"])
        self.assertEqual(code, 0)
        self.assertIn("project", out)
        self.assertIn("session", out)

        code, out, err = run_cli(["--stateless", "est", "--source", "trae-cn"])
        self.assertEqual(code, 0)
        self.assertIn("Trae CN 弱估算", err)
        self.assertIn("no estimate data in range", err)

        self.assertEqual(run_cli(["backfill"])[0], 0)
        code, out, err = run_cli(["est", "--format", "table"])
        self.assertEqual(code, 0, err)
        self.assertIn("est_input", out)
        self.assertIn("GLM-5.3-Flash", out)

    def test_html_offline_with_db_covers_cached_paths(self):
        self.assertEqual(run_cli(["backfill"])[0], 0)
        output = os.path.join(self.home, "report.html")
        code, out, err = run_cli(["html", "--offline", "--output", output])
        self.assertEqual(code, 0, err)
        self.assertIn("trae-cn.credits: offline cache", err)
        self.assertIn("rows=", out)

    def test_sync_dry_run_reports_activity_and_estimates(self):
        code, out, _ = run_cli(["sync", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("qoder.activity:", out)
        self.assertIn("trae-cn.est:", out)


class HelperTest(unittest.TestCase):
    def test_formatting_helpers(self):
        self.assertEqual(cli._human_size(2048), "2.0 KB")
        self.assertEqual(cli._human_size(2 * 1024 * 1024), "2.0 MB")
        self.assertEqual(cli._fmt_cost(None), "—")
        self.assertEqual(cli._fmt_cost(0.12345), "0.1235")
        self.assertEqual(cli._fmt_int(1234), "1,234")
        self.assertEqual(cli._fmt_duration(1000), "1s")
        self.assertEqual(cli._fmt_duration(61000), "1m 01s")
        self.assertEqual(cli._fmt_duration(3661000), "1h 01m")
        self.assertEqual(cli._fmt_duration(0), "0s")
        with patch("src.usage_ledger.cli.time.time", return_value=1000.0):
            self.assertEqual(cli._ago(970), "30s ago")
            self.assertEqual(cli._ago(880), "2m ago")
            self.assertEqual(cli._ago(1000 - 7200), "2h ago")
            self.assertEqual(cli._ago(1000 - 172800), "2d ago")
            self.assertEqual(cli._ago(2000), "0s ago")

    def test_status_and_parse_helpers(self):
        result = SourceResult("x", available=False)
        self.assertEqual(cli._status(result), "unsupported")
        result = SourceResult("x", available=True, errors=[("p", "e")])
        self.assertEqual(cli._status(result), "error")
        result = SourceResult("x", available=True, complete=False)
        self.assertEqual(cli._status(result), "partial")
        self.assertEqual(cli._status(SourceResult("x")), "ok")

        self.assertEqual(cli.parse_day(" 2026-10-01 "), "2026-10-01")
        self.assertEqual(cli.parse_day("1d"),
                         (date.today() - timedelta(days=1)).isoformat())
        self.assertEqual(cli.parse_day("2w"),
                         (date.today() - timedelta(days=14)).isoformat())
        self.assertEqual(cli.parse_day("1m"),
                         (date.today() - timedelta(days=30)).isoformat())
        with self.assertRaises(ValueError):
            cli.parse_day("soon")
        self.assertEqual(cli.parse_range("2026-10-01..2026-10-02"),
                         ("2026-10-01", "2026-10-02"))
        with self.assertRaises(ValueError):
            cli.parse_range("2026-10-01")
        self.assertEqual(cli.parse_filters("source=qoder, model=m1"),
                         {"source": "qoder", "model": "m1"})
        self.assertEqual(cli.parse_filters(None), {})
        with self.assertRaises(ValueError):
            cli.parse_filters("source")
        with self.assertRaises(ValueError):
            cli.parse_filters("bad=1")
        self.assertEqual(cli.parse_dims(None), cli.DEFAULT_DIMS)
        self.assertEqual(cli.parse_dims("day, model"), ("day", "model"))
        with self.assertRaises(ValueError):
            cli.parse_dims("nope")
        self.assertEqual(cli._parse_activity_dims(None), cli.ACTIVITY_DIMS)
        self.assertEqual(cli._parse_activity_dims("month,project"),
                         ("month", "project"))
        with self.assertRaises(ValueError):
            cli._parse_activity_dims("model")
        self.assertEqual(cli._parse_est_dims(None), ("day", "model"))
        self.assertEqual(cli._parse_est_dims("project"), ("project",))
        with self.assertRaises(ValueError):
            cli._parse_est_dims("source")

        self.assertEqual(cli._period(SimpleNamespace(weekly=False, monthly=False)), "day")
        self.assertEqual(cli._period(SimpleNamespace(weekly=True, monthly=False)), "week")
        self.assertEqual(cli._period(SimpleNamespace(weekly=False, monthly=True)), "month")

    def test_effective_range(self):
        empty = SimpleNamespace(range=None, since=None, until=None)
        self.assertEqual(cli._effective_range(empty), (None, None))
        ranged = SimpleNamespace(range="2026-10-01..2026-10-02", since=None, until=None)
        self.assertEqual(cli._effective_range(ranged), ("2026-10-01", "2026-10-02"))
        explicit = SimpleNamespace(range=None, since="2026-10-03", until="2026-10-04")
        self.assertEqual(cli._effective_range(explicit), ("2026-10-03", "2026-10-04"))
        invalid = SimpleNamespace(range=None, since="2026-10-04", until="2026-10-03")
        with self.assertRaises(ValueError):
            cli._effective_range(invalid)

    def test_activity_helpers(self):
        acts = [Activity(day="2026-10-01", project="", sessions=1, prompts=2,
                         assistant_calls=3, assistant_with_metrics=1, turns=4,
                         tool_calls=5, duration_ms=61000),
                Activity(day="2026-10-31", project="p", sessions=2, prompts=1,
                         assistant_calls=1, assistant_with_metrics=1, turns=1,
                         tool_calls=0, duration_ms=1000)]
        totals = cli._activity_totals(acts)
        self.assertEqual(totals["rows"], 2)
        self.assertEqual(totals["sessions"], 3)
        self.assertEqual(totals["duration_ms"], 62000)
        rows = cli._aggregate_activity(acts, ("day", "week", "month", "source", "project"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["dims"][3], "qoder")
        self.assertEqual(rows[0]["dims"][4], "-")
        self.assertEqual(rows[0]["dims"][1], "2026-W40")
        months = cli._activity_month_summary(acts)
        self.assertEqual(months["2026-10"]["sessions"], 3)
        self.assertEqual(cli._filter_activity(acts, "2026-10-02", None, {}), [acts[1]])
        self.assertEqual(cli._filter_activity(acts, None, None, {"source": "claude"}), [])
        self.assertEqual(cli._filter_activity(acts, None, None, {"project": "p"}),
                         [acts[1]])

        dims = ("day", "source", "project")
        writer_rows = cli._aggregate_activity(acts, dims)
        for fmt in ("json", "csv", "table"):
            _, out, _ = capture(cli._write_activity, writer_rows, dims, fmt)
            self.assertTrue(out)
        _, out, _ = capture(cli._write_activity, [], dims, "table")
        self.assertIn("sessions", out)

    def test_coverage_helpers(self):
        self.assertIsNone(cli._qoder_coverage(stateless=True))
        self.assertIsNone(cli._qoder_coverage_text(None))
        rec = make_record(source="qoder", day="2026-10-01")
        act = Activity(day="2026-10-02")
        coverage = cli._qoder_coverage([rec], [act], stateless=True)
        self.assertEqual(coverage["qoder"]["token_since"], "2026-10-01")
        self.assertEqual(coverage["qoder"]["activity_until"], "2026-10-02")
        text = cli._qoder_coverage_text(coverage)
        self.assertIn("token 覆盖 2026-10-01", text)
        self.assertIn("活动覆盖 2026-10-02", text)
        activity_only = cli._qoder_coverage([], [act], stateless=True)
        self.assertIn("本地无 token 数据", cli._qoder_coverage_text(activity_only))

    def test_qoder_report_notes(self):
        coverage = {"qoder": {"token_since": None, "token_until": None,
                              "activity_since": "2026-10-01",
                              "activity_until": "2026-10-02"}}
        _, _, err = capture(cli._qoder_report_notes, [], coverage, None, None, {})
        self.assertIn("本地无该区间 token 数据", err)
        _, _, err = capture(cli._qoder_report_notes, [], coverage, None, None,
                            {"source": "claude"})
        self.assertNotIn("本地无该区间 token 数据", err)
        _, _, err = capture(cli._qoder_report_notes,
                            [make_record(source="qoder")], coverage, None, None, {})
        self.assertNotIn("本地无该区间 token 数据", err)
        _, _, err = capture(cli._qoder_report_notes, [], coverage, "2026-01-01",
                            "2026-01-02", {})
        self.assertNotIn("本地该区间", err)
        _, _, err = capture(cli._qoder_report_notes, [], None, None, None, {})
        self.assertEqual(err, "")

    def test_footnotes(self):
        _, _, err = capture(cli._footnotes, [], None, None)
        self.assertIn("cost_equiv_usd", err)
        _, _, err = capture(cli._footnotes, [make_record(day="2026-10-01")],
                         "2026-10-01", "2026-10-03")
        self.assertIn("no data: 2026-10-02, 2026-10-03", err)

    def test_credit_aggregation_helpers(self):
        credits = [
            Credit("r1", 1000.0, "2026-10-01", "p", "gfmodel", "s1", 2.5, True),
            Credit("r2", 1001.0, "2026-10-01", "p", "gfmodel", "s1", 1.0, False),
            Credit("r3", 2000.0, "2026-10-02", "p", "m2", "s2", 3.0, True,
                   source="trae-cn"),
        ]
        quota = [QuotaSnapshot("q1", 1000.0, "2026-10-01", "add_on", 2300, 100,
                               2200, "credits", 0.04, None)]
        daily = cli._credit_daily_from_rows(credits, quota, None, None)
        self.assertEqual([row["day"] for row in daily],
                         ["2026-10-01", "2026-10-02"])
        self.assertEqual(daily[0]["credits"], 2.5)
        self.assertEqual(daily[0]["free_credits"], 1.0)
        self.assertEqual(daily[0]["snapshots"], 1)
        self.assertEqual(cli._credit_daily_from_rows(credits, quota,
                                                     "2026-10-02", None)[0]["source"],
                         "trae-cn")
        totals = cli._credit_totals_from_rows(credits, None, None)
        self.assertEqual(totals["qoder"]["requests"], 2)
        self.assertEqual(totals["qoder"]["days"], 1)
        self.assertEqual(totals["qoder"]["models"], 1)
        self.assertEqual(totals["trae-cn"]["credits"], 3.0)
        rows = cli._credit_rows_from_rows(credits, None, None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["source"], "trae-cn")
        self.assertEqual(rows[1]["free_requests"], 0)
        self.assertEqual(cli._credit_source(SimpleNamespace()), "qoder")

        latest = cli._quota_latest_rows([
            quota[0],
            QuotaSnapshot("q2", 2000.0, "2026-10-02", "add_on", 2300, 200,
                          2100, "credits", 0.08, None)])
        self.assertEqual(latest["add_on"]["used"], 200)

        table_rows = [
            {"day": "2026-10-01", "source": "qoder", "credits": 2.5,
             "requests": 1, "free_credits": 1.0, "snapshots": 1},
            {"day": "2026-10-02", "source": "trae-cn", "credits": 3.0,
             "requests": 2, "free_credits": 0.0, "snapshots": 0},
        ]
        table_totals = {"qoder": {"credits": 2.5, "requests": 1, "free_credits": 1.0},
                        "trae-cn": {"credits": 3.0, "requests": 2}}
        _, out, _ = capture(cli._write_credit_rows, table_rows, table_totals,
                            {"add_on": {"used": 100, "total": 2300, "remaining": 2200,
                                        "pct": 0.04, "day": "2026-10-01", "ts": 1000.0}},
                            "table")
        self.assertIn("source: qoder", out)
        self.assertIn("source: trae-cn", out)
        self.assertIn("total trae-cn: 3.00 credits / 2 会话", out)
        _, out, _ = capture(cli._write_credit_rows, table_rows, table_totals, {}, "json")
        self.assertIn('"factor_version"', out)

        _, _, err = capture(cli._print_quota, {})
        self.assertIn("额度快照：无", err)
        _, _, err = capture(cli._print_quota,
                         {"add_on": {"used": 100, "total": 2300, "remaining": 2200,
                                     "pct": 0.04, "day": "2026-10-01", "ts": 1000.0},
                          "user": None})
        self.assertIn("额度快照 add_on", err)

    def test_quota_cross_check(self):
        credits = [Credit("r1", 1500.0, "2026-10-01", "p", "m", "s", 55.0, True),
                   Credit("r2", 1600.0, "2026-10-01", "p", "m", "s", 30.0, True)]
        quota = [QuotaSnapshot("q1", 1000.0, "2026-10-01", "add_on", 2300, 100,
                               2200, "credits", 0.04, None),
                 QuotaSnapshot("q2", 2000.0, "2026-10-01", "add_on", 2300, 160,
                               2140, "credits", 0.07, None)]
        lines = cli._quota_cross_check(credits, quota)
        self.assertEqual(len(lines), 1)
        self.assertIn("疑似漏读", lines[0])
        empty = cli._quota_cross_check(credits, quota[:1])
        self.assertEqual(empty, [])

    def test_estimate_aggregation_helpers(self):
        estimates = [Estimate("r1", 1000.0, "2026-10-01", "", "gfmodel", "s1",
                              100, 10, 400, 40, None),
                     Estimate("r2", 2000.0, "2026-10-02", "p", "trae-model", "s2",
                              50, 5, 200, 20, 0.5, source="trae-cn.est")]
        rows = cli._aggregate_estimates(
            estimates, ("day", "project", "model", "session"), None, None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["project"], "-")
        self.assertEqual(rows[0]["missing_ratio"], 1)
        rows = cli._aggregate_estimates(estimates, ("day",), "2026-10-02", None)
        self.assertEqual(len(rows), 1)
        cli._label_est_rows(rows)
        cli._label_credit_rows([{"source": "", "project": ""}])
        self.assertEqual(cli._empty_est_totals()["requests"], 0)

        for fmt in ("json", "csv", "table"):
            _, out, _ = capture(cli._write_est_rows, rows, ("day",), fmt)
            self.assertTrue(out)
        _, out, _ = capture(cli._write_est_rows, [], ("day",), "table")
        self.assertIn("est_input", out)

    def test_write_rows_all_formats(self):
        rows = [{"dims": ("2026-10-01", "claude", "m"),
                 "input": 10, "output": 2, "cache_read": 0, "cache_write": 0,
                 "reasoning": 0, "cost_equiv_usd": None, "cost_source": "unknown",
                 "turns": 1}]
        dims = ("day", "source", "model")
        for fmt in ("json", "csv", "table"):
            _, out, _ = capture(cli._write_rows, rows, dims, fmt)
            self.assertTrue(out)
        _, out, _ = capture(cli._write_rows, [], dims, "table")
        self.assertIn("cost_equiv_usd", out)

    def test_credit_sources_for_filters(self):
        self.assertEqual(cli._credit_sources_for_filters({}), ["qoder", "trae-cn"])
        self.assertEqual(cli._credit_sources_for_filters({"source": "qoder"}),
                         ["qoder"])
        self.assertEqual(cli._credit_sources_for_filters({"source": "claude"}), [])

    def test_open_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = patch.dict(os.environ, {"USAGE_LEDGER_DB": os.path.join(tmp, "u.db")})
            env.start()
            try:
                self.assertIsNone(cli.open_store(True))
                store = cli.open_store(False)
                self.assertIsInstance(store, SqliteStore)
                store.close()
            finally:
                env.stop()

    def test_source_results_uses_env_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = patch.dict(os.environ, {"USAGE_LEDGER_SOURCE_HOME": tmp})
            env.start()
            try:
                results = cli._source_results(["claude"], skip_qoder_tokens=True)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].name, "claude")
            finally:
                env.stop()


class ModuleEntryTest(unittest.TestCase):
    def test_python_dash_m_version(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, PYTHONPATH=str(root / "src"),
                       USAGE_LEDGER_HOME=home)
            proc = subprocess.run(
                [sys.executable, "-m", "usage_ledger", "--version"],
                cwd=home, env=env, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usage-ledger %s" % __version__, proc.stdout)


if __name__ == "__main__":
    unittest.main()
