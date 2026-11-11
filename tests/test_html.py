import contextlib
import io
import json
import os
import re
import shutil
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
        self.assertIn("单击只看", html)

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
        self.assertEqual(len(payload["activity"]), 2)
        self.assertTrue(all(row["source"] == "qoder" for row in payload["activity"]))
        self.assertEqual(payload["coverage"]["qoder"]["token_until"], "2026-10-02")
        self.assertEqual(payload["coverage"]["qoder"]["activity_until"], "2026-10-02")
        self.assertIn("补充口径", html)
        self.assertIn('data-qoder-tab="credits"', html)
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
        self.assertEqual(payload["credits"]["totals"]["credits"], 2.5)
        self.assertEqual(payload["credits"]["quota"]["add_on"]["used"], 100)
        self.assertEqual(payload["est"]["factor_version"], "v1")
        self.assertEqual(len(payload["est"]["rows"]), 1)
        est = payload["est"]["rows"][0]
        self.assertEqual((est["day"], est["model"], est["est_input"],
                          est["est_output"], est["requests"]),
                         ("2026-10-01", "gfmodel", 50_000, 1, 1))
        self.assertEqual(payload["est"]["totals"]["requests"], 1)
        self.assertIn("额度消耗（credits）", html)
        self.assertIn("估算 token（est）", html)
        self.assertIn("最新额度余额", html)
        self.assertIn("活动、额度、估算与 token 真值口径不同，不可相加", html)
        self.assertIn("不可与 token 真值或额度相加", html)
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))


if __name__ == "__main__":
    unittest.main()
