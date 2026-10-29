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
class SourceResult:
    name: str
    files: int = 0
    raw: int = 0
    available: bool = True
    complete: bool = True
    records: list[Record] = field(default_factory=list)
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
