#!/usr/bin/env python3
"""Run the fast suite and enforce skip/expected-failure allowlists and time budget."""
from __future__ import annotations

import json
import sys
import time
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "tests" / "skip_allowlist.json"
BUDGET_SECONDS = 5.0
ALLOWED_KINDS = {"skip", "expectedFailure"}


class PolicyResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skips: dict[str, str] = {}
        self.expected_failures: set[str] = set()

    def addSkip(self, test, reason):
        self.skips[test.id()] = reason
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.expected_failures.add(test.id())
        super().addExpectedFailure(test, err)


def load_allowlist() -> list[dict]:
    if not ALLOWLIST.exists():
        return []
    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    entries = payload.get("allow", [])
    if not isinstance(entries, list):
        raise SystemExit("tests/skip_allowlist.json: 'allow' must be a list")
    return entries


def validate_entry(index: int, entry: dict, failures: list[str]) -> tuple[str, str] | None:
    if not isinstance(entry, dict):
        failures.append("allow[%d]: must be an object" % index)
        return None
    test = entry.get("test")
    kind = entry.get("kind")
    owner = entry.get("owner")
    reason = entry.get("reason")
    expires = entry.get("expires")
    if not isinstance(test, str) or not test:
        failures.append("allow[%d]: missing test id" % index)
        return None
    if kind not in ALLOWED_KINDS:
        failures.append("allow[%d] %s: kind must be one of %s" % (index, test, sorted(ALLOWED_KINDS)))
        return None
    if not isinstance(owner, str) or not owner.strip():
        failures.append("allow[%d] %s: missing owner" % (index, test))
    if not isinstance(reason, str) or not reason.strip():
        failures.append("allow[%d] %s: missing reason" % (index, test))
    try:
        expiry = date.fromisoformat(str(expires))
    except ValueError:
        failures.append("allow[%d] %s: expires must be YYYY-MM-DD" % (index, test))
        return None
    if expiry < date.today():
        failures.append("allow[%d] %s: expired on %s" % (index, test, expiry.isoformat()))
    return kind, test


def main() -> int:
    sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))

    print("running fast suite with policy checks...", file=sys.stderr)
    started = time.monotonic()
    runner = unittest.TextTestRunner(verbosity=1, resultclass=PolicyResult, buffer=False)
    result: PolicyResult = runner.run(suite)
    elapsed = time.monotonic() - started

    failures: list[str] = []
    allowed: dict[tuple[str, str], dict] = {}
    for index, entry in enumerate(load_allowlist()):
        key = validate_entry(index, entry, failures)
        if key is not None:
            allowed[key] = entry

    observed = {("skip", test): reason for test, reason in result.skips.items()}
    observed.update({("expectedFailure", test): "" for test in result.expected_failures})

    for (kind, test), reason in sorted(observed.items()):
        if (kind, test) not in allowed:
            failures.append("unauthorized %s: %s（%s）" % (kind, test, reason or "no reason"))
    for key, entry in sorted(allowed.items()):
        if key not in observed:
            failures.append("stale allowlist entry: %s %s" % key)

    print("tests: %d, failures: %d, errors: %d, skips: %d, expected failures: %d"
          % (result.testsRun, len(result.failures), len(result.errors),
             len(result.skips), len(result.expectedFailures)))
    print("fast suite: %.3fs (budget %.1fs)" % (elapsed, BUDGET_SECONDS))

    if elapsed > BUDGET_SECONDS:
        failures.append("fast suite %.3fs exceeds %.1fs budget" % (elapsed, BUDGET_SECONDS))
    if result.unexpectedSuccesses:
        failures.append("unexpected successes: %s"
                        % ", ".join(test.id() for test in result.unexpectedSuccesses))
    if not result.wasSuccessful():
        failures.append("unittest reported failures/errors")
    if failures:
        print("\ntest policy failed:", file=sys.stderr)
        for failure in failures:
            print(" - " + failure, file=sys.stderr)
        return 1
    print("test policy passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
