from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from .models import FIELDS, Record
from .qoder_models import qoder_model_label

DIMENSIONS = ("day", "week", "month", "source", "model", "project", "session")


def period_label(day: str, period: str) -> str:
    if period == "week":
        iso = date.fromisoformat(day).isocalendar()
        return "%d-W%02d" % (iso[0], iso[1])
    if period == "month":
        return day[:7]
    return day


def _dim_value(rec: Record, dim: str, period: str) -> str:
    if dim == "day":
        return period_label(rec.day, period)
    if dim == "week":
        return period_label(rec.day, "week")
    if dim == "month":
        return period_label(rec.day, "month")
    if dim == "source":
        return rec.source
    if dim == "model":
        return qoder_model_label(rec.model) if rec.source == "qoder" else rec.model
    if dim == "project":
        return rec.project or "-"
    if dim == "session":
        return rec.session or "-"
    raise ValueError("unknown dimension: %s" % dim)


def aggregate(records: list[Record], dims: tuple[str, ...] = ("day", "source", "model"),
              period: str = "day") -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for rec in records:
        key = tuple(_dim_value(rec, dim, period) for dim in dims)
        row = buckets.get(key)
        if row is None:
            row = {"dims": key, "cost": 0.0, "cost_known_turns": 0,
                   "cost_sources": Counter(), "turns": 0}
            for field in FIELDS:
                row[field] = 0
            buckets[key] = row
        for field in FIELDS:
            row[field] += getattr(rec.counts, field)
        row["turns"] += rec.turns
        if rec.cost is not None:
            row["cost"] += rec.cost
            row["cost_known_turns"] += rec.turns
            row["cost_sources"][rec.cost_source] += 1

    rows = []
    for key in sorted(buckets):
        bucket = buckets[key]
        if bucket["cost_known_turns"] == 0:
            cost, cost_source = None, "unknown"
        elif bucket["cost_known_turns"] == bucket["turns"]:
            cost, cost_source = bucket["cost"], bucket["cost_sources"].most_common(1)[0][0]
        else:
            cost, cost_source = bucket["cost"], "partial"
        row = {"dims": key, "cost_equiv_usd": cost, "cost_source": cost_source,
               "turns": bucket["turns"]}
        for field in FIELDS:
            row[field] = bucket[field]
        row["total"] = sum(bucket[field] for field in FIELDS)
        rows.append(row)
    return rows


def match(rec: Record, filters: dict[str, str] | None = None, project: str | None = None) -> bool:
    if project and (rec.project or "") != project:
        return False
    for key, value in (filters or {}).items():
        if key == "source" and rec.source != value:
            return False
        if key == "model" and rec.model != value:
            if not (rec.source == "qoder" and qoder_model_label(rec.model) == value):
                return False
        if key == "project" and (rec.project or "") != value:
            return False
        if key == "session" and (rec.session or "") != value:
            return False
    return True


def merge_records(db_records: list[Record], source_records: list[Record]) -> list[Record]:
    merged = {rec.key: rec for rec in db_records}
    for rec in source_records:
        merged[rec.key] = rec
    return list(merged.values())


def missing_days(records: list[Record], since: str | None, until: str | None) -> list[str]:
    if not since or not until:
        return []
    present = {rec.day for rec in records}
    start, end = date.fromisoformat(since), date.fromisoformat(until)
    days = []
    cursor = start
    while cursor <= end:
        label = cursor.isoformat()
        if label not in present:
            days.append(label)
        cursor += timedelta(days=1)
    return days
