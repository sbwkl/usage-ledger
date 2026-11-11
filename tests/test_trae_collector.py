import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.usage_ledger.collectors import (collect_all, local_day, scan_trae_cn_est,
                                         source_signatures)
from src.usage_ledger.trae_hooks import trae_event_dir

BASE_TS = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc).timestamp()


def event(offset, kind, uid, session="s1", project="proj", **fields):
    row = {"v": 1, "uid": uid, "ts": BASE_TS + offset, "event": kind,
           "session": session, "project": project}
    row.update(fields)
    return row


def write_events(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class TraeReplayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "trae-cn")
        os.makedirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        write_events(os.path.join(self.root, "events-2026-10-30.jsonl"), rows)

    def test_design_example(self):
        self.write([
            event(0, "SessionStart", "u0"),
            event(1, "UserPromptSubmit", "u1", chars_in=200),
            event(2, "PreToolUse", "u2", chars_out=120),
            event(3, "PostToolUse", "u3", chars_in=8000),
            event(4, "Stop", "u4", chars_out=300),
        ])
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertTrue(result.available)
        self.assertEqual(result.name, "trae-cn.est")
        self.assertEqual(result.files, 1)
        self.assertEqual(result.key_kinds["events"], 5)
        self.assertEqual(result.key_kinds["sessions"], 1)
        self.assertEqual(len(result.estimates), 2)
        first, second = result.estimates
        self.assertEqual((first.request_id, first.est_input, first.est_output,
                          first.chars_in, first.chars_out),
                         ("trae-cn:u2", 53, 32, 200, 120))
        self.assertEqual((second.request_id, second.est_input, second.est_output,
                          second.chars_in, second.chars_out),
                         ("trae-cn:u4", 2189, 79, 8320, 300))
        self.assertEqual(first.day, local_day(BASE_TS + 2))
        self.assertEqual(second.day, local_day(BASE_TS + 4))
        for row in result.estimates:
            self.assertEqual(row.source, "trae-cn.est")
            self.assertIsNone(row.ratio)
            self.assertEqual(row.model, "trae-cn")
            self.assertEqual(row.project, "proj")
            self.assertEqual(row.session, "s1")

    def test_sessions_are_isolated_and_events_sorted(self):
        rows = [
            event(5, "Stop", "u6", session="s2", chars_out=38),
            event(1, "UserPromptSubmit", "u1", session="s1", chars_in=100),
            event(2, "UserPromptSubmit", "u2", session="s2", chars_in=200),
            event(3, "PreToolUse", "u3", session="s1", chars_out=38),
            event(4, "PreToolUse", "u4", session="s2", chars_out=38),
            event(6, "Stop", "u5", session="s1", chars_out=38),
        ]
        self.write(rows)
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertEqual(len(result.estimates), 4)
        by_session = {}
        for row in result.estimates:
            by_session.setdefault(row.session, []).append(row)
        self.assertEqual([row.est_input for row in by_session["s1"]], [26, 36])
        self.assertEqual([row.est_input for row in by_session["s2"]], [53, 63])
        self.assertEqual([row.est_output for row in by_session["s1"]], [10, 10])
        self.assertEqual(result.key_kinds["sessions"], 2)

    def test_session_start_does_not_reset_started_context(self):
        self.write([
            event(1, "UserPromptSubmit", "u1", chars_in=100),
            event(2, "SessionStart", "u2"),
            event(3, "Stop", "u3", chars_out=38),
        ])
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.estimates[0].est_input, 26)

    def test_event_model_wins_over_fallback(self):
        self.write([
            event(1, "UserPromptSubmit", "u1", chars_in=100),
            event(2, "PreToolUse", "u2", chars_out=38, model="trae-pro"),
        ])
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertEqual(result.estimates[0].model, "trae-pro")

    def test_env_factor_overhead_and_window(self):
        self.write([
            event(1, "UserPromptSubmit", "u1", chars_in=1000),
            event(2, "PreToolUse", "u2", chars_out=10),
        ])
        with patch.dict(os.environ, {"USAGE_LEDGER_TRAE_EST_FACTOR": "2",
                                     "USAGE_LEDGER_TRAE_EST_OVERHEAD": "7",
                                     "USAGE_LEDGER_TRAE_EST_WINDOW": "100"}):
            result = scan_trae_cn_est(event_dir=self.root)
        row = result.estimates[0]
        self.assertEqual(row.est_input, 100)
        self.assertEqual(row.est_output, 5)
        self.assertEqual(row.chars_in, 200)

    def test_invalid_env_falls_back_to_defaults(self):
        self.write([
            event(1, "UserPromptSubmit", "u1", chars_in=200),
            event(2, "PreToolUse", "u2", chars_out=120),
        ])
        with patch.dict(os.environ, {"USAGE_LEDGER_TRAE_EST_FACTOR": "abc",
                                     "USAGE_LEDGER_TRAE_EST_WINDOW": "0"}):
            result = scan_trae_cn_est(event_dir=self.root)
        self.assertEqual(result.estimates[0].est_input, 53)
        self.assertEqual(result.estimates[0].est_output, 32)

    def test_duplicate_uid_is_counted_once(self):
        self.write([
            event(1, "UserPromptSubmit", "u1", chars_in=38),
            event(2, "PreToolUse", "u2", chars_out=38),
            event(3, "PreToolUse", "u2", chars_out=38),
        ])
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.key_kinds["dup:uid"], 1)

    def test_bad_lines_and_shapes_are_skipped(self):
        path = os.path.join(self.root, "events-2026-10-30.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{bad\n")
            fh.write(json.dumps({"v": 2, "event": "Stop", "uid": "x",
                                 "ts": BASE_TS}) + "\n")
            fh.write(json.dumps({"v": 1, "event": "Unknown", "uid": "y",
                                 "ts": BASE_TS}) + "\n")
            fh.write(json.dumps({"v": 1, "event": "Stop", "uid": "z",
                                 "ts": "bad"}) + "\n")
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertEqual(result.estimates, [])
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.key_kinds["skipped:shape"], 1)
        self.assertEqual(result.key_kinds["skipped:event"], 1)
        self.assertEqual(result.key_kinds["skipped:ts"], 1)

    def test_missing_dir_is_unavailable(self):
        result = scan_trae_cn_est(event_dir=os.path.join(self.root, "missing"))
        self.assertFalse(result.available)
        self.assertIn("usage hooks install", result.notes[0])

    def test_empty_dir_is_available_without_estimates(self):
        result = scan_trae_cn_est(event_dir=self.root)
        self.assertTrue(result.available)
        self.assertEqual(result.files, 0)
        self.assertEqual(result.estimates, [])


class TraeWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.data_home = os.path.join(self.home, ".local", "share", "usage-ledger")
        self.env = patch.dict(os.environ, {"USAGE_LEDGER_HOME": self.data_home})
        self.env.start()
        self.event_dir = trae_event_dir(self.home)
        write_events(os.path.join(self.event_dir, "events-2026-10-30.jsonl"), [
            event(1, "UserPromptSubmit", "u1", chars_in=200),
            event(2, "Stop", "u2", chars_out=300),
        ])

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_signatures_include_public_and_sub_source(self):
        signatures = source_signatures(self.home, ["trae-cn"])
        self.assertIsNotNone(signatures["trae-cn"])
        self.assertEqual(signatures["trae-cn"], signatures["trae-cn.est"])
        os.utime(os.path.join(self.event_dir, "events-2026-10-30.jsonl"),
                 ns=(os.stat(os.path.join(self.event_dir,
                                          "events-2026-10-30.jsonl")).st_atime_ns,
                     1_900_000_000_000_000_000))
        updated = source_signatures(self.home, ["trae-cn"])
        self.assertGreater(updated["trae-cn"], signatures["trae-cn"])

    def test_collect_all_includes_trae_est(self):
        results = collect_all(self.home, ["trae-cn"])
        self.assertEqual([result.name for result in results], ["trae-cn.est"])
        self.assertEqual(len(results[0].estimates), 1)


if __name__ == "__main__":
    unittest.main()
