"""MiniMax Code 采集测试用的目录构造器。

MiniMax Code 把会话落盘在按日期分层的目录里：
<home>/.minimax/v2/sessions/<YYYY>/<MM>/<DD>/<HH-MM-SS-mmm-session_<base64url(sessionId)>>/
    ├── manifest.json    # sessionId 是会话 ID 的权威来源
    └── messages.jsonl   # 每行一个 {message_id, turn_id, message}

运行库 <home>/.minimax/v2/sqlite/runtime-state.sqlite 里的
`local_runtime_sessions` 表提供 session_id -> workspace_dir 的项目映射。
"""

import base64
import json
import os
import sqlite3

SESSIONS_REL = os.path.join(".minimax", "v2", "sessions")
RUNTIME_DB_REL = os.path.join(".minimax", "v2", "sqlite", "runtime-state.sqlite")

DEFAULT_DAY = ("2026", "11", "20")
DEFAULT_MODEL = "MiniMax-M3.1-Flash"
DEFAULT_SESSION = "mvs_312b6b55e9c143949b13cbdfa4a50f44"


def sessions_root(home):
    return os.path.join(home, SESSIONS_REL)


def runtime_db_path(home):
    return os.path.join(home, RUNTIME_DB_REL)


def session_dirname(session_id):
    """会话目录名：时间戳前缀 + base64url(sessionId)。"""
    tail = base64.urlsafe_b64encode(session_id.encode("utf-8")).decode("ascii")
    return "05-47-46-783-session_%s" % tail.rstrip("=")


def session_dir(home, session_id=DEFAULT_SESSION, day=DEFAULT_DAY):
    return os.path.join(sessions_root(home), *day, session_dirname(session_id))


def write_manifest(home, session_id=DEFAULT_SESSION, day=DEFAULT_DAY):
    directory = session_dir(home, session_id, day)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "schemaVersion": 1,
            "sessionId": session_id,
            "createdAtMs": 1795153666783,
            "source": "local-runtime",
            "layout": "v2-final-dated-session",
        }, fh)
    return path


def usage(input_tokens=100, output_tokens=20, cache_read=0, cache_write=0):
    return {
        "input": input_tokens,
        "output": output_tokens,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "totalTokens": input_tokens + output_tokens + cache_read,
        "cost": {"input": 0, "output": 0, "cacheRead": 0,
                 "cacheWrite": 0, "total": 0},
    }


_DEFAULT = object()


def assistant_row(msg_id, model=DEFAULT_MODEL, provider="minimax",
                  timestamp_ms=1795153668789, usage_value=_DEFAULT, **extra):
    """usage_value 不传 → 带默认 usage；显式传 None → 该条**没有** usage 字段。"""
    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": "hi"}],
        "api": "anthropic-messages",
        "provider": provider,
        "model": model,
        "stopReason": "toolUse",
        "timestamp": timestamp_ms,
        "responseId": "resp-%s" % msg_id,
    }
    if usage_value is _DEFAULT:
        message["usage"] = usage()
    elif usage_value is not None:
        message["usage"] = usage_value
    message.update(extra)
    return {"message_id": msg_id, "turn_id": "turn-1", "message": message}


def user_row(msg_id="msg-user-1", timestamp_ms=1795153667019):
    return {
        "message_id": msg_id,
        "turn_id": "turn-1",
        "message": {"role": "user", "content": [{"type": "text", "text": "hi"}],
                    "timestamp": timestamp_ms},
    }


def tool_row(msg_id="msg-tool-1", timestamp_ms=1795153669000):
    return {
        "message_id": msg_id,
        "turn_id": "turn-1",
        "message": {"role": "toolResult", "toolCallId": "call-1",
                    "toolName": "bash", "content": [], "timestamp": timestamp_ms},
    }


def write_messages(home, rows, session_id=DEFAULT_SESSION, day=DEFAULT_DAY,
                   manifest=True):
    """写 messages.jsonl。rows 可以是 dict（正常消息）或 str（原始行，用于坏行）。"""
    directory = session_dir(home, session_id, day)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "messages.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            if isinstance(row, str):
                fh.write(row + "\n")
            else:
                fh.write(json.dumps(row) + "\n")
    if manifest:
        write_manifest(home, session_id, day)
    return path


def write_runtime_db(home, sessions, path=None):
    """写运行库的 local_runtime_sessions 表。

    sessions: [(session_id, workspace_dir, project_workspace_dir), ...]
    """
    db_path = path or runtime_db_path(home)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE local_runtime_sessions ("
                 "session_id TEXT PRIMARY KEY, workspace_dir TEXT, "
                 "project_workspace_dir TEXT)")
    conn.executemany("INSERT INTO local_runtime_sessions VALUES (?,?,?)", sessions)
    conn.commit()
    conn.close()
    return db_path
