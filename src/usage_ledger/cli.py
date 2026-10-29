from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta

from . import scheduler
from .aggregation import DIMENSIONS, aggregate, match, merge_records, missing_days
from .collectors import collect_all
from .models import FIELDS, SourceResult
from .pricing import cost_for_record, normalize_model
from .store import SqliteStore

SOURCES = ("claude", "codex", "opencode", "kilo")
DEFAULT_DIMS = ("day", "source", "model")
HEADERS = {
    "day": "date", "week": "week", "month": "month", "source": "source",
    "model": "model", "project": "project", "session": "session",
}
NO_TOKEN_NOTICE = ("无 token 数据：Qoder（订阅套餐本地 token 恒为 0）、"
                   "Trae CN（本地只有额度键）、ChatGPT 桌面端（无本地数据）")
COST_NOTICE = "cost_equiv_usd 为按 API 价折算的等价成本，非实付；unknown 表示无价格表匹配"


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


def _source_results(sources: list[str] | None = None) -> list[SourceResult]:
    return collect_all(source_home(), sources)


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


def cmd_sync(args):
    if args.stateless:
        print("sync 需要写入数据库，不能与 --stateless 同时使用", file=sys.stderr)
        return 2
    since = parse_day(args.since) if args.since else None
    results = _source_results(args.source)
    if args.dry_run:
        for result in results:
            records = [rec for rec in result.records if not since or rec.day >= since]
            tokens = sum(rec.counts.total() for rec in records)
            print("%s: %d records, %s tokens, files=%d, status=%s" %
                  (result.name, len(records), _fmt_int(tokens), result.files, _status(result)))
        return 0

    store = SqliteStore(db_path())
    total = 0
    archived_total = 0
    for result in results:
        if args.source and result.name not in args.source:
            continue
        records = [rec for rec in result.records if not since or rec.day >= since]
        if records:
            store.upsert_records(records, cost_fn=cost_for_record)
        status = _status(result)
        error = "; ".join(msg for _, msg in result.errors[:3]) or None
        store.update_source_state(
            result.name, result.files, len(result.records), status, error,
            max((rec.ts for rec in result.records), default=None),
        )
        archived = restored = 0
        if args.full and result.healthy and not since:
            archived, restored = store.mark_archived(
                result.name, {rec.key for rec in result.records})
            store.set_meta("full_scan_at:" + result.name, _now_iso())
            archived_total += archived
        total += len(records)
        tokens = sum(rec.counts.total() for rec in records)
        extra = ""
        if args.full and result.healthy and not since:
            extra = ", archived=%d restored=%d" % (archived, restored)
        print("%s: %d records, %s tokens, files=%d, errors=%d, status=%s%s" %
              (result.name, len(records), _fmt_int(tokens), result.files,
               len(result.errors), status, extra))
        for note in result.notes:
            print("  note:", note)
    store.close()
    print("synced %d records -> %s" % (total, db_path()))
    if archived_total:
        print("newly archived %d records (source no longer contains them)" % archived_total)
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
    print(NO_TOKEN_NOTICE)


def _effective_range(args) -> tuple[str | None, str | None]:
    since = until = None
    if getattr(args, "range", None):
        since, until = parse_range(args.range)
    if getattr(args, "since", None):
        since = parse_day(args.since)
    if getattr(args, "until", None):
        until = parse_day(args.until)
    return since, until


def _load_records(args, since, until, filters) -> list:
    if args.stateless:
        results = _source_results([filters["source"]] if "source" in filters else None)
        records = [rec for result in results for rec in result.records]
    else:
        if not os.path.exists(db_path()):
            print("warning: 数据库不存在，自动降级为 --stateless（读源）", file=sys.stderr)
            results = _source_results([filters["source"]] if "source" in filters else None)
            records = [rec for result in results for rec in result.records]
        else:
            store = SqliteStore(db_path())
            records = store.fetch_records(
                since=since, until=until, source=filters.get("source"),
                model=filters.get("model"), project=filters.get("project"))
            store.close()
            if getattr(args, "live", False):
                results = _source_results([filters["source"]] if "source" in filters else None)
                records = merge_records(records, [rec for result in results
                                                  for rec in result.records])
    records = [rec for rec in records
               if (not since or rec.day >= since) and (not until or rec.day <= until)
               and match(rec, filters)]
    return records


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
    records = _load_records(args, since, until, filters)
    dims = parse_dims(args.group_by)
    rows = aggregate(records, dims, _period(args))
    return rows, dims, records, since, until


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


def cmd_report(args):
    rows, dims, records, since, until = _report_rows(args)
    _write_rows(rows, dims, args.format)
    _footnotes(records, since, until)
    return 0


def cmd_export(args):
    args.format = "csv"
    return cmd_report(args)


def cmd_top(args):
    since, until = _effective_range(args)
    filters = parse_filters(None)
    records = _load_records(args, since, until, filters)
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


def cmd_doctor(args):
    state = {}
    path = db_path()
    if not args.stateless:
        print("DB:", path)
        if os.path.exists(path):
            store = SqliteStore(path)
            print("turns:", store.turn_count(), " daily aggregates:", store.daily_count())
            print("已保全 %d 条源已删除的历史记录 (archived=1)" % store.archived_count())
            print("size: %s  wal: %s" % (_human_size(store.db_size()),
                                          _human_size(store.wal_size())))
            for row in store.source_states():
                print("state:", row)
                state[row[0]] = row
            for source in SOURCES:
                full = store.get_meta("full_scan_at:" + source)
                if full:
                    print("last full scan %s: %s" % (source, full))
            if store.wal_size() > 1_000_000:
                print("warning: WAL 超过 1MB，建议执行 sqlite3 %s 'PRAGMA wal_checkpoint(TRUNCATE)'" % path)
            store.close()
        else:
            print("DB 不存在（尚未 sync/backfill）")

    results = _source_results([args.probe] if args.probe else None)
    if args.probe and not any(result.name == args.probe for result in results):
        print("unknown source: %s" % args.probe, file=sys.stderr)
        return 2
    recent_cutoff = (date.today() - timedelta(days=7)).isoformat()
    for result in results:
        tokens = sum(rec.counts.total() for rec in result.records)
        recent = sum(1 for rec in result.records if rec.day >= recent_cutoff)
        print("%s: files=%d records=%d tokens=%s recent7d=%d errors=%d status=%s" %
              (result.name, result.files, len(result.records), _fmt_int(tokens),
               recent, len(result.errors), _status(result)))
        for note in result.notes:
            print("  note:", note)
        if tokens == 0 and result.records:
            print("  warning: 记录存在但 token 全为 0，疑似上游字段变更")
        for path, error in result.errors[:5]:
            print("  ERROR", path, error)
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


def build_parser():
    parser = argparse.ArgumentParser(prog="usage")
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
