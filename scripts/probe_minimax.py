#!/usr/bin/env python3
"""MiniMax Code 用量采集探针（只读）。

回答四个问题，供 CHG 评审使用：

1. 用量落在哪里 —— `~/.minimax/v2/sessions/<YYYY>/<MM>/<DD>/<session>/messages.jsonl`
   里 assistant 消息的 `usage` 是否稳定、字段口径是什么。
2. 口径对不对 —— `input` 是否**已排除** cache read（`totalTokens` 是否等于
   `input + output + cacheRead`），`cacheWrite` 是否有值。
3. 去重键够不够 —— `message_id` 在会话内 / 全局是否唯一，会话目录名能否还原
   `session_id`。
4. 项目维度从哪来 —— 运行库 `runtime-state.sqlite` 的 `local_runtime_sessions
   .workspace_dir` 能否覆盖到这些会话；运行库自带的 `local_runtime_message_rows`
   与会话文件里的用量是否一致（两个独立读取交叉校验）。

只读文件，不写任何数据，不联网。用法：

    python3 scripts/probe_minimax.py [HOME]

HOME 默认取 `os.path.expanduser("~")`，便于指向 fixture 目录做回归。
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import sys
from collections import Counter
from urllib.parse import quote

SESSIONS_REL = os.path.join(".minimax", "v2", "sessions")
RUNTIME_DB_REL = os.path.join(".minimax", "v2", "sqlite", "runtime-state.sqlite")
MESSAGES = "messages.jsonl"
MANIFEST = "manifest.json"


def sessions_root(home: str) -> str:
    return os.path.join(home, SESSIONS_REL)


def runtime_db(home: str) -> str:
    return os.path.join(home, RUNTIME_DB_REL)


def message_files(home: str) -> list[str]:
    root = sessions_root(home)
    if not os.path.isdir(root):
        return []
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if MESSAGES in filenames:
            found.append(os.path.join(dirpath, MESSAGES))
    return sorted(found)


def session_id_from_dir(session_dir: str) -> str | None:
    """会话目录名后缀是 base64url(session_id)；manifest.json 是权威来源。"""
    manifest_path = os.path.join(session_dir, MANIFEST)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict) and isinstance(loaded.get("sessionId"), str):
                return loaded["sessionId"]
        except (OSError, ValueError):
            pass
    name = os.path.basename(session_dir)
    if "-session_" not in name:
        return None
    tail = name.rsplit("-session_", 1)[1]
    padded = tail + "=" * (-len(tail) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    except Exception:
        return None
    return decoded or None


def read_rows(path: str) -> tuple[list[dict], list[str]]:
    """逐行读 JSONL；返回 (解析成功的行, 无法解析的行首片段)。"""
    rows, bad = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                bad.append("line %d: %s" % (lineno, line[:80]))
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            else:
                bad.append("line %d: 非对象" % lineno)
    return rows, bad


def open_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect("file:%s?mode=ro" % quote(path), uri=True, timeout=2)
    conn.execute("PRAGMA query_only=ON")
    return conn


def main(home: str) -> int:
    root = sessions_root(home)
    print("home:", home)
    print("sessions root:", root, "(exists=%s)" % os.path.isdir(root))

    files = message_files(home)
    print("messages.jsonl files:", len(files))

    roles = Counter()
    usage_keys = Counter()
    models = Counter()
    providers = Counter()
    totals = Counter()
    identity_ok = 0
    identity_bad = 0
    missing_usage = 0
    ids = Counter()
    file_usage: dict[tuple, tuple] = {}
    session_ids: dict[str, str] = {}
    bad_lines: list[str] = []

    for path in files:
        session_dir = os.path.dirname(path)
        sid = session_id_from_dir(session_dir)
        if sid:
            session_ids[path] = sid
        rows, bad = read_rows(path)
        for item in bad:
            bad_lines.append("%s: %s" % (os.path.basename(session_dir), item))
        for row in rows:
            msg = row.get("message")
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            roles[role] += 1
            if role != "assistant":
                continue
            msg_id = row.get("message_id")
            if isinstance(msg_id, str):
                ids[(sid, msg_id)] += 1
            models[str(msg.get("model"))] += 1
            providers[str(msg.get("provider"))] += 1
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                missing_usage += 1
                continue
            usage_keys[tuple(sorted(usage.keys()))] += 1
            inp = usage.get("input") or 0
            out = usage.get("output") or 0
            cread = usage.get("cacheRead") or 0
            cwrite = usage.get("cacheWrite") or 0
            total = usage.get("totalTokens") or 0
            totals["input"] += inp
            totals["output"] += out
            totals["cache_read"] += cread
            totals["cache_write"] += cwrite
            if isinstance(msg_id, str):
                file_usage[(sid, msg_id)] = (inp, out, cread)
            if total == inp + out + cread:
                identity_ok += 1
            else:
                identity_bad += 1

    print("\n[roles]", dict(roles))
    print("[usage key shapes]")
    for shape, count in usage_keys.most_common():
        print("   ", count, shape)
    print("[models]", dict(models))
    print("[providers]", dict(providers))
    print("[assistant without usage]:", missing_usage)
    print("[totalTokens == input+output+cacheRead]: ok=%d bad=%d" % (identity_ok, identity_bad))
    print("[totals]", dict(totals))
    print("[duplicate (session,message_id) pairs]:",
          sum(1 for _, c in ids.items() if c > 1))
    print("[distinct sessions]:", len(set(session_ids.values())))
    print("[unparsable lines]:", len(bad_lines))
    for item in bad_lines[:5]:
        print("   ", item)

    db_path = runtime_db(home)
    print("\nruntime db:", db_path, "(exists=%s)" % os.path.exists(db_path))
    if os.path.exists(db_path):
        try:
            conn = open_ro(db_path)
        except sqlite3.Error as exc:
            print("  open failed:", exc)
            conn = None
        if conn is not None:
            try:
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "local_runtime_sessions" in tables:
                    rows = conn.execute(
                        "SELECT session_id, workspace_dir, title FROM local_runtime_sessions"
                    ).fetchall()
                    print("  local_runtime_sessions:", len(rows))
                    mapped = 0
                    for sid, workspace, title in rows:
                        hit = sid in set(session_ids.values())
                        if hit:
                            mapped += 1
                        print("    %s workspace=%s hit=%s title=%s" %
                              (sid, workspace, hit, (title or "")[:40]))
                    print("  sessions covered by workspace_dir:", mapped)
                if "local_runtime_message_rows" in tables:
                    # 运行库内部 msg_id 是 UUID，canonical_message_id 才与会话文件
                    # 的 message_id 对应；用它做交叉校验键。
                    rows = conn.execute(
                        "SELECT session_id, msg_id, role, "
                        "json_extract(data_json,'$.canonical_message_id'), "
                        "json_extract(data_json,'$.usage.input_tokens'), "
                        "json_extract(data_json,'$.usage.output_tokens'), "
                        "json_extract(data_json,'$.usage.cache_read') "
                        "FROM local_runtime_message_rows WHERE role='assistant'"
                    ).fetchall()
                    print("  message_rows assistant:", len(rows))
                    db_keys = {(r[0], r[3]) for r in rows if r[3]}
                    file_keys = set(ids.keys())
                    print("  file keys:", len(file_keys), " db keys:", len(db_keys))
                    print("  only in file:", len(file_keys - db_keys))
                    print("  only in db:", len(db_keys - file_keys))
                    db_usage = {(r[0], r[3]): (r[4], r[5], r[6]) for r in rows if r[3]}
                    same = sum(1 for key, usage in file_usage.items()
                               if db_usage.get(key) == usage)
                    print("  usage identical on common keys: %d / %d"
                          % (same, len(file_usage)))
            finally:
                conn.close()
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    raise SystemExit(main(target))
