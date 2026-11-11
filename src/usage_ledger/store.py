from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

from .models import Activity, Counts, Record

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
CREATE TABLE IF NOT EXISTS usage_activity (
  source TEXT NOT NULL,
  day TEXT NOT NULL,
  project TEXT NOT NULL DEFAULT '',
  sessions INTEGER NOT NULL DEFAULT 0,
  prompts INTEGER NOT NULL DEFAULT 0,
  assistant_calls INTEGER NOT NULL DEFAULT 0,
  assistant_with_metrics INTEGER NOT NULL DEFAULT 0,
  turns INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  PRIMARY KEY (source, day, project)
);
CREATE INDEX IF NOT EXISTS idx_activity_day_source ON usage_activity(day, source);
CREATE TABLE IF NOT EXISTS price_override (
  model_pattern TEXT PRIMARY KEY, input REAL, output REAL,
  cache_read REAL, cache_write REAL, reasoning REAL, currency TEXT DEFAULT 'USD',
  note TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS usage_credit (
  request_id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  day TEXT NOT NULL,
  project TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL,
  session_id TEXT,
  credits REAL NOT NULL DEFAULT 0,
  billable INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credit_day ON usage_credit(day);
CREATE TABLE IF NOT EXISTS usage_quota (
  request_id TEXT NOT NULL,
  quota_kind TEXT NOT NULL,
  ts REAL NOT NULL,
  day TEXT NOT NULL,
  total INTEGER NOT NULL,
  used INTEGER NOT NULL,
  remaining INTEGER NOT NULL,
  unit TEXT NOT NULL,
  raw_pct REAL,
  expires_at INTEGER,
  PRIMARY KEY (request_id, quota_kind)
);
CREATE INDEX IF NOT EXISTS idx_quota_day ON usage_quota(day, quota_kind);
CREATE TABLE IF NOT EXISTS usage_est (
  request_id TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'qoder.est',
  ts REAL NOT NULL,
  day TEXT NOT NULL,
  project TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL,
  session_id TEXT,
  est_input INTEGER NOT NULL DEFAULT 0,
  est_output INTEGER NOT NULL DEFAULT 0,
  chars_in INTEGER NOT NULL DEFAULT 0,
  chars_out INTEGER NOT NULL DEFAULT 0,
  ratio REAL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_est_day ON usage_est(day);
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
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(usage_est)")}
        if "source" not in columns:
            self.conn.execute(
                "ALTER TABLE usage_est ADD COLUMN source TEXT NOT NULL DEFAULT 'qoder.est'")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_est_source_day ON usage_est(source, day)")

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
                            last_ts: float | None = None,
                            last_mtime: int | None = None):
        self.conn.execute(
            """INSERT INTO source_state
            (source,parser_version,last_sync_at,last_event_ts,last_file_mtime,
             files_seen,records_total,status,last_error)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source) DO UPDATE SET
             last_sync_at=excluded.last_sync_at, last_event_ts=excluded.last_event_ts,
             last_file_mtime=excluded.last_file_mtime,
             files_seen=excluded.files_seen, records_total=excluded.records_total,
             status=excluded.status, last_error=excluded.last_error""",
            (source, 1, datetime.now(timezone.utc).isoformat(), last_ts, last_mtime,
             files, records, status, error),
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

    def replace_activity_days(self, source: str, days, activities: list[Activity]) -> int:
        targets = set(days) | {act.day for act in activities}
        if not targets:
            return 0
        now = datetime.now(timezone.utc).timestamp()
        self.conn.execute("BEGIN")
        for day in sorted(targets):
            self.conn.execute(
                "DELETE FROM usage_activity WHERE source=? AND day=?", (source, day))
        n = 0
        for act in activities:
            self.conn.execute(
                """INSERT OR REPLACE INTO usage_activity
                (source,day,project,sessions,prompts,assistant_calls,assistant_with_metrics,
                 turns,tool_calls,duration_ms,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (source, act.day, act.project, act.sessions, act.prompts,
                 act.assistant_calls, act.assistant_with_metrics, act.turns,
                 act.tool_calls, act.duration_ms, now),
            )
            n += 1
        self.conn.commit()
        return n

    def fetch_activity(self, since: str | None = None, until: str | None = None,
                       source: str | None = None,
                       project: str | None = None) -> list[Activity]:
        clauses, params = [], []
        if since:
            clauses.append("day >= ?")
            params.append(since)
        if until:
            clauses.append("day <= ?")
            params.append(until)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if project is not None:
            clauses.append("project = ?")
            params.append(project)
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        return [
            Activity(
                source=row[0], day=row[1], project=row[2], sessions=row[3],
                prompts=row[4], assistant_calls=row[5], assistant_with_metrics=row[6],
                turns=row[7], tool_calls=row[8], duration_ms=row[9])
            for row in self.conn.execute(
                f"""SELECT source,day,project,sessions,prompts,assistant_calls,
                    assistant_with_metrics,turns,tool_calls,duration_ms
                    FROM usage_activity WHERE {where_sql} ORDER BY day, project""",
                params)
        ]

    def source_bounds(self, source: str) -> tuple[str | None, str | None]:
        row = self.conn.execute(
            "SELECT MIN(day), MAX(day) FROM usage_turn WHERE source=?", (source,)
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def activity_bounds(self, source: str) -> tuple[str | None, str | None]:
        row = self.conn.execute(
            "SELECT MIN(day), MAX(day) FROM usage_activity WHERE source=?", (source,)
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def activity_summary(self, source: str) -> dict:
        row = self.conn.execute(
            """SELECT COUNT(DISTINCT day), COALESCE(SUM(sessions),0), COALESCE(SUM(prompts),0),
               COALESCE(SUM(assistant_calls),0), COALESCE(SUM(assistant_with_metrics),0),
               COALESCE(SUM(turns),0), COALESCE(SUM(tool_calls),0),
               COALESCE(SUM(duration_ms),0)
               FROM usage_activity WHERE source=?""", (source,)
        ).fetchone()
        return dict(zip(("days", "sessions", "prompts", "assistant_calls",
                         "assistant_with_metrics", "turns", "tool_calls",
                         "duration_ms"), row))

    def activity_count(self, source: str | None = None) -> int:
        if source:
            return self.conn.execute(
                "SELECT COUNT(*) FROM usage_activity WHERE source=?", (source,)
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM usage_activity").fetchone()[0]

    def upsert_credits(self, credits, quota) -> tuple[int, int]:
        now = datetime.now(timezone.utc).timestamp()
        for row in credits:
            self.conn.execute(
                """INSERT INTO usage_credit
                (request_id,ts,day,project,model,session_id,credits,billable,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(request_id) DO UPDATE SET
                 ts=excluded.ts, day=excluded.day, project=excluded.project,
                 model=excluded.model, session_id=excluded.session_id,
                 credits=excluded.credits, billable=excluded.billable,
                 updated_at=excluded.updated_at""",
                (row.request_id, row.ts, row.day, row.project, row.model,
                 row.session, row.credits, 1 if row.billable else 0, now))
        for row in quota:
            self.conn.execute(
                """INSERT INTO usage_quota
                (request_id,quota_kind,ts,day,total,used,remaining,unit,raw_pct,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(request_id,quota_kind) DO UPDATE SET
                 ts=excluded.ts, day=excluded.day, total=excluded.total,
                 used=excluded.used, remaining=excluded.remaining,
                 unit=excluded.unit, raw_pct=excluded.raw_pct,
                 expires_at=excluded.expires_at""",
                (row.request_id, row.quota_kind, row.ts, row.day, row.total,
                 row.used, row.remaining, row.unit, row.raw_pct, row.expires_at))
        self.conn.commit()
        return len(credits), len(quota)

    def upsert_estimates(self, estimates) -> int:
        now = datetime.now(timezone.utc).timestamp()
        for row in estimates:
            self.conn.execute(
                """INSERT INTO usage_est
                (request_id,source,ts,day,project,model,session_id,est_input,est_output,
                 chars_in,chars_out,ratio,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(request_id) DO UPDATE SET
                 source=excluded.source, ts=excluded.ts, day=excluded.day,
                 project=excluded.project, model=excluded.model,
                 session_id=excluded.session_id,
                 est_input=excluded.est_input, est_output=excluded.est_output,
                 chars_in=excluded.chars_in, chars_out=excluded.chars_out,
                 ratio=excluded.ratio, updated_at=excluded.updated_at""",
                (row.request_id, row.source, row.ts, row.day, row.project, row.model,
                 row.session, row.est_input, row.est_output, row.chars_in,
                 row.chars_out, row.ratio, now))
        self.conn.commit()
        return len(estimates)

    def credit_daily(self, since: str | None = None,
                     until: str | None = None) -> list[dict]:
        clauses, params = [], []
        if since:
            clauses.append("day >= ?")
            params.append(since)
        if until:
            clauses.append("day <= ?")
            params.append(until)
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        snapshots = {
            row[0]: row[1] for row in self.conn.execute(
                "SELECT day, COUNT(DISTINCT request_id) FROM usage_quota "
                "WHERE %s GROUP BY day" % where_sql, params)
        }
        rows = []
        for day, credits, requests, free_credits in self.conn.execute(
                """SELECT day,
                   COALESCE(SUM(CASE WHEN billable=1 THEN credits ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN billable=1 THEN 1 ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN billable=0 THEN credits ELSE 0 END),0)
                   FROM usage_credit WHERE %s GROUP BY day ORDER BY day""" % where_sql,
                params):
            rows.append({"day": day, "credits": round(credits, 6),
                         "requests": requests,
                         "free_credits": round(free_credits, 6),
                         "snapshots": snapshots.get(day, 0)})
        return rows

    def credits_totals(self, since: str | None = None,
                       until: str | None = None) -> dict:
        clauses, params = [], []
        if since:
            clauses.append("day >= ?")
            params.append(since)
        if until:
            clauses.append("day <= ?")
            params.append(until)
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        row = self.conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN billable=1 THEN credits ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN billable=0 THEN credits ELSE 0 END),0),
               COUNT(*), COUNT(DISTINCT day), COUNT(DISTINCT model)
               FROM usage_credit WHERE %s""" % where_sql, params).fetchone()
        return {"credits": row[0], "free_credits": row[1], "requests": row[2],
                "days": row[3], "models": row[4]}

    def latest_quota(self) -> dict:
        result = {}
        for kind in ("user", "add_on"):
            row = self.conn.execute(
                """SELECT request_id,ts,day,total,used,remaining,unit,raw_pct,expires_at
                FROM usage_quota WHERE quota_kind=? ORDER BY ts DESC LIMIT 1""",
                (kind,)).fetchone()
            if row:
                result[kind] = {"ts": row[1], "day": row[2], "total": row[3],
                                "used": row[4], "remaining": row[5],
                                "unit": row[6], "pct": row[7], "expires_at": row[8]}
        return result

    def quota_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM usage_quota").fetchone()[0]

    def credit_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM usage_credit").fetchone()[0]

    def credit_bounds(self) -> tuple[str | None, str | None]:
        row = self.conn.execute(
            "SELECT MIN(day), MAX(day), MAX(ts) FROM usage_credit").fetchone()
        return (row[0], row[1], row[2]) if row else (None, None, None)

    def est_count(self, source: str | None = "qoder.est") -> int:
        if source in (None, "*"):
            return self.conn.execute("SELECT COUNT(*) FROM usage_est").fetchone()[0]
        return self.conn.execute(
            "SELECT COUNT(*) FROM usage_est WHERE source=?", (source,)).fetchone()[0]

    def est_bounds(self, source: str | None = "qoder.est") -> tuple[str | None, str | None, float | None]:
        where, params = "", []
        if source not in (None, "*"):
            where, params = " WHERE source=?", [source]
        row = self.conn.execute(
            "SELECT MIN(day), MAX(day), MAX(ts) FROM usage_est" + where, params).fetchone()
        return (row[0], row[1], row[2]) if row else (None, None, None)

    def est_missing_ratio(self, source: str | None = "qoder.est") -> int:
        where, params = "", []
        if source not in (None, "*"):
            where, params = " AND source=?", [source]
        return self.conn.execute(
            "SELECT COUNT(*) FROM usage_est WHERE ratio IS NULL" + where, params).fetchone()[0]

    def est_rows(self, since: str | None = None, until: str | None = None,
                 dims: tuple[str, ...] = ("day", "model"),
                 source: str | None = "qoder.est") -> list[dict]:
        allowed = {"day", "project", "model", "session"}
        dims = tuple(dim for dim in dims if dim in allowed) or ("day",)
        clauses, params = [], []
        if since:
            clauses.append("day >= ?")
            params.append(since)
        if until:
            clauses.append("day <= ?")
            params.append(until)
        if source not in (None, "*"):
            clauses.append("source = ?")
            params.append(source)
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        col_map = {"day": "day", "project": "project", "model": "model",
                   "session": "session_id"}
        cols = ", ".join(col_map[dim] for dim in dims)
        rows = []
        for row in self.conn.execute(
                """SELECT %s, SUM(est_input), SUM(est_output), COUNT(*),
                   SUM(chars_in), SUM(chars_out),
                   SUM(CASE WHEN ratio IS NULL THEN 1 ELSE 0 END)
                   FROM usage_est WHERE %s GROUP BY %s
                   ORDER BY %s""" % (cols, where_sql, cols, cols), params):
            item = {dim: row[i] for i, dim in enumerate(dims)}
            item.update({"est_input": row[len(dims)],
                         "est_output": row[len(dims) + 1],
                         "requests": row[len(dims) + 2],
                         "chars_in": row[len(dims) + 3],
                         "chars_out": row[len(dims) + 4],
                         "missing_ratio": row[len(dims) + 5]})
            rows.append(item)
        return rows

    def est_totals(self, since: str | None = None,
                   until: str | None = None,
                   source: str | None = "qoder.est") -> dict:
        clauses, params = [], []
        if since:
            clauses.append("day >= ?")
            params.append(since)
        if until:
            clauses.append("day <= ?")
            params.append(until)
        if source not in (None, "*"):
            clauses.append("source = ?")
            params.append(source)
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        row = self.conn.execute(
            """SELECT COALESCE(SUM(est_input),0), COALESCE(SUM(est_output),0),
               COUNT(*), COUNT(DISTINCT day), COUNT(DISTINCT model),
               COALESCE(SUM(CASE WHEN ratio IS NULL THEN 1 ELSE 0 END),0)
               FROM usage_est WHERE %s""" % where_sql, params).fetchone()
        return {"est_input": row[0], "est_output": row[1], "requests": row[2],
                "days": row[3], "models": row[4], "missing_ratio": row[5]}

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

    def source_mtimes(self) -> dict[str, int]:
        return {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT source, last_file_mtime FROM source_state WHERE last_file_mtime IS NOT NULL"
            )
        }

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
