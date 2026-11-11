from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
import webbrowser
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from . import __version__, scheduler, trae_hooks
from .aggregation import (DIMENSIONS, aggregate, match, merge_records, missing_days,
                          period_label)
from .collectors import (EST_FACTOR_VERSION, TRAE_EST_SOURCE, TRAE_EST_VERSION,
                         collect_all, qoder_paths, scan_qoder_activity,
                         scan_qoder_credit_sources, scan_trae_cn_est,
                         source_signatures)
from .html_report import build_payload, render_html
from .models import ACTIVITY_FIELDS, FIELDS, Activity, SourceResult
from .pricing import cost_for_record, normalize_model
from .store import SqliteStore

SOURCES = ("claude", "codex", "opencode", "kilo", "cline", "qoder", "trae-cn")
EST_SOURCES = {"qoder": "qoder.est", "trae-cn": TRAE_EST_SOURCE}
ACTIVITY_SOURCE = "qoder.activity"
ACTIVITY_CURSOR_KEY = "activity_cursor:qoder"
ACTIVITY_STALL_KEY = "activity_stall:qoder"
ACTIVITY_MESSAGES_KEY = "activity_messages:qoder"
DEFAULT_DIMS = ("day", "source", "model")
ACTIVITY_DIMS = ("day", "source", "project")
HEADERS = {
    "day": "date", "week": "week", "month": "month", "source": "source",
    "model": "model", "project": "project", "session": "session",
}
NO_TOKEN_NOTICE = ("无 token 真值：Trae CN（仅 hook 字符弱估算，见 usage est --source trae-cn）、"
                   "ChatGPT 桌面端（无本地数据）")
TRAE_EST_NOTICE = ("Trae CN 弱估算（%s）：仅 hook 可见内容，不含系统提示/工具定义，"
                   "误差可能数倍且方向不定，不可与真值/额度相加" % TRAE_EST_VERSION)
COST_NOTICE = "cost_equiv_usd 为按 API 价折算的等价成本，非实付；unknown 表示无价格表匹配"
ACTIVITY_NOTICE = "活动指标（会话/提示/工具调用/时长）与 token 不可相加，也不参与成本"


def source_home() -> str:
    return os.environ.get("USAGE_LEDGER_SOURCE_HOME") or os.path.expanduser("~")


def db_path() -> str:
    explicit = os.environ.get("USAGE_LEDGER_DB")
    if explicit:
        return explicit
    home = os.environ.get("USAGE_LEDGER_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share", "usage-ledger")
    return os.path.join(home, "usage.db")


def parse_day(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    matched = re.fullmatch(r"(\d+)([dwm])", value)
    if matched:
        days = int(matched.group(1)) * {"d": 1, "w": 7, "m": 30}[matched.group(2)]
        return (date.today() - timedelta(days=days)).isoformat()
    raise ValueError("无法识别的日期：%s（支持 2026-06-01 / 7d / 4w / 3m）" % value)


def parse_range(value: str) -> tuple[str, str]:
    parts = value.split("..")
    if len(parts) != 2:
        raise ValueError("--range 格式应为 <start>..<end>")
    return parse_day(parts[0]), parse_day(parts[1])


def parse_filters(value: str | None) -> dict[str, str]:
    filters = {}
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("--filter 格式应为 key=value[,key=value]")
        key, val = item.split("=", 1)
        if key not in ("source", "model", "project", "session"):
            raise ValueError("未知过滤字段：%s" % key)
        filters[key] = val
    return filters


def parse_dims(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_DIMS
    dims = tuple(item.strip() for item in value.split(",") if item.strip())
    for dim in dims:
        if dim not in DIMENSIONS:
            raise ValueError("未知分组维度：%s" % dim)
    return dims


def open_store(stateless: bool) -> SqliteStore | None:
    if stateless:
        return None
    return SqliteStore(db_path())


def _status(result: SourceResult) -> str:
    if not result.available:
        return "unsupported"
    if result.errors:
        return "error"
    if not result.complete:
        return "partial"
    return "ok"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _human_size(size: int) -> str:
    if size >= 1024 * 1024:
        return "%.1f MB" % (size / 1024 / 1024)
    return "%.1f KB" % (size / 1024)


def _fmt_cost(value: float | None) -> str:
    return "—" if value is None else "%.4f" % value


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _ago(ts: float) -> str:
    seconds = max(time.time() - ts, 0)
    if seconds < 60:
        return "%ds ago" % seconds
    if seconds < 3600:
        return "%dm ago" % (seconds // 60)
    if seconds < 86400:
        return "%dh ago" % (seconds // 3600)
    return "%dd ago" % (seconds // 86400)


def _source_results(sources: list[str] | None = None, skip_qoder_tokens: bool = False,
                    activity_cursor_ms: int | None = None,
                    transcript_state: dict | None = None) -> list[SourceResult]:
    return collect_all(source_home(), sources, skip_qoder_tokens=skip_qoder_tokens,
                       activity_cursor_ms=activity_cursor_ms,
                       transcript_state=transcript_state)


def _activity_totals(activities: list[Activity]) -> dict:
    totals = {field: 0 for field in ACTIVITY_FIELDS}
    for act in activities:
        for field in ACTIVITY_FIELDS:
            totals[field] += getattr(act, field)
    totals["rows"] = len(activities)
    return totals


def _fmt_duration(ms: int) -> str:
    seconds = int(round((ms or 0) / 1000))
    if seconds >= 3600:
        return "%dh %02dm" % (seconds // 3600, seconds % 3600 // 60)
    if seconds >= 60:
        return "%dm %02ds" % (seconds // 60, seconds % 60)
    return "%ds" % seconds


def _qoder_coverage(records: list | None = None, activities: list[Activity] | None = None,
                    stateless: bool = False) -> dict | None:
    if not stateless and os.path.exists(db_path()):
        store = SqliteStore(db_path())
        try:
            token_since, token_until = store.source_bounds("qoder")
            activity_since, activity_until = store.activity_bounds(ACTIVITY_SOURCE)
        finally:
            store.close()
    else:
        days = [rec.day for rec in (records or []) if rec.source == "qoder"]
        act_days = [act.day for act in (activities or [])]
        token_since, token_until = (min(days), max(days)) if days else (None, None)
        activity_since = min(act_days) if act_days else None
        activity_until = max(act_days) if act_days else None
    if not token_since and not activity_since:
        return None
    return {"qoder": {
        "token_since": token_since, "token_until": token_until,
        "activity_since": activity_since, "activity_until": activity_until,
    }}


def _qoder_coverage_text(coverage: dict | None) -> str | None:
    qoder = (coverage or {}).get("qoder") or {}
    if not qoder:
        return None
    if qoder.get("token_since"):
        text = "Qoder：token 覆盖 %s ~ %s" % (qoder["token_since"], qoder["token_until"])
    else:
        text = "Qoder：本地无 token 数据"
    if qoder.get("activity_since"):
        text += "；活动覆盖 %s ~ %s" % (qoder["activity_since"], qoder["activity_until"])
    text += "；活动指标与 token 不可相加"
    if qoder.get("token_until"):
        text += "，%s 之后本地无 token 真值" % qoder["token_until"]
    return text


def _store_activity_result(store, result: SourceResult, signatures: dict,
                           stored_mtimes: dict, quiet: bool) -> int:
    status = _status(result)
    error = "; ".join(msg for _, msg in result.errors[:3]) or None
    inserted = 0
    if result.affected_days or result.activities:
        inserted = store.replace_activity_days(
            ACTIVITY_SOURCE, result.affected_days, result.activities)
    previous = store.get_meta(ACTIVITY_CURSOR_KEY)
    signature = signatures.get(ACTIVITY_SOURCE)
    mtime_changed = (signature is not None
                     and stored_mtimes.get(ACTIVITY_SOURCE) != signature)
    if result.cursor_ms is not None:
        store.set_meta(ACTIVITY_CURSOR_KEY, str(result.cursor_ms))
    stall = 0
    messages = result.key_kinds.get("messages")
    previous_messages = store.get_meta(ACTIVITY_MESSAGES_KEY)
    if messages is not None:
        if (mtime_changed and result.cursor_ms is not None and previous
                and previous.isdigit() and result.cursor_ms <= int(previous)
                and previous_messages and previous_messages.isdigit()
                and messages > int(previous_messages)):
            stall = int(store.get_meta(ACTIVITY_STALL_KEY) or 0) + 1
        store.set_meta(ACTIVITY_MESSAGES_KEY, str(messages))
    store.set_meta(ACTIVITY_STALL_KEY, str(stall))
    store.update_source_state(
        ACTIVITY_SOURCE, result.files, store.activity_count(ACTIVITY_SOURCE), status, error,
        last_ts=(result.cursor_ms / 1000.0) if result.cursor_ms else None,
        last_mtime=signature,
    )
    if not quiet:
        totals = _activity_totals(result.activities)
        print("qoder.activity: days=%d sessions=%d prompts=%d assistant=%d "
              "tool_calls=%d rows=%d status=%s" %
              (len(result.affected_days), totals["sessions"], totals["prompts"],
               totals["assistant_calls"], totals["tool_calls"], totals["rows"], status))
        for note in result.notes:
            print("  note:", note)
    return inserted


def _store_credit_result(store, result: SourceResult, signatures: dict,
                         quiet: bool) -> None:
    status = _status(result)
    error = "; ".join(msg for _, msg in result.errors[:3]) or None
    n_credit, n_quota = store.upsert_credits(result.credits, result.quota)
    store.upsert_estimates(result.estimates)
    if result.transcript_state is not None:
        store.set_meta("transcript_files",
                       json.dumps(result.transcript_state, ensure_ascii=False))
    store.set_meta("est_factor_version", EST_FACTOR_VERSION)
    store.update_source_state(
        "qoder.credits", result.files, store.credit_count(), status, error,
        last_ts=max((row.ts for row in result.credits), default=None),
        last_mtime=signatures.get("qoder.credits"))
    store.update_source_state(
        "qoder.est", result.files, store.est_count(), status, error,
        last_ts=max((row.ts for row in result.estimates), default=None),
        last_mtime=signatures.get("qoder.est"))
    if quiet:
        return
    print("qoder.credits: %d 请求 / %d 快照（本批 %d / %d），est %d 条（本批 %d），status=%s" %
          (store.credit_count(), store.quota_count(), n_credit, n_quota,
           store.est_count(), len(result.estimates), status))
    for note in result.notes:
        print("  note:", note)


def _store_trae_est_result(store, result: SourceResult, signatures: dict,
                           quiet: bool) -> int:
    status = _status(result)
    error = "; ".join(msg for _, msg in result.errors[:3]) or None
    inserted = store.upsert_estimates(result.estimates)
    store.update_source_state(
        TRAE_EST_SOURCE, result.files, store.est_count(TRAE_EST_SOURCE), status, error,
        last_ts=max((row.ts for row in result.estimates), default=None),
        last_mtime=signatures.get(TRAE_EST_SOURCE))
    if not quiet:
        print("trae-cn.est: 弱估算 %d 条（本批 %d），files=%d events=%d sessions=%d errors=%d status=%s" %
              (store.est_count(TRAE_EST_SOURCE), inserted, result.files,
               result.key_kinds.get("events", 0), result.key_kinds.get("sessions", 0),
               len(result.errors), status))
        for note in result.notes:
            print("  note:", note)
    return inserted


def _sync_into(store, sources=None, full=False, since=None, quiet=False) -> dict:
    wanted = list(sources) if sources else list(SOURCES)
    signatures = source_signatures(source_home(), wanted)
    stored_mtimes = store.source_mtimes()
    skip_tokens = ("qoder" in wanted and signatures.get("qoder") is not None
                   and signatures.get("qoder") == stored_mtimes.get("qoder"))
    cursor_raw = store.get_meta(ACTIVITY_CURSOR_KEY)
    cursor = int(cursor_raw) if cursor_raw and cursor_raw.isdigit() else None
    state_raw = store.get_meta("transcript_files")
    try:
        transcript_state = json.loads(state_raw) if state_raw else None
    except ValueError:
        transcript_state = None
    results = _source_results(wanted, skip_qoder_tokens=skip_tokens,
                              activity_cursor_ms=cursor,
                              transcript_state=transcript_state)
    total = 0
    archived_total = 0
    activity_rows = 0
    for result in results:
        if result.name == ACTIVITY_SOURCE:
            activity_rows += _store_activity_result(
                store, result, signatures, stored_mtimes, quiet)
            continue
        if result.name == "qoder.credits":
            _store_credit_result(store, result, signatures, quiet)
            continue
        if result.name == TRAE_EST_SOURCE:
            total += _store_trae_est_result(store, result, signatures, quiet)
            continue
        records = [rec for rec in result.records if not since or rec.day >= since]
        if records:
            store.upsert_records(records, cost_fn=cost_for_record)
        status = _status(result)
        error = "; ".join(msg for _, msg in result.errors[:3]) or None
        store.update_source_state(
            result.name, result.files, len(result.records), status, error,
            max((rec.ts for rec in result.records), default=None),
            last_mtime=signatures.get(result.name),
        )
        archived = restored = 0
        if full and result.healthy and not since:
            archived, restored = store.mark_archived(
                result.name, {rec.key for rec in result.records})
            store.set_meta("full_scan_at:" + result.name, _now_iso())
            archived_total += archived
        total += len(records)
        if quiet:
            continue
        tokens = sum(rec.counts.total() for rec in records)
        extra = ""
        if full and result.healthy and not since:
            extra = ", archived=%d restored=%d" % (archived, restored)
        print("%s: %d records, %s tokens, files=%d, errors=%d, status=%s%s" %
              (result.name, len(records), _fmt_int(tokens), result.files,
               len(result.errors), status, extra))
        for note in result.notes:
            print("  note:", note)
    if skip_tokens and not quiet:
        print("qoder: token 库 mtime 未变化，跳过全量扫描")
    return {"total": total, "archived": archived_total, "activity_rows": activity_rows,
            "sources": [result.name for result in results]}


def _refresh_if_stale(store, source=None) -> bool:
    sources = [source] if source else None
    current = source_signatures(source_home(), sources)
    stored = store.source_mtimes()
    stale = []
    for name, signature in current.items():
        if signature is None:
            continue
        stored_signature = stored.get(name)
        if stored_signature is None and name == "trae-cn":
            stored_signature = stored.get(TRAE_EST_SOURCE)
        if stored_signature is None or signature > stored_signature:
            stale.append(name)
    if not stale:
        return False
    public = []
    for name in stale:
        public_name = ("qoder" if name in (ACTIVITY_SOURCE, "qoder.credits", "qoder.est")
                       else "trae-cn" if name == TRAE_EST_SOURCE
                       else name)
        if public_name not in public:
            public.append(public_name)
    print("auto-sync: 检测到 %s 有新数据，正在刷新…" % "、".join(stale), file=sys.stderr)
    try:
        stats = _sync_into(store, sources=public, quiet=True)
    except (sqlite3.Error, OSError) as exc:
        print("auto-sync: 刷新失败（%s），继续使用库中现有数据" % exc, file=sys.stderr)
        return False
    print("auto-sync: 已更新 %d 条记录" % stats["total"], file=sys.stderr)
    return True


def _refresh_activity_if_stale(store) -> bool:
    signatures = source_signatures(source_home(), ["qoder"])
    signature = signatures.get(ACTIVITY_SOURCE)
    stored = store.source_mtimes()
    if signature is None or stored.get(ACTIVITY_SOURCE) == signature:
        return False
    print("auto-sync: 检测到 Qoder 活动库有新数据，正在刷新…", file=sys.stderr)
    cursor_raw = store.get_meta(ACTIVITY_CURSOR_KEY)
    cursor = int(cursor_raw) if cursor_raw and cursor_raw.isdigit() else None
    result = scan_qoder_activity(qoder_paths(source_home())[1], cursor_ms=cursor)
    _store_activity_result(store, result, signatures, stored, quiet=True)
    print("auto-sync: 活动重算 %d 天 / %d 行" %
          (len(result.affected_days), len(result.activities)), file=sys.stderr)
    return True


def _refresh_credits_if_stale(store) -> bool:
    signatures = source_signatures(source_home(), ["qoder"])
    stored = store.source_mtimes()
    stale = [name for name in ("qoder.credits", "qoder.est")
             if signatures.get(name) is not None
             and stored.get(name) != signatures.get(name)]
    if not stale:
        return False
    print("auto-sync: 检测到 Qoder 转录/日志有新数据，正在刷新额度与估算…",
          file=sys.stderr)
    try:
        _sync_into(store, sources=["qoder"], quiet=True)
    except (sqlite3.Error, OSError) as exc:
        print("auto-sync: 额度刷新失败（%s），继续使用库中现有数据" % exc, file=sys.stderr)
        return False
    return True


def _refresh_trae_est_if_stale(store) -> bool:
    signatures = source_signatures(source_home(), ["trae-cn"])
    stored = store.source_mtimes()
    signature = signatures.get(TRAE_EST_SOURCE)
    if signature is None or stored.get(TRAE_EST_SOURCE) == signature:
        return False
    print("auto-sync: 检测到 Trae CN hook 事件有新数据，正在刷新估算…",
          file=sys.stderr)
    try:
        _sync_into(store, sources=["trae-cn"], quiet=True)
    except (sqlite3.Error, OSError) as exc:
        print("auto-sync: Trae 估算刷新失败（%s），继续使用库中现有数据" % exc,
              file=sys.stderr)
        return False
    return True


def cmd_sync(args):
    if args.stateless:
        print("sync 需要写入数据库，不能与 --stateless 同时使用", file=sys.stderr)
        return 2
    since = parse_day(args.since) if args.since else None
    if args.dry_run:
        for result in _source_results(args.source):
            if result.name == ACTIVITY_SOURCE:
                totals = _activity_totals(result.activities)
                print("qoder.activity: days=%d rows=%d sessions=%d tool_calls=%d files=%d status=%s" %
                      (len(result.affected_days), totals["rows"], totals["sessions"],
                       totals["tool_calls"], result.files, _status(result)))
                continue
            if result.name == TRAE_EST_SOURCE:
                est_total = sum(row.est_input + row.est_output
                                for row in result.estimates)
                print("trae-cn.est: %d estimates, %s est tokens, files=%d, status=%s" %
                      (len(result.estimates), _fmt_int(est_total), result.files,
                       _status(result)))
                continue
            records = [rec for rec in result.records if not since or rec.day >= since]
            tokens = sum(rec.counts.total() for rec in records)
            print("%s: %d records, %s tokens, files=%d, status=%s" %
                  (result.name, len(records), _fmt_int(tokens), result.files, _status(result)))
        return 0

    store = SqliteStore(db_path())
    try:
        stats = _sync_into(store, sources=args.source, full=args.full, since=since)
    finally:
        store.close()
    print("synced %d records -> %s" % (stats["total"], db_path()))
    if stats["archived"]:
        print("newly archived %d records (source no longer contains them)" % stats["archived"])
    return 0


def cmd_backfill(args):
    args.full = True
    args.dry_run = False
    return cmd_sync(args)


def cmd_live(args):
    interval = args.watch if args.watch is not None else None
    try:
        while True:
            _print_live(args)
            if interval is None:
                break
            print()
            time.sleep(max(interval, 1))
    except KeyboardInterrupt:
        return 0
    return 0


def _print_live(args):
    results = _source_results([args.source] if args.source else None)
    records = [rec for result in results for rec in result.records]
    if args.session:
        records = [rec for rec in records if rec.session == args.session]
    records.sort(key=lambda rec: rec.ts, reverse=True)

    print(f"{'source':8}{'session':20}{'model':34}{'tokens':>14}  {'updated':10}")
    for rec in records[:50]:
        print(f"{rec.source:8}{(rec.session or '-')[:18]:20}{(rec.model or 'unknown')[:32]:34}"
              f"{_fmt_int(rec.counts.total()):>14}  {_ago(rec.ts):10}")

    today = date.today().isoformat()
    today_records = [rec for rec in records if rec.day == today]
    per_source = Counter()
    for rec in today_records:
        per_source[rec.source] += rec.counts.total()
    detail = " · ".join("%s %s" % (name, _fmt_int(value))
                        for name, value in per_source.most_common())
    print("today: %s tokens%s" % (_fmt_int(sum(per_source.values())),
                                  "  (%s)" % detail if detail else ""))
    qoder_records = [rec for rec in records if rec.source == "qoder"]
    if qoder_records:
        days = [rec.day for rec in qoder_records]
        print("qoder: token 覆盖 %s ~ %s（IDE 旧库；之后本地无 token 真值，活动见 usage activity）" %
              (min(days), max(days)))
    else:
        print("qoder: 本地无 token 数据；活动指标见 usage activity（不可与 token 相加）")
    print(NO_TOKEN_NOTICE)


def _effective_range(args) -> tuple[str | None, str | None]:
    since = until = None
    if getattr(args, "range", None):
        since, until = parse_range(args.range)
    if getattr(args, "since", None):
        since = parse_day(args.since)
    if getattr(args, "until", None):
        until = parse_day(args.until)
    if since and until and since > until:
        raise ValueError("起始日期 %s 晚于结束日期 %s" % (since, until))
    return since, until


def _load_records(args, since, until, filters) -> tuple[list, list[Activity], dict | None]:
    wanted = [filters["source"]] if "source" in filters else None
    activities: list[Activity] = []
    use_stateless = args.stateless
    if use_stateless:
        results = _source_results(wanted)
        records = [rec for result in results for rec in result.records]
        activities = [act for result in results for act in result.activities]
    else:
        if not os.path.exists(db_path()):
            print("warning: 数据库不存在，自动降级为 --stateless（读源）", file=sys.stderr)
            results = _source_results(wanted)
            records = [rec for result in results for rec in result.records]
            activities = [act for result in results for act in result.activities]
            use_stateless = True
        else:
            store = SqliteStore(db_path())
            try:
                _refresh_if_stale(store, filters.get("source"))
                records = store.fetch_records(
                    since=since, until=until, source=filters.get("source"),
                    model=filters.get("model"), project=filters.get("project"))
                activities = store.fetch_activity(source=ACTIVITY_SOURCE)
            finally:
                store.close()
            if getattr(args, "live", False):
                results = _source_results(wanted)
                records = merge_records(records, [rec for result in results
                                                  for rec in result.records])
    coverage = _qoder_coverage(records, activities, stateless=use_stateless)
    records = [rec for rec in records
               if (not since or rec.day >= since) and (not until or rec.day <= until)
               and match(rec, filters)]
    return records, activities, coverage


def _period(args) -> str:
    if getattr(args, "weekly", False):
        return "week"
    if getattr(args, "monthly", False):
        return "month"
    return "day"


def _report_rows(args):
    since, until = _effective_range(args)
    filters = parse_filters(args.filter)
    if getattr(args, "project", None):
        filters["project"] = args.project
    if getattr(args, "source", None):
        filters["source"] = args.source
    if getattr(args, "model", None):
        filters["model"] = args.model
    records, activities, coverage = _load_records(args, since, until, filters)
    dims = parse_dims(args.group_by)
    rows = aggregate(records, dims, _period(args))
    return rows, dims, records, since, until, coverage, filters


def _write_rows(rows, dims, fmt: str):
    headers = [HEADERS[dim] for dim in dims] + list(FIELDS) + [
        "cost_equiv_usd", "cost_source", "turns"]
    if fmt == "json":
        payload = []
        for row in rows:
            item = {headers[i]: row["dims"][i] for i in range(len(dims))}
            for field in FIELDS:
                item[field] = row[field]
            item["cost_equiv_usd"] = row["cost_equiv_usd"]
            item["cost_source"] = row["cost_source"]
            item["turns"] = row["turns"]
            payload.append(item)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if fmt == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        for row in rows:
            values = list(row["dims"])
            values += [row[field] for field in FIELDS]
            values += [_fmt_cost(row["cost_equiv_usd"]), row["cost_source"], row["turns"]]
            writer.writerow(values)
        return

    table = []
    for row in rows:
        values = list(row["dims"])
        values += [_fmt_int(row[field]) for field in FIELDS]
        values += [_fmt_cost(row["cost_equiv_usd"]), row["cost_source"], str(row["turns"])]
        table.append(values)
    widths = [max(len(headers[i]), *(len(line[i]) for line in table)) if table
              else len(headers[i]) for i in range(len(headers))]
    print("".join(header.ljust(widths[i] + 2) for i, header in enumerate(headers)))
    for line in table:
        print("".join(value.ljust(widths[i] + 2) for i, value in enumerate(line)))


def _footnotes(records, since, until):
    print(COST_NOTICE, file=sys.stderr)
    print(NO_TOKEN_NOTICE, file=sys.stderr)
    if since:
        until = until or date.today().isoformat()
        days = missing_days(records, since, until)
        if days:
            shown = ", ".join(days[:15])
            more = "" if len(days) <= 15 else " … (+%d)" % (len(days) - 15)
            print("no data: %s%s" % (shown, more), file=sys.stderr)


def _qoder_report_notes(records, coverage, since, until, filters):
    text = _qoder_coverage_text(coverage)
    if text:
        print(text, file=sys.stderr)
    qoder = (coverage or {}).get("qoder") or {}
    if filters.get("source") not in (None, "qoder"):
        return
    token_total = sum(rec.counts.total() for rec in records if rec.source == "qoder")
    if token_total or not qoder.get("activity_since"):
        return
    lo = since or qoder["activity_since"]
    hi = until or qoder["activity_until"]
    if lo <= qoder["activity_until"] and hi >= qoder["activity_since"]:
        print("qoder: 本地无该区间 token 数据；活动指标见 usage activity（不可与 token 相加）",
              file=sys.stderr)


def cmd_report(args):
    rows, dims, records, since, until, coverage, filters = _report_rows(args)
    _write_rows(rows, dims, args.format)
    _footnotes(records, since, until)
    _qoder_report_notes(records, coverage, since, until, filters)
    return 0


def cmd_export(args):
    args.format = "csv"
    return cmd_report(args)


def _parse_activity_dims(value: str | None) -> tuple[str, ...]:
    if not value:
        return ACTIVITY_DIMS
    dims = tuple(item.strip() for item in value.split(",") if item.strip())
    for dim in dims:
        if dim not in ("day", "week", "month", "source", "project"):
            raise ValueError("未知活动分组维度：%s" % dim)
    return dims


def _aggregate_activity(activities: list[Activity], dims: tuple[str, ...],
                        period: str = "day") -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for act in activities:
        key = []
        for dim in dims:
            if dim == "day":
                key.append(period_label(act.day, period))
            elif dim == "week":
                key.append(period_label(act.day, "week"))
            elif dim == "month":
                key.append(period_label(act.day, "month"))
            elif dim == "source":
                key.append("qoder")
            elif dim == "project":
                key.append(act.project or "-")
        bucket = buckets.setdefault(tuple(key), {field: 0 for field in ACTIVITY_FIELDS})
        for field in ACTIVITY_FIELDS:
            bucket[field] += getattr(act, field)
    rows = []
    for key in sorted(buckets):
        row = {"dims": key}
        row.update(buckets[key])
        rows.append(row)
    return rows


def _write_activity(rows, dims, fmt: str):
    headers = [HEADERS[dim] for dim in dims] + [
        "sessions", "prompts", "assistant_calls", "assistant_with_metrics",
        "turns", "tool_calls", "duration"]
    if fmt == "json":
        payload = []
        for row in rows:
            item = {headers[i]: row["dims"][i] for i in range(len(dims))}
            for field in ACTIVITY_FIELDS:
                item[field] = row[field]
            item["duration"] = _fmt_duration(row["duration_ms"])
            payload.append(item)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if fmt == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        for row in rows:
            values = list(row["dims"])
            values += [row[field] for field in ACTIVITY_FIELDS]
            writer.writerow(values)
        return

    numeric = ("sessions", "prompts", "assistant_calls", "assistant_with_metrics",
               "turns", "tool_calls")
    table = []
    for row in rows:
        values = list(row["dims"])
        values += [_fmt_int(row[field]) for field in numeric]
        values.append(_fmt_duration(row["duration_ms"]))
        table.append(values)
    widths = [max(len(headers[i]), *(len(line[i]) for line in table)) if table
              else len(headers[i]) for i in range(len(headers))]
    print("".join(header.ljust(widths[i] + 2) for i, header in enumerate(headers)))
    for line in table:
        print("".join(value.ljust(widths[i] + 2) for i, value in enumerate(line)))


def cmd_activity(args):
    since, until = _effective_range(args)
    chosen = args.source or "qoder"
    use_stateless = args.stateless
    activities: list[Activity] = []
    if chosen == "qoder":
        if use_stateless:
            results = _source_results(["qoder"], skip_qoder_tokens=True)
            activities = [act for result in results for act in result.activities]
        elif not os.path.exists(db_path()):
            print("warning: 数据库不存在，自动降级为 --stateless（读源）", file=sys.stderr)
            results = _source_results(["qoder"], skip_qoder_tokens=True)
            activities = [act for result in results for act in result.activities]
        else:
            store = SqliteStore(db_path())
            try:
                _refresh_activity_if_stale(store)
                activities = store.fetch_activity(
                    since=since, until=until, source=ACTIVITY_SOURCE,
                    project=args.project)
            finally:
                store.close()
        activities = [act for act in activities
                      if (not since or act.day >= since)
                      and (not until or act.day <= until)
                      and (args.project is None or (act.project or "") == args.project)]
    dims = _parse_activity_dims(args.group_by)
    rows = _aggregate_activity(activities, dims)
    _write_activity(rows, dims, args.format)
    totals = _activity_totals(activities)
    print(ACTIVITY_NOTICE, file=sys.stderr)
    if not rows:
        print("no activity data in range", file=sys.stderr)
    if totals["assistant_calls"]:
        print("turnMetrics 覆盖 %d/%d assistant（%.1f%%）；sessions 为按天去重的活跃会话数" %
              (totals["assistant_with_metrics"], totals["assistant_calls"],
               100.0 * totals["assistant_with_metrics"] / totals["assistant_calls"]),
              file=sys.stderr)
    if chosen == "qoder" and activities:
        days = [act.day for act in activities]
        print("Qoder 活动覆盖 %s ~ %s（仅活动指标，与 token 不可相加）" %
              (min(days), max(days)), file=sys.stderr)
    return 0


def _filter_activity(activities: list[Activity], since, until, filters) -> list[Activity]:
    if filters.get("source") not in (None, "qoder"):
        return []
    selected = []
    for act in activities:
        if since and act.day < since:
            continue
        if until and act.day > until:
            continue
        if filters.get("project") and (act.project or "") != filters["project"]:
            continue
        selected.append(act)
    return selected


def _quota_latest_rows(quota) -> dict:
    result = {}
    for row in quota:
        current = result.get(row.quota_kind)
        if current is None or row.ts > current["ts"]:
            result[row.quota_kind] = {
                "ts": row.ts, "day": row.day, "total": row.total,
                "used": row.used, "remaining": row.remaining,
                "unit": row.unit, "pct": row.raw_pct,
                "expires_at": row.expires_at}
    return result


def _credit_daily_from_rows(credits, quota, since, until) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in credits:
        if since and row.day < since:
            continue
        if until and row.day > until:
            continue
        item = buckets.setdefault(row.day, {
            "day": row.day, "credits": 0.0, "requests": 0,
            "free_credits": 0.0, "snapshots": 0})
        if row.billable:
            item["credits"] += row.credits
            item["requests"] += 1
        else:
            item["free_credits"] += row.credits
    for row in quota:
        if since and row.day < since:
            continue
        if until and row.day > until:
            continue
        buckets.setdefault(row.day, {
            "day": row.day, "credits": 0.0, "requests": 0,
            "free_credits": 0.0, "snapshots": 0})
    seen_snapshots = set()
    for row in quota:
        key = (row.request_id, row.day)
        if key in seen_snapshots:
            continue
        seen_snapshots.add(key)
        item = buckets.get(row.day)
        if item is not None:
            item["snapshots"] += 1
    rows = []
    for day in sorted(buckets):
        item = buckets[day]
        item["credits"] = round(item["credits"], 6)
        item["free_credits"] = round(item["free_credits"], 6)
        rows.append(item)
    return rows


def _credit_totals_from_rows(credits, since, until) -> dict:
    selected = [row for row in credits
                if (not since or row.day >= since) and (not until or row.day <= until)]
    billable = [row for row in selected if row.billable]
    return {
        "credits": round(sum(row.credits for row in billable), 6),
        "free_credits": round(sum(row.credits for row in selected
                                  if not row.billable), 6),
        "requests": len(selected),
        "days": len({row.day for row in selected}),
        "models": len({row.model for row in selected}),
    }


def _write_credit_rows(rows, totals, quota, fmt: str):
    headers = ["day", "credits", "requests", "free_credits", "snapshots"]
    if fmt == "json":
        print(json.dumps({"days": rows, "totals": totals, "quota": quota,
                          "factor_version": EST_FACTOR_VERSION},
                         ensure_ascii=False, indent=2))
        return
    table = []
    for row in rows:
        table.append([row["day"], "%.2f" % row["credits"], str(row["requests"]),
                      "%.2f" % row["free_credits"], str(row["snapshots"])])
    widths = [max(len(headers[i]), *(len(line[i]) for line in table)) if table
              else len(headers[i]) for i in range(len(headers))]
    print("".join(header.ljust(widths[i] + 2) for i, header in enumerate(headers)))
    for line in table:
        print("".join(value.ljust(widths[i] + 2) for i, value in enumerate(line)))
    print("total: %.2f credits / %d requests（免费 %.2f，不计配额）"
          % (totals["credits"], totals["requests"], totals["free_credits"]))


def _print_quota(quota: dict):
    if not quota:
        print("额度快照：无（本地日志未留存或尚未触发用量查询）", file=sys.stderr)
        return
    add_on = quota.get("add_on")
    user = quota.get("user")
    for label, item in (("add_on", add_on), ("user", user)):
        if not item:
            continue
        pct = item.get("pct")
        pct_text = "%.1f%%" % (pct * 100) if isinstance(pct, (int, float)) else "-"
        print("额度快照 %s：used %s/%s（%s），remaining %s，%s（%s）" %
              (label, _fmt_int(item["used"]), _fmt_int(item["total"]), pct_text,
               _fmt_int(item["remaining"]), item["day"], _ago(item["ts"])),
              file=sys.stderr)


def cmd_credits(args):
    since, until = _effective_range(args)
    if args.stateless:
        result = scan_qoder_credit_sources(source_home())
        daily = _credit_daily_from_rows(result.credits, result.quota, since, until)
        totals = _credit_totals_from_rows(result.credits, since, until)
        quota = _quota_latest_rows(result.quota)
        for note in result.notes:
            print("note:", note, file=sys.stderr)
    else:
        store = SqliteStore(db_path())
        try:
            _refresh_credits_if_stale(store)
            daily = store.credit_daily(since, until)
            totals = store.credits_totals(since, until)
            quota = store.latest_quota()
        finally:
            store.close()
    _write_credit_rows(daily, totals, quota, args.format)
    print("credits 为服务端每请求计费真值（billable=1 计入配额）；非 token，不可与 token 相加",
          file=sys.stderr)
    _print_quota(quota)
    if not daily:
        print("no credits data in range", file=sys.stderr)
    return 0


def _parse_est_dims(value: str | None) -> tuple[str, ...]:
    if not value:
        return ("day", "model")
    dims = tuple(item.strip() for item in value.split(",") if item.strip())
    for dim in dims:
        if dim not in ("day", "project", "model", "session"):
            raise ValueError("未知估算分组维度：%s" % dim)
    return dims


def _aggregate_estimates(estimates, dims, since, until) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for row in estimates:
        if since and row.day < since:
            continue
        if until and row.day > until:
            continue
        key = []
        for dim in dims:
            if dim == "day":
                key.append(row.day)
            elif dim == "project":
                key.append(row.project or "-")
            elif dim == "model":
                key.append(row.model)
            elif dim == "session":
                key.append(row.session or "-")
        bucket = buckets.setdefault(tuple(key), {
            "est_input": 0, "est_output": 0, "requests": 0,
            "chars_in": 0, "chars_out": 0, "missing_ratio": 0})
        bucket["est_input"] += row.est_input
        bucket["est_output"] += row.est_output
        bucket["requests"] += 1
        bucket["chars_in"] += row.chars_in
        bucket["chars_out"] += row.chars_out
        if row.ratio is None:
            bucket["missing_ratio"] += 1
    rows = []
    for key in sorted(buckets):
        item = {dim: key[i] for i, dim in enumerate(dims)}
        item.update(buckets[key])
        rows.append(item)
    return rows


def _write_est_rows(rows, dims, fmt: str):
    headers = [HEADERS[dim] for dim in dims] + ["est_input", "est_output", "requests"]
    if fmt == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if fmt == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row[dim] for dim in dims]
                            + [row["est_input"], row["est_output"], row["requests"]])
        return
    table = []
    for row in rows:
        values = [str(row[dim]) for dim in dims]
        values += [_fmt_int(row["est_input"]), _fmt_int(row["est_output"]),
                   str(row["requests"])]
        table.append(values)
    widths = [max(len(headers[i]), *(len(line[i]) for line in table)) if table
              else len(headers[i]) for i in range(len(headers))]
    print("".join(header.ljust(widths[i] + 2) for i, header in enumerate(headers)))
    for line in table:
        print("".join(value.ljust(widths[i] + 2) for i, value in enumerate(line)))


def cmd_est(args):
    since, until = _effective_range(args)
    dims = _parse_est_dims(args.group_by)
    source = EST_SOURCES[args.source]
    if args.stateless:
        if args.source == "trae-cn":
            result = scan_trae_cn_est(home=source_home())
        else:
            result = scan_qoder_credit_sources(source_home())
        rows = _aggregate_estimates(result.estimates, dims, since, until)
        missing = sum(1 for row in result.estimates if row.ratio is None)
        requests = len(result.estimates)
        for note in result.notes:
            print("note:", note, file=sys.stderr)
    else:
        store = SqliteStore(db_path())
        try:
            if args.source == "trae-cn":
                _refresh_trae_est_if_stale(store)
            else:
                _refresh_credits_if_stale(store)
            rows = store.est_rows(since, until, dims, source=source)
            totals = store.est_totals(since, until, source=source)
            missing = totals["missing_ratio"]
            requests = totals["requests"]
        finally:
            store.close()
    _write_est_rows(rows, dims, args.format)
    if args.source == "trae-cn":
        print(TRAE_EST_NOTICE, file=sys.stderr)
        if requests:
            print("估算覆盖 %d 请求（仅 hook 安装后的会话；无上下文比例）" % requests,
                  file=sys.stderr)
        else:
            print("no estimate data in range（先运行 usage hooks install trae-cn --scope global）",
                  file=sys.stderr)
    else:
        print("估算 token 由转录文本 + 上下文比例推算（%s），±30~40%% 误差，"
              "不可与真值/额度相加" % EST_FACTOR_VERSION, file=sys.stderr)
        if requests:
            print("估算覆盖 %d 请求；ratio 缺失 %d（这些请求 est_input 记 0）" %
                  (requests, missing), file=sys.stderr)
        else:
            print("no estimate data in range", file=sys.stderr)
    return 0


def _load_credit_payload(args, since, until, filters):
    if filters.get("source") not in (None, "qoder"):
        return None, {}, [], {}, EST_FACTOR_VERSION
    if args.stateless or not os.path.exists(db_path()):
        result = scan_qoder_credit_sources(source_home())
        days = _credit_daily_from_rows(result.credits, result.quota, since, until)
        totals = _credit_totals_from_rows(result.credits, since, until)
        quota = _quota_latest_rows(result.quota)
        est_rows = _aggregate_estimates(result.estimates, ("day", "model"), since, until)
        selected = [row for row in result.estimates
                    if (not since or row.day >= since) and (not until or row.day <= until)]
        est_totals = {
            "est_input": sum(row.est_input for row in selected),
            "est_output": sum(row.est_output for row in selected),
            "requests": len(selected),
            "days": len({row.day for row in selected}),
            "models": len({row.model for row in selected}),
            "missing_ratio": sum(1 for row in selected if row.ratio is None),
        }
    else:
        store = SqliteStore(db_path())
        try:
            _refresh_credits_if_stale(store)
            days = store.credit_daily(since, until)
            totals = store.credits_totals(since, until)
            quota = store.latest_quota()
            est_rows = store.est_rows(since, until, ("day", "model"))
            est_totals = store.est_totals(since, until)
        finally:
            store.close()
    return ({"days": days, "totals": totals}, quota, est_rows, est_totals,
            EST_FACTOR_VERSION)


def _load_trae_est_payload(args, since, until, filters):
    if filters.get("source") not in (None, "trae-cn"):
        return [], {}, TRAE_EST_VERSION
    if args.stateless or not os.path.exists(db_path()):
        result = scan_trae_cn_est(home=source_home())
        rows = _aggregate_estimates(result.estimates, ("day", "model"), since, until)
        selected = [row for row in result.estimates
                    if (not since or row.day >= since) and (not until or row.day <= until)]
        totals = {
            "est_input": sum(row.est_input for row in selected),
            "est_output": sum(row.est_output for row in selected),
            "requests": len(selected),
            "days": len({row.day for row in selected}),
            "models": len({row.model for row in selected}),
            "missing_ratio": sum(1 for row in selected if row.ratio is None),
        }
    else:
        store = SqliteStore(db_path())
        try:
            _refresh_trae_est_if_stale(store)
            rows = store.est_rows(since, until, ("day", "model"), source=TRAE_EST_SOURCE)
            totals = store.est_totals(since, until, source=TRAE_EST_SOURCE)
        finally:
            store.close()
    return rows, totals, TRAE_EST_VERSION


def cmd_html(args):
    since, until = _effective_range(args)
    filters = parse_filters(args.filter)
    if getattr(args, "project", None):
        filters["project"] = args.project
    if getattr(args, "source", None):
        filters["source"] = args.source
    if getattr(args, "model", None):
        filters["model"] = args.model
    records, activities, coverage = _load_records(args, since, until, filters)
    credit_data, quota, est_rows, est_totals, factor_version = _load_credit_payload(
        args, since, until, filters)
    trae_rows, trae_totals, trae_factor = _load_trae_est_payload(
        args, since, until, filters)
    dims = ("day", "source", "model", "project")
    rows = aggregate(records, dims)
    activity_rows = _filter_activity(activities, since, until, filters)
    span_days = [rec.day for rec in records] + [act.day for act in activity_rows]
    if credit_data:
        span_days += [row["day"] for row in credit_data["days"]]
    span_days += [row["day"] for row in est_rows]
    span_days += [row["day"] for row in trae_rows]
    display_since = since or min(span_days, default=None)
    display_until = until or max(span_days, default=None)
    payload = build_payload(rows, dims, display_since, display_until,
                            [COST_NOTICE, NO_TOKEN_NOTICE],
                            activity=activity_rows, coverage=coverage,
                            credits=credit_data, quota=quota, est_rows=est_rows,
                            est_totals=est_totals, factor_version=factor_version,
                            trae_est_rows=trae_rows, trae_est_totals=trae_totals,
                            trae_factor_version=trae_factor)
    output = os.path.abspath(os.path.expanduser(args.output or "usage-report.html"))
    parent = os.path.dirname(output)
    if parent and not os.path.isdir(parent):
        raise ValueError("输出目录不存在：%s" % parent)
    with open(output, "w", encoding="utf-8") as fh:
        fh.write(render_html(payload))
    total = sum(row["total"] for row in rows)
    span = "%s..%s" % (display_since, display_until) if display_since and display_until else "empty"
    print("wrote %s" % output)
    print("rows=%d records=%d tokens=%s range=%s" %
          (len(rows), len(records), _fmt_int(total), span))
    if args.open:
        webbrowser.open(Path(output).as_uri())
    return 0


def cmd_top(args):
    since, until = _effective_range(args)
    filters = parse_filters(None)
    records, _, _ = _load_records(args, since, until, filters)
    dims = {
        "models": ("source", "model"),
        "sources": ("source",),
        "projects": ("project",),
        "sessions": ("source", "session"),
    }[args.kind]
    rows = aggregate(records, dims)
    rows.sort(key=lambda row: row["total"], reverse=True)
    rows = rows[:args.limit]
    if args.format == "json":
        payload = []
        for row in rows:
            item = {HEADERS[dim]: row["dims"][i] for i, dim in enumerate(dims)}
            item["total"] = row["total"]
            item["turns"] = row["turns"]
            for field in FIELDS:
                item[field] = row[field]
            payload.append(item)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        print("%s\t%s\t%s" % ("\t".join(row["dims"]), row["total"], row["turns"]))
    return 0


def _activity_month_summary(activities: list[Activity]) -> dict:
    months: dict[str, dict] = {}
    for act in activities:
        bucket = months.setdefault(act.day[:7], {
            "sessions": 0, "prompts": 0, "assistant_calls": 0,
            "assistant_with_metrics": 0, "turns": 0, "tool_calls": 0,
            "duration_ms": 0})
        for field in ACTIVITY_FIELDS:
            bucket[field] += getattr(act, field)
    return months


def _quota_cross_check(credits, quota) -> list[str]:
    points = sorted((row.ts, row.used) for row in quota if row.quota_kind == "add_on")
    if len(points) < 2:
        return []
    billable = [(row.ts, row.credits) for row in credits if row.billable]
    lines = []
    for (t1, u1), (t2, u2) in zip(points, points[1:]):
        delta = u2 - u1
        if delta <= 0 or t2 <= t1:
            continue
        total = sum(value for ts, value in billable if t1 < ts <= t2)
        if total <= 0:
            continue
        deviation = abs(total - delta) / delta
        lines.append("%s→%s 快照 +%d，billable credits %.2f，偏差 %.0f%%%s" %
                     (datetime.fromtimestamp(t1).strftime("%m-%d %H:%M"),
                      datetime.fromtimestamp(t2).strftime("%H:%M"), delta, total,
                      deviation * 100, "（>20%，疑似漏读）" if deviation > 0.2 else ""))
    return lines[-3:]


def cmd_doctor(args):
    state = {}
    meta = {}
    path = db_path()
    if not args.stateless:
        print("DB:", path)
        if os.path.exists(path):
            store = SqliteStore(path)
            print("turns:", store.turn_count(), " daily aggregates:", store.daily_count())
            print("已保全 %d 条源已删除的历史记录 (archived=1)" % store.archived_count())
            activity = store.activity_summary(ACTIVITY_SOURCE)
            if activity["days"]:
                print("activity: days=%d rows=%d sessions=%d prompts=%d tool_calls=%d" %
                      (activity["days"], store.activity_count(), activity["sessions"],
                       activity["prompts"], activity["tool_calls"]))
            print("credits: requests=%d quota_snapshots=%d est_rows=%d missing_ratio=%d "
                  "trae_est_rows=%d" %
                  (store.credit_count(), store.quota_count(), store.est_count(),
                   store.est_missing_ratio(), store.est_count(TRAE_EST_SOURCE)))
            latest_quota = store.latest_quota().get("add_on")
            if latest_quota:
                age_h = (time.time() - latest_quota["ts"]) / 3600
                print("quota: used %s/%s remaining %s（%s，%.1f 小时前）" %
                      (_fmt_int(latest_quota["used"]), _fmt_int(latest_quota["total"]),
                       _fmt_int(latest_quota["remaining"]), latest_quota["day"], age_h))
                if age_h > 24:
                    print("warning: 额度快照已超过 24h，本地日志可能未触发用量查询")
            elif store.credit_count():
                print("warning: 有 credits 记录但无额度快照（日志留存窗口可能已过）")
            print("size: %s  wal: %s" % (_human_size(store.db_size()),
                                          _human_size(store.wal_size())))
            for row in store.source_states():
                print("state:", row)
                state[row[0]] = row
            for key in (ACTIVITY_CURSOR_KEY, ACTIVITY_STALL_KEY):
                meta[key] = store.get_meta(key)
            for source in SOURCES:
                full = store.get_meta("full_scan_at:" + source)
                if full:
                    print("last full scan %s: %s" % (source, full))
            if store.wal_size() > 1_000_000:
                print("warning: WAL 超过 1MB，建议执行 sqlite3 %s 'PRAGMA wal_checkpoint(TRUNCATE)'" % path)
            store.close()
        else:
            print("DB 不存在（尚未 sync/backfill）")

    hook = trae_hooks.status("global", home=source_home())
    installed = sum(hook["hook_groups"].values())
    if hook["config_exists"] or hook["script_exists"] or installed:
        print("trae-cn hooks: config=%s installed=%d/%d script=%s files=%d events=%d "
              "sessions=%d" %
              (hook["config_path"], installed, len(trae_hooks.HOOK_EVENTS),
               hook["script_path"], hook.get("files", 0), hook.get("events", 0),
               hook.get("sessions", 0)))
        if hook.get("error"):
            print("  warning: hooks 配置无法解析：%s" % hook["error"])
        latest = hook.get("last")
        if isinstance(latest, dict) and isinstance(latest.get("ts"), (int, float)):
            print("  latest: %s（%s）" % (latest.get("event"), _ago(latest["ts"])))
    else:
        print("trae-cn hooks: 未安装（usage hooks install trae-cn --scope global）")

    results = _source_results([args.probe] if args.probe else None)
    probe_name = TRAE_EST_SOURCE if args.probe == "trae-cn" else args.probe
    if args.probe and not any(result.name == probe_name for result in results):
        print("unknown source: %s" % args.probe, file=sys.stderr)
        return 2
    recent_cutoff = (date.today() - timedelta(days=7)).isoformat()
    for result in results:
        if result.name == ACTIVITY_SOURCE:
            totals = _activity_totals(result.activities)
            print("qoder.activity: files=%d days=%d sessions=%d prompts=%d assistant=%d "
                  "tool_calls=%d rows=%d errors=%d status=%s" %
                  (result.files, len(result.affected_days), totals["sessions"],
                   totals["prompts"], totals["assistant_calls"], totals["tool_calls"],
                   totals["rows"], len(result.errors), _status(result)))
            for note in result.notes:
                print("  note:", note)
            if totals["assistant_calls"]:
                print("  turnMetrics 覆盖：%d/%d assistant（%.1f%%）" %
                      (totals["assistant_with_metrics"], totals["assistant_calls"],
                       100.0 * totals["assistant_with_metrics"] / totals["assistant_calls"]))
            for error_path, error in result.errors[:5]:
                print("  ERROR", error_path, error)
            if not result.available:
                print("  warning: Qoder 活动库不可读；活动指标无法刷新")
            if not args.stateless:
                stall = meta.get(ACTIVITY_STALL_KEY)
                if stall and stall.isdigit() and int(stall) >= 3:
                    print("  warning: 活动库持续更新但连续 %s 次未推进 cursor，疑似 schema drift" % stall)
                previous = state.get(result.name)
                if previous and previous[3] and totals["rows"] < previous[3] * 0.5:
                    print("  warning: 活动行数较上次下降超过 50%%（%d -> %d），疑似格式漂移" %
                          (previous[3], totals["rows"]))
            if args.probe == "qoder":
                for month, bucket in sorted(_activity_month_summary(result.activities).items()):
                    print("  %s sessions=%d prompts=%d assistant=%d tool_calls=%d "
                          "turns=%d duration=%s" %
                          (month, bucket["sessions"], bucket["prompts"],
                           bucket["assistant_calls"], bucket["tool_calls"],
                           bucket["turns"], _fmt_duration(bucket["duration_ms"])))
            continue

        if result.name == TRAE_EST_SOURCE:
            print("trae-cn.est: files=%d events=%d sessions=%d estimates=%d "
                  "errors=%d status=%s" %
                  (result.files, result.key_kinds.get("events", 0),
                   result.key_kinds.get("sessions", 0), len(result.estimates),
                   len(result.errors), _status(result)))
            for note in result.notes:
                print("  note:", note)
            if not result.available:
                print("  warning: hook 事件目录不存在；估算无法刷新")
            for error_path, error in result.errors[:5]:
                print("  ERROR", error_path, error)
            continue

        if result.name == "qoder.credits":
            print("qoder.credits: files=%d credits=%d est=%d quota=%d errors=%d status=%s" %
                  (result.files, len(result.credits), len(result.estimates),
                   len(result.quota), len(result.errors), _status(result)))
            for note in result.notes:
                print("  note:", note)
            if result.credits:
                days = [row.day for row in result.credits]
                print("  credits 覆盖 %s ~ %s；ratio 缺失响应 %d（旧版转录，不计估算）" %
                      (min(days), max(days), result.key_kinds.get("missing:ratio", 0)))
            if result.key_kinds.get("quota:parse_error"):
                print("  warning: 额度日志解析失败 %d 行，疑似 schema drift" %
                      result.key_kinds["quota:parse_error"])
            latest = _quota_latest_rows(result.quota).get("add_on")
            if latest:
                age_h = (time.time() - latest["ts"]) / 3600
                print("  最新额度快照：used %s/%s，remaining %s，%s（%.1f 小时前）" %
                      (_fmt_int(latest["used"]), _fmt_int(latest["total"]),
                       _fmt_int(latest["remaining"]), latest["day"], age_h))
                if age_h > 24:
                    print("  warning: 额度快照已 %.1f 小时未更新（>24h），"
                          "客户端可能未触发用量查询" % age_h)
            else:
                print("  warning: 未找到额度快照；日志留存窗口内无 AccountUsage 摘要")
            for line in _quota_cross_check(result.credits, result.quota):
                print("  check: %s" % line)
            continue

        tokens = sum(rec.counts.total() for rec in result.records)
        recent = sum(1 for rec in result.records if rec.day >= recent_cutoff)
        print("%s: files=%d records=%d tokens=%s recent7d=%d errors=%d status=%s" %
              (result.name, result.files, len(result.records), _fmt_int(tokens),
               recent, len(result.errors), _status(result)))
        for note in result.notes:
            print("  note:", note)
        if tokens == 0 and result.records:
            print("  warning: 记录存在但 token 全为 0，疑似上游字段变更")
        if result.name == "qoder":
            if not result.available:
                print("  warning: Qoder token 库不存在；历史 token 只能从库中已有记录查看")
            else:
                signature = source_signatures(source_home(), ["qoder"]).get("qoder")
                if signature:
                    age_days = (time.time() - signature / 1_000_000) / 86400
                    if age_days > 30:
                        print("  warning: Qoder token 库已 %.0f 天未更新（新版客户端不写 token）" %
                              age_days)
        for error_path, error in result.errors[:5]:
            print("  ERROR", error_path, error)
        if args.probe:
            models = Counter()
            for rec in result.records:
                models[rec.model] += rec.counts.total()
            for model, total in models.most_common(30):
                print("  %-45s %s" % (model, _fmt_int(total)))

        if not args.stateless:
            previous = state.get(result.name)
            if previous and previous[3] and len(result.records) < previous[3] * 0.5:
                print("  warning: 记录数较上次下降超过 50%%（%d -> %d），疑似格式漂移" %
                      (previous[3], len(result.records)))
            if previous and previous[4]:
                try:
                    last = datetime.fromisoformat(previous[4])
                    age = (datetime.now(last.tzinfo) - last).total_seconds() / 3600
                    if age > 26:
                        print("  warning: 上次同步在 %.1f 小时前（>26h，归档判定可能停摆）" % age)
                except ValueError:
                    pass
    print(NO_TOKEN_NOTICE)
    return 0


def cmd_pricing(args):
    from .pricing import ALIASES, PRICES
    if not args.model:
        for alias, target in sorted(ALIASES.items()):
            price = PRICES.get(target)
            status = "priced" if price and any(v is not None for v in price.values()) else "unknown"
            print("%-45s -> %-28s %s" % (alias, target, status))
        return 0
    normalized = normalize_model(args.model)
    print("model:      ", args.model)
    print("normalized: ", normalized)
    price = PRICES.get(normalized)
    if not price or all(value is None for value in price.values()):
        print("price:       unknown（不估算、不填 0）")
    else:
        print("price per 1M tokens:", price)
    return 0


def cmd_prune(args):
    if args.stateless:
        print("prune 需要数据库，不能与 --stateless 同时使用", file=sys.stderr)
        return 2
    store = SqliteStore(db_path())
    stats = store.prune(args.keep_days, args.dry_run)
    store.close()
    prefix = "dry-run: " if args.dry_run else ""
    print("%scutoff=%s candidate=%d deleted=%d kept_archived=%d" %
          (prefix, stats["cutoff"], stats["candidate"], stats["deleted"],
           stats["kept_archived"]))
    return 0


def cmd_schedule(args):
    if args.action == "install":
        for message in scheduler.install(dry_run=args.dry_run):
            print(message)
        if args.dry_run:
            print("dry-run: 未写入、未加载。正式安装：usage schedule install")
    elif args.action == "uninstall":
        for message in scheduler.uninstall():
            print(message)
    else:
        rows = scheduler.status()
        for row in rows:
            print("%-6s %-32s installed=%-5s loaded=%-5s %s" %
                  (row["job"], row["label"], row["installed"], row["loaded"], row["plist"]))
    return 0


def cmd_hooks(args):
    if args.action == "status":
        info = trae_hooks.status(args.scope, args.project, home=source_home())
        print("source: trae-cn")
        print("config: %s (exists=%s)" % (info["config_path"], info["config_exists"]))
        print("script: %s (exists=%s)" % (info["script_path"], info["script_exists"]))
        if info.get("error"):
            print("error: %s" % info["error"])
        for event, count in info["hook_groups"].items():
            print("hook: %-18s groups=%d" % (event, count))
        print("events: files=%d events=%d sessions=%d" %
              (info.get("files", 0), info.get("events", 0), info.get("sessions", 0)))
        latest = info.get("last")
        if isinstance(latest, dict) and isinstance(latest.get("ts"), (int, float)):
            print("latest: %s at %s" %
                  (latest.get("event"),
                   datetime.fromtimestamp(latest["ts"]).astimezone().isoformat(
                       timespec="seconds")))
        if not sum(info["hook_groups"].values()):
            print("hint: usage hooks install trae-cn --scope global")
        return 0

    if args.action == "install":
        info = trae_hooks.install(args.scope, args.project, home=source_home(),
                                  dry_run=args.dry_run)
        print("config: %s" % info["config_path"])
        print("script: %s" % info["script_path"])
        print("command: %s" % info["command"])
        if info["backup"]:
            print("backup: %s" % info["backup"])
        touched = sum(1 for event, groups in info["config"]["hooks"].items()
                      if event in trae_hooks.HOOK_EVENTS and groups)
        print("installed: %d events（弱估算，仅记录字符数与元数据）" % touched)
        print("提示：如 Trae CN 未自动加载，请在 Settings > Hooks 中确认并启用；"
              "hook 需要以“本地自动运行”模式执行。")
        if args.dry_run:
            print("dry-run: 未写入 hooks.json、未创建 hook 脚本")
        return 0

    info = trae_hooks.uninstall(args.scope, args.project, home=source_home(),
                                dry_run=args.dry_run)
    print("config: %s" % info["config_path"])
    print("removed groups: %d" % info["removed"])
    if info["backup"]:
        print("backup: %s" % info["backup"])
    if args.dry_run:
        print("dry-run: 未修改 hooks.json")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="usage")
    parser.add_argument("--version", action="version",
                        version="usage-ledger %s" % __version__)
    parser.add_argument("--stateless", action="store_true",
                        help="不读库、不落库，直接读源")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sync = sub.add_parser("sync")
    sync.add_argument("--source", action="append", choices=SOURCES)
    sync.add_argument("--since")
    sync.add_argument("--full", action="store_true")
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=cmd_sync)

    backfill = sub.add_parser("backfill")
    backfill.add_argument("--since")
    backfill.add_argument("--source", action="append", choices=SOURCES)
    backfill.set_defaults(func=cmd_backfill)

    live = sub.add_parser("live")
    live.add_argument("--source", choices=SOURCES)
    live.add_argument("--session")
    live.add_argument("--watch", nargs="?", const=2, type=int)
    live.set_defaults(func=cmd_live)

    def add_report_args(command):
        command.add_argument("--daily", action="store_true")
        command.add_argument("--weekly", action="store_true")
        command.add_argument("--monthly", action="store_true")
        command.add_argument("--range")
        command.add_argument("--group-by")
        command.add_argument("--filter")
        command.add_argument("--format", choices=["table", "json", "csv"], default="table")
        command.add_argument("--project")
        command.add_argument("--live", action="store_true")
        command.add_argument("--since")
        command.add_argument("--until")
        command.add_argument("--source", choices=SOURCES)
        command.add_argument("--model")

    report = sub.add_parser("report")
    add_report_args(report)
    report.set_defaults(func=cmd_report)

    export = sub.add_parser("export")
    add_report_args(export)
    export.set_defaults(func=cmd_export)

    activity = sub.add_parser("activity")
    activity.add_argument("--range")
    activity.add_argument("--since")
    activity.add_argument("--until")
    activity.add_argument("--source", choices=SOURCES)
    activity.add_argument("--project")
    activity.add_argument("--group-by")
    activity.add_argument("--format", choices=["table", "json", "csv"], default="table")
    activity.set_defaults(func=cmd_activity)

    credits = sub.add_parser("credits")
    credits.add_argument("--range")
    credits.add_argument("--since")
    credits.add_argument("--until")
    credits.add_argument("--format", choices=["table", "json"], default="table")
    credits.set_defaults(func=cmd_credits)

    est = sub.add_parser("est")
    est.add_argument("--range")
    est.add_argument("--since")
    est.add_argument("--until")
    est.add_argument("--source", choices=["qoder", "trae-cn"], default="qoder")
    est.add_argument("--group-by")
    est.add_argument("--format", choices=["table", "json", "csv"], default="table")
    est.set_defaults(func=cmd_est)

    html = sub.add_parser("html")
    html.add_argument("--range")
    html.add_argument("--since")
    html.add_argument("--until")
    html.add_argument("--source", choices=SOURCES)
    html.add_argument("--model")
    html.add_argument("--project")
    html.add_argument("--filter")
    html.add_argument("--live", action="store_true")
    html.add_argument("--output", default="usage-report.html")
    html.add_argument("--open", action="store_true")
    html.set_defaults(func=cmd_html)

    top = sub.add_parser("top")
    top.add_argument("kind", choices=["models", "sources", "projects", "sessions"])
    top.add_argument("--since")
    top.add_argument("--until")
    top.add_argument("--limit", type=int, default=20)
    top.add_argument("--format", choices=["table", "json"], default="table")
    top.set_defaults(func=cmd_top)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--probe", choices=SOURCES)
    doctor.set_defaults(func=cmd_doctor)

    pricing = sub.add_parser("pricing")
    pricing.add_argument("model", nargs="?")
    pricing.set_defaults(func=cmd_pricing)

    prune = sub.add_parser("prune")
    prune.add_argument("--keep-days", type=int, default=90)
    prune.add_argument("--dry-run", action="store_true")
    prune.set_defaults(func=cmd_prune)

    schedule = sub.add_parser("schedule")
    schedule.add_argument("action", choices=["install", "uninstall", "status"])
    schedule.add_argument("--dry-run", action="store_true")
    schedule.set_defaults(func=cmd_schedule)

    hooks = sub.add_parser("hooks", help="Trae CN hook 安装/状态/卸载")
    hooks.add_argument("action", choices=["install", "uninstall", "status"])
    hooks.add_argument("source", choices=["trae-cn"])
    hooks.add_argument("--scope", choices=["global", "project"], default="global")
    hooks.add_argument("--project")
    hooks.add_argument("--dry-run", action="store_true")
    hooks.set_defaults(func=cmd_hooks)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print("error:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
