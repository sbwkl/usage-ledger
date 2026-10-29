import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.usage_ledger.cli import main
from src.usage_ledger.html_report import build_payload, render_html

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
        self.assertIsNone(parsed["range"]["since"])


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
        self.assertTrue(any("Qoder" in notice for notice in payload["notices"]))
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))
        self.assertIn("Content-Security-Policy", html)

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


if __name__ == "__main__":
    unittest.main()
