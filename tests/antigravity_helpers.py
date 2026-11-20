"""Antigravity 采集测试用的目录构造器。

Antigravity 的 IDE 与 agy CLI 写两个互不复用的 app data dir，格式一致：
<home>/.gemini/<app>/brain/<convId>/.system_generated/logs/transcript_full.jsonl
"""

import json
import os
import sqlite3

TRANSCRIPT = "transcript_full.jsonl"

IDE_APP = "antigravity"
CLI_APP = "antigravity-cli"


def app_dir(home, app=IDE_APP):
    return os.path.join(home, ".gemini", app)


def logs_dir(home, app, conv):
    return os.path.join(app_dir(home, app), "brain", conv,
                        ".system_generated", "logs")


def transcript_path(home, app, conv):
    return os.path.join(logs_dir(home, app, conv), TRANSCRIPT)


def model_step(idx, model="gemini-3.8-flash-high", input_tokens=100,
               output_tokens=20, cache_read_tokens=0, created_at="2026-11-20T01:00:00Z",
               **extra):
    step = {
        "step_index": idx,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "created_at": created_at,
    }
    step.update(extra)
    return step


def user_step(idx, created_at="2026-11-20T01:00:00Z"):
    return {
        "step_index": idx,
        "source": "USER_EXPLICIT",
        "type": "USER_INPUT",
        "status": "DONE",
        "content": "hi",
        "created_at": created_at,
    }


def write_raw(home, app, conv, lines):
    """把任意行写进 transcript，用于构造游离片段等非 JSON 行。"""
    path = transcript_path(home, app, conv)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def write_transcript(home, app, conv, steps, chunks=None):
    """写 transcript_full.jsonl；chunks 非 None 时同时写镜像分片。"""
    path = transcript_path(home, app, conv)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for step in steps:
            fh.write(json.dumps(step) + "\n")
    if chunks is not None:
        chunk_dir = os.path.join(os.path.dirname(path), "chunks", "transcript_full")
        os.makedirs(chunk_dir, exist_ok=True)
        with open(os.path.join(chunk_dir, "00000000.jsonl"), "w",
                  encoding="utf-8") as fh:
            for step in chunks:
                fh.write(json.dumps(step) + "\n")
    return path


def write_summaries(home, app, rows):
    """写 conversation_summaries.db；只建采集器真正读的两列。"""
    path = os.path.join(app_dir(home, app), "conversation_summaries.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE conversation_summaries ("
                 "conversation_id TEXT PRIMARY KEY, workspace_uris TEXT)")
    conn.executemany(
        "INSERT INTO conversation_summaries VALUES (?,?)", rows)
    conn.commit()
    conn.close()
    return path