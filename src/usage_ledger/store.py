from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

from .models import Counts, Record

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS source_state (
  source TEXT PRIMARY KEY,
  parser_version INTEGER NOT NULL,
  last_sync_at TEXT,
  last_event_ts REAL,
  last_file_mtime REAL,
  files_seen INTEGER DEFAULT 0,
  records_total INTEGER DEFAULT 0,
  status TEXT,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS usage_turn (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  event_ts REAL NOT NULL,
  day TEXT NOT NULL,
  project TEXT,
  session_id TEXT,
  agent TEXT,
  provider TEXT,
  model TEXT NOT NULL,
  model_raw TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read INTEGER NOT NULL DEFAULT 0,
  cache_write INTEGER NOT NULL DEFAULT 0,
  reasoning INTEGER NOT NULL DEFAULT 0,
  cost_equiv_usd REAL,
  cost_source TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turn_day_source ON usage_turn(day, source);
CREATE INDEX IF NOT EXISTS idx_turn_model ON usage_turn(model);
CREATE INDEX IF NOT EXISTS idx_turn_project ON usage_turn(project);
CREATE INDEX IF NOT EXISTS idx_turn_archived ON usage_turn(archived);
CREATE TABLE IF NOT EXISTS usage_daily (
  day TEXT NOT NULL, source TEXT NOT NULL, model TEXT NOT NULL,
  project TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL DEFAULT '',
  input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read INTEGER NOT NULL DEFAULT 0, cache_write INTEGER NOT NULL DEFAULT 0,
  reasoning INTEGER NOT NULL DEFAULT 0, cost_equiv_usd REAL,
  cost_source TEXT, turn_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, source, model, project, session_id)
);
CREATE TABLE IF NOT EXISTS price_override (
  model_pattern TEXT PRIMARY KEY, input REAL, output REAL,
  cache_read REAL, cache_write REAL, reasoning REAL, currency TEXT DEFAULT 'USD',
  note TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

CHUNK = 500


def _chunks(values: list[str]):
    for i in range(0, len(values), CHUNK):
        yield values[i:i + CHUNK]


class SqliteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, timeout=5)
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def upsert_records(self, records: list[Record], cost_fn=None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        n = 0
        for rec in records:
            if cost_fn:
                cost, cost_source = cost_fn(rec)
            else:
                cost, cost_source = rec.cost, rec.cost_source
            self.conn.execute(
                """INSERT INTO usage_turn
                (id,source,event_ts,day,project,session_id,agent,provider,model,model_raw,
                 input_tokens,output_tokens,cache_read,cache_write,reasoning,
                 cost_equiv_usd,cost_source,archived,first_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)
                ON CONFLICT(id) DO UPDATE SET
                 event_ts=excluded.event_ts, day=excluded.day, project=excluded.project,
                 session_id=excluded.session_id, model=excluded.model, model_raw=excluded.model_raw,
                 input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                 cache_read=excluded.cache_read, cache_write=excluded.cache_write,
                 reasoning=excluded.reasoning, cost_equiv_usd=excluded.cost_equiv_usd,
                 cost_source=excluded.cost_source, archived=0""",
                (rec.key, rec.source, rec.ts, rec.day, rec.project, rec.session, rec.agent,
                 rec.provider, rec.model, rec.model_raw or rec.model, rec.counts.input,
                 rec.counts.output, rec.counts.cache_read, rec.counts.cache_write,
                 rec.counts.reasoning, cost, cost_source, now),
            )
            n += 1
        self.conn.commit()
        return n

    def mark_archived(self, source: str, seen_keys: set[str]) -> tuple[int, int]:
        rows = self.conn.execute(
            "SELECT id, archived FROM usage_turn WHERE source=?", (source,)
        ).fetchall()
        archive = [row[0] for row in rows if row[0] not in seen_keys and not row[1]]
        restore = [row[0] for row in rows if row[0] in seen_keys and row[1]]
        for chunk in _chunks(archive):
            marks = ",".join("?" for _ in chunk)
            self.conn.execute(
                f"UPDATE usage_turn SET archived=1 WHERE id IN ({marks})", chunk
            )
        for chunk in _chunks(restore):
            marks = ",".join("?" for _ in chunk)
            self.conn.execute(
                f"UPDATE usage_turn SET archived=0 WHERE id IN ({marks})", chunk
            )
        self.conn.commit()
        return len(archive), len(restore)

    def update_source_state(self, source: str, files: int, records: int,
                            status: str = "ok", error: str | None = None,
                            last_ts: float | None = None):
        self.conn.execute(
            """INSERT INTO source_state
            (source,parser_version,last_sync_at,last_event_ts,files_seen,records_total,status,last_error)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(source) DO UPDATE SET
             last_sync_at=excluded.last_sync_at, last_event_ts=excluded.last_event_ts,
             files_seen=excluded.files_seen, records_total=excluded.records_total,
             status=excluded.status, last_error=excluded.last_error""",
            (source, 1, datetime.now(timezone.utc).isoformat(), last_ts, files, records,
             status, error),
        )
        self.conn.commit()

    def set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def fetch_records(self, since: str | None = None, until: str | None = None,
                      source: str | None = None, model: str | None = None,
                      project: str | None = None, include_daily: bool = True) -> list[Record]:
        params = []
        clauses = []
        if since:
            clauses.append("day >= ?")
            params.append(since)
        if until:
            clauses.append("day <= ?")
            params.append(until)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if model:
            clauses.append("model = ?")
            params.append(model)
        if project:
            clauses.append("project = ?")
            params.append(project)
        where_sql = " AND ".join(clauses) if clauses else "1=1"

        records = []
        for row in self.conn.execute(
            f"""SELECT id,source,event_ts,day,project,session_id,agent,provider,model,model_raw,
                input_tokens,output_tokens,cache_read,cache_write,reasoning,cost_equiv_usd,cost_source
                FROM usage_turn WHERE {where_sql}""",
            params,
        ):
            records.append(Record(
                source=row[1], day=row[3], model=row[8], project=row[4], session=row[5],
                key=row[0],
                counts=Counts(input=row[10], output=row[11], cache_read=row[12],
                              cache_write=row[13], reasoning=row[14]),
                ts=row[2], model_raw=row[9], provider=row[7], agent=row[6],
                cost=row[15], cost_source=row[16] or "unknown",
            ))

        if include_daily:
            for row in self.conn.execute(
                f"""SELECT day,source,model,project,session_id,input_tokens,output_tokens,
                    cache_read,cache_write,reasoning,cost_equiv_usd,cost_source,turn_count
                    FROM usage_daily WHERE {where_sql}""",
                params,
            ):
                day = row[0]
                ts = datetime.fromisoformat(day).timestamp()
                records.append(Record(
                    source=row[1], day=day, model=row[2], project=row[3] or None,
                    session=row[4] or None,
                    key="daily:%s:%s:%s:%s:%s" % (day, row[1], row[2], row[3], row[4]),
                    counts=Counts(input=row[5], output=row[6], cache_read=row[7],
                                  cache_write=row[8], reasoning=row[9]),
                    ts=ts, cost=row[10], cost_source=row[11] or "unknown",
                    turns=row[12] or 1,
                ))
        return records

    def prune(self, keep_days: int = 90, dry_run: bool = False) -> dict:
        cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
        old = self.conn.execute(
            "SELECT COUNT(*) FROM usage_turn WHERE day < ? AND archived=0", (cutoff,)
        ).fetchone()[0]
        kept = self.conn.execute(
            "SELECT COUNT(*) FROM usage_turn WHERE day < ? AND archived=1", (cutoff,)
        ).fetchone()[0]
        if dry_run or old == 0:
            return {"cutoff": cutoff, "deleted": 0, "kept_archived": kept, "candidate": old}
        self.conn.execute("BEGIN")
        self.conn.execute(
            """INSERT INTO usage_daily
            (day,source,model,project,session_id,input_tokens,output_tokens,cache_read,
             cache_write,reasoning,cost_equiv_usd,cost_source,turn_count)
            SELECT day,source,model,COALESCE(project,''),COALESCE(session_id,''),
             SUM(input_tokens),SUM(output_tokens),SUM(cache_read),SUM(cache_write),
             SUM(reasoning),SUM(cost_equiv_usd),MAX(cost_source),COUNT(*)
            FROM usage_turn WHERE day < ? AND archived=0
            GROUP BY day,source,model,project,session_id
            ON CONFLICT(day,source,model,project,session_id) DO UPDATE SET
             input_tokens=usage_daily.input_tokens+excluded.input_tokens,
             output_tokens=usage_daily.output_tokens+excluded.output_tokens,
             cache_read=usage_daily.cache_read+excluded.cache_read,
             cache_write=usage_daily.cache_write+excluded.cache_write,
             reasoning=usage_daily.reasoning+excluded.reasoning,
             cost_equiv_usd=COALESCE(usage_daily.cost_equiv_usd,0)+COALESCE(excluded.cost_equiv_usd,0),
             cost_source=COALESCE(excluded.cost_source,usage_daily.cost_source),
             turn_count=usage_daily.turn_count+excluded.turn_count""",
            (cutoff,),
        )
        cur = self.conn.execute(
            "DELETE FROM usage_turn WHERE day < ? AND archived=0", (cutoff,)
        )
        self.conn.commit()
        return {"cutoff": cutoff, "deleted": cur.rowcount, "kept_archived": kept,
                "candidate": old}

    def archived_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM usage_turn WHERE archived=1"
        ).fetchone()[0]

    def turn_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM usage_turn").fetchone()[0]

    def daily_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM usage_daily").fetchone()[0]

    def source_states(self):
        return self.conn.execute(
            """SELECT source,status,files_seen,records_total,last_sync_at,last_error
            FROM source_state ORDER BY source"""
        ).fetchall()

    def source_totals(self) -> dict[str, int]:
        return {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT source, COUNT(*) FROM usage_turn GROUP BY source"
            )
        }

    def wal_size(self) -> int:
        try:
            return os.path.getsize(self.db_path + "-wal")
        except OSError:
            return 0

    def db_size(self) -> int:
        try:
            return os.path.getsize(self.db_path)
        except OSError:
            return 0
