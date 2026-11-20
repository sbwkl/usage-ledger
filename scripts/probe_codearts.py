#!/usr/bin/env python3
"""CodeArts（码道）采集探针（只读）。

回答三个问题，供 CHG-0018 评审使用：

1. 数据形状 —— `~/.codeartsdoer/codearts-data/opencode.db` 是不是 OpenCode 旧版
   schema（`message` 表、`role` 在 `data` JSON 内），assistant 行的字段是否齐全。
2. token 字段语义 —— `tokens.input` 是否不含 cache read（`total == input + output
   + cache.read + reasoning` 是否成立），`tokens.total` 为什么不能直接用。
3. 去重规则 —— `message.id` 是否全局唯一，能否作 `codearts:<message.id>` 去重键。

只读打开数据库，不写任何数据，不联网。用法：

    python3 scripts/probe_codearts.py [DB_PATH]

DB_PATH 默认取 `~/.codeartsdoer/codearts-data/opencode.db`，便于指向冻结快照做回归。
活库建议先用 `sqlite3 <db> ".backup /tmp/snap.db"` 做一致性快照再探针（裸 cp 复制
WAL 活库可能得到打不开的文件，本机实测出现过一次）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime

DEFAULT_DB = os.path.join(".codeartsdoer", "codearts-data", "opencode.db")


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def open_ro(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def local_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def main(argv: list[str]) -> int:
    home = os.path.expanduser(argv[1] if len(argv) > 1 else "~")
    db = argv[1] if len(argv) > 1 and os.path.isabs(argv[1]) else os.path.join(home, DEFAULT_DB)
    print("DB = %s" % db)
    if not os.path.exists(db):
        print("数据库不存在：源未安装或尚未产生会话。")
        return 1
    conn = open_ro(db)

    # ---------- 1. schema 与行盘点 ----------
    section("1. schema 与行盘点")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    print("表：%s" % ", ".join(sorted(tables)))
    print("legacy `message` 表：%s；新版 `session_message` 表：%s"
          % ("message" in tables, "session_message" in tables))
    if "message" not in tables:
        print("→ 非 legacy schema，adapter 需要走 session_message 分支。")
        return 0

    roles: Counter = Counter()
    models: Counter = Counter()
    providers: Counter = Counter()
    cwd_missing = 0
    rows = []
    for mid, sid, t_created, data in conn.execute(
            "SELECT id, session_id, time_created, data FROM message"):
        try:
            obj = json.loads(data)
        except Exception:
            roles["<bad json>"] += 1
            continue
        role = obj.get("role")
        roles[role or "<null>"] += 1
        if role == "assistant":
            models[obj.get("modelID") or "<null>"] += 1
            providers[obj.get("providerID") or "<null>"] += 1
            if not (obj.get("path") or {}).get("cwd"):
                cwd_missing += 1
            rows.append((mid, sid, t_created, obj))
    print("role 分布：%s" % dict(roles.most_common()))
    print("modelID 分布：%s" % dict(models.most_common()))
    print("providerID 分布：%s" % dict(providers.most_common()))
    print("assistant 行缺 path.cwd：%d / %d" % (cwd_missing, len(rows)))

    # ---------- 2. token 字段语义 ----------
    section("2. token 字段语义（input 是否含 cache read，total 为什么不采）")
    complete = zero = bad_total = 0
    sums = defaultdict(int)
    day_counter: Counter = Counter()
    sessions = set()
    projects = set()
    for mid, sid, t_created, obj in rows:
        tokens = obj.get("tokens") or {}
        total = tokens.get("total")
        i = tokens.get("input") or 0
        o = tokens.get("output") or 0
        cache = tokens.get("cache") or {}
        cr = cache.get("read") or 0
        cw = cache.get("write") or 0
        rsn = tokens.get("reasoning") or 0
        if total is None:
            bad_total += 1
        if i == 0 and o == 0 and cr == 0 and rsn == 0:
            zero += 1
            continue
        if total == i + o + cr + rsn:
            complete += 1
        for field, value in (("input", i), ("output", o), ("cache_read", cr),
                             ("cache_write", cw), ("reasoning", rsn)):
            sums[field] += value
        day_counter[local_day(t_created)] += 1
        sessions.add(sid)
        projects.add(os.path.basename(((obj.get("path") or {}).get("cwd") or "/").rstrip("/")))
    print("total == input+output+cache.read+reasoning：%d / %d（非全零行）" % (complete, len(rows) - zero))
    print("tokens.total 缺失的行：%d（中断/失败响应，字段全 0，采集按 zero-usage 跳过）" % bad_total)
    print("全零 token 行：%d" % zero)
    print("合计 input=%(input)d output=%(output)d cache_read=%(cache_read)d "
          "cache_write=%(cache_write)d reasoning=%(reasoning)d" % sums)
    print("会话数：%d；项目：%s" % (len(sessions), sorted(projects)))
    print("覆盖日期：%s ~ %s" % (min(day_counter) if day_counter else "-",
                                max(day_counter) if day_counter else "-"))

    # ---------- 3. 去重规则 ----------
    section("3. 去重规则校验")
    ids = [mid for mid, _sid, _t, _obj in rows]
    dup = len(ids) - len(set(ids))
    print("assistant 行 message.id 重复：%d 处（应恒为 0）" % dup)
    print("→ 去重键 `codearts:<message.id>` 可用。" if dup == 0
          else "→ message.id 有重复，需要换去重键！")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))