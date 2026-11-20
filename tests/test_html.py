import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from src.usage_ledger.cli import main
from src.usage_ledger.html_report import build_payload, render_html
from src.usage_ledger.models import Activity
from tests.qoder_helpers import (activity_path, create_activity_db, create_token_db,
                                 log_path, quota_line, token_path, transcript_path,
                                 write_jsonl, write_quota_log)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
DATA_MARKER = '<script type="application/json" id="data">'


def extract_payload(html):
    blob = html.split(DATA_MARKER, 1)[1].split("</script>", 1)[0]
    return blob, json.loads(blob)


def make_row(day, source, model, project, values):
    fields = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "reasoning": 0}
    fields.update(values)
    total = sum(fields.values())
    return {
        "dims": (day, source, model, project),
        **fields,
        "total": total,
        "turns": 1,
        "cost_equiv_usd": None,
        "cost_source": "unknown",
    }


class HtmlRenderTest(unittest.TestCase):
    def test_payload_escaped_and_offline(self):
        model = "</script><script>alert('x')</script>"
        rows = [make_row("2026-10-01", "claude", model, "proj", {"input": 10, "output": 2})]
        payload = build_payload(rows, ("day", "source", "model", "project"),
                                "2026-10-01", "2026-10-01", ["notice </script>"])
        html = render_html(payload)

        self.assertTrue(html.startswith("<!doctype html>"))
        blob, parsed = extract_payload(html)
        self.assertNotIn("<", blob)
        self.assertEqual(parsed["rows"][0]["model"], model)
        self.assertEqual(parsed["notices"], ["notice </script>"])
        self.assertEqual(parsed["rows"][0]["total"], 12)
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))

    def test_empty_payload_renders(self):
        payload = build_payload([], ("day", "source", "model", "project"), None, None, [])
        html = render_html(payload)
        _, parsed = extract_payload(html)
        self.assertEqual(parsed["rows"], [])
        self.assertEqual(parsed["activity"], [])
        self.assertEqual(parsed["coverage"], {})
        self.assertIsNone(parsed["range"]["since"])

    def test_codearts_is_classified_as_token(self):
        payload = build_payload([], ("day", "source", "model", "project"), None, None, [])
        self.assertEqual(payload["agents"]["codearts"], "token")

    def test_payload_activity_normalized_as_qoder(self):
        activity = [Activity(day="2026-10-30", project="proj", sessions=2, prompts=3,
                             assistant_calls=3, assistant_with_metrics=2, turns=5,
                             tool_calls=7, duration_ms=1000)]
        coverage = {"qoder": {"token_since": "2026-06-01", "token_until": "2026-09-16",
                              "activity_since": "2026-06-01",
                              "activity_until": "2026-10-30"}}
        payload = build_payload([], ("day", "source", "model", "project"),
                                None, None, [], activity=activity, coverage=coverage)
        self.assertEqual(payload["activity"][0]["source"], "qoder")
        self.assertEqual(payload["activity"][0]["project"], "proj")
        self.assertEqual(payload["activity"][0]["tool_calls"], 7)
        self.assertEqual(payload["coverage"], coverage)

    def test_minimax_is_classified_as_token(self):
        payload = build_payload([], ("day", "source", "model", "project"), None, None, [])
        self.assertEqual(payload["agents"]["minimax"], "token")
        html = render_html(payload)
        self.assertIn("MiniMax", html)

    def test_codebuddy_is_classified_as_token(self):
        payload = build_payload([], ("day", "source", "model", "project"), None, None, [])
        self.assertEqual(payload["agents"]["codebuddy"], "token")
        html = render_html(payload)
        self.assertIn("CodeBuddy", html)


class AgentSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = build_payload([], ("day", "source", "model", "project"), None, None, [])
        cls.html = render_html(payload)

    def test_chip_click_semantics_present(self):
        self.assertIn("单击只看", self.html)
        self.assertIn("再次单击恢复全部", self.html)
        self.assertIn("event.metaKey || event.ctrlKey || event.shiftKey", self.html)
        self.assertIn("function resolveAgentSelection", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_resolve_agent_selection_behavior(self):
        start = self.html.index("function resolveAgentSelection")
        end = self.html.index("function applyAgentSelection", start)
        source = self.html[start:end]
        harness = """
const AGENTS = ["a", "b", "c"];
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("普通点击只看", resolveAgentSelection(["a", "b", "c"], "b", false), ["b"]);
eq("再次点击恢复全部", resolveAgentSelection(["b"], "b", false), ["a", "b", "c"]);
eq("从子集普通点击", resolveAgentSelection(["a", "b"], "b", false), ["b"]);
eq("修饰键增加", resolveAgentSelection(["a"], "b", true), ["a", "b"]);
eq("修饰键移除", resolveAgentSelection(["a", "b"], "a", true), ["b"]);
eq("修饰键保留最后一个", resolveAgentSelection(["a"], "a", true), ["a"]);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class SourceAwareCreditsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.credit_rows = [
            {"day": "2026-10-30", "source": "qoder", "model": "qmodel",
             "project": "p", "credits": 2.0, "free_credits": 1.0,
             "requests": 1, "free_requests": 1},
            {"day": "2026-10-30", "source": "trae-cn", "model": "tmodel",
             "project": "-", "credits": 3.0, "free_credits": 0.0,
             "requests": 2, "free_requests": 0},
        ]
        payload = build_payload(
            [], ("day", "source", "model", "project"), "2026-10-30", "2026-10-30",
            [], credit_rows=cls.credit_rows,
            credits={"days": cls.credit_rows, "rows": cls.credit_rows,
                     "totals": {"qoder": {"credits": 2.0},
                                "trae-cn": {"credits": 3.0}}},
            coverage={"trae-cn.credits": {
                "available": True, "last_sync_at": "2026-10-30T12:00:00+08:00",
                "last_attempt_at": "2026-10-30T12:00:00+08:00",
                "sessions": 2, "status": "ok", "refresh_mode": "auto",
                "refresh_error": None, "stale": False}},
            trae_est_rows=[{"day": "2026-10-30", "model": "tmodel", "project": "-",
                            "est_input": 100, "est_output": 10, "requests": 2,
                            "chars_in": 1000, "chars_out": 100,
                            "missing_ratio": 0}])
        cls.html = render_html(payload)
        cls.payload = payload

    def test_trae_is_classified_as_credits(self):
        self.assertEqual(self.payload["agents"]["trae-cn"], "credits")
        self.assertEqual(self.payload["agents"]["qoder"], "credits")
        self.assertIn("精确 Credits", self.html)
        self.assertIn('id="trae-status"', self.html)

    def test_credit_rows_keep_source(self):
        self.assertEqual([row["source"] for row in self.payload["credits"]["rows"]],
                         ["qoder", "trae-cn"])
        self.assertEqual(self.payload["coverage"]["trae-cn.credits"]["refresh_mode"],
                         "auto")
        self.assertIn("估算请求", self.html)
        self.assertNotIn("est 请求", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_estimate_only_rows_not_ranked_as_zero_credit(self):
        top_start = self.html.index("function topValue(")
        text_start = self.html.index("function topValueText", top_start)
        filter_start = self.html.index("function filterTopItems", text_start)
        filter_end = self.html.index("function topSecondary", filter_start)
        source = self.html[top_start:text_start] + self.html[filter_start:filter_end]
        harness = """
var items = [
  { key: "estimate-only", credits: 0, est: 2242 },
  { key: "with-credits", credits: 1.5, est: 111 }
];
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("zero credits hidden", filterTopItems(items, "credits").map(function (item) {
  return item.key;
}), ["with-credits"]);
eq("est ranking keeps all", filterTopItems(items, "est").map(function (item) {
  return item.key;
}), ["estimate-only", "with-credits"]);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_credit_filters_respect_selected_agent(self):
        start = self.html.index("function creditRowsFor")
        end = self.html.index("function dimensionRows", start)
        source = self.html[start:end]
        harness = """
var state = { agents: new Set(["trae-cn"]), shadow: true };
var CREDIT_ROWS = [{ source: "qoder" }, { source: "trae-cn" }];
var EST = [{ source: "qoder" }];
var TRAE_EST = [{ source: "trae-cn" }];
function hasCreditsSelected() { return true; }
function hasQoderShadowSelected() {
  return state.shadow && state.agents.has("qoder") && EST.length > 0;
}
function hasTraeEstimateSelected() {
  return state.shadow && state.agents.has("trae-cn") && TRAE_EST.length > 0;
}
function matchesFilters() { return true; }
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("credits only selected source", creditRowsFor().map(function (row) {
  return row.source;
}), ["trae-cn"]);
eq("qoder shadow hidden", qoderEstRowsFor().length, 0);
eq("trae estimate visible", traeRowsFor().length, 1);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TraeStatusCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = build_payload([], ("day", "source", "model", "project"),
                                None, None, [])
        cls.html = render_html(payload)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_refresh_failure_wording_matches_cache_state(self):
        start = self.html.index("function traeUnavailableWord")
        end = self.html.index("function emptyActivityTotals", start)
        source = self.html[start:end]
        harness = """
var COVERAGE = {};
var state = {agents: new Set(["trae-cn"])};
var classes = [];
var node = { className: "", hidden: true, textContent: "",
  classList: { add: function (name) { classes.push(name); } } };
var el = { traeStatus: node };
function fmtDateTime(value) { return value || "—"; }
function fmtInt(value) { return String(value); }
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
COVERAGE["trae-cn.credits"] = {
  refresh_error: "API 认证失败（HTTP 401）", available: false,
  last_sync_at: null, sessions: 0, stale: true, refresh_mode: "auto" };
eq("failure word", traeUnavailableWord(), "刷新失败");
renderTraeStatus();
eq("no cache", node.textContent.indexOf("暂无缓存数据") >= 0, true);
eq("no cache never claims cache", node.textContent.indexOf("当前为缓存数据"), -1);
eq("no placeholder time", node.textContent.indexOf("—"), -1);
eq("error style", classes.indexOf("error") >= 0, true);

classes = [];
COVERAGE["trae-cn.credits"] = {
  refresh_error: "HTTP 500", available: true,
  last_sync_at: "2026-10-30T12:00:00+08:00", sessions: 2,
  stale: true, refresh_mode: "auto" };
renderTraeStatus();
eq("cached failure", node.textContent.indexOf("当前为缓存数据") >= 0, true);
eq("cached never claims empty", node.textContent.indexOf("暂无缓存数据"), -1);
eq("cached keeps sync time", node.textContent.indexOf("2026-10-30T12:00:00+08:00") >= 0, true);

COVERAGE["trae-cn.credits"].refresh_error = null;
eq("plain sync word", traeUnavailableWord(), "未同步");
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class HtmlCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        shutil.copytree(os.path.join(FIXTURES, "claude", "projects"),
                        os.path.join(self.home, ".claude", "projects"))
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": os.path.join(self.home, "missing.db"),
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

    def test_html_command_writes_interactive_page(self):
        output = os.path.join(self.home, "report.html")
        code, out, err = self.run_cli(["--stateless", "html", "--output", output])
        self.assertEqual(code, 0, err)
        self.assertIn(output, out)

        with open(output, encoding="utf-8") as fh:
            html = fh.read()
        _, payload = extract_payload(html)
        rows = payload["rows"]
        self.assertTrue(rows)
        self.assertEqual(sum(row["input"] for row in rows), 110)
        self.assertEqual(sum(row["output"] for row in rows), 25)
        self.assertEqual(payload["range"]["since"], min(row["day"] for row in rows))
        self.assertEqual(payload["range"]["until"], max(row["day"] for row in rows))
        self.assertTrue(any("Trae" in notice for notice in payload["notices"]))
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("点击筛选 / 再点取消", html)
        self.assertIn('id="agent-nav"', html)

    def test_html_empty_source_generates_page(self):
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        output = os.path.join(self.home, "empty.html")
        with patch.dict(os.environ, {"USAGE_LEDGER_SOURCE_HOME": empty.name}):
            code, out, err = self.run_cli(["--stateless", "html", "--output", output])
        self.assertEqual(code, 0, err)
        with open(output, encoding="utf-8") as fh:
            _, payload = extract_payload(fh.read())
        self.assertEqual(payload["rows"], [])

    def test_html_rejects_missing_output_dir(self):
        output = os.path.join(self.home, "no-such-dir", "report.html")
        code, _, err = self.run_cli(["--stateless", "html", "--output", output])
        self.assertEqual(code, 2)
        self.assertIn("输出目录不存在", err)

    def test_html_rejects_inverted_range(self):
        output = os.path.join(self.home, "report.html")
        code, _, err = self.run_cli(["--stateless", "html", "--range",
                                     "2026-10-10..2026-10-01", "--output", output])
        self.assertEqual(code, 2)
        self.assertIn("晚于", err)


class QoderHtmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        ts1 = int(datetime(2026, 10, 1, 12, 0).timestamp() * 1000)
        ts2 = int(datetime(2026, 10, 2, 12, 0).timestamp() * 1000)
        create_token_db(token_path(self.home), [
            ("m1", "s1", "assistant", ts1, '{"model_key":"qmodel"}',
             '{"prompt_tokens":1000,"completion_tokens":50,"cached_tokens":800}'),
            ("m2", "s2", "assistant", ts2, '{"model_key":"qmodel"}',
             '{"prompt_tokens":100,"completion_tokens":20}'),
        ], {"s1": {"project_name": "proj-x"}, "s2": {"project_name": "proj-y"}})
        create_activity_db(activity_path(self.home), [
            ("u1", "s1", "user", {}, ts1, None),
            ("a1", "s1", "assistant", {"parts": [{"type": "tool"}],
                                       "turnMetrics": {"turnCount": 2, "durationMs": 1000}},
             ts1, None),
            ("u2", "s2", "user", {}, ts2, None),
            ("a2", "s2", "assistant", {"parts": [{"type": "tool"}]}, ts2, None),
        ], {"s1": "/tmp/proj-x", "s2": "/tmp/proj-y"})
        self.credit_iso = datetime(2026, 10, 1, 12, 5).isoformat()
        self.credit_iso2 = datetime(2026, 10, 1, 12, 5, 5).isoformat()
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
        ])
        write_quota_log(log_path(self.home), [
            quota_line(self.credit_iso2, "q1", used=100, remaining=2200, pct=0.04),
        ])
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_DB": os.path.join(self.home, "usage.db"),
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

    def test_html_contains_activity_and_coverage(self):
        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        output = os.path.join(self.home, "qoder.html")
        code, _, err = self.run_cli(["html", "--source", "qoder", "--output", output])
        self.assertEqual(code, 0, err)
        with open(output, encoding="utf-8") as fh:
            html = fh.read()
        _, payload = extract_payload(html)
        self.assertTrue(payload["rows"])
        self.assertTrue(all(row["source"] == "qoder" for row in payload["rows"]))
        self.assertEqual({row["model"] for row in payload["rows"]}, {"Qwen3.7-Plus"})
        self.assertEqual(len(payload["activity"]), 2)
        self.assertTrue(all(row["source"] == "qoder" for row in payload["activity"]))
        self.assertEqual(payload["coverage"]["qoder"]["token_until"], "2026-10-02")
        self.assertEqual(payload["coverage"]["qoder"]["activity_until"], "2026-10-02")
        self.assertEqual(payload["agents"]["qoder"], "credits")
        self.assertTrue(payload["credits"]["rows"])
        self.assertEqual({row["model"] for row in payload["credits"]["rows"]},
                         {"GLM-5.3-Flash"})
        self.assertIn("补充：活动指标", html)
        self.assertIn('id="shadow-switch"', html)
        self.assertIn('id="panel-credits"', html)
        self.assertIn('id="panel-est"', html)
        self.assertIn("精确 Credits", html)
        self.assertIn("不可相加", html)
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))

        code, _, _ = self.run_cli(["html", "--source", "claude", "--output", output])
        self.assertEqual(code, 0)
        with open(output, encoding="utf-8") as fh:
            _, payload = extract_payload(fh.read())
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["activity"], [])
        self.assertEqual(payload["credits"]["days"], [])
        self.assertEqual(payload["est"]["rows"], [])

    def test_html_contains_credits_and_estimates(self):
        self.assertEqual(self.run_cli(["backfill"])[0], 0)
        output = os.path.join(self.home, "credits.html")
        code, _, err = self.run_cli(["html", "--source", "qoder", "--output", output])
        self.assertEqual(code, 0, err)
        with open(output, encoding="utf-8") as fh:
            html = fh.read()
        _, payload = extract_payload(html)
        self.assertEqual(len(payload["credits"]["days"]), 1)
        day = payload["credits"]["days"][0]
        self.assertEqual((day["day"], day["credits"], day["requests"],
                          day["free_credits"], day["snapshots"]),
                         ("2026-10-01", 2.5, 1, 0.0, 1))
        self.assertEqual(payload["credits"]["totals"]["qoder"]["credits"], 2.5)
        self.assertEqual(payload["credits"]["quota"]["add_on"]["used"], 100)
        self.assertEqual(payload["est"]["factor_version"], "v1")
        self.assertEqual(len(payload["est"]["rows"]), 1)
        est = payload["est"]["rows"][0]
        self.assertEqual((est["day"], est["model"], est["est_input"],
                          est["est_output"], est["requests"]),
                         ("2026-10-01", "GLM-5.3-Flash", 50_000, 1, 1))
        self.assertEqual(est["project"], "proj-x")
        self.assertEqual(payload["est"]["totals"]["requests"], 1)
        self.assertIn("区间 credits", html)
        self.assertIn("billable 请求", html)
        self.assertIn("最新额度余额", html)
        self.assertIn("Credits 按 Agent 分列", html)
        self.assertIn("不可与 token 真值或额度相加", html)
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))


def extract_js(html, start_marker, end_marker):
    start = html.index(start_marker)
    end = html.index(end_marker, start)
    return html[start:end]


class HtmlDateRangeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_default_range_is_last_seven_days(self):
        source = extract_js(self.html, "function parseDay", "function setAttrs")
        harness = r"""
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var r = defaultDateRange("2026-06-01", "2026-11-15", "2026-11-16");
eq("default start", r.start, "2026-11-09");
eq("default end", r.end, "2026-11-15");
r = defaultDateRange("2026-11-12", "2026-11-15", "2026-11-16");
eq("clamp to since", r.start, "2026-11-12");
r = defaultDateRange("", "", "2026-11-16");
eq("empty fallback start", r.start, "2026-11-10");
eq("empty fallback end", r.end, "2026-11-16");
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_presets_anchor_to_data_until(self):
        source = extract_js(self.html, "function parseDay", "function setAttrs")
        harness = r"""
%s
var number = function (value) { var n = Number(value); return isFinite(n) ? n : 0; };
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
function check(name, kind, days, expectedStart, expectedEnd) {
  var r = presetDateRange(kind, days, "2026-06-01", "2026-11-15", "2026-11-16");
  eq(name + " start", r.start, expectedStart);
  eq(name + " end", r.end, expectedEnd);
}
check("latest", "latest", 0, "2026-11-15", "2026-11-15");
check("all", "all", 0, "2026-06-01", "2026-11-15");
check("7d", "days", 7, "2026-11-09", "2026-11-15");
check("30d", "days", 30, "2026-10-17", "2026-11-15");
var clamped = clampDateRange("2026-11-16", "2026-11-20", "2026-06-01", "2026-11-15", "2026-11-16");
eq("future start clamped", clamped.start, "2026-11-15");
eq("future end clamped", clamped.end, "2026-11-15");
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_html_shows_data_until_and_latest_preset(self):
        self.assertIn("最新", self.html)
        self.assertIn("数据截至", self.html)
        self.assertIn("function defaultDateRange", self.html)
        self.assertIn("data-until", self.html)


class HtmlEmptyStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_empty_state_decision(self):
        source = extract_js(self.html, "function shouldShowEmptyState",
                            "function renderTraeCreditKpis")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("all empty", shouldShowEmptyState({token: 0, credit: 0, est: 0, activity: 0}), true);
eq("token present", shouldShowEmptyState({token: 1, credit: 0, est: 0, activity: 0}), false);
eq("activity present", shouldShowEmptyState({token: 0, credit: 0, est: 0, activity: 1}), false);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_trae_kpi_distinguishes_out_of_range_from_unsynced(self):
        source = extract_js(self.html, "function shouldShowEmptyState",
                            "function renderTraeCreditKpis")
        harness = r"""
%s
function fmtInt(value) { return String(value); }
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var st = traeCreditState([], [{day: "2026-10-01"}], {available: true, refresh_error: null});
eq("out of range label", st.label, "当前区间无 Trae credits");
st = traeCreditState([], [], {available: false, refresh_error: null});
eq("unsynced label", st.label, "未同步");
st = traeCreditState([], [], {available: false, refresh_error: "HTTP 401"});
eq("refresh failure label", st.label, "刷新失败");
st = traeCreditState([], [], {available: true, refresh_error: null});
eq("no data label", st.label, "无 credits 数据");
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_empty_state_markup(self):
        self.assertIn('id="empty-state"', self.html)
        self.assertIn('id="empty-quota"', self.html)
        self.assertIn("与区间无关", self.html)
        self.assertIn("当前区间无数据", self.html)


class HtmlActivityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_activity_chart_uses_full_date_buckets(self):
        source = extract_js(self.html, "function parseDay", "function setAttrs")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var rows = [
  {day: "2026-07-09", tool_calls: 1},
  {day: "2026-08-22", tool_calls: 2}
];
var buckets = activityBuckets(rows, "2026-07-01", "2026-08-31", ["tool_calls"]);
eq("bucket count", buckets.length, 62);
eq("first day", buckets[0].key, "2026-07-01");
function value(day) {
  var found = buckets.filter(function (bucket) { return bucket.key === day; });
  return found.length ? found[0].values.tool_calls : null;
}
eq("gap is zero", value("2026-07-10"), 0);
eq("july value", value("2026-07-09"), 1);
eq("august value", value("2026-08-22"), 2);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_activity_table_sort_updates_aria_sort(self):
        source = extract_js(self.html, "function sortRows", "function renderDataTable")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var rows = [
  {day: "2026-07-09", tool_calls: 1},
  {day: "2026-07-10", tool_calls: 3},
  {day: "2026-07-08", tool_calls: 2}
];
var sorted = sortRows(rows, "tool_calls", "desc", {tool_calls: true});
eq("numeric desc", sorted.map(function (row) { return row.tool_calls; }), [3, 2, 1]);
sorted = sortRows(rows, "day", "asc", {});
eq("text asc", sorted.map(function (row) { return row.day; }),
   ["2026-07-08", "2026-07-09", "2026-07-10"]);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("aria-sort", self.html)
        self.assertIn("activitySortKey", self.html)


class HtmlFilterLinkageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_dimension_rows_follow_range_and_search(self):
        source = extract_js(self.html, "function groupTotals", "function pageMetric")
        harness = r"""
var state = {agents: new Set(["claude"]), start: "2026-11-09", end: "2026-11-15",
             model: "", project: "", q: ""};
var TOKEN_ROWS = [
  {day: "2026-11-10", source: "claude", model: "m1", project: "p1", total: 10, turns: 1},
  {day: "2026-10-01", source: "claude", model: "m2", project: "p2", total: 20, turns: 1}
];
var CREDIT_ROWS = [];
var EST = [];
var TRAE_EST = [];
function hasCreditsSelected() { return false; }
function hasQoderShadowSelected() { return false; }
function hasTraeEstimateSelected() { return false; }
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
function keys(rows, key) {
  return groupTotals(rows, key).map(function (item) { return item.key; });
}
eq("date range", keys(dimensionRows("model"), "model"), ["m1"]);
state.q = "m1";
eq("search", keys(dimensionRows("model"), "model"), ["m1"]);
state.q = "";
state.project = "p1";
eq("project filters models", keys(dimensionRows("model"), "model"), ["m1"]);
state.project = "";
state.model = "m1";
eq("model filters projects", keys(dimensionRows("project"), "project"), ["p1"]);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_agent_chip_totals_follow_range(self):
        source = extract_js(self.html, "function navTotal", "function addKpiTo")
        harness = r"""
var state = {start: "2026-11-09", end: "2026-11-15", model: "", project: "", q: "",
             agents: new Set(["claude", "codex"])};
var TOKEN_ROWS = [
  {day: "2026-11-10", source: "claude", total: 10},
  {day: "2026-10-01", source: "claude", total: 20},
  {day: "2026-11-10", source: "codex", total: 30}
];
var CREDIT_ROWS = [];
var TRAE_EST = [];
function matchesFilters(row) { return row.day >= state.start && row.day <= state.end; }
function agentKind(name) { return name === "qoder" || name === "trae-cn" ? "credits" : "token"; }
function fmtCompact(value) { return String(value); }
function fmtInt(value) { return String(value); }
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function sumField(rows, field) {
  return rows.reduce(function (acc, row) { return acc + number(row[field]); }, 0);
}
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("claude range total", navTotal("claude"), 10);
eq("codex range total", navTotal("codex"), 30);
eq("out of range excluded", navTotal("trae-cn"), 0);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_select_all_preserves_other_filters(self):
        source = extract_js(self.html, "function applyAgentSelection",
                            "function buildAgentFilter")
        harness = r"""
var AGENTS = ["claude", "codex"];
var state = {agents: new Set(["claude"]), model: "m1", project: "p1", q: "x", page: 2};
function rebuildDimensionSelects() {}
function syncAgentFilter() {}
function renderAll() {}
function refreshFocusAfterFilterChange() {}
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
applyAgentSelection(["claude", "codex"]);
eq("agents", Array.from(state.agents).join(","), "claude,codex");
eq("model kept", state.model, "m1");
eq("project kept", state.project, "p1");
eq("search kept", state.q, "x");
eq("page reset", state.page, 0);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("applyAgentSelection(AGENTS.slice())", self.html)


class HtmlTableLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_table_keeps_identity_columns_and_groups(self):
        source = extract_js(self.html, "var STICKY_WIDTHS", "function renderDataTable")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var columns = [
  {key: "day", identity: true},
  {key: "source", identity: true},
  {key: "model", identity: true},
  {key: "project", identity: true},
  {key: "input", group: "Token"},
  {key: "output", group: "Token"},
  {key: "credits", group: "Credits"}
];
var groups = groupHeader(columns);
eq("groups", groups.map(function (g) { return g.identity ? g.identity.key : g.label + ":" + g.span; }),
   ["day", "source", "model", "project", "Token:2", "Credits:1"]);
var sticky = stickyLayout(columns);
eq("day left", sticky.left.day, 0);
eq("source left", sticky.left.source, 96);
eq("model left", sticky.left.model, 186);
eq("project left", sticky.left.project, 356);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('id="detail-table"', self.html)
        self.assertIn('id="colgroup"', self.html)
        self.assertIn('id="tfoot"', self.html)
        self.assertIn("sticky-wide", self.html)
        self.assertIn("group-head", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_table_fills_available_width_without_moving_identity_columns(self):
        source = extract_js(self.html, "var STICKY_WIDTHS", "function renderDataTable")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var columns = [
  {key: "day", identity: true},
  {key: "source", identity: true},
  {key: "credits", type: "num"},
  {key: "sessions", type: "num"}
];
var wide = tableColumnWidths(columns, 1200);
eq("wide total", wide.total, 1200);
eq("day fixed", wide.widths[0], 96);
eq("source fixed", wide.widths[1], 90);
eq("data fills", wide.widths[2] + wide.widths[3], 1200 - 186);
eq("data balanced", wide.widths[2] - wide.widths[3] <= 1, true);
var narrow = tableColumnWidths(columns, 300);
eq("narrow total", narrow.total, 334);
eq("narrow day", narrow.widths[0], 96);
eq("narrow credits", narrow.widths[2], 74);
var fixedOnly = tableColumnWidths([{key: "day", identity: true}], 1200);
eq("fixed only", fixedOnly.total, 96);
eq("zero available", tableColumnWidths(columns, 0).total, 334);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("tableColumnWidths(columns,", self.html)
        self.assertIn("tableWrap: el.tableWrap", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_table_totals_are_unit_scoped_and_empty_columns_hidden(self):
        source = extract_js(self.html, "var STICKY_WIDTHS", "function renderDataTable")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function sourceLabel(source) { return source === "trae-cn" ? "Trae CN" : source === "qoder" ? "Qoder" : source; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var columns = [
  {key: "day", identity: true},
  {key: "source", identity: true},
  {key: "input", unit: "token", type: "num", group: "Token"},
  {key: "credits", unit: "credit", type: "num", group: "Credits"},
  {key: "free_credits", unit: "credit", type: "num", source: "qoder", group: "Credits"},
  {key: "credit_sessions", unit: "credit", type: "num", source: "trae-cn",
   group: "Credits"},
  {key: "est_total", unit: "est", type: "num", group: "估算"}
];
var rows = [
  {day: "2026-11-10", source: "claude", unit: "token", input: 10},
  {day: "2026-11-10", source: "qoder", unit: "credit", credits: 2, free_credits: 0},
  {day: "2026-11-10", source: "trae-cn", unit: "credit", credits: 3,
   free_credits: null, credit_sessions: 4},
  {day: "2026-11-10", source: "trae-cn", unit: "est", est_total: 5}
];
var kept = pruneColumns(columns, rows).map(function (c) { return c.key; });
eq("zero column hidden", kept.indexOf("free_credits"), -1);
eq("non-empty kept", kept.indexOf("credits") >= 0, true);
var totals = tableTotals(rows, columns, new Set(["token", "credit", "est"]),
                         ["qoder", "trae-cn"]);
eq("totals labels", totals.map(function (t) { return t.label; }),
   ["Token 合计", "Qoder credits 合计", "Trae CN credits 合计", "Trae 弱估算合计"]);
eq("token total", totals[0].values.input, 10);
eq("qoder credits", totals[1].values.credits, 2);
eq("trae credits", totals[2].values.credits, 3);
eq("est total", totals[3].values.est_total, 5);
var freeCol = columns.find(function (c) { return c.key === "free_credits"; });
var sessionCol = columns.find(function (c) { return c.key === "credit_sessions"; });
eq("qoder free", totalCellValue(freeCol, totals[1]), 0);
eq("qoder sessions dash", totalCellValue(sessionCol, totals[1]), null);
eq("trae sessions", totalCellValue(sessionCol, totals[2]), 4);
eq("trae free dash", totalCellValue(freeCol, totals[2]), null);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_table_pagination_page_size_and_jump(self):
        source = extract_js(self.html, "function paginateRows", "function tableTotals")
        harness = r"""
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var rows = [];
for (var i = 0; i < 51; i += 1) rows.push(i);
var p = paginateRows(rows, 1, 25);
eq("pages", p.pages, 3);
eq("page", p.page, 1);
eq("start", p.start, 25);
eq("slice", p.slice.length, 25);
eq("clamped", paginateRows(rows, 999, 25).page, 2);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('id="page-size"', self.html)
        self.assertIn('id="page-jump"', self.html)


class HtmlKpiLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    def test_kpi_groups_have_single_primary_and_no_ellipsis(self):
        self.assertIn("function addKpiGroup", self.html)
        self.assertIn("function addKpiNoData", self.html)
        self.assertIn("kpi-group-title", self.html)
        self.assertIn("kpi-grid", self.html)
        self.assertIn("grid-template-columns:repeat(4", self.html)
        self.assertIn("overflow-wrap:anywhere", self.html)
        self.assertNotIn("grid-column:span 2", self.html)
        self.assertNotIn('className = "kpi primary quota-kpi"', self.html)
        self.assertIn('card.className = "kpi quota-kpi"', self.html)


class HtmlCreditParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        credit_rows = [
            {"day": "2026-11-14", "source": "qoder", "model": "dfmodel",
             "project": "playground", "credits": 10.0, "free_credits": 1.0,
             "requests": 4, "free_requests": 1},
            {"day": "2026-11-14", "source": "trae-cn", "model": "GLM-5.3-Flash",
             "project": "-", "credits": 20.0, "free_credits": 0.0,
             "requests": 2, "free_requests": 0},
        ]
        trae_est = [
            {"day": "2026-11-14", "model": "trae-cn", "project": "-",
             "est_input": 100, "est_output": 10, "requests": 2},
        ]
        quota = {"add_on": {"day": "2026-11-16", "total": 2700, "used": 160,
                            "remaining": 2540, "pct": 0.06}}
        cls.payload = build_payload(
            [], ("day", "source", "model", "project"), None, None, [],
            credits={"quota": quota}, credit_rows=credit_rows,
            quota=quota, trae_est_rows=trae_est,
            coverage={"trae-cn.credits": {"available": True, "refresh_mode": "auto"}})
        cls.html = render_html(cls.payload)

    def test_credit_kpis_share_one_four_card_structure(self):
        self.assertIn("function renderCreditKpisForSource", self.html)
        for label in ("区间 credits", "免费 credits", "区间日均", "最新额度余额"):
            self.assertIn(label, self.html)
        self.assertIn("Trae API 不返回免费额度", self.html)
        self.assertIn("Trae CN 不提供额度快照", self.html)
        self.assertNotIn('addKpiTo(host, "会话数"', self.html)
        self.assertNotIn('addKpiTo(host, "覆盖天数"', self.html)
        self.assertNotIn('addKpiTo(host, "模型数"', self.html)
        self.assertIn('aria-label="显示估算"', self.html)
        self.assertIn('id="shadow-label"', self.html)
        self.assertIn("Trae 弱估算未计入", self.html)
        self.assertIn('state.shadow && state.agents.has("qoder")', self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_credit_kpi_cards_match_for_qoder_and_trae(self):
        source = extract_js(self.html, "function traeCreditDataState",
                            "function renderQoderCreditKpis")
        harness = r"""
var COVERAGE = {"trae-cn.credits": {available: true, refresh_mode: "auto"}};
var CREDIT_ROWS = [];
var QUOTA = {add_on: {day: "2026-11-16", total: 2700, used: 160,
                      remaining: 2540, pct: 0.06}};
var cards = [];
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
function fmtCredits(value) { return String(value); }
function fmtInt(value) { return String(value); }
function fmtQuota(value) { return String(value); }
function fmtDateTime(value) { return value || "—"; }
function pct(value) { return String(value); }
function quotaSummary() { return QUOTA.add_on; }
function addKpiTo(host, label, value, sub, primary, cls) {
  cards.push({label: label, value: value, sub: sub, primary: !!primary});
}
function addKpiNoData(host, label, sub, primary) {
  cards.push({label: label, value: "—", sub: sub, primary: !!primary});
}
function addQuotaKpi(host, quota, source) {
  cards.push({label: "最新额度余额", value: quota ? "2540" : "—",
              sub: source === "trae-cn" ? "Trae CN 不提供额度快照" : "本地日志无额度快照",
              primary: false});
}
function traeCreditState() { return {label: "无数据", sub: ""}; }
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var qoder = [{day: "2026-11-14", model: "dfmodel", credits: 10,
              free_credits: 1, requests: 4, free_requests: 1}];
var trae = [{day: "2026-11-14", model: "GLM", credits: 20,
             free_credits: 0, requests: 2, free_requests: 0}];
renderCreditKpisForSource(cards, "qoder", qoder, true);
eq("qoder labels", cards.map(function (c) { return c.label; }),
   ["区间 credits", "免费 credits", "区间日均", "最新额度余额"]);
eq("qoder primary", cards.filter(function (c) { return c.primary; }).length, 1);
eq("qoder free", cards[1].value, "1");
cards = [];
renderCreditKpisForSource(cards, "trae-cn", trae, true);
eq("trae labels", cards.map(function (c) { return c.label; }),
   ["区间 credits", "免费 credits", "区间日均", "最新额度余额"]);
eq("trae free is unavailable", cards[1].value, "—");
eq("trae quota reason", cards[3].sub, "Trae CN 不提供额度快照");
eq("trae primary", cards.filter(function (c) { return c.primary; }).length, 1);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_estimates_are_off_until_shared_switch(self):
        toggle = extract_js(self.html, "function hasTraeEstimateSelected",
                            "var initialRange")
        rows = extract_js(self.html, "function traeRowsFor", "function dimensionRows")
        harness = r"""
var TRAE_EST = [{day: "2026-11-14", total: 110}];
var EST = [{day: "2026-11-14", total: 20}];
var state = {shadow: false, agents: new Set(["trae-cn"])};
%s
function matchesFilters() { return true; }
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("trae off by default", hasTraeEstimateSelected(), false);
eq("no trae rows by default", traeRowsFor().length, 0);
state.shadow = true;
eq("trae on with switch", hasTraeEstimateSelected(), true);
eq("trae rows with switch", traeRowsFor().length, 1);
""" % (toggle, rows)
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("if (!hasTraeEstimateSelected()) return [];", self.html)
        self.assertIn("return rows.concat(estimateRows());", self.html)


class HtmlCoverageBlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    def test_help_panel_replaces_standalone_coverage_block(self):
        self.assertIn('id="help-toggle"', self.html)
        self.assertIn('id="help-panel"', self.html)
        self.assertIn('id="coverage-extra"', self.html)
        self.assertIn('aria-controls="help-panel"', self.html)
        self.assertIn('role="dialog"', self.html)
        self.assertIn('aria-expanded="false"', self.html)
        self.assertNotIn('class="card coverage-block"', self.html)
        self.assertEqual(self.html.count('id="generated"'), 1)
        self.assertIn('state.agents.has("trae-cn")', self.html)
        self.assertIn("Qoder 影子估算未计入", self.html)
        self.assertIn("库内：", self.html)
        self.assertIn("本页：", self.html)
        self.assertIn("function setHelpPanel", self.html)
        self.assertIn("function syncHelpAlert", self.html)
        self.assertIn("el.helpPanel.hidden", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_help_panel_toggle_and_warning_state(self):
        source = extract_js(self.html, "function setHelpPanel",
                            "function buildControls")
        harness = r"""
var focused = [];
var el = {
  helpPanel: {hidden: true},
  helpToggle: {attrs: {}, focus: function () { focused.push("toggle"); }, classList: {
    toggle: function (name, on) { this[name] = !!on; }
  }, setAttribute: function (name, value) { this.attrs[name] = value; }},
  helpClose: {focus: function () { focused.push("close"); }},
  traeStatus: {hidden: false, classList: {contains: function (name) {
    return name === "warn";
  }}}
};
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
setHelpPanel(true, true);
eq("opened", el.helpPanel.hidden, false);
eq("expanded", el.helpToggle.attrs["aria-expanded"], "true");
eq("focus close", focused, ["close"]);
setHelpPanel(false, true);
eq("closed", el.helpPanel.hidden, true);
eq("collapsed", el.helpToggle.attrs["aria-expanded"], "false");
eq("focus toggle", focused, ["close", "toggle"]);
syncHelpAlert();
eq("warn dot", el.helpToggle.classList.warn, true);
eq("warn title", el.helpToggle.attrs["aria-label"], "查看口径与数据覆盖（有数据提醒）");
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class HtmlTopListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_top_bars_share_denominator_with_labels(self):
        source = extract_js(self.html, "function topValueText", "function filterTopItems")
        harness = r"""
%s
function pct(value) {
  if (!isFinite(value) || value <= 0) return "0%";
  return (value * 100).toFixed(1) + "%";
}
function fmtCredits(value) { return String(value); }
function fmtCompact(value) { return String(value); }
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("first is full", topShare(10, 10).text, "100.0%");
eq("half", topShare(5, 10).text, "50.0%");
eq("zero", topShare(0, 0).text, "—");
eq("width", topShare(5, 10).width, 50);
""".replace("%s", source, 1)
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("相对第一", self.html)
        self.assertIn("top-sort-note", self.html)


class HtmlChartControlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    def test_chart_controls_live_in_their_panels(self):
        token = self.html.index('id="panel-token"')
        metric = self.html.index('id="metric-field"')
        credits = self.html.index('id="panel-credits"')
        shadow = self.html.index('id="shadow-switch"')
        estimate = self.html.index('id="panel-est"')
        self.assertLess(token, metric)
        self.assertLess(metric, credits)
        self.assertLess(credits, shadow)
        self.assertLess(shadow, estimate)
        self.assertIn("Trae 弱估算", self.html)
        self.assertIn("shadowAxisTitle", self.html)
        self.assertIn("axis-title", self.html)
        self.assertIn('aria-label="Token 指标"', self.html)
        self.assertIn('aria-label="显示估算"', self.html)


class HtmlNavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    def test_sticky_filter_bar_and_back_to_top(self):
        for marker in ('id="filter-shell"', 'id="filter-toggle"', 'id="sheet-close"',
                       'id="back-top"', "sticky-enabled", "stuck", ".filter-shell.sheet",
                       'event.key === "Escape"', "updateChrome"):
            self.assertIn(marker, self.html)
        self.assertIn("@media (max-width:640px)", self.html)


class HtmlChartA11yTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_chart_points_focusable_and_tooltip_clamped(self):
        source = extract_js(self.html, "function clampTooltipX", "function buildStackBuckets")
        harness = r"""
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("left clamp", clampTooltipX(10, 1000, 290), 145);
eq("right clamp", clampTooltipX(990, 1000, 290), 855);
eq("middle", clampTooltipX(500, 1000, 290), 500);
eq("narrow", clampTooltipX(10, 200, 290), 145);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('tabindex: "0"', self.html)
        self.assertIn('role: "button"', self.html)
        self.assertIn("offsetWidth", self.html)
        self.assertIn('event.key === "Escape"', self.html)


class HtmlActivityPagingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    def test_activity_table_paginates_and_skips_when_collapsed(self):
        for marker in ('id="activity-page-size"', 'id="activity-prev"', 'id="activity-next"',
                       'id="activity-pageinfo"', "if (!el.activityBlock.open) return;",
                       "state.activityPage", "ACTIVITY_STICKY", "paginateRows(sorted"):
            self.assertIn(marker, self.html)
        self.assertIn("activity-table-wrap", self.html)


class HtmlLabelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_display_names_and_formatters_are_consistent(self):
        labels = extract_js(self.html, "var DISPLAY_NAMES", "function sourceLabel")
        formatters = extract_js(self.html, "function fmtInt", "function fmtDuration")
        harness = r"""
%s
%s
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
var numberFormat = new Intl.NumberFormat("en-US");
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("trae label", displayName("trae-cn"), "Trae CN");
eq("turns label", displayName("turns"), "记录数");
eq("used label", displayName("used"), "已用");
eq("unknown fallback", displayName("x"), "x");
eq("quota matches credits", fmtQuota(2.5), fmtCredits(2.5));
""" % (labels, formatters)
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('label: "记录数"', self.html)
        self.assertIn('{ key: "turns", label: "轮次"', self.html)
        self.assertIn("已用 ", self.html)
        self.assertNotIn("est 请求", self.html)


class HtmlStatePersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_filters_round_trip_via_url_state(self):
        source = extract_js(self.html, "function normalizeAgentKeys",
                            "function readPersistedState")
        harness = r"""
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var allowed = ["claude", "qoder", "trae-cn"];
eq("valid agents", normalizeAgentKeys("qoder,bogus,trae-cn", allowed), ["qoder", "trae-cn"]);
eq("empty agents", normalizeAgentKeys("", allowed), []);
eq("page size", normalizePageSize("25", [25, 50], 50), 25);
eq("bad page size", normalizePageSize("999", [25, 50], 50), 50);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snapshot = extract_js(self.html, "function stateSnapshot", "function persistState")
        self.assertNotIn("token", snapshot)
        self.assertNotIn("credits", snapshot)
        self.assertIn("history.replaceState", self.html)
        self.assertIn("URLSearchParams", self.html)
        self.assertIn("STATE_KEY", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_url_boolean_state_round_trip(self):
        source = extract_js(self.html, "function persistedFlag", "function stateSnapshot")
        harness = r"""
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
var params = new URLSearchParams();
params.set("shadow", true);
params.set("focusRange", false);
var raw = {};
params.forEach(function (value, key) { raw[key] = value; });
eq("shadow true", persistedFlag(raw.shadow), true);
eq("focus false", persistedFlag(raw.focusRange), false);
eq("native bool", persistedFlag(true), true);
eq("url one", persistedFlag("1"), true);
eq("url false", persistedFlag("false"), false);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("target.shadow = persistedFlag(raw.shadow)", self.html)
        self.assertIn("target.focusRange = persistedFlag(raw.focusRange)", self.html)


class HtmlFocusRangeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_focus_range_toggle_is_opt_in(self):
        source = extract_js(self.html, "function matchesDimensionFilters",
                            "function hasFocusableData")
        harness = r"""
var state = {agents: new Set(["claude", "qoder"]), model: "", project: "", q: ""};
var TOKEN_ROWS = [{day: "2026-11-10", source: "claude"}, {day: "2026-11-12", source: "claude"}];
var CREDIT_ROWS = [{day: "2026-11-08", source: "qoder"}, {day: "2026-11-14", source: "qoder"}];
var EST = [];
var TRAE_EST = [];
function matchesQuery() { return true; }
function hasTokenSelected() { return true; }
function hasCreditsSelected() { return true; }
function hasTraeEstimateSelected() { return false; }
function minMaxDay(rows) {
  var min = "", max = "";
  rows.forEach(function (row) {
    if (!min || row.day < min) min = row.day;
    if (!max || row.day > max) max = row.day;
  });
  return [min, max];
}
function number(value) { var n = Number(value); return isFinite(n) ? n : 0; }
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
eq("focus union", focusBounds(), ["2026-11-08", "2026-11-14"]);
TOKEN_ROWS = []; CREDIT_ROWS = [];
eq("no data", focusBounds(), ["", ""]);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('id="focus-range"', self.html)
        self.assertIn("聚焦有数据区间", self.html)
        self.assertIn("defaultDateRange", self.html)
        self.assertIn("无可聚焦的数据区间", self.html)

    @unittest.skipUnless(shutil.which("node"), "node 不可用")
    def test_top8_dimension_pick_refreshes_focus_and_selects(self):
        source = extract_js(self.html, "function pickModel", "function renderTopLists")
        harness = r"""
var state = {model: "", project: "", page: 3};
var el = {model: {value: ""}, project: {value: ""}};
var calls = [];
function refreshFocusAfterFilterChange() { calls.push("focus"); }
function rebuildDimensionSelects() { calls.push("rebuild"); }
function renderAll() { calls.push("render"); }
%s
function eq(name, actual, expected) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  if (a !== e) {
    console.error(name + ": " + a + " != " + e);
    process.exitCode = 1;
  }
}
pickModel("m1");
eq("model", state.model, "m1");
eq("model page", state.page, 0);
eq("model calls", calls, ["focus", "rebuild", "render"]);
calls = [];
pickModel("m1");
eq("model cleared", state.model, "");
eq("model clear calls", calls, ["focus", "rebuild", "render"]);
calls = [];
pickProject("p1");
eq("project", state.project, "p1");
eq("project calls", calls, ["focus", "rebuild", "render"]);
""" % source
        proc = subprocess.run([shutil.which("node"), "-e", harness],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_footer_refreshes_after_filters(self):
        source = extract_js(self.html, "function renderAll", "buildAgentFilter")
        self.assertIn("renderFooter();", source)


class HtmlFilterLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html(build_payload([], ("day", "source", "model", "project"),
                                             None, None, []))

    def test_filter_row_width_stable_across_agents(self):
        self.assertIn("dimension-line", self.html)
        self.assertIn("grid-template-columns:220px 220px minmax(200px,1fr)", self.html)
        self.assertIn("text-overflow:ellipsis", self.html)
        self.assertIn("无可用模型", self.html)
        self.assertIn("无可用项目", self.html)
        self.assertIn("el.q.value = state.q", self.html)
        self.assertIn("el.model.title", self.html)
        self.assertIn("el.project.title", self.html)


if __name__ == "__main__":
    unittest.main()
