import os
import tempfile
import unittest
from datetime import date, datetime

from src.usage_ledger.models import Counts, Record
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
