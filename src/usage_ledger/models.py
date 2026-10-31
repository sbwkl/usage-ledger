from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict


FIELDS = ("input", "output", "cache_read", "cache_write", "reasoning")


@dataclass
class Counts:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {f: getattr(self, f) for f in FIELDS}

    def total(self) -> int:
        return sum(getattr(self, f) for f in FIELDS)


@dataclass
class Record:
    source: str
    day: str
    model: str
    project: str | None
    session: str | None
    key: str
    counts: Counts
    ts: float
    model_raw: str | None = None
    provider: str | None = None
    agent: str | None = None
    sidechain: bool = False
    cost: float | None = None
    cost_source: str = "unknown"
    turns: int = 1


@dataclass
class Activity:
    day: str
    project: str = ""
    sessions: int = 0
    prompts: int = 0
    assistant_calls: int = 0
    assistant_with_metrics: int = 0
    turns: int = 0
    tool_calls: int = 0
    duration_ms: int = 0
    source: str = "qoder.activity"


@dataclass
class Credit:
    request_id: str
    ts: float
    day: str
    project: str
    model: str
    session: str
    credits: float
    billable: bool


@dataclass
class QuotaSnapshot:
    request_id: str
    ts: float
    day: str
    quota_kind: str
    total: int
    used: int
    remaining: int
    unit: str
    raw_pct: float | None
    expires_at: int | None


@dataclass
class Estimate:
    request_id: str
    ts: float
    day: str
    project: str
    model: str
    session: str
    est_input: int
    est_output: int
    chars_in: int
    chars_out: int
    ratio: float | None


ACTIVITY_FIELDS = ("sessions", "prompts", "assistant_calls",
                   "assistant_with_metrics", "turns", "tool_calls", "duration_ms")


@dataclass
class SourceResult:
    name: str
    files: int = 0
    raw: int = 0
    available: bool = True
    complete: bool = True
    records: list[Record] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    credits: list[Credit] = field(default_factory=list)
    quota: list[QuotaSnapshot] = field(default_factory=list)
    estimates: list[Estimate] = field(default_factory=list)
    transcript_state: dict | None = None
    affected_days: set[str] = field(default_factory=set)
    cursor_ms: int | None = None
    errors: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    seen_keys: set[str] = field(default_factory=set)
    dup_dropped: int = 0
    key_kinds: Counter = field(default_factory=Counter)
    _index: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def healthy(self) -> bool:
        return self.available and self.complete and not self.errors

    def add(self, rec: Record) -> None:
        self.raw += 1
        prev_idx = self._index.get(rec.key)
        if prev_idx is not None:
            self.dup_dropped += 1
            prev = self.records[prev_idx]
            if rec.counts.total() > prev.counts.total():
                self.records[prev_idx] = rec
            return
        self._index[rec.key] = len(self.records)
        self.records.append(rec)
