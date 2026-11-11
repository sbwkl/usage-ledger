import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.usage_ledger import trae_hooks
from src.usage_ledger.collectors import scan_trae_cn_est


class HookInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.data_home = os.path.join(self.home, ".local", "share", "usage-ledger")
        self.env = patch.dict(os.environ, {"USAGE_LEDGER_HOME": self.data_home})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def config_path(self):
        return os.path.join(self.home, ".trae-cn", "hooks.json")

    def read_config(self):
        with open(self.config_path(), encoding="utf-8") as fh:
            return json.load(fh)

    def write_config(self, config):
        os.makedirs(os.path.dirname(self.config_path()), exist_ok=True)
        with open(self.config_path(), "w", encoding="utf-8") as fh:
            json.dump(config, fh)

    def test_install_fresh_config(self):
        info = trae_hooks.install("global", home=self.home, python="/usr/bin/python3")
        self.assertEqual(info["config_path"], self.config_path())
        self.assertEqual(info["script_path"],
                         os.path.join(self.data_home, "hooks", "trae-cn-hook.py"))
        self.assertIsNone(info["backup"])
        config = self.read_config()
        self.assertEqual(config["version"], 1)
        self.assertEqual(sorted(config["hooks"]), sorted(trae_hooks.HOOK_EVENTS))
        for event in trae_hooks.HOOK_EVENTS:
            groups = config["hooks"][event]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["hooks"][0]["type"], "command")
            self.assertIn(trae_hooks.HOOK_MARKER, groups[0]["hooks"][0]["command"])
            self.assertIn("/usr/bin/python3", groups[0]["hooks"][0]["command"])
            self.assertEqual(groups[0]["hooks"][0]["timeout"], trae_hooks.HOOK_TIMEOUT)
        for event in trae_hooks.MATCHER_EVENTS:
            self.assertEqual(config["hooks"][event][0]["matcher"], "*")
        self.assertNotIn("matcher", config["hooks"]["Stop"][0])

        self.assertTrue(os.path.isfile(info["script_path"]))
        script_mode = stat.S_IMODE(os.stat(info["script_path"]).st_mode)
        self.assertEqual(script_mode, 0o700)
        config_mode = stat.S_IMODE(os.stat(self.config_path()).st_mode)
        self.assertEqual(config_mode, 0o600)
        with open(info["script_path"], encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn(repr(self.data_home), script)
        self.assertNotIn("__DATA_HOME__", script)

    def test_install_merges_and_is_idempotent(self):
        existing = {
            "version": 1,
            "hooks": {
                "Notification": [
                    {"matcher": "*", "hooks": [
                        {"type": "command", "command": "echo custom"}]},
                ],
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [
                        {"type": "command", "command": "echo pre"}]},
                ],
            },
        }
        self.write_config(existing)
        first = trae_hooks.install("global", home=self.home)
        self.assertIsNotNone(first["backup"])
        self.assertTrue(os.path.isfile(first["backup"]))
        config = self.read_config()
        self.assertEqual(len(config["hooks"]["Notification"]), 1)
        self.assertEqual(config["hooks"]["Notification"][0]["hooks"][0]["command"],
                         "echo custom")
        self.assertEqual(len(config["hooks"]["PreToolUse"]), 2)
        self.assertEqual(config["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
                         "echo pre")

        second = trae_hooks.install("global", home=self.home)
        self.assertIsNotNone(second["backup"])
        config = self.read_config()
        self.assertEqual(len(config["hooks"]["PreToolUse"]), 2)
        for event in trae_hooks.HOOK_EVENTS:
            own = [group for group in config["hooks"][event]
                   if trae_hooks._is_ours(group)]
            self.assertEqual(len(own), 1, event)

    def test_invalid_json_aborts_without_writing(self):
        path = self.config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        script_path = os.path.join(self.data_home, "hooks", "trae-cn-hook.py")
        with self.assertRaises(ValueError):
            trae_hooks.install("global", home=self.home)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{not json")
        self.assertFalse(os.path.exists(script_path))

    def test_uninstall_removes_only_own_groups(self):
        self.write_config({"version": 1, "hooks": {
            "Notification": [
                {"matcher": "*", "hooks": [
                    {"type": "command", "command": "echo custom"}]},
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [
                    {"type": "command", "command": "echo pre"}]},
            ],
        }})
        trae_hooks.install("global", home=self.home)
        info = trae_hooks.uninstall("global", home=self.home)
        self.assertEqual(info["removed"], 5)
        self.assertIsNotNone(info["backup"])
        config = self.read_config()
        self.assertIn("Notification", config["hooks"])
        self.assertEqual(len(config["hooks"]["PreToolUse"]), 1)
        self.assertEqual(config["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "echo pre")
        self.assertNotIn("SessionStart", config["hooks"])
        self.assertNotIn("Stop", config["hooks"])

    def test_project_scope_requires_project(self):
        with self.assertRaises(ValueError):
            trae_hooks.install("project", home=self.home)

    def test_status_before_and_after_install(self):
        before = trae_hooks.status("global", home=self.home)
        self.assertFalse(before["config_exists"])
        self.assertFalse(before["script_exists"])
        self.assertEqual(sum(before["hook_groups"].values()), 0)

        trae_hooks.install("global", home=self.home)
        after = trae_hooks.status("global", home=self.home)
        self.assertTrue(after["config_exists"])
        self.assertTrue(after["script_exists"])
        self.assertEqual(after["hook_groups"],
                         {event: 1 for event in trae_hooks.HOOK_EVENTS})
        self.assertEqual(after["events"], 0)


class HookScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.data_home = os.path.join(self.home, ".local", "share", "usage-ledger")
        self.env = patch.dict(os.environ, {"USAGE_LEDGER_HOME": self.data_home})
        self.env.start()
        info = trae_hooks.install("global", home=self.home)
        self.script = info["script_path"]

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_hook(self, payload):
        return subprocess.run([sys.executable, self.script],
                              input=json.dumps(payload).encode("utf-8"),
                              capture_output=True)

    def event_lines(self):
        files = trae_hooks.event_files(trae_hooks.trae_event_dir(self.home))
        rows = []
        for path in files:
            with open(path, encoding="utf-8") as fh:
                rows.extend(json.loads(line) for line in fh if line.strip())
        return files, rows

    def test_capture_is_private_and_counts_chars(self):
        base = {"session_id": "s1", "cwd": "/tmp/secret-work/proj"}
        prompt = "SECRET_PROMPT hello"
        tool_input = {"file_path": "/tmp/SECRET_FILE"}
        tool_response = "SECRET_TOOL_RESPONSE"
        final = "SECRET_FINAL_ANSWER"
        events = [
            dict(base, hook_event_name="SessionStart", source="startup"),
            dict(base, hook_event_name="UserPromptSubmit", prompt=prompt),
            dict(base, hook_event_name="PreToolUse", tool_name="Read",
                 tool_use_id="t1", tool_input=tool_input, model="trae-pro"),
            dict(base, hook_event_name="PostToolUse", tool_name="Read",
                 tool_use_id="t1", tool_response=tool_response),
            dict(base, hook_event_name="Stop", tool_use_id="",
                 last_assistant_message=final, loop_count=1),
        ]
        for payload in events:
            proc = self.run_hook(payload)
            self.assertEqual(proc.returncode, 0, proc.stderr)

        files, rows = self.event_lines()
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(os.stat(files[0]).st_mode), 0o600)
        self.assertEqual(len(rows), 5)
        self.assertEqual([row["event"] for row in rows],
                         ["SessionStart", "UserPromptSubmit", "PreToolUse",
                          "PostToolUse", "Stop"])
        by_event = {row["event"]: row for row in rows}
        self.assertEqual(by_event["UserPromptSubmit"]["chars_in"], len(prompt))
        self.assertEqual(by_event["PreToolUse"]["chars_out"],
                         len(json.dumps(tool_input, ensure_ascii=False,
                                        separators=(",", ":"))))
        self.assertEqual(by_event["PreToolUse"]["model"], "trae-pro")
        self.assertEqual(by_event["PostToolUse"]["chars_in"], len(tool_response))
        self.assertEqual(by_event["Stop"]["chars_out"], len(final))
        self.assertEqual(by_event["Stop"]["loop"], 1)
        for row in rows:
            self.assertEqual(row["v"], 1)
            self.assertEqual(row["session"], "s1")
            self.assertEqual(row["project"], "proj")
            self.assertIsInstance(row["uid"], str)
            self.assertTrue(row["uid"])
        self.assertEqual(len({row["uid"] for row in rows}), 5)

        with open(files[0], encoding="utf-8") as fh:
            raw = fh.read()
        for secret in ("SECRET_PROMPT", "SECRET_FILE", "SECRET_TOOL_RESPONSE",
                       "SECRET_FINAL_ANSWER", "secret-work"):
            self.assertNotIn(secret, raw)
        for key in ("prompt", "tool_input", "tool_response",
                    "last_assistant_message", "cwd"):
            self.assertNotIn('"%s"' % key, raw)

    def test_invalid_input_exits_zero_without_writing(self):
        proc = subprocess.run([sys.executable, self.script], input=b"not json",
                              capture_output=True)
        self.assertEqual(proc.returncode, 0)
        proc = self.run_hook({"hook_event_name": "Unknown", "session_id": "s1"})
        self.assertEqual(proc.returncode, 0)
        files, rows = self.event_lines()
        self.assertEqual(files, [])
        self.assertEqual(rows, [])

    def test_capture_replays_through_collector(self):
        base = {"session_id": "s1", "cwd": "/tmp/work/proj"}
        for payload in (
            dict(base, hook_event_name="SessionStart", source="startup"),
            dict(base, hook_event_name="UserPromptSubmit", prompt="x" * 200),
            dict(base, hook_event_name="PreToolUse", tool_name="Read",
                 tool_use_id="t1", tool_input="y" * 120),
            dict(base, hook_event_name="PostToolUse", tool_name="Read",
                 tool_use_id="t1", tool_response="z" * 8000),
            dict(base, hook_event_name="Stop", last_assistant_message="w" * 300),
        ):
            self.assertEqual(self.run_hook(payload).returncode, 0)

        result = scan_trae_cn_est(home=self.home)
        self.assertTrue(result.available)
        self.assertEqual(len(result.estimates), 2)
        first, second = result.estimates
        self.assertEqual((first.est_input, first.est_output, first.chars_in,
                          first.chars_out), (53, 32, 200, 120))
        self.assertEqual((second.est_input, second.est_output, second.chars_in,
                          second.chars_out), (2189, 79, 8320, 300))
        self.assertEqual(first.source, "trae-cn.est")
        self.assertIsNone(first.ratio)
        self.assertEqual(first.project, "proj")


if __name__ == "__main__":
    unittest.main()
