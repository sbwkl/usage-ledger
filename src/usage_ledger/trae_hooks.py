from __future__ import annotations

import glob
import json
import os
import shlex
import shutil
import sys
from datetime import datetime

HOOK_MARKER = "trae-cn-hook.py"
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")
MATCHER_EVENTS = ("PreToolUse", "PostToolUse")
HOOK_TIMEOUT = 5
CONFIG_VERSION = 1

_HOOK_SCRIPT = '''#!/usr/bin/env python3
import json
import os
import sys
import time

DATA_HOME = __DATA_HOME__
EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}


def _chars(value):
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        return len(str(value))


def _project(obj):
    root = obj.get("cwd")
    if not isinstance(root, str) or not root:
        roots = obj.get("workspace_roots")
        if isinstance(roots, list) and roots and isinstance(roots[0], str):
            root = roots[0]
    if not isinstance(root, str) or not root:
        return ""
    return os.path.basename(root.rstrip("/")) or ""


def main():
    raw = sys.stdin.buffer.read(64 * 1024 * 1024)
    obj = json.loads(raw.decode("utf-8", "replace"))
    if not isinstance(obj, dict):
        return
    event = obj.get("hook_event_name")
    if event not in EVENTS:
        return
    session = obj.get("session_id") or "unknown"
    ts = time.time()
    chars_in = 0
    chars_out = 0
    loop = 0
    if event == "UserPromptSubmit":
        chars_in = _chars(obj.get("prompt"))
    elif event == "PreToolUse":
        chars_out = _chars(obj.get("tool_input"))
    elif event == "PostToolUse":
        chars_in = _chars(obj.get("tool_response"))
    elif event == "Stop":
        chars_out = _chars(obj.get("last_assistant_message"))
        try:
            loop = int(obj.get("loop_count") or 0)
        except (TypeError, ValueError):
            loop = 0
    tool = obj.get("tool_name") or obj.get("llm_tool_name") or ""
    tool_use_id = obj.get("tool_use_id") or ""
    uid = "%s:%d:%s:%s" % (session, time.time_ns(), event, tool_use_id or loop)
    record = {
        "v": 1,
        "uid": uid,
        "ts": round(ts, 6),
        "event": event,
        "session": session,
        "project": _project(obj),
        "tool": tool,
        "tool_use_id": tool_use_id,
        "loop": loop,
        "chars_in": chars_in,
        "chars_out": chars_out,
    }
    model = obj.get("model")
    if isinstance(model, str) and model:
        record["model"] = model
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\\n"
    day = time.strftime("%Y-%m-%d", time.localtime(ts))
    path = os.path.join(DATA_HOME, "trae-cn", "events-%s.jsonl" % day)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
'''


def usage_data_home(home: str | None = None) -> str:
    explicit = os.environ.get("USAGE_LEDGER_HOME")
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.join(home or os.path.expanduser("~"), ".local", "share", "usage-ledger")


def hook_script_path(home: str | None = None) -> str:
    return os.path.join(usage_data_home(home), "hooks", HOOK_MARKER)


def trae_event_dir(home: str | None = None) -> str:
    return os.path.join(usage_data_home(home), "trae-cn")


def trae_config_path(scope: str = "global", project: str | None = None,
                     home: str | None = None) -> str:
    if scope == "global":
        return os.path.join(home or os.path.expanduser("~"), ".trae-cn", "hooks.json")
    if scope == "project":
        if not project:
            raise ValueError("项目级 hook 需要 --project <绝对路径>")
        return os.path.join(os.path.abspath(os.path.expanduser(project)), ".trae", "hooks.json")
    raise ValueError("未知 scope：%s" % scope)


def hook_command(python: str | None = None, script: str | None = None) -> str:
    return "%s %s" % (shlex.quote(python or sys.executable),
                      shlex.quote(script or hook_script_path()))


def render_hook_script(data_home: str | None = None) -> str:
    return _HOOK_SCRIPT.replace("__DATA_HOME__", repr(usage_data_home(data_home)))


def event_files(event_dir: str | None = None) -> list[str]:
    root = event_dir or trae_event_dir()
    if not os.path.isdir(root):
        return []
    return sorted(glob.glob(os.path.join(root, "events-*.jsonl")))


def event_stats(event_dir: str | None = None) -> dict:
    files = event_files(event_dir)
    sessions: set[str] = set()
    events = 0
    last = None
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    events += 1
                    session = obj.get("session")
                    if isinstance(session, str) and session:
                        sessions.add(session)
                    ts = obj.get("ts")
                    if isinstance(ts, (int, float)) and (last is None or ts > last["ts"]):
                        last = obj
        except OSError:
            continue
    return {"files": len(files), "events": events, "sessions": len(sessions),
            "last": last}


def _load_config(path: str) -> dict:
    if not os.path.exists(path):
        return {"version": CONFIG_VERSION, "hooks": {}}
    with open(path, "r", encoding="utf-8") as fh:
        try:
            config = json.load(fh)
        except ValueError as exc:
            raise ValueError("hooks.json 不是合法 JSON：%s（%s）" % (path, exc)) from exc
    if not isinstance(config, dict):
        raise ValueError("hooks.json 顶层必须是对象：%s" % path)
    version = config.get("version", CONFIG_VERSION)
    if version != CONFIG_VERSION:
        raise ValueError("不支持的 hooks version：%r（仅支持 %d）" % (version, CONFIG_VERSION))
    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks.json 的 hooks 必须是对象：%s" % path)
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError("hooks.%s 必须是数组：%s" % (event, path))
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError("hooks.%s 的 Hook 组格式无效：%s" % (event, path))
    config["version"] = version
    config["hooks"] = hooks
    return config


def _is_ours(group: dict) -> bool:
    for hook in group.get("hooks") or []:
        if isinstance(hook, dict) and HOOK_MARKER in str(hook.get("command") or ""):
            return True
    return False


def _remove_ours(config: dict) -> int:
    removed = 0
    hooks = config.setdefault("hooks", {})
    for event in list(hooks):
        groups = hooks[event]
        kept = [group for group in groups if not _is_ours(group)]
        removed += len(groups) - len(kept)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    return removed


def _groups_for(command: str) -> dict:
    groups = {}
    for event in HOOK_EVENTS:
        group = {}
        if event in MATCHER_EVENTS:
            group["matcher"] = "*"
        group["hooks"] = [{"type": "command", "command": command,
                           "timeout": HOOK_TIMEOUT}]
        groups[event] = [group]
    return groups


def _atomic_write(path: str, text: str, mode: int = 0o600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _backup(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = "%s.bak-%s" % (path, stamp)
    if os.path.exists(backup):
        backup = "%s-%d" % (backup, os.getpid())
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    return backup


def install(scope: str = "global", project: str | None = None,
            home: str | None = None, python: str | None = None,
            dry_run: bool = False) -> dict:
    config_path = trae_config_path(scope, project, home)
    script_path = hook_script_path(home)
    command = hook_command(python, script_path)
    config = _load_config(config_path)
    _remove_ours(config)
    hooks = config.setdefault("hooks", {})
    for event, groups in _groups_for(command).items():
        hooks.setdefault(event, []).extend(groups)
    text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    result = {"config_path": config_path, "script_path": script_path,
              "command": command, "config": config, "backup": None,
              "dry_run": dry_run}
    if dry_run:
        return result
    script = render_hook_script(home)
    os.makedirs(os.path.dirname(script_path), mode=0o700, exist_ok=True)
    old = None
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as fh:
            old = fh.read()
    if old != script:
        _atomic_write(script_path, script, mode=0o700)
    result["backup"] = _backup(config_path)
    _atomic_write(config_path, text, mode=0o600)
    return result


def uninstall(scope: str = "global", project: str | None = None,
              home: str | None = None, dry_run: bool = False) -> dict:
    config_path = trae_config_path(scope, project, home)
    config = _load_config(config_path)
    removed = _remove_ours(config)
    result = {"config_path": config_path, "removed": removed, "config": config,
              "backup": None, "dry_run": dry_run}
    if dry_run or not removed:
        return result
    result["backup"] = _backup(config_path)
    _atomic_write(config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    return result


def status(scope: str = "global", project: str | None = None,
           home: str | None = None) -> dict:
    config_path = trae_config_path(scope, project, home)
    script_path = hook_script_path(home)
    result = {"config_path": config_path, "script_path": script_path,
              "config_exists": os.path.exists(config_path),
              "script_exists": os.path.exists(script_path),
              "hook_groups": {}, "error": None}
    try:
        config = _load_config(config_path)
    except ValueError as exc:
        result["error"] = str(exc)
        config = {"hooks": {}}
    for event in HOOK_EVENTS:
        groups = [group for group in config.get("hooks", {}).get(event, [])
                  if _is_ours(group)]
        result["hook_groups"][event] = len(groups)
    result.update(event_stats(trae_event_dir(home)))
    return result
