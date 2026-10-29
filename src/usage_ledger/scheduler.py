from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
STATE_DIR = Path.home() / ".local" / "state" / "usage-ledger"

JOBS = {
    "sync": ("local.usage-ledger.sync", ["sync"], {"Minute": 7}),
    "full": ("local.usage-ledger.full", ["sync", "--full"], {"Hour": 0, "Minute": 15}),
    "prune": ("local.usage-ledger.prune", ["prune", "--keep-days", "90"],
              {"Hour": 0, "Minute": 20}),
}


def plist_path(name: str, launch_agents: Path | None = None) -> Path:
    return (launch_agents or LAUNCH_AGENTS) / (JOBS[name][0] + ".plist")


def build_plist(name: str, launch_agents: Path | None = None) -> dict:
    label, args, calendar = JOBS[name]
    state_dir = STATE_DIR
    log = state_dir / (name + ".log")
    err = state_dir / (name + ".err")
    environment = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "USAGE_LEDGER_HOME": os.environ.get(
            "USAGE_LEDGER_HOME", str(Path.home() / ".local" / "share" / "usage-ledger")),
        "USAGE_LEDGER_SOURCE_HOME": os.environ.get("USAGE_LEDGER_SOURCE_HOME", str(Path.home())),
    }
    if os.environ.get("USAGE_LEDGER_DB"):
        environment["USAGE_LEDGER_DB"] = os.environ["USAGE_LEDGER_DB"]
    return {
        "Label": label,
        "ProgramArguments": [sys.executable, "-m", "usage_ledger", *args],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": environment,
        "StartCalendarInterval": calendar,
        "RunAtLoad": False,
        "ProcessType": "Background",
        "StandardOutPath": str(log),
        "StandardErrorPath": str(err),
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _loaded(label: str) -> bool:
    return _launchctl("print", "gui/%d/%s" % (os.getuid(), label)).returncode == 0


def render(name: str) -> str:
    return plistlib.dumps(build_plist(name), fmt=plistlib.FMT_XML).decode()


def install(launch_agents: Path | None = None, load: bool = True,
            dry_run: bool = False) -> list[str]:
    target_dir = launch_agents or LAUNCH_AGENTS
    messages = []
    if not dry_run:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        target_dir.mkdir(parents=True, exist_ok=True)
    for name in JOBS:
        label = JOBS[name][0]
        path = plist_path(name, target_dir)
        if dry_run:
            messages.append("dry-run: would write %s\n%s" % (path, render(name)))
            continue
        path.write_bytes(plistlib.dumps(build_plist(name, target_dir)))
        messages.append("written %s" % path)
        if not load:
            continue
        if _loaded(label):
            _launchctl("bootout", "gui/%d/%s" % (os.getuid(), label))
        result = _launchctl("bootstrap", "gui/%d" % os.getuid(), str(path))
        if result.returncode != 0:
            fallback = _launchctl("load", "-w", str(path))
            if fallback.returncode != 0:
                messages.append("load failed: %s" % (result.stderr or fallback.stderr).strip())
            else:
                messages.append("loaded %s (legacy load)" % label)
        else:
            messages.append("loaded %s" % label)
    return messages


def uninstall(launch_agents: Path | None = None) -> list[str]:
    target_dir = launch_agents or LAUNCH_AGENTS
    messages = []
    for name in JOBS:
        label = JOBS[name][0]
        path = plist_path(name, target_dir)
        if _loaded(label):
            _launchctl("bootout", "gui/%d/%s" % (os.getuid(), label))
            if _loaded(label):
                _launchctl("unload", "-w", str(path))
            messages.append("unloaded %s" % label)
        if path.exists():
            path.unlink()
            messages.append("removed %s" % path)
    return messages


def status(launch_agents: Path | None = None) -> list[dict]:
    rows = []
    for name in JOBS:
        label = JOBS[name][0]
        path = plist_path(name, launch_agents)
        rows.append({
            "job": name,
            "label": label,
            "plist": str(path),
            "installed": path.exists(),
            "loaded": _loaded(label),
        })
    return rows
