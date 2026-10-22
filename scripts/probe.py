#!/usr/bin/env python3
"""usage-ledger 探针：只读扫描本机 4 个源，产出真实 token 台账快照。

用途：在实现完整框架前，用一次性全量扫描回答 DESIGN 里悬而未决的问题
（成本口径、覆盖完整性、去重行为、模型清单），同时验证各源格式规格。

约束：
  - 标准库 only
  - 严格只读（源目录只开读，SQLite 用 mode=ro URI）
  - 不写任何源目录；只输出到 stdout

用法：
  python3 scripts/probe.py [--days N] [--source NAME] [--json OUT.json]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import os
import sqlite3
import sys

HOME = os.path.expanduser("~")

CLAUDE_DIR = os.path.join(HOME, ".claude", "projects")
CODEX_DIR = os.path.join(HOME, ".codex", "sessions")
CODEX_ARCHIVED_DIR = os.path.join(HOME, ".codex", "archived_sessions")
OPENCODE_DB = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")
KILO_DB = os.path.join(HOME, ".local", "share", "kilo", "kilo.db")

FIELDS = ("input", "output", "cache_read", "cache_write", "reasoning")


def local_day(ts_seconds: float) -> str:
    return dt.datetime.fromtimestamp(ts_seconds).strftime("%Y-%m-%d")


def parse_iso(ts: str) -> float:
    """ISO8601（可能带 Z）→ epoch 秒。"""
    s = ts.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s).timestamp()


def blank() -> dict:
    return {f: 0 for f in FIELDS}


# --------------------------------------------------------------------------
# 记录模型
# --------------------------------------------------------------------------

class Record:
    __slots__ = ("source", "day", "model", "project", "session", "key", "counts", "ts")

    def __init__(self, source, day, model, project, session, key, counts, ts):
        self.source = source
        self.day = day
        self.model = model
        self.project = project
        self.session = session
        self.key = key
        self.counts = counts
        self.ts = ts


class SourceResult:
    def __init__(self, name):
        self.name = name
        self.files = 0
        self.raw = 0          # 原始命中行数
        self.records = []     # 去重后的 Record
        self.errors = []      # (文件, 原因)
        self.notes = []
        self.seen_keys = set()
        self.dup_dropped = 0
        self.key_kinds = collections.Counter()
        self._index = {}

    def add(self, rec: Record):
        self.raw += 1
        prev_idx = self._index.get(rec.key)
        if prev_idx is not None:
            self.dup_dropped += 1
            # 同键重复行：保留 token 总量更大的那条（实测同键行 usage 完全一致，
            # 这里只是防御性策略，避免"先到先得"把完整行丢掉）
            prev = self.records[prev_idx]
            if sum(rec.counts.values()) > sum(prev.counts.values()):
                self.records[prev_idx] = rec
            return
        self._index[rec.key] = len(self.records)
        self.records.append(rec)

    def summary(self):
        days = sorted({r.day for r in self.records}) if self.records else []
        return {
            "source": self.name,
            "files": self.files,
            "raw_lines": self.raw,
            "unique_records": len(self.records),
            "duplicates_dropped": self.dup_dropped,
            "day_from": days[0] if days else None,
            "day_to": days[-1] if days else None,
            "active_days": len(days),
            "errors": len(self.errors),
            "key_kinds": dict(self.key_kinds),
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# Claude Code（JSONL）
# --------------------------------------------------------------------------

def scan_claude(res: SourceResult):
    if not os.path.isdir(CLAUDE_DIR):
        res.notes.append("目录不存在：%s" % CLAUDE_DIR)
        return
    files = sorted(glob.glob(os.path.join(CLAUDE_DIR, "**", "*.jsonl"), recursive=True))
    subagent_files = [f for f in files if os.sep + "subagents" + os.sep in f]
    res.notes.append("含 subagents/ transcript：%d 个" % len(subagent_files))
    for path in files:
        res.files += 1
        try:
            fh = open(path, "r", errors="ignore")
        except OSError as exc:
            res.errors.append((path, str(exc)))
            continue
        with fh:
            for lineno, line in enumerate(fh, 1):
                if '"assistant"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    res.errors.append((path, "line %d: JSON 解析失败" % lineno))
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage") or {}
                if not usage:
                    continue
                # 中间态行：Claude Code 会为同一条 assistant 消息反复写入
                # "进行中"的 usage（output=0、cache=0、cache_creation=null），
                # 最终才写入一条完整 usage（含 usage.iterations 与 cache_creation 明细）。
                # 只保留完整行，否则会把上下文总量误记为 input、并丢掉 cache_read。
                if "iterations" not in usage:
                    res.key_kinds["skipped:intermediate"] += 1
                    continue
                model = msg.get("model") or "unknown"
                counts = {
                    "input": usage.get("input_tokens") or 0,
                    "output": usage.get("output_tokens") or 0,
                    "cache_read": usage.get("cache_read_input_tokens") or 0,
                    "cache_write": usage.get("cache_creation_input_tokens") or 0,
                    "reasoning": 0,
                }
                # 去重键：requestId 优先，退回 message.id
                rid = obj.get("requestId") or msg.get("id") or obj.get("uuid")
                key_kind = "requestId" if obj.get("requestId") else ("message.id" if msg.get("id") else "uuid")
                res.key_kinds[key_kind] += 1
                if not any(counts.values()):
                    res.key_kinds["zero-usage"] += 1
                    continue
                sid = obj.get("sessionId") or os.path.basename(path).split(".")[0]
                try:
                    ts = parse_iso(obj["timestamp"])
                except Exception:
                    res.errors.append((path, "line %d: 时间戳缺失/无法解析" % lineno))
                    continue
                res.add(Record(
                    source="claude", day=local_day(ts), model=model,
                    project=os.path.basename(obj.get("cwd") or "") or None,
                    session=sid, key="claude:%s" % rid, counts=counts, ts=ts,
                ))


# --------------------------------------------------------------------------
# Codex CLI（JSONL）
#
# 口径（实测结论，DESIGN §5.2 需要修订）：
#   * event_msg/token_count 是唯一的累计口径；info.total_token_usage 是累计值，
#     info.last_token_usage 是"最近一次 API 调用"的增量。
#   * 每个事件的 last_token_usage == 累计值的本次增量（4,328/4,328 完全吻合）。
#   * 同一事件可能被重复写多次（累计值不变）→ 求和 last 会重复计数，
#     正确做法是取累计值的增量。
#   * 每个 rollout 文件的累计值可能"继承"上一段会话（同一 session_id 的续写文件），
#     此时首个事件的累计值远大于 last_token_usage → 首事件必须用 last_token_usage。
#   * token_usage_record 是新格式下"每个 API 响应一条"的明细，与 token_count
#     是同一条流，不能相加（老文件根本没有它，新文件才有）。
#   * 模型名不在 token_count 里，在同文件的 turn_context.payload.model。
# --------------------------------------------------------------------------

def scan_codex(res: SourceResult):
    roots = []
    for root in (CODEX_DIR, CODEX_ARCHIVED_DIR):
        if os.path.isdir(root):
            roots.extend(sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)))
        else:
            res.notes.append("目录不存在：%s" % root)
    zst = []
    for root in (CODEX_DIR, CODEX_ARCHIVED_DIR):
        zst.extend(glob.glob(os.path.join(root, "**", "*.jsonl.zst"), recursive=True))
    res.notes.append("归档 rollout 文件：%d 个（其中 sessions/ %d + archived_sessions/ %d）"
                     % (len(roots),
                        len([f for f in roots if CODEX_DIR in f]),
                        len([f for f in roots if CODEX_ARCHIVED_DIR in f])))
    res.notes.append("未解析的 .zst 压缩归档：%d 个" % len(zst))

    for path in roots:
        res.files += 1
        stem = os.path.basename(path).split(".")[0]
        events = []          # (ts, cum, last)
        models = []          # 与 events 同序的模型（由 turn_context 决定）
        current_model = None
        session = None
        project = None
        try:
            fh = open(path, "r", errors="ignore")
        except OSError as exc:
            res.errors.append((path, str(exc)))
            continue
        with fh:
            for lineno, line in enumerate(fh, 1):
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
            def g(d, k):
                v = d.get(k)
                return v if isinstance(v, int) else 0

            def split(raw_in, cached, raw_out, reasoning):
                """Codex 口径：
                   input_tokens 已包含 cached_input_tokens → 需扣出；
                   reasoning_output_tokens 是 output_tokens 的子集 → 需拆出。
                   拆分后五项互不重叠，合计 == total_tokens。"""
                return {
                    "input": max(raw_in - cached, 0),
                    "output": max(raw_out - reasoning, 0),
                    "cache_read": cached,
                    "cache_write": 0,
                    "reasoning": reasoning,
                }

            if prev_cum is None:
                # 首事件：累计值可能继承自上一段会话，用 last_token_usage 更稳
                inc = split(g(last, "input_tokens"), g(last, "cached_input_tokens"),
                            g(last, "output_tokens"), g(last, "reasoning_output_tokens"))
                inc["cache_write"] = g(last, "cache_write_input_tokens")
            else:
                d_cached = max(g(cum, "cached_input_tokens") - g(prev_cum, "cached_input_tokens"), 0)
                d_reason = max(g(cum, "reasoning_output_tokens") - g(prev_cum, "reasoning_output_tokens"), 0)
                inc = split(max(g(cum, "input_tokens") - g(prev_cum, "input_tokens"), 0),
                            d_cached,
                            max(g(cum, "output_tokens") - g(prev_cum, "output_tokens"), 0),
                            d_reason)
                inc["cache_write"] = max(g(cum, "cache_write_input_tokens") - g(prev_cum, "cache_write_input_tokens"), 0)
            prev_cum = cum
            if not any(inc.values()):
                res.key_kinds["zero-usage"] += 1
                continue
            # 去重键：文件 stem + 累计值（累计值在文件内单调，唯一标识一次调用）
            key = "codex:%s:%d" % (stem, g(cum, "total_tokens"))
            try:
                epoch = parse_iso(ts)
            except Exception:
                continue
            res.key_kinds["stem+cum"] += 1
            res.add(Record(
                source="codex", day=local_day(epoch), model=model or "unknown",
                project=os.path.basename(project or "") or None,
                session=session, key=key, counts=inc, ts=epoch,
            ))


# --------------------------------------------------------------------------
# OpenCode / Kilo（SQLite，同构 adapter）
# --------------------------------------------------------------------------

def scan_sqlite_agent(res: SourceResult, db_path: str, source_name: str):
    if not os.path.exists(db_path):
        res.notes.append("DB 不存在：%s" % db_path)
        return
    res.files += 1
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    except Exception as exc:
        res.errors.append((db_path, str(exc)))
        return
    try:
        rows = conn.execute(
            "SELECT id, session_id, time_created, time_updated, data FROM message"
        ).fetchall()
    except Exception as exc:
        res.errors.append((db_path, "查询失败：%s" % exc))
        conn.close()
        return
    for mid, sid, t_created, t_updated, data in rows:
        try:
            obj = json.loads(data) if isinstance(data, str) else (data or {})
        except Exception:
            res.errors.append((db_path, "message %s: data JSON 解析失败" % mid))
            continue
        if obj.get("role") != "assistant":
            continue
        tokens = obj.get("tokens") or {}
        if not tokens:
            continue
        cache = tokens.get("cache") or {}
        counts = {
            "input": tokens.get("input") or 0,
            "output": tokens.get("output") or 0,
            "cache_read": cache.get("read") or 0,
            "cache_write": cache.get("write") or 0,
            "reasoning": tokens.get("reasoning") or 0,
        }
        if not any(counts.values()):
            res.key_kinds["zero-usage"] += 1
            continue
        ts = (t_created or t_updated or 0) / 1000.0
        if ts <= 0:
            continue
        path = obj.get("path") or {}
        res.key_kinds["message.id"] += 1
        res.add(Record(
            source=source_name, day=local_day(ts),
            model=obj.get("modelID") or "unknown",
            project=os.path.basename(path.get("cwd") or "") or None,
            session=sid, key="%s:%s" % (source_name, mid),
            counts=counts, ts=ts,
        ))
    conn.close()


# --------------------------------------------------------------------------
# 聚合输出
# --------------------------------------------------------------------------

def aggregate(records):
    daily = collections.defaultdict(lambda: collections.Counter())
    models = collections.defaultdict(lambda: collections.Counter())
    for r in records:
        k = (r.day, r.source, r.model)
        daily[k]["turns"] += 1
        models[(r.source, r.model)]["turns"] += 1
        for f in FIELDS:
            daily[k][f] += r.counts[f]
            models[(r.source, r.model)][f] += r.counts[f]
    return daily, models


def fmt(n):
    return "{:,}".format(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="只看最近 N 天")
    ap.add_argument("--source", action="append", help="只扫指定源，可重复")
    ap.add_argument("--json", help="额外输出 JSON 汇总到该路径")
    args = ap.parse_args()
    want = set(args.source or [])

    results = []
    if not want or "claude" in want:
        r = SourceResult("claude"); scan_claude(r); results.append(r)
    if not want or "codex" in want:
        r = SourceResult("codex"); scan_codex(r); results.append(r)
    if not want or "opencode" in want:
        r = SourceResult("opencode"); scan_sqlite_agent(r, OPENCODE_DB, "opencode"); results.append(r)
    if not want or "kilo" in want:
        r = SourceResult("kilo"); scan_sqlite_agent(r, KILO_DB, "kilo"); results.append(r)

    all_records = []
    for r in results:
        all_records.extend(r.records)

    cutoff = None
    if args.days:
        cutoff = (dt.datetime.now() - dt.timedelta(days=args.days)).strftime("%Y-%m-%d")
        all_records = [r for r in all_records if r.day >= cutoff]

    daily, models = aggregate(all_records)

    out = []
    w = out.append
    w("=" * 100)
    w("usage-ledger 探针快照   生成于 %s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if cutoff:
        w("（仅最近 %d 天：%s 起）" % (args.days, cutoff))
    w("=" * 100)

    w("")
    w("## 1. 各源概况")
    w("")
    w("| 源 | 文件数 | 命中行 | 去重后记录 | 丢弃重复 | 活跃天数 | 日期范围 | 解析错误 |")
    w("|---|---|---|---|---|---|---|---|")
    for r in results:
        s = r.summary()
        w("| %s | %d | %d | %d | %d | %d | %s ~ %s | %d |" % (
            s["source"], s["files"], s["raw_lines"], s["unique_records"],
            s["duplicates_dropped"], s["active_days"],
            s["day_from"] or "—", s["day_to"] or "—", s["errors"]))
    w("")
    for r in results:
        for n in r.notes:
            w("- `%s`: %s" % (r.name, n))
        if r.key_kinds:
            w("- `%s` 去重键来源: %s" % (r.name, dict(r.key_kinds)))
        if r.errors:
            for path, msg in r.errors[:5]:
                w("- ⚠️ `%s`: %s (%s)" % (r.name, msg, path))

    w("")
    w("## 2. 模型清单（source × model）")
    w("")
    w("| 源 | 模型 | 记录数 | input | output | cache_read | cache_write | reasoning | 合计 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for (src, model), c in sorted(models.items(), key=lambda kv: -sum(kv[1][f] for f in FIELDS)):
        total = sum(c[f] for f in FIELDS)
        w("| %s | %s | %d | %s | %s | %s | %s | %s | %s |" % (
            src, model, c["turns"], fmt(c["input"]), fmt(c["output"]), fmt(c["cache_read"]),
            fmt(c["cache_write"]), fmt(c["reasoning"]), fmt(total)))

    w("")
    w("## 3. 每日明细（最近 30 天，source × model）")
    w("")
    days = sorted({d for d, _, _ in daily})[-30:]
    w("| 日期 | 源 | 模型 | input | output | cache_read | cache_write | reasoning | 合计 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for day in days:
        for (d, src, model), c in sorted(daily.items()):
            if d != day:
                continue
            total = sum(c[f] for f in FIELDS)
            w("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                day, src, model, fmt(c["input"]), fmt(c["output"]), fmt(c["cache_read"]),
                fmt(c["cache_write"]), fmt(c["reasoning"]), fmt(total)))

    w("")
    w("## 4. 全量合计")
    w("")
    grand = collections.Counter()
    for c in daily.values():
        for f in FIELDS:
            grand[f] += c[f]
        grand["turns"] += c["turns"]
    w("| 源 | 记录数 | input | output | cache_read | cache_write | reasoning | 合计 |")
    w("|---|---|---|---|---|---|---|---|")
    for src in sorted({s for _, s, _ in daily}):
        c = collections.Counter()
        for (d, s, m), v in daily.items():
            if s != src:
                continue
            for f in FIELDS:
                c[f] += v[f]
            c["turns"] += v["turns"]
        w("| %s | %d | %s | %s | %s | %s | %s | %s |" % (
            src, c["turns"], fmt(c["input"]), fmt(c["output"]), fmt(c["cache_read"]),
            fmt(c["cache_write"]), fmt(c["reasoning"]), fmt(sum(c[f] for f in FIELDS))))
    w("| **合计** | **%d** | **%s** | **%s** | **%s** | **%s** | **%s** | **%s** |" % (
        grand["turns"], fmt(grand["input"]), fmt(grand["output"]), fmt(grand["cache_read"]),
        fmt(grand["cache_write"]), fmt(grand["reasoning"]), fmt(sum(grand[f] for f in FIELDS))))

    w("")
    w("## 5. 项目分布（cwd basename）")
    w("")
    proj = collections.defaultdict(lambda: collections.Counter())
    for r in all_records:
        c = proj[(r.source, r.project or "(未知)")]
        c["turns"] += 1
        for f in FIELDS:
            c[f] += r.counts[f]
    w("| 源 | 项目 | 记录数 | 合计 token |")
    w("|---|---|---|---|")
    for (src, p), c in sorted(proj.items(), key=lambda kv: -sum(kv[1][f] for f in FIELDS))[:25]:
        w("| %s | %s | %d | %s |" % (src, p, c["turns"], fmt(sum(c[f] for f in FIELDS))))

    text = "\n".join(out)
    print(text)

    if args.json:
        payload = {
            "generated_at": dt.datetime.now().isoformat(),
            "sources": [r.summary() for r in results],
            "models": {("%s|%s" % k): dict(v) for k, v in models.items()},
            "daily": {("|".join(k)): dict(v) for k, v in daily.items()},
            "grand": dict(grand),
        }
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print("\nJSON 汇总已写入 %s" % args.json)


if __name__ == "__main__":
    sys.exit(main())
