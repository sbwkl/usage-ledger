import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from src.usage_ledger.cli import main
from src.usage_ledger.models import Credit
from src.usage_ledger.store import SqliteStore
from src.usage_ledger.trae_credits import TRAE_CREDITS_SOURCE, TraeCreditsError
from src.usage_ledger.trae_hooks import trae_event_dir

BASE_TS = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc).timestamp()


def event(offset, kind, uid, session="s1", project="proj", **fields):
    row = {"v": 1, "uid": uid, "ts": BASE_TS + offset, "event": kind,
           "session": session, "project": project}
    row.update(fields)
    return row


def extract_payload(html):
    marker = '<script type="application/json" id="data">'
    blob = html.split(marker, 1)[1].split("</script>", 1)[0]
    return json.loads(blob)


class TraeCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.data_home = os.path.join(self.home, ".local", "share", "usage-ledger")
        self.db_path = os.path.join(self.home, "usage.db")
        self.env = patch.dict(os.environ, {
            "USAGE_LEDGER_SOURCE_HOME": self.home,
            "USAGE_LEDGER_HOME": self.data_home,
            "USAGE_LEDGER_DB": self.db_path,
        })
        self.env.start()
        self.event_dir = trae_event_dir(self.home)
        os.makedirs(self.event_dir)
        path = os.path.join(self.event_dir, "events-2026-10-30.jsonl")
        rows = [
            event(0, "SessionStart", "u0"),
            event(1, "UserPromptSubmit", "u1", chars_in=200),
            event(2, "PreToolUse", "u2", chars_out=120),
            event(3, "PostToolUse", "u3", chars_in=8000),
            event(4, "Stop", "u4", chars_out=300),
        ]
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_sync_and_est_are_idempotent(self):
        code, out, err = self.run_cli(["sync", "--source", "trae-cn"])
        self.assertEqual(code, 0, err)
        self.assertIn("trae-cn.est: 弱估算 2 条", out)
        self.assertIn("Trae CN 弱估算", out)

        store = SqliteStore(self.db_path)
        try:
            self.assertEqual(store.est_count("trae-cn.est"), 2)
            self.assertEqual(store.est_count(), 0)
            rows = store.est_rows(source="trae-cn.est")
            self.assertEqual((rows[0]["est_input"], rows[0]["est_output"],
                              rows[0]["requests"], rows[0]["missing_ratio"]),
                             (2242, 111, 2, 2))
            states = {row[0]: row for row in store.source_states()}
            self.assertEqual(states["trae-cn.est"][1], "ok")
            self.assertEqual(states["trae-cn.est"][2], 1)
            self.assertEqual(states["trae-cn.est"][3], 2)
        finally:
            store.close()

        code, out, _ = self.run_cli(["sync", "--source", "trae-cn"])
        self.assertEqual(code, 0)
        store = SqliteStore(self.db_path)
        try:
            self.assertEqual(store.est_count("trae-cn.est"), 2)
        finally:
            store.close()

        code, out, err = self.run_cli(["est", "--source", "trae-cn",
                                       "--group-by", "day,session", "--format", "json"])
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session"], "s1")
        self.assertEqual((rows[0]["est_input"], rows[0]["est_output"],
                          rows[0]["requests"]), (2242, 111, 2))
        self.assertIn("无上下文比例", err)
        self.assertIn("不可与真值/额度相加", err)

        code, stateless, _ = self.run_cli(["--stateless", "est", "--source", "trae-cn",
                                           "--group-by", "day,session", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stateless), rows)

        code, out, err = self.run_cli(["est", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])
        self.assertIn("no estimate data in range", err)

    def test_report_does_not_resync_unchanged_trae_events(self):
        self.assertEqual(self.run_cli(["sync", "--source", "trae-cn"])[0], 0)
        code, _, err = self.run_cli(["report", "--source", "trae-cn", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertNotIn("auto-sync", err)

    def test_dry_run_and_report_have_no_token_truth(self):
        code, out, _ = self.run_cli(["sync", "--source", "trae-cn", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("trae-cn.est: 2 estimates", out)
        self.assertFalse(os.path.exists(self.db_path))

        code, out, _ = self.run_cli(["--stateless", "report", "--source", "trae-cn",
                                     "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_doctor_reports_hooks_and_estimates(self):
        self.assertEqual(self.run_cli(["sync", "--source", "trae-cn"])[0], 0)
        code, out, err = self.run_cli(["doctor", "--probe", "trae-cn"])
        self.assertEqual(code, 0, err)
        self.assertIn("trae-cn hooks:", out)
        self.assertIn("trae-cn.est: files=1 events=5 sessions=1 estimates=2", out)
        self.assertIn("Trae CN 弱估算", out)

        code, out, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("trae_est_rows=2", out)
        self.assertIn("trae-cn.est: files=1", out)

    def test_hooks_commands(self):
        code, out, _ = self.run_cli(["hooks", "status", "trae-cn"])
        self.assertEqual(code, 0)
        self.assertIn("exists=False", out)
        self.assertIn("hint: usage hooks install", out)

        code, out, _ = self.run_cli(["hooks", "install", "trae-cn",
                                     "--scope", "global", "--dry-run"])
        self.assertEqual(code, 0)
        config_path = os.path.join(self.home, ".trae-cn", "hooks.json")
        self.assertIn(config_path, out)
        self.assertIn("dry-run", out)
        self.assertFalse(os.path.exists(config_path))

        code, out, _ = self.run_cli(["hooks", "install", "trae-cn", "--scope", "global"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(config_path))
        with open(config_path, encoding="utf-8") as fh:
            config = json.load(fh)
        self.assertEqual(sorted(config["hooks"]),
                         ["PostToolUse", "PreToolUse", "SessionStart", "Stop",
                          "UserPromptSubmit"])
        self.assertTrue(os.path.isfile(os.path.join(
            self.data_home, "hooks", "trae-cn-hook.py")))
        self.assertIn("Settings > Hooks", out)

        code, out, _ = self.run_cli(["hooks", "status", "trae-cn"])
        self.assertEqual(code, 0)
        self.assertIn("exists=True", out)
        self.assertIn("groups=1", out)
        self.assertIn("files=1 events=5 sessions=1", out)

        code, out, _ = self.run_cli(["hooks", "uninstall", "trae-cn", "--scope", "global"])
        self.assertEqual(code, 0)
        self.assertIn("removed groups: 5", out)
        with open(config_path, encoding="utf-8") as fh:
            config = json.load(fh)
        self.assertEqual(config["hooks"], {})

    def test_html_trae_is_credits_primary_with_weak_est_panel(self):
        self.assertEqual(self.run_cli(["sync", "--source", "trae-cn"])[0], 0)
        output = os.path.join(self.home, "trae.html")
        with patch("src.usage_ledger.cli.sync_trae_credits") as refresh:
            code, _, err = self.run_cli(["html", "--offline", "--output", output])
        self.assertEqual(code, 0, err)
        refresh.assert_not_called()
        with open(output, encoding="utf-8") as fh:
            html = fh.read()
        self.assertNotIn("<", html.split('id="data">', 1)[1].split("</script>", 1)[0])
        self.assertIn("Trae CN", html)
        payload = extract_payload(html)
        self.assertEqual(payload["agents"]["trae-cn"], "credits")
        self.assertEqual(payload["coverage"]["trae-cn.credits"]["refresh_mode"], "offline")
        self.assertEqual(payload["trae_est"]["factor_version"], "trae-hook-v1")
        self.assertEqual(payload["trae_est"]["totals"]["requests"], 2)
        rows = payload["trae_est"]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["day"], rows[0]["est_input"], rows[0]["est_output"]),
                         ("2026-10-30", 2242, 111))
        self.assertIn("Trae CN 弱估算", html)
        self.assertNotIn('data-supp-source="trae-cn"', html)
        self.assertIn('id="agent-nav"', html)
        self.assertIn('id="shadow-switch"', html)
        self.assertIn("精确 Credits", html)
        self.assertIn("Trae credits 未同步", html)
        self.assertIsNone(re.search(r'(?:src|href)=["\']https?://', html))

        code, _, _ = self.run_cli(["html", "--source", "claude", "--output", output])
        self.assertEqual(code, 0)
        with open(output, encoding="utf-8") as fh:
            payload = extract_payload(fh.read())
        self.assertEqual(payload["trae_est"]["rows"], [])
        self.assertNotIn("trae-cn.credits", payload["coverage"])

    def _seed_trae_credit(self, day=None):
        day = day or date.today().isoformat()
        ts = datetime.now(timezone.utc).timestamp()
        store = SqliteStore(self.db_path)
        try:
            store.upsert_credits([Credit(
                request_id="trae-cn:seed", ts=ts, day=day, project="proj",
                model="seed-model", session="seed", credits=1.25,
                billable=True, source="trae-cn")], [])
            store.update_source_state(TRAE_CREDITS_SOURCE, files=0, records=1,
                                      status="ok", last_ts=ts)
        finally:
            store.close()
        return day

    def test_sync_without_remote_does_not_call_network(self):
        with patch("src.usage_ledger.cli.sync_trae_credits") as remote:
            code, _, err = self.run_cli(["sync", "--source", "trae-cn"])
        self.assertEqual(code, 0, err)
        remote.assert_not_called()

    def test_sync_remote_calls_trae_refresh(self):
        self.assertEqual(self.run_cli(["sync", "--source", "trae-cn"])[0], 0)
        fake = SimpleNamespace(sessions=2, credits=1.5, skipped=0, pages=1,
                               since=date.today().isoformat(),
                               until=date.today().isoformat(), jwt_warning=None)
        with patch("src.usage_ledger.cli.sync_trae_credits", return_value=fake) as remote:
            code, out, err = self.run_cli(["sync", "--source", "trae-cn", "--remote"])
        self.assertEqual(code, 0, err)
        remote.assert_called_once()
        self.assertIn("refreshed 2 sessions / 1.50 credits", out)

    def test_html_default_refreshes_trae_credits(self):
        self.assertEqual(self.run_cli(["sync", "--source", "trae-cn"])[0], 0)
        output = os.path.join(self.home, "fresh.html")
        fake = SimpleNamespace(sessions=3, credits=4.5, skipped=0, pages=1,
                               since=date.today().isoformat(),
                               until=date.today().isoformat(), jwt_warning=None)
        with patch("src.usage_ledger.cli.sync_trae_credits", return_value=fake) as remote:
            code, _, err = self.run_cli(["html", "--output", output])
        self.assertEqual(code, 0, err)
        remote.assert_called_once()
        self.assertIn("refreshed 3 sessions / 4.50 credits", err)
        with open(output, encoding="utf-8") as fh:
            payload = extract_payload(fh.read())
        self.assertEqual(payload["coverage"]["trae-cn.credits"]["refresh_mode"], "auto")

    def test_html_source_qoder_skips_trae_refresh(self):
        output = os.path.join(self.home, "qoder-only.html")
        with patch("src.usage_ledger.cli.sync_trae_credits") as remote:
            code, _, err = self.run_cli(
                ["html", "--source", "qoder", "--output", output])
        self.assertEqual(code, 0, err)
        remote.assert_not_called()
        with open(output, encoding="utf-8") as fh:
            payload = extract_payload(fh.read())
        self.assertNotIn("trae-cn.credits", payload["coverage"])

    def test_html_stateless_skips_trae_refresh(self):
        output = os.path.join(self.home, "stateless.html")
        with patch("src.usage_ledger.cli.sync_trae_credits") as remote:
            code, _, err = self.run_cli(
                ["--stateless", "html", "--output", output])
        self.assertEqual(code, 0, err)
        remote.assert_not_called()
        with open(output, encoding="utf-8") as fh:
            payload = extract_payload(fh.read())
        self.assertEqual(payload["coverage"]["trae-cn.credits"]["refresh_mode"],
                         "stateless")

    def test_html_refresh_failure_uses_cache_and_strict_exits_nonzero(self):
        day = self._seed_trae_credit()
        output = os.path.join(self.home, "fallback.html")
        error = TraeCreditsError("API 请求失败（HTTP 500）", status=500)
        with patch("src.usage_ledger.cli.sync_trae_credits", side_effect=error):
            code, _, err = self.run_cli(["html", "--output", output])
        self.assertEqual(code, 0, err)
        self.assertIn("refresh failed, using cached data", err)
        with open(output, encoding="utf-8") as fh:
            payload = extract_payload(fh.read())
        coverage = payload["coverage"]["trae-cn.credits"]
        self.assertIn("HTTP 500", coverage["refresh_error"])
        self.assertTrue(coverage["stale"])
        trae_rows = [row for row in payload["credits"]["rows"]
                     if row["source"] == "trae-cn"]
        self.assertEqual([(row["day"], row["credits"]) for row in trae_rows],
                         [(day, 1.25)])

        strict_output = os.path.join(self.home, "strict.html")
        with patch("src.usage_ledger.cli.sync_trae_credits", side_effect=error):
            code, _, _ = self.run_cli(
                ["html", "--strict-refresh", "--output", strict_output])
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(strict_output))
        with open(strict_output, encoding="utf-8") as fh:
            payload = extract_payload(fh.read())
        self.assertEqual(
            payload["coverage"]["trae-cn.credits"]["refresh_mode"], "auto")
        self.assertTrue(payload["credits"]["rows"])

    def test_html_max_age_reuses_fresh_cache(self):
        self.assertEqual(self.run_cli(["sync", "--source", "trae-cn"])[0], 0)
        output = os.path.join(self.home, "max-age.html")
        calls = []

        def fake(store, since, until, jwt_file=None):
            calls.append((since, until))
            ts = datetime.now(timezone.utc).timestamp()
            store.upsert_credits([Credit(
                request_id="trae-cn:%s" % since, ts=ts, day=since,
                project="proj", model="m", session="s", credits=1.0,
                billable=True, source="trae-cn")], [])
            store.update_source_state(TRAE_CREDITS_SOURCE, files=0, records=1,
                                      status="ok", last_ts=ts)
            store.set_meta("trae_credits_last_window",
                           json.dumps({"since": since, "until": until}))
            return SimpleNamespace(sessions=1, credits=1.0, skipped=0, pages=1,
                                   since=since, until=until, jwt_warning=None)

        with patch("src.usage_ledger.cli.sync_trae_credits", side_effect=fake):
            code, _, err = self.run_cli(
                ["html", "--max-age", "300", "--output", output])
            self.assertEqual(code, 0, err)
            code, _, err = self.run_cli(
                ["html", "--max-age", "300", "--output", output])
            self.assertEqual(code, 0, err)
        self.assertEqual(len(calls), 1)
        self.assertIn("cache fresh", err)

    def test_credits_command_lists_trae_sessions(self):
        day = self._seed_trae_credit()
        code, out, err = self.run_cli(["credits", "--source", "trae-cn"])
        self.assertEqual(code, 0, err)
        self.assertIn("sessions", out)
        self.assertIn("total trae-cn: 1.25 credits / 1 会话", out)

        code, out, err = self.run_cli(
            ["credits", "--source", "trae-cn", "--format", "json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["days"][0]["source"], "trae-cn")
        self.assertEqual(payload["days"][0]["day"], day)
        self.assertEqual(payload["totals"]["trae-cn"]["credits"], 1.25)


if __name__ == "__main__":
    unittest.main()
