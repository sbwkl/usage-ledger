import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.usage_ledger import scheduler


def completed(code=0, stderr=""):
    return subprocess.CompletedProcess([], code, "", stderr)


class SchedulerTest(unittest.TestCase):
    def test_plists_have_calendar_and_environment(self):
        sync = scheduler.build_plist("sync")
        self.assertEqual(sync["Label"], "local.usage-ledger.sync")
        self.assertEqual(sync["StartCalendarInterval"], {"Minute": 7})
        self.assertEqual(sync["ProgramArguments"][-1], "sync")
        self.assertTrue(sync["ProgramArguments"])

        full = scheduler.build_plist("full")
        self.assertEqual(full["StartCalendarInterval"], {"Hour": 0, "Minute": 15})
        self.assertEqual(full["ProgramArguments"][-1], "--full")

        prune = scheduler.build_plist("prune")
        self.assertEqual(prune["StartCalendarInterval"], {"Hour": 0, "Minute": 20})

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            messages = scheduler.install(launch_agents=target, dry_run=True)
            self.assertEqual(len(messages), 3)
            self.assertFalse(target.exists())

    def test_build_plist_includes_db_and_source_home(self):
        env = {"USAGE_LEDGER_DB": "/tmp/custom.db",
               "USAGE_LEDGER_HOME": "/tmp/ledger-home",
               "USAGE_LEDGER_SOURCE_HOME": "/tmp/sources",
               "PATH": "/custom/bin"}
        with patch.dict(os.environ, env, clear=True):
            plist = scheduler.build_plist("sync")
        variables = plist["EnvironmentVariables"]
        self.assertEqual(variables["USAGE_LEDGER_DB"], "/tmp/custom.db")
        self.assertEqual(variables["USAGE_LEDGER_HOME"], "/tmp/ledger-home")
        self.assertEqual(variables["USAGE_LEDGER_SOURCE_HOME"], "/tmp/sources")
        self.assertEqual(variables["PATH"], "/custom/bin")

        with patch.dict(os.environ, {}, clear=True):
            plist = scheduler.build_plist("sync")
        variables = plist["EnvironmentVariables"]
        self.assertNotIn("USAGE_LEDGER_DB", variables)
        self.assertEqual(variables["PATH"], "/usr/local/bin:/usr/bin:/bin")

    def test_plist_path_and_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self.assertEqual(scheduler.plist_path("sync", target),
                             target / "local.usage-ledger.sync.plist")
        rendered = scheduler.render("prune")
        self.assertIn("local.usage-ledger.prune", rendered)
        self.assertEqual(plistlib.loads(rendered.encode())["Label"],
                         "local.usage-ledger.prune")

    def test_launch_command_prefers_installed_script(self):
        with patch.object(scheduler.shutil, "which", return_value="/opt/bin/usage"):
            args, extra = scheduler._launch_command(["sync"])
        self.assertEqual(args, ["/opt/bin/usage", "sync"])
        self.assertEqual(extra, {})

        with patch.object(scheduler.shutil, "which", return_value=None):
            args, extra = scheduler._launch_command(["prune"])
        self.assertEqual(args, [sys.executable, "-m", "usage_ledger", "prune"])
        if scheduler.SOURCE_TREE:
            self.assertEqual(extra, {"PYTHONPATH": str(scheduler.ROOT / "src")})
        else:
            self.assertEqual(extra, {})

    def test_loaded_uses_launchctl_returncode(self):
        with patch.object(scheduler, "_launchctl", return_value=completed(0)):
            self.assertTrue(scheduler._loaded("local.usage-ledger.sync"))
        with patch.object(scheduler, "_launchctl", return_value=completed(1)):
            self.assertFalse(scheduler._loaded("local.usage-ledger.sync"))

    def test_install_writes_and_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            state = Path(tmp) / "state"
            with patch.object(scheduler, "STATE_DIR", state), \
                    patch.object(scheduler, "_launchctl", return_value=completed(0)):
                messages = scheduler.install(launch_agents=target)
            self.assertEqual(len(messages), 6)
            self.assertTrue(any(message.startswith("written") for message in messages))
            self.assertTrue(any(message.startswith("loaded") for message in messages))
            for name in scheduler.JOBS:
                self.assertTrue(scheduler.plist_path(name, target).exists())
            self.assertTrue(state.is_dir())

    def test_install_bootstrap_failure_uses_legacy_load(self):
        def fake_launchctl(*args):
            if args[0] == "print":
                return completed(1)
            if args[0] == "bootstrap":
                return completed(1, "bootstrap boom")
            return completed(0)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            with patch.object(scheduler, "STATE_DIR", Path(tmp) / "state"), \
                    patch.object(scheduler, "_launchctl", side_effect=fake_launchctl):
                messages = scheduler.install(launch_agents=target)
        self.assertEqual(sum("legacy load" in message for message in messages), 3)

    def test_install_load_failure_reports_error(self):
        def fake_launchctl(*args):
            if args[0] == "print":
                return completed(1)
            if args[0] == "bootstrap":
                return completed(1, "")
            return completed(1, "load denied")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            with patch.object(scheduler, "STATE_DIR", Path(tmp) / "state"), \
                    patch.object(scheduler, "_launchctl", side_effect=fake_launchctl):
                messages = scheduler.install(launch_agents=target)
        self.assertEqual(sum("load failed: load denied" in message
                             for message in messages), 3)

    def test_install_without_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            with patch.object(scheduler, "STATE_DIR", Path(tmp) / "state"), \
                    patch.object(scheduler, "_launchctl") as launchctl:
                messages = scheduler.install(launch_agents=target, load=False)
        self.assertEqual(len(messages), 3)
        self.assertTrue(all(message.startswith("written") for message in messages))
        launchctl.assert_not_called()

    def test_uninstall_unloads_and_removes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            target.mkdir()
            for name in scheduler.JOBS:
                scheduler.plist_path(name, target).write_text("plist")
            with patch.object(scheduler, "_launchctl",
                              return_value=completed(0)) as launchctl:
                messages = scheduler.uninstall(launch_agents=target)
            self.assertEqual(sum("unloaded" in message for message in messages), 3)
            self.assertEqual(sum("removed" in message for message in messages), 3)
            calls = [call.args[0] for call in launchctl.call_args_list]
            self.assertIn("bootout", calls)
            self.assertIn("unload", calls)
            self.assertFalse(any(scheduler.plist_path(name, target).exists()
                                 for name in scheduler.JOBS))

    def test_uninstall_without_loaded_or_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            with patch.object(scheduler, "_launchctl", return_value=completed(1)):
                messages = scheduler.uninstall(launch_agents=target)
        self.assertEqual(messages, [])

    def test_status_reports_installed_and_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "LaunchAgents"
            target.mkdir()
            scheduler.plist_path("sync", target).write_text("plist")
            with patch.object(scheduler, "_launchctl",
                              side_effect=[completed(0), completed(1), completed(1)]):
                rows = scheduler.status(launch_agents=target)
        self.assertEqual([row["job"] for row in rows], ["sync", "full", "prune"])
        self.assertTrue(rows[0]["installed"])
        self.assertTrue(rows[0]["loaded"])
        self.assertFalse(rows[1]["installed"])
        self.assertFalse(rows[1]["loaded"])


if __name__ == "__main__":
    unittest.main()
