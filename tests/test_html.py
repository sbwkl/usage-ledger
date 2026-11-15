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
        self.assertIn("est 请求", self.html)

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
        self.assertIn("区间 billable", html)
        self.assertIn("影子：Qoder 估算 token", html)
        self.assertIn("最新额度余额", html)
        self.assertIn("Credits 按 Agent 分列", html)
        self.assertIn("不可与 token 真值或额度相加", html)
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))


if __name__ == "__main__":
    unittest.main()
