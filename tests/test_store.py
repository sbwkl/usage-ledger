import os
import tempfile
import unittest
from datetime import date, datetime

from src.usage_ledger.models import Activity, Counts, Credit, Estimate, QuotaSnapshot, Record
from src.usage_ledger.store import SqliteStore


def make_record(key, source="claude", day="2026-10-01", model="m", value=10,
                project="proj", session="s1"):
    return Record(
        source=source, day=day, model=model, project=project, session=session,
        key=key, counts=Counts(input=value), ts=datetime.fromisoformat(day).timestamp(),
    )


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = SqliteStore(os.path.join(self.dir.name, "usage.db"))

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def test_upsert_is_idempotent(self):
        records = [make_record("a"), make_record("b", value=20)]
        self.store.upsert_records(records)
        self.store.upsert_records(records)
        self.assertEqual(self.store.turn_count(), 2)
        total = sum(rec.counts.input for rec in self.store.fetch_records())
        self.assertEqual(total, 30)

        self.store.upsert_records([make_record("a", value=50)])
        self.assertEqual(self.store.turn_count(), 2)
        total = sum(rec.counts.input for rec in self.store.fetch_records())
        self.assertEqual(total, 70)

    def test_mark_archived_and_restore(self):
        self.store.upsert_records([make_record("a"), make_record("b"), make_record("c")])
        archived, restored = self.store.mark_archived("claude", {"a", "b"})
        self.assertEqual((archived, restored), (1, 0))
        self.assertEqual(self.store.archived_count(), 1)

        archived, restored = self.store.mark_archived("claude", {"a"})
        self.assertEqual((archived, restored), (1, 0))
        self.assertEqual(self.store.archived_count(), 2)

        archived, restored = self.store.mark_archived("claude", {"a", "b", "c"})
        self.assertEqual((archived, restored), (0, 2))
        self.assertEqual(self.store.archived_count(), 0)

    def test_prune_rolls_up_and_keeps_archived_detail(self):
        old_prunable = make_record("old-ok", source="codex", day="2020-01-01", value=10)
        old_archived = make_record("old-arch", source="claude", day="2020-01-02", value=20)
        recent = make_record("recent", source="codex", day=date.today().isoformat(), value=30)
        self.store.upsert_records([old_prunable, old_archived, recent])
        self.store.mark_archived("claude", set())

        preview = self.store.prune(keep_days=30, dry_run=True)
        self.assertEqual(preview["candidate"], 1)
        self.assertEqual(preview["kept_archived"], 1)
        self.assertEqual(self.store.turn_count(), 3)
        self.assertEqual(self.store.daily_count(), 0)

        stats = self.store.prune(keep_days=30)
        self.assertEqual(stats["deleted"], 1)
        self.assertEqual(self.store.turn_count(), 2)
        self.assertEqual(self.store.daily_count(), 1)

        records = self.store.fetch_records()
        self.assertEqual(sum(rec.counts.input for rec in records), 60)
        self.assertEqual(len(records), 3)

        self.store.prune(keep_days=30)
        records = self.store.fetch_records()
        self.assertEqual(sum(rec.counts.input for rec in records), 60)
        self.assertEqual(len(records), 3)

    def test_activity_replace_is_per_day(self):
        def act(day, project, tool, sessions=1, prompts=1, assistant=1, metrics=1,
                turns=2, duration=100):
            return Activity(day=day, project=project, sessions=sessions, prompts=prompts,
                            assistant_calls=assistant, assistant_with_metrics=metrics,
                            turns=turns, tool_calls=tool, duration_ms=duration)

        self.assertEqual(self.store.replace_activity_days(
            "qoder.activity", {"2026-10-01"},
            [act("2026-10-01", "a", 10), act("2026-10-01", "b", 5)]), 2)
        self.assertEqual(self.store.activity_count("qoder.activity"), 2)

        self.assertEqual(self.store.replace_activity_days(
            "qoder.activity", {"2026-10-01"}, [act("2026-10-01", "a", 20)]), 1)
        self.assertEqual(self.store.activity_count("qoder.activity"), 1)
        rows = self.store.fetch_activity()
        self.assertEqual([(row.day, row.project, row.tool_calls) for row in rows],
                         [("2026-10-01", "a", 20)])

        self.store.replace_activity_days("qoder.activity", {"2026-10-02"},
                                         [act("2026-10-02", "a", 1)])
        self.store.replace_activity_days("qoder.activity", {"2026-10-02"},
                                         [act("2026-10-02", "a", 2)])
        self.assertEqual(self.store.activity_count("qoder.activity"), 2)
        self.assertEqual([row.day for row in self.store.fetch_activity(since="2026-10-02")],
                         ["2026-10-02"])
        self.assertEqual([row.day for row in self.store.fetch_activity(project="a")],
                         ["2026-10-01", "2026-10-02"])
        self.assertEqual(self.store.activity_bounds("qoder.activity"),
                         ("2026-10-01", "2026-10-02"))
        summary = self.store.activity_summary("qoder.activity")
        self.assertEqual((summary["days"], summary["tool_calls"]), (2, 22))

        self.store.replace_activity_days("qoder.activity", {"2026-10-01"},
                                         [act("2026-10-01", "a", 20)])
        self.assertEqual(self.store.activity_count("qoder.activity"), 2)

    def test_credits_quota_and_estimates(self):
        def credit(rid, day, value, billable, model="gfmodel"):
            return Credit(request_id=rid, ts=datetime.fromisoformat(day).timestamp(),
                          day=day, project="proj", model=model, session="s1",
                          credits=value, billable=billable)

        credits = [
            credit("r1", "2026-10-01", 2.5, True),
            credit("r2", "2026-10-01", 1.0, False),
            credit("r3", "2026-10-02", 3.25, True),
        ]
        quota = [
            QuotaSnapshot(request_id="q1", ts=datetime.fromisoformat("2026-10-01").timestamp(),
                          day="2026-10-01", quota_kind="add_on", total=2300, used=100,
                          remaining=2200, unit="credits", raw_pct=0.04,
                          expires_at=253402214400000),
            QuotaSnapshot(request_id="q2", ts=datetime.fromisoformat("2026-10-02").timestamp(),
                          day="2026-10-02", quota_kind="add_on", total=2300, used=150,
                          remaining=2150, unit="credits", raw_pct=0.06,
                          expires_at=253402214400000),
        ]
        self.assertEqual(self.store.upsert_credits(credits, quota), (3, 2))
        self.assertEqual(self.store.upsert_credits(credits, quota), (3, 2))
        self.assertEqual(self.store.credit_count(), 3)
        self.assertEqual(self.store.quota_count(), 2)

        daily = self.store.credit_daily()
        self.assertEqual([(row["day"], row["credits"], row["requests"],
                           row["free_credits"]) for row in daily],
                         [("2026-10-01", 2.5, 1, 1.0), ("2026-10-02", 3.25, 1, 0.0)])
        totals = self.store.credits_totals()
        self.assertEqual((totals["credits"], totals["free_credits"], totals["requests"]),
                         (5.75, 1.0, 3))
        latest = self.store.latest_quota()
        self.assertEqual(latest["add_on"]["used"], 150)
        self.assertEqual(latest["add_on"]["remaining"], 2150)
        self.assertEqual(self.store.credit_bounds()[0:2], ("2026-10-01", "2026-10-02"))

        estimates = [
            Estimate(request_id="s1:t1", ts=1.0, day="2026-10-01", project="proj",
                     model="gfmodel", session="s1", est_input=50000, est_output=10,
                     chars_in=100, chars_out=38, ratio=0.25),
            Estimate(request_id="s1:t2", ts=2.0, day="2026-10-01", project="proj",
                     model="dfmodel", session="s1", est_input=20000, est_output=5,
                     chars_in=50, chars_out=23, ratio=None),
        ]
        self.assertEqual(self.store.upsert_estimates(estimates), 2)
        self.assertEqual(self.store.upsert_estimates(estimates), 2)
        self.assertEqual(self.store.est_count(), 2)
        self.assertEqual(self.store.est_missing_ratio(), 1)
        est_rows = self.store.est_rows(dims=("day", "model"))
        self.assertEqual(len(est_rows), 2)
        gf = next(row for row in est_rows if row["model"] == "gfmodel")
        self.assertEqual((gf["est_input"], gf["est_output"], gf["missing_ratio"]),
                         (50000, 10, 0))
        totals = self.store.est_totals()
        self.assertEqual((totals["est_input"], totals["est_output"],
                          totals["requests"], totals["missing_ratio"]),
                         (70000, 15, 2, 1))
        self.assertEqual(self.store.est_bounds()[0:2], ("2026-10-01", "2026-10-01"))

    def test_source_state_roundtrip(self):
        self.store.update_source_state("claude", files=2, records=3, status="ok",
                                       last_ts=123.0)
        rows = self.store.source_states()
        self.assertEqual(rows[0][0], "claude")
        self.assertEqual(rows[0][1], "ok")
        self.assertEqual(rows[0][2], 2)
        self.assertEqual(rows[0][3], 3)


if __name__ == "__main__":
    unittest.main()
