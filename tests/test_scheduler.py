import tempfile
import unittest
from pathlib import Path

from src.usage_ledger import scheduler


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


if __name__ == "__main__":
    unittest.main()
