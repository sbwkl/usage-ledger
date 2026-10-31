import json
import os
import sqlite3


def token_path(home):
    return os.path.join(home, "Library", "Application Support", "Qoder",
                        "SharedClientCache", "cache", "db", "local.db")


def activity_path(home):
    return os.path.join(home, "Library", "Application Support",
                        "com.qoder.app.stable", "main.sqlite")


def create_token_db(path, messages, sessions):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE chat_message (id TEXT, session_id TEXT, role TEXT, "
                 "gmt_create INTEGER, model_info TEXT, token_info TEXT)")
    conn.execute("CREATE TABLE chat_session (session_id TEXT PRIMARY KEY, project_name TEXT, "
                 "project_uri TEXT, session_type TEXT, preferred_model_info TEXT)")
    for sid, info in sessions.items():
        conn.execute(
            "INSERT INTO chat_session VALUES (?,?,?,?,?)",
            (sid, info.get("project_name"), info.get("project_uri"),
             info.get("session_type"), info.get("preferred_model_info")))
    conn.executemany(
        "INSERT INTO chat_message VALUES (?,?,?,?,?,?)", messages)
    conn.commit()
    conn.close()


def transcript_path(home, name="session-1.jsonl", project="demo"):
    return os.path.join(home, ".qoder", "projects", project, name)


def log_path(home, name="main.log", bucket="20261030"):
    return os.path.join(home, "Library", "Application Support",
                        "com.qoder.app.stable", "logs", bucket, name)


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_quota_log(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def quota_line(when, request_id, total=2300, used=100, remaining=2200, pct=0.04):
    payload = {
        "operation": "GetUserUsage",
        "requestId": request_id,
        "qoderUsage": {
            "userQuota": {"total": 0, "used": 0, "remaining": 0, "unit": "credits"},
            "addOnQuota": {"total": total, "used": used, "remaining": remaining,
                           "unit": "credits"},
            "totalUsagePercentage": pct,
            "expiresAt": 253402214400000,
        },
    }
    return "[%s] INFO 用量响应摘要 %s\n" % (when, json.dumps(payload, ensure_ascii=False))


def create_activity_db(path, messages, sessions):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE chat_session_messages (id TEXT PRIMARY KEY, session_id TEXT, "
                 "role TEXT, payload_json TEXT, created_at INTEGER, updated_at INTEGER)")
    conn.execute("CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, cwd TEXT)")
    for sid, cwd in sessions.items():
        conn.execute("INSERT INTO chat_sessions VALUES (?,?)", (sid, cwd))
    rows = []
    for mid, sid, role, payload, created, updated in messages:
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        rows.append((mid, sid, role, payload, created, updated))
    conn.executemany(
        "INSERT INTO chat_session_messages VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
