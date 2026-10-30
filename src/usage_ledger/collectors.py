from __future__ import annotations

import glob
import json
import os
import sqlite3
from datetime import datetime

from .models import Counts, Record, SourceResult


def local_day(ts_seconds: float) -> str:
    return datetime.fromtimestamp(ts_seconds).strftime("%Y-%m-%d")


def parse_iso(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def scan_claude(root: str, result: SourceResult | None = None) -> SourceResult:
    if result is None:
        result = SourceResult("claude")
    if not os.path.isdir(root):
        result.available = False
        result.notes.append("目录不存在：%s" % root)
        return result
    files = sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    result.notes.append("含 subagents/ transcript：%d 个" % len([f for f in files if os.sep + "subagents" + os.sep in f]))
    for path in files:
        result.files += 1
        try:
            fh = open(path, "r", errors="ignore")
        except OSError as exc:
            result.errors.append((path, str(exc)))
            continue
        with fh:
            for lineno, line in enumerate(fh, 1):
                if '"assistant"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    result.errors.append((path, "line %d: JSON 解析失败" % lineno))
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage") or {}
                if not usage or "iterations" not in usage:
                    if usage:
                        result.key_kinds["skipped:intermediate"] += 1
                    continue
                counts = Counts(
                    input=usage.get("input_tokens") or 0,
                    output=usage.get("output_tokens") or 0,
                    cache_read=usage.get("cache_read_input_tokens") or 0,
                    cache_write=usage.get("cache_creation_input_tokens") or 0,
                )
                if not counts.total():
                    result.key_kinds["zero-usage"] += 1
                    continue
                rid = msg.get("id") or obj.get("uuid")
                if not rid:
                    result.errors.append((path, "line %d: 缺少 message.id" % lineno))
                    continue
                try:
                    ts = parse_iso(obj["timestamp"])
                except Exception:
                    result.errors.append((path, "line %d: 时间戳缺失/无法解析" % lineno))
                    continue
                result.key_kinds["message.id"] += 1
                result.add(Record(
                    source="claude",
                    day=local_day(ts),
                    model=msg.get("model") or "unknown",
                    project=os.path.basename(obj.get("cwd") or "") or None,
                    session=obj.get("sessionId") or os.path.basename(path).split(".")[0],
                    key="claude:%s" % rid,
                    counts=counts,
                    ts=ts,
                ))
    return result


def scan_codex(sessions_root: str, archived_root: str, result: SourceResult | None = None) -> SourceResult:
    if result is None:
        result = SourceResult("codex")
    roots = []
    missing = 0
    for root in (sessions_root, archived_root):
        if os.path.isdir(root):
            roots.extend(sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)))
        else:
            missing += 1
            result.notes.append("目录不存在：%s" % root)
    if missing:
        result.complete = False
    if missing == 2:
        result.available = False
        return result
    zst = []
    for root in (sessions_root, archived_root):
        if os.path.isdir(root):
            zst.extend(glob.glob(os.path.join(root, "**", "*.jsonl.zst"), recursive=True))
    result.notes.append("rollout 文件（含归档）：%d 个" % len(roots))
    result.notes.append("未解析的 .zst 压缩归档：%d 个" % len(zst))

    def g(d, k):
        v = d.get(k)
        return v if isinstance(v, int) else 0

    def split(raw_in, cached, raw_out, reasoning):
        return Counts(
            input=max(raw_in - cached, 0),
            output=max(raw_out - reasoning, 0),
            cache_read=cached,
            cache_write=0,
            reasoning=reasoning,
        )

    for path in roots:
        result.files += 1
        stem = os.path.splitext(os.path.basename(path))[0]
        events = []
        current_model = None
        session = None
        project = None
        try:
            fh = open(path, "r", errors="ignore")
        except OSError as exc:
            result.errors.append((path, str(exc)))
            continue
        with fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                otype = obj.get("type")
                payload = obj.get("payload") or {}
                if otype == "session_meta":
                    session = payload.get("id") or payload.get("session_id")
                    project = payload.get("cwd")
                    prov = ((payload.get("base_instructions") or {}).get("provenance") or {})
                    if prov.get("model"):
                        current_model = prov["model"]
                elif otype == "turn_context":
                    if payload.get("model"):
                        current_model = payload["model"]
                elif otype == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    events.append((obj.get("timestamp"), info.get("total_token_usage") or {},
                                   info.get("last_token_usage") or {}, current_model))
        if not events:
            continue
        events.sort(key=lambda e: e[0] or "")
        prev_cum = None
        for ts, cum, last, model in events:
            if prev_cum is None:
                inc = split(g(last, "input_tokens"), g(last, "cached_input_tokens"),
                            g(last, "output_tokens"), g(last, "reasoning_output_tokens"))
                inc.cache_write = g(last, "cache_write_input_tokens")
            else:
                d_cached = max(g(cum, "cached_input_tokens") - g(prev_cum, "cached_input_tokens"), 0)
                d_reason = max(g(cum, "reasoning_output_tokens") - g(prev_cum, "reasoning_output_tokens"), 0)
                inc = split(
                    max(g(cum, "input_tokens") - g(prev_cum, "input_tokens"), 0),
                    d_cached,
                    max(g(cum, "output_tokens") - g(prev_cum, "output_tokens"), 0),
                    d_reason,
                )
                inc.cache_write = max(g(cum, "cache_write_input_tokens") - g(prev_cum, "cache_write_input_tokens"), 0)
            prev_cum = cum
            if not inc.total():
                result.key_kinds["zero-usage"] += 1
                continue
            try:
                epoch = parse_iso(ts)
            except Exception:
                continue
            result.key_kinds["stem+cum"] += 1
            result.add(Record(
                source="codex",
                day=local_day(epoch),
                model=model or "unknown",
                project=os.path.basename(project or "") or None,
                session=session,
                key="codex:%s:%d" % (stem, g(cum, "total_tokens")),
                counts=inc,
                ts=epoch,
            ))
    return result


def scan_sqlite_agent(db_path: str, source_name: str, result: SourceResult | None = None) -> SourceResult:
    if result is None:
        result = SourceResult(source_name)
    if not os.path.exists(db_path):
        if result.files == 0:
            result.available = False
        result.notes.append("DB 不存在：%s" % db_path)
        return result
    result.files += 1
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    except Exception as exc:
        result.errors.append((db_path, str(exc)))
        return result
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        rows = []
        # OpenCode 新版本把消息迁到 session_message（旧 message 表不再写入）
        if "session_message" in tables:
            if "session_v2" in tables:
                rows.extend(conn.execute(
                    """SELECT sm.id, sm.session_id, sm.time_created, sm.time_updated,
                              sm.data, sv.directory, 0
                       FROM session_message sm
                       LEFT JOIN session_v2 sv ON sv.id = sm.session_id
                       WHERE sm.type = 'assistant'""").fetchall())
            else:
                rows.extend(row + (None, 0) for row in conn.execute(
                    """SELECT id, session_id, time_created, time_updated, data
                       FROM session_message WHERE type = 'assistant'""").fetchall())
        if "message" in tables:
            legacy_sql = "SELECT id, session_id, time_created, time_updated, data FROM message"
            if "session_message" in tables:
                legacy_sql += (" WHERE NOT EXISTS "
                               "(SELECT 1 FROM session_message sm WHERE sm.id = message.id)")
            rows.extend(row + (None, 1) for row in conn.execute(legacy_sql).fetchall())
    except Exception as exc:
        result.errors.append((db_path, "查询失败：%s" % exc))
        conn.close()
        return result
    for mid, sid, t_created, t_updated, data, directory, legacy in rows:
        try:
            obj = json.loads(data) if isinstance(data, str) else (data or {})
        except Exception:
            result.errors.append((db_path, "message %s: data JSON 解析失败" % mid))
            continue
        if legacy and obj.get("role") != "assistant":
            continue
        tokens = obj.get("tokens") or {}
        if not tokens:
            continue
        cache = tokens.get("cache") or {}
        counts = Counts(
            input=tokens.get("input") or 0,
            output=tokens.get("output") or 0,
            cache_read=cache.get("read") or 0,
            cache_write=cache.get("write") or 0,
            reasoning=tokens.get("reasoning") or 0,
        )
        if not counts.total():
            result.key_kinds["zero-usage"] += 1
            continue
        ts = (t_created or t_updated or 0) / 1000.0
        if ts <= 0:
            continue
        model_info = obj.get("model")
        if isinstance(model_info, dict):
            model = model_info.get("id") or "unknown"
            provider = obj.get("providerID") or model_info.get("providerID")
        else:
            model = obj.get("modelID") or (model_info if isinstance(model_info, str) else None) or "unknown"
            provider = obj.get("providerID")
        path = obj.get("path") or {}
        project_dir = path.get("cwd") or directory
        project = os.path.basename(project_dir.rstrip("/")) if project_dir else None
        result.key_kinds["message.id"] += 1
        result.add(Record(
            source=source_name,
            day=local_day(ts),
            model=model,
            project=project or None,
            session=sid,
            key="%s:%s" % (source_name, mid),
            counts=counts,
            ts=ts,
            provider=provider,
            model_raw=model,
        ))
    conn.close()
    return result


def _latest_mtime_us(paths: list[str]) -> int | None:
    # 微秒级：纳秒时间戳超出 SQLite REAL 的精确整数范围（2^53），会在回写后失真
    latest = None
    for path in paths:
        try:
            mtime = os.stat(path).st_mtime_ns // 1_000
        except OSError:
            continue
        if latest is None or mtime > latest:
            latest = mtime
    return latest


def source_signatures(home: str | None = None,
                      sources: list[str] | None = None) -> dict[str, int | None]:
    home = home or os.path.expanduser("~")
    wanted = list(sources or ("claude", "codex", "opencode", "kilo"))
    signatures = {}
    for source in wanted:
        if source == "claude":
            root = os.path.join(home, ".claude", "projects")
            paths = (glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
                     if os.path.isdir(root) else [])
            signatures[source] = _latest_mtime_us(paths)
        elif source == "codex":
            paths = []
            for sub in ("sessions", "archived_sessions"):
                root = os.path.join(home, ".codex", sub)
                if os.path.isdir(root):
                    paths.extend(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
            signatures[source] = _latest_mtime_us(paths)
        elif source == "opencode":
            share = os.path.join(home, ".local", "share", "opencode")
            paths = []
            for name in ("opencode.db", "opencode-stable.db"):
                base = os.path.join(share, name)
                paths.extend([base, base + "-wal"])
            signatures[source] = _latest_mtime_us(paths)
        elif source == "kilo":
            base = os.path.join(home, ".local", "share", "kilo", "kilo.db")
            signatures[source] = _latest_mtime_us([base, base + "-wal"])
    return signatures


def collect_all(home: str | None = None, sources: list[str] | None = None) -> list[SourceResult]:
    home = home or os.path.expanduser("~")
    wanted = set(sources or ["claude", "codex", "opencode", "kilo"])
    results = []
    if "claude" in wanted:
        results.append(scan_claude(os.path.join(home, ".claude", "projects")))
    if "codex" in wanted:
        results.append(scan_codex(os.path.join(home, ".codex", "sessions"),
                                 os.path.join(home, ".codex", "archived_sessions")))
    if "opencode" in wanted:
        share = os.path.join(home, ".local", "share", "opencode")
        result = SourceResult("opencode")
        dbs = [os.path.join(share, name) for name in ("opencode.db", "opencode-stable.db")]
        found = [path for path in dbs if os.path.exists(path)]
        for path in found or dbs[:1]:
            scan_sqlite_agent(path, "opencode", result)
        results.append(result)
    if "kilo" in wanted:
        kilo_db = os.path.join(home, ".local", "share", "kilo", "kilo.db")
        results.append(scan_sqlite_agent(kilo_db, "kilo"))
    return results
