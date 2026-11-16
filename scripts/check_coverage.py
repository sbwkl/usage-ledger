#!/usr/bin/env python3
"""Fail when coverage is below the configured thresholds or regresses from baseline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tests" / "coverage_policy.json"


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("invalid JSON in %s: %s" % (path, exc))


def percent(summary: dict) -> float:
    return float(summary.get("percent_covered", 0.0))


def main(argv: list[str]) -> int:
    coverage_path = Path(argv[1]) if len(argv) > 1 else ROOT / "coverage.json"
    policy_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_POLICY
    coverage = load(coverage_path)
    policy = load(policy_path)

    files = coverage.get("files", {})
    totals = coverage.get("totals", {})
    max_drop = float(policy.get("max_drop_pp", 1.0))
    failures: list[str] = []

    def check(label: str, actual: float, threshold: float, baseline: float | None) -> None:
        status = "ok"
        if actual + 1e-9 < threshold:
            status = "FAIL"
            failures.append("%s %.1f%% < threshold %.1f%%" % (label, actual, threshold))
        if baseline is not None and actual + 1e-9 < baseline - max_drop:
            status = "FAIL"
            failures.append(
                "%s %.1f%% dropped more than %.1fpp from baseline %.1f%%"
                % (label, actual, max_drop, baseline))
        baseline_text = "%.1f%%" % baseline if baseline is not None else "-"
        print("%-42s %6.1f%%  threshold %5.1f%%  baseline %7s  %s"
              % (label, actual, threshold, baseline_text, status))

    check("TOTAL", percent(totals), float(policy["total"]),
          policy.get("baseline", {}).get("total"))

    for module, threshold in policy.get("modules", {}).items():
        key = module.replace("\\", "/")
        entry = files.get(key)
        if entry is None:
            failures.append("%s: not present in coverage report" % module)
            print("%-42s %6s   threshold %5.1f%%  MISSING" % (module, "-", threshold))
            continue
        check(module, percent(entry["summary"]), float(threshold),
              policy.get("baseline", {}).get(module))

    if failures:
        print("\ncoverage policy failed:", file=sys.stderr)
        for failure in failures:
            print(" - " + failure, file=sys.stderr)
        return 1
    print("\ncoverage policy passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
