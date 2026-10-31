from __future__ import annotations

import glob
import json
import os
import sqlite3
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from .models import (Activity, Counts, Credit, Estimate, QuotaSnapshot, Record,
                     SourceResult)


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


QODER_TOKEN_SQL = """
SELECT cm.id, cm.session_id, cm.gmt_create, cm.model_info, cm.token_info,
       cs.project_name, cs.project_uri, cs.session_type, cs.preferred_model_info
FROM chat_message cm
LEFT JOIN chat_session cs ON cs.session_id = cm.session_id
WHERE cm.role = 'assistant'
  AND cm.token_info IS NOT NULL
  AND cm.token_info NOT IN ('', 'null', '{}')
"""


def qoder_paths(home: str | None = None) -> tuple[str, str]:
    home = home or os.path.expanduser("~")
    token_db = os.environ.get("USAGE_LEDGER_QODER_TOKEN_DB") or os.path.join(
        home, "Library", "Application Support", "Qoder",
        "SharedClientCache", "cache", "db", "local.db")
    activity_db = os.environ.get("USAGE_LEDGER_QODER_ACTIVITY_DB") or os.path.join(
        home, "Library", "Application Support", "com.qoder.app.stable", "main.sqlite")
    return token_db, activity_db


def _open_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect("file:%s?mode=ro" % quote(path), uri=True, timeout=2)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _json_obj(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return {}
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _as_int(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def scan_qoder_tokens(db_path: str, result: SourceResult | None = None) -> SourceResult:
    if result is None:
        result = SourceResult("qoder")
    if not os.path.exists(db_path):
        result.available = False
        result.notes.append("token 库不存在：%s" % db_path)
        return result
    result.files += 1
    try:
        conn = _open_ro(db_path)
    except sqlite3.Error as exc:
        result.errors.append((db_path, str(exc)))
        return result
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "chat_message" not in tables or "chat_session" not in tables:
            result.available = False
            result.errors.append((db_path, "schema drift: 缺少 chat_message/chat_session 表"))
            return result
        try:
            rows = conn.execute(QODER_TOKEN_SQL).fetchall()
        except sqlite3.Error as exc:
            result.errors.append((db_path, "查询失败：%s" % exc))
            return result
    finally:
        conn.close()

    for (mid, sid, gmt_create, model_info, token_info, project_name,
         project_uri, session_type, preferred_info) in rows:
        tokens = _json_obj(token_info)
        prompt = _as_int(tokens.get("prompt_tokens"))
        completion = _as_int(tokens.get("completion_tokens"))
        cached = _as_int(tokens.get("cached_tokens"))
        if prompt + completion <= 0:
            result.key_kinds["zero-usage"] += 1
            continue
        if not mid or not isinstance(gmt_create, (int, float)) or gmt_create <= 0:
            result.errors.append((db_path, "消息 %s 缺少 id/gmt_create" % mid))
            continue
        model = str(_json_obj(model_info).get("model_key") or "").strip()
        if not model:
            preferred = _json_obj(preferred_info)
            if preferred:
                model = str(preferred.get("preferred_model")
                            or preferred.get("model_key") or "").strip()
            elif isinstance(preferred_info, str):
                model = preferred_info.strip()
        project = (project_name or "").strip()
        if not project and project_uri:
            project = os.path.basename(str(project_uri).rstrip("/"))
        ts = gmt_create / 1000.0
        result.key_kinds["message.id"] += 1
        result.add(Record(
            source="qoder",
            day=local_day(ts),
            model=model or "unknown",
            model_raw=model or None,
            project=project or None,
            session=sid,
            key="qoder:%s" % mid,
            counts=Counts(
                input=max(prompt - cached, 0),
                output=completion,
                cache_read=cached,
            ),
            ts=ts,
            provider="qoder",
            agent=session_type,
        ))
    if result.records:
        days = [rec.day for rec in result.records]
        result.notes.append("token 覆盖 %s..%s（IDE 旧库，只读）" % (min(days), max(days)))
    return result


def _activity_enriched_sql(has_sessions: bool) -> str:
    join = ("LEFT JOIN chat_sessions s ON s.session_id = m.session_id"
            if has_sessions else "")
    cwd = "s.cwd" if has_sessions else "NULL"
    return """
SELECT m.created_at AS created_at,
       m.session_id AS session_id,
       LOWER(COALESCE(m.role,
         CASE WHEN json_valid(m.payload_json)
              THEN json_extract(m.payload_json, '$.role') END)) AS role,
       CASE WHEN json_valid(m.payload_json)
            THEN CAST(COALESCE(json_extract(m.payload_json, '$.turnMetrics.turnCount'), 0) AS INTEGER)
            ELSE 0 END AS turns,
       CASE WHEN json_valid(m.payload_json)
            THEN CAST(COALESCE(json_extract(m.payload_json, '$.turnMetrics.durationMs'), 0) AS INTEGER)
            ELSE 0 END AS duration_ms,
       CASE WHEN json_valid(m.payload_json) THEN
         CASE WHEN json_type(m.payload_json, '$.turnMetrics') IS NOT NULL THEN 1 ELSE 0 END
       ELSE 0 END AS has_metrics,
       CASE WHEN json_valid(m.payload_json) THEN
         CASE WHEN json_type(m.payload_json, '$.parts') = 'array'
              THEN (SELECT COUNT(*) FROM json_each(m.payload_json, '$.parts') p
                    WHERE json_extract(p.value, '$.type') = 'tool')
              ELSE 0 END
       ELSE 0 END AS tool_calls,
       %s AS cwd
FROM chat_session_messages m
%s
WHERE m.created_at >= ? AND m.created_at < ?
""" % (cwd, join)


def _activity_rows_sql(has_sessions: bool) -> str:
    return """
WITH enriched AS (%s)
SELECT created_at, session_id, role, turns, duration_ms, has_metrics, tool_calls, cwd
FROM enriched
""" % _activity_enriched_sql(has_sessions)


def _merge_activity(day: str, rows) -> list[Activity]:
    merged: dict[str, dict] = {}
    sessions: dict[str, set] = {}
    for created_at, session_id, role, turns, duration_ms, has_metrics, tool_calls, cwd in rows:
        project = os.path.basename(cwd.rstrip("/")) if cwd else ""
        bucket = merged.setdefault(project, {
            "sessions": 0, "prompts": 0, "assistant_calls": 0,
            "assistant_with_metrics": 0, "turns": 0, "tool_calls": 0, "duration_ms": 0})
        if role == "user":
            bucket["prompts"] += 1
            sessions.setdefault(project, set()).add(session_id)
        elif role == "assistant":
            bucket["assistant_calls"] += 1
            bucket["assistant_with_metrics"] += int(has_metrics or 0)
            bucket["turns"] += turns or 0
            bucket["tool_calls"] += tool_calls or 0
            bucket["duration_ms"] += duration_ms or 0
    activities = []
    for project in sorted(merged):
        bucket = merged[project]
        bucket["sessions"] = len(sessions.get(project, ()))
        activities.append(Activity(day=day, project=project, source="qoder.activity",
                                   **bucket))
    return activities


def _json1_available(conn: sqlite3.Connection) -> bool:
    try:
        return conn.execute("SELECT json_valid('{}')").fetchone()[0] == 1
    except sqlite3.Error:
        return False


def _day_start_ms(day: str) -> int:
    return int(datetime.combine(date.fromisoformat(day), time.min).timestamp() * 1000)


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def scan_qoder_activity(db_path: str, cursor_ms: int | None = None,
                        result: SourceResult | None = None) -> SourceResult:
    if result is None:
        result = SourceResult("qoder.activity")
    if not os.path.exists(db_path):
        result.available = False
        result.notes.append("活动库不存在：%s" % db_path)
        return result
    result.files += 1
    try:
        conn = _open_ro(db_path)
    except sqlite3.Error as exc:
        result.errors.append((db_path, str(exc)))
        return result
    try:
        if not _json1_available(conn):
            result.available = False
            result.errors.append((db_path, "SQLite 缺少 JSON1 扩展，无法提取活动元数据"))
            return result
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "chat_session_messages" not in tables:
            result.available = False
            result.errors.append((db_path, "schema drift: 缺少 chat_session_messages 表"))
            return result
        has_sessions = "chat_sessions" in tables

        total_messages = conn.execute(
            "SELECT COUNT(*) FROM chat_session_messages").fetchone()[0] or 0
        result.key_kinds["messages"] = total_messages
        max_updated = conn.execute(
            "SELECT MAX(COALESCE(updated_at, created_at)) FROM chat_session_messages"
        ).fetchone()[0] or 0
        if cursor_ms and max_updated:
            if max_updated < cursor_ms:
                cursor_ms = None
            elif max_updated <= cursor_ms:
                result.cursor_ms = int(max_updated)
                result.notes.append("无新消息（updated_at 未推进）")
                return result

        affected: set[str] = set()
        if cursor_ms:
            since = int(cursor_ms) - 120000
            touched = conn.execute(
                "SELECT created_at FROM chat_session_messages "
                "WHERE COALESCE(updated_at, created_at) >= ?", (since,)).fetchall()
            for (created,) in touched:
                if created:
                    affected.add(local_day(created / 1000.0))
        else:
            # 全量扫描按日历逐日重建，空白天也要覆盖，避免旧行残留
            lo, hi = conn.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM chat_session_messages"
            ).fetchone()
            if lo and hi:
                cursor_day = datetime.fromtimestamp(lo / 1000.0).date()
                last_day = datetime.fromtimestamp(hi / 1000.0).date()
                while cursor_day <= last_day:
                    affected.add(cursor_day.isoformat())
                    cursor_day += timedelta(days=1)
        today = date.today()
        affected.add(today.isoformat())
        affected.add((today - timedelta(days=1)).isoformat())

        # 一次扫描覆盖全部受影响日期，避免按天重复解析 payload_json
        failed: set[str] = set()
        by_day: dict[str, list] = {}
        try:
            rows = conn.execute(
                _activity_rows_sql(has_sessions),
                (_day_start_ms(min(affected)), _day_start_ms(_next_day(max(affected)))),
            ).fetchall()
        except sqlite3.Error as exc:
            failed = set(affected)
            result.errors.append((db_path, "活动聚合失败：%s" % exc))
        else:
            for row in rows:
                by_day.setdefault(local_day(row[0] / 1000.0), []).append(row)
            for day in sorted(affected):
                result.activities.extend(_merge_activity(day, by_day.get(day, ())))

        result.affected_days = affected - failed
        result.cursor_ms = int(max_updated) if max_updated else (
            int(cursor_ms) if cursor_ms else None)
        result.notes.append("重算 %d 天" % len(result.affected_days))
        if result.activities:
            days = [act.day for act in result.activities]
            result.notes.append("活动覆盖 %s..%s（桌面端，仅活动指标）" % (min(days), max(days)))
    finally:
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


QODER_CTX_WINDOW = 200_000
EST_FACTORS = {"gfmodel": 3.85, "dfmodel": 4.58}
EST_DEFAULT_FACTOR = 3.8
EST_FACTOR_VERSION = "v1"
TRANSCRIPT_OVERLAP = 1 << 20
_LOG_MARKER = "用量响应摘要"


def qoder_transcript_root(home: str | None = None) -> str:
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".qoder", "projects")


def qoder_log_root(home: str | None = None) -> str:
    home = home or os.path.expanduser("~")
    return os.path.join(home, "Library", "Application Support",
                        "com.qoder.app.stable", "logs")


def est_factor(model: str | None) -> float:
    return EST_FACTORS.get(model or "", EST_DEFAULT_FACTOR)


def _content_chars(content) -> tuple[int, int]:
    """返回 (tool_result 字符数, text/thinking/tool_use 字符数)，不读其他字段。"""
    tool = 0
    out = 0
    if isinstance(content, str):
        return 0, len(content)
    if not isinstance(content, list):
        return 0, 0
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind in ("text", "thinking"):
            value = item.get(kind)
            if isinstance(value, str):
                out += len(value)
        elif kind == "tool_use":
            try:
                out += len(json.dumps(item.get("input"), ensure_ascii=False))
            except (TypeError, ValueError):
                pass
        elif kind == "tool_result":
            inner = item.get("content")
            if isinstance(inner, str):
                tool += len(inner)
            elif isinstance(inner, list):
                for part in inner:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        tool += len(part["text"])
    return tool, out


def _message_chars(typ: str, obj: dict) -> tuple[int, int]:
    """(输入字符, 输出字符)。humanInput 与 content 首段重复，优先只计一次。"""
    msg = obj.get("message") or {}
    tool, out = _content_chars(msg.get("content"))
    if typ == "assistant":
        return 0, out
    human = obj.get("humanInput")
    human_text = human.get("text") if isinstance(human, dict) else None
    text = human_text if isinstance(human_text, str) else ""
    if not text:
        text_len = 0
        content = msg.get("content")
        if isinstance(content, list):
            text_len = sum(len(part.get("text") or "") for part in content
                           if isinstance(part, dict) and part.get("type") == "text")
        elif isinstance(content, str):
            text_len = len(content)
        return tool + text_len, 0
    return tool + len(text), 0


def scan_qoder_transcripts(root: str | None = None,
                           file_state: dict | None = None,
                           result: SourceResult | None = None) -> SourceResult:
    root = root or qoder_transcript_root()
    if result is None:
        result = SourceResult("qoder.credits")
    if not os.path.isdir(root):
        result.available = False
        result.notes.append("目录不存在：%s" % root)
        result.transcript_state = dict(file_state or {})
        return result
    state = dict(file_state or {})
    new_state: dict[str, dict] = {}
    files = sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    result.files = len(files)
    credits: dict[str, Credit] = {}
    estimates: dict[str, Estimate] = {}
    max_ts = None

    for path in files:
        try:
            st = os.stat(path)
        except OSError as exc:
            result.errors.append((path, str(exc)))
            continue
        prev = state.get(path)
        if prev and prev.get("size") == st.st_size and prev.get("mtime_ns") == st.st_mtime_ns:
            new_state[path] = prev
            continue
        start = 0
        if prev and st.st_size >= prev.get("size", 0):
            start = max(0, int(prev.get("offset", 0)) - TRANSCRIPT_OVERLAP)
        try:
            fh = open(path, "rb")
        except OSError as exc:
            result.errors.append((path, str(exc)))
            continue
        last_cwd = prev.get("cwd") if prev else None
        last_model = prev.get("model") if prev else None
        offset = start
        pending_in = 0

        def emit(resp):
            if not resp or not resp.get("ts_raw"):
                return
            ts = resp["ts"]
            day = local_day(ts)
            model = resp.get("model") or "unknown"
            usage = resp.get("usage") or {}
            ratio = usage.get("context_usage_ratio")
            ratio = float(ratio) if isinstance(ratio, (int, float)) and ratio > 0 else None
            if ratio is None:
                # 旧版转录（无 usage/ratio）已有 token 真值轨，不重复估算
                result.key_kinds["missing:ratio"] += 1
                return
            est_input = int(round(ratio * QODER_CTX_WINDOW))
            est_output = int(round(resp["chars_out"] / est_factor(model)))
            key = "%s:%s" % (resp["session"], resp["ts_raw"])
            estimates[key] = Estimate(
                request_id=key, ts=ts, day=day, project=resp["project"],
                model=model, session=resp["session"], est_input=est_input,
                est_output=est_output, chars_in=resp["chars_in"],
                chars_out=resp["chars_out"], ratio=ratio)
            rid = usage.get("request_id")
            credits_value = usage.get("credits")
            if rid and isinstance(credits_value, (int, float)):
                credits[rid] = Credit(
                    request_id=rid, ts=ts, day=day, project=resp["project"],
                    model=model, session=resp["session"], credits=float(credits_value),
                    billable=bool(usage.get("billable")))

        with fh:
            if start:
                fh.seek(start)
                fh.readline()
            offset = fh.tell()
            resp = None
            for raw in fh:
                offset += len(raw)
                if b'"type"' not in raw:
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    if len(result.errors) < 20:
                        result.errors.append((path, "JSON 解析失败（offset %d）" % offset))
                    continue
                typ = obj.get("type")
                if typ not in ("assistant", "user"):
                    continue
                try:
                    ts_raw = obj.get("timestamp") or ""
                    ts = parse_iso(ts_raw)
                except Exception:
                    result.key_kinds["missing:timestamp"] += 1
                    continue
                cwd = obj.get("cwd") or last_cwd
                if cwd:
                    last_cwd = cwd
                project = os.path.basename((cwd or "").rstrip("/")) or ""
                session = obj.get("sessionId") or os.path.splitext(os.path.basename(path))[0]
                if typ == "user":
                    chars_in, _ = _message_chars("user", obj)
                    pending_in += chars_in
                    continue
                msg = obj.get("message") or {}
                model = msg.get("model") or last_model
                if model:
                    last_model = model
                _, chars_out = _message_chars("assistant", obj)
                if resp is not None and resp["ts_raw"] == ts_raw:
                    resp["chars_out"] += chars_out
                    if isinstance(msg.get("usage"), dict):
                        resp["usage"] = msg["usage"]
                else:
                    emit(resp)
                    resp = {"ts": ts, "ts_raw": ts_raw, "model": model,
                            "session": session, "project": project,
                            "chars_out": chars_out, "chars_in": pending_in,
                            "usage": msg.get("usage") if isinstance(msg.get("usage"), dict) else None}
                    pending_in = 0
                max_ts = ts if max_ts is None or ts > max_ts else max_ts
            emit(resp)
        new_state[path] = {"offset": offset, "size": st.st_size,
                           "mtime_ns": st.st_mtime_ns, "cwd": last_cwd,
                           "model": last_model}

    result.credits = list(credits.values())
    result.estimates = list(estimates.values())
    result.transcript_state = new_state
    result.key_kinds["credits"] = len(result.credits)
    result.key_kinds["estimates"] = len(result.estimates)
    if result.credits:
        days = [row.day for row in result.credits]
        result.notes.append("额度覆盖 %s..%s（每请求 credits，billable 计入配额）"
                            % (min(days), max(days)))
    return result


def scan_qoder_quota(log_root: str | None = None,
                     result: SourceResult | None = None) -> SourceResult:
    log_root = log_root or qoder_log_root()
    if result is None:
        result = SourceResult("qoder.credits")
    if not os.path.isdir(log_root):
        result.notes.append("日志目录不存在：%s（额度快照不可用）" % log_root)
        return result
    dirs = [d for d in glob.glob(os.path.join(log_root, "*")) if os.path.isdir(d)]
    files = sorted(glob.glob(os.path.join(log_root, "*", "main*.log*")))
    snapshots: dict[tuple[str, str], QuotaSnapshot] = {}
    parsed = 0
    for path in files:
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError as exc:
            result.errors.append((path, str(exc)))
            continue
        with fh:
            for line in fh:
                if _LOG_MARKER not in line:
                    continue
                start = line.find('{"operation"')
                if start < 0:
                    continue
                try:
                    obj = json.loads(line[start:])
                except ValueError:
                    result.key_kinds["quota:parse_error"] += 1
                    continue
                parsed += 1
                try:
                    ts = parse_iso(line[1:line.index("]")])
                except Exception:
                    result.key_kinds["quota:parse_error"] += 1
                    continue
                rid = obj.get("requestId")
                usage = obj.get("qoderUsage")
                if not rid or not isinstance(usage, dict):
                    continue
                expires = usage.get("expiresAt")
                for kind, field in (("user", "userQuota"), ("add_on", "addOnQuota")):
                    q = usage.get(field)
                    if not isinstance(q, dict):
                        continue
                    try:
                        total = int(q.get("total") or 0)
                        used = int(q.get("used") or 0)
                        remaining = int(q.get("remaining") or 0)
                    except (TypeError, ValueError):
                        continue
                    pct = usage.get("totalUsagePercentage")
                    snapshots[(rid, kind)] = QuotaSnapshot(
                        request_id=rid, ts=ts, day=local_day(ts), quota_kind=kind,
                        total=total, used=used, remaining=remaining,
                        unit=str(q.get("unit") or "credits"),
                        raw_pct=float(pct) if isinstance(pct, (int, float)) else None,
                        expires_at=int(expires) if isinstance(expires, (int, float)) else None)
    result.quota = list(snapshots.values())
    result.key_kinds["quota:lines"] = parsed
    result.key_kinds["quota:snapshots"] = len(result.quota)
    result.notes.append("额度快照 %d 条（日志目录 %d 个 / 文件 %d 个）"
                        % (len(result.quota), len(dirs), len(files)))
    if not result.quota:
        result.notes.append("日志中未找到用量响应摘要；额度余额暂不可用")
    return result


def scan_qoder_credit_sources(home: str | None = None,
                              file_state: dict | None = None,
                              result: SourceResult | None = None) -> SourceResult:
    home = home or os.path.expanduser("~")
    result = scan_qoder_transcripts(qoder_transcript_root(home), file_state, result)
    return scan_qoder_quota(qoder_log_root(home), result)


def source_signatures(home: str | None = None,
                      sources: list[str] | None = None) -> dict[str, int | None]:
    home = home or os.path.expanduser("~")
    wanted = list(sources or ("claude", "codex", "opencode", "kilo", "qoder"))
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
        elif source == "qoder":
            token_db, activity_db = qoder_paths(home)
            signatures["qoder"] = _latest_mtime_us([token_db, token_db + "-wal"])
            signatures["qoder.activity"] = _latest_mtime_us(
                [activity_db, activity_db + "-wal"])
            transcript_root = qoder_transcript_root(home)
            transcripts = (glob.glob(os.path.join(transcript_root, "**", "*.jsonl"),
                                     recursive=True)
                           if os.path.isdir(transcript_root) else [])
            log_root = qoder_log_root(home)
            logs = (glob.glob(os.path.join(log_root, "*", "main*.log*"))
                    if os.path.isdir(log_root) else [])
            signatures["qoder.credits"] = _latest_mtime_us(transcripts + logs)
            signatures["qoder.est"] = _latest_mtime_us(transcripts)
    return signatures


def collect_all(home: str | None = None, sources: list[str] | None = None,
                skip_qoder_tokens: bool = False,
                activity_cursor_ms: int | None = None,
                transcript_state: dict | None = None) -> list[SourceResult]:
    home = home or os.path.expanduser("~")
    wanted = set(sources or ["claude", "codex", "opencode", "kilo", "qoder"])
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
    if "qoder" in wanted:
        token_db, activity_db = qoder_paths(home)
        if not skip_qoder_tokens:
            results.append(scan_qoder_tokens(token_db))
        results.append(scan_qoder_activity(activity_db, cursor_ms=activity_cursor_ms))
        results.append(scan_qoder_credit_sources(home, transcript_state))
    return results
