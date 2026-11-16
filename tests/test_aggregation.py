import unittest
from datetime import datetime

from src.usage_ledger.aggregation import (_dim_value, aggregate, match,
                                          merge_records, missing_days,
                                          period_label)
from src.usage_ledger.models import Counts, Record


def make_record(key, source="claude", day="2026-10-01", model="m",
                project="proj", session="s1", value=10, cost=None,
                cost_source="unknown", turns=1):
    return Record(
        source=source, day=day, model=model, project=project, session=session,
        key=key, counts=Counts(input=value), ts=datetime.fromisoformat(day).timestamp(),
        cost=cost, cost_source=cost_source, turns=turns,
    )


class PeriodLabelTest(unittest.TestCase):
    def test_labels_for_each_period(self):
        self.assertEqual(period_label("2026-10-01", "day"), "2026-10-01")
        self.assertEqual(period_label("2026-10-01", "week"), "2026-W40")
        self.assertEqual(period_label("2026-10-01", "month"), "2026-10")


class DimensionValueTest(unittest.TestCase):
    def test_known_dimensions(self):
        rec = make_record("a", source="qoder", model="gfmodel",
                          project=None, session=None)
        self.assertEqual(_dim_value(rec, "day", "month"), "2026-10")
        self.assertEqual(_dim_value(rec, "week", "day"), "2026-W40")
        self.assertEqual(_dim_value(rec, "month", "week"), "2026-10")
        self.assertEqual(_dim_value(rec, "source", "day"), "qoder")
        self.assertEqual(_dim_value(rec, "model", "day"), "GLM-5.3-Flash")
        self.assertEqual(_dim_value(rec, "project", "day"), "-")
        self.assertEqual(_dim_value(rec, "session", "day"), "-")

    def test_non_qoder_model_is_not_mapped(self):
        rec = make_record("a", source="claude", model="gfmodel")
        self.assertEqual(_dim_value(rec, "model", "day"), "gfmodel")

    def test_unknown_dimension_raises(self):
        with self.assertRaises(ValueError):
            _dim_value(make_record("a"), "bogus", "day")


class AggregateTest(unittest.TestCase):
    def test_known_cost_uses_dominant_source(self):
        rows = aggregate([
            make_record("a", model="m1", value=10, cost=1.5,
                        cost_source="pricing", turns=2),
            make_record("b", model="m1", value=5, cost=0.5,
                        cost_source="pricing", turns=1),
        ], dims=("day", "source", "model"))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["dims"], ("2026-10-01", "claude", "m1"))
        self.assertEqual(row["input"], 15)
        self.assertEqual(row["total"], 15)
        self.assertEqual(row["turns"], 3)
        self.assertEqual(row["cost_equiv_usd"], 2.0)
        self.assertEqual(row["cost_source"], "pricing")

    def test_unknown_and_partial_cost(self):
        unknown = aggregate([make_record("a", model="m1"),
                             make_record("b", model="m1", value=3)])
        self.assertIsNone(unknown[0]["cost_equiv_usd"])
        self.assertEqual(unknown[0]["cost_source"], "unknown")

        partial = aggregate([
            make_record("a", model="m1", value=10, cost=1.0,
                        cost_source="pricing", turns=2),
            make_record("b", model="m1", value=5, turns=1),
        ])
        self.assertEqual(partial[0]["cost_equiv_usd"], 1.0)
        self.assertEqual(partial[0]["cost_source"], "partial")

    def test_month_period_and_multiple_buckets(self):
        rows = aggregate([
            make_record("a", day="2026-10-01", model="m1"),
            make_record("b", day="2026-10-31", model="m1", value=5),
            make_record("c", day="2026-11-01", model="m2", source="codex"),
        ], dims=("month", "source"), period="month")
        self.assertEqual([row["dims"] for row in rows],
                         [("2026-10", "claude"), ("2026-11", "codex")])
        self.assertEqual([row["turns"] for row in rows], [2, 1])


class MatchTest(unittest.TestCase):
    def test_project_and_filters(self):
        rec = make_record("a", source="claude", model="m1", project="p1", session="s1")
        self.assertTrue(match(rec))
        self.assertTrue(match(rec, project="p1"))
        self.assertFalse(match(rec, project="p2"))
        self.assertTrue(match(rec, {"source": "claude", "model": "m1",
                                    "project": "p1", "session": "s1"}))
        self.assertFalse(match(rec, {"source": "codex"}))
        self.assertFalse(match(rec, {"model": "m2"}))
        self.assertFalse(match(rec, {"project": "p2"}))
        self.assertFalse(match(rec, {"session": "s2"}))
        self.assertTrue(match(rec, {"unknown": "ignored"}))

    def test_missing_project_and_session_match_empty_filter(self):
        rec = make_record("a", project=None, session=None)
        self.assertTrue(match(rec, {"project": "", "session": ""}))

    def test_qoder_model_filter_accepts_display_label(self):
        rec = make_record("a", source="qoder", model="gfmodel")
        self.assertTrue(match(rec, {"model": "GLM-5.3-Flash"}))
        self.assertFalse(match(rec, {"model": "Auto"}))


class MergeTest(unittest.TestCase):
    def test_source_records_override_same_key(self):
        db = [make_record("a", value=10), make_record("b", value=20)]
        fresh = [make_record("b", value=99), make_record("c", value=30)]
        merged = {rec.key: rec for rec in merge_records(db, fresh)}
        self.assertEqual(sorted(merged), ["a", "b", "c"])
        self.assertEqual(merged["b"].counts.input, 99)
        self.assertEqual(merged["a"].counts.input, 10)


class MissingDaysTest(unittest.TestCase):
    def test_requires_both_bounds(self):
        records = [make_record("a", day="2026-10-01")]
        self.assertEqual(missing_days(records, None, "2026-10-03"), [])
        self.assertEqual(missing_days(records, "2026-10-01", None), [])

    def test_reports_gaps_inclusive(self):
        records = [make_record("a", day="2026-10-01"),
                   make_record("b", day="2026-10-03")]
        self.assertEqual(missing_days(records, "2026-10-01", "2026-10-04"),
                         ["2026-10-02", "2026-10-04"])
