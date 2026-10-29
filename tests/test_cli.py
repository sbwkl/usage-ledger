import contextlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.usage_ledger.cli import main
from src.usage_ledger.store import SqliteStore

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


if __name__ == "__main__":
    unittest.main()
