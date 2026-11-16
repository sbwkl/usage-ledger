#!/usr/bin/env python3
"""Verify every REQ acceptance criterion maps to at least one existing automated test."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AC_MAP = ROOT / "tests" / "ac_map.json"


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("invalid JSON in %s: %s" % (path, exc))


def collect_test_ids() -> set[str]:
    sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    ids: set[str] = set()

    def walk(item):
        if isinstance(item, unittest.TestSuite):
            for child in item:
                walk(child)
        else:
            ids.add(item.id())

    walk(suite)
    return ids


def parse_acceptance_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^## 5\. .*?(?=^## )", text, re.S | re.M)
    if not match:
        raise SystemExit("%s: section '## 5.' not found" % path)
    ids = re.findall(r"^\| (R\d+) \|", match.group(0), re.M)
    if not ids:
        raise SystemExit("%s: no acceptance criteria found in section 5" % path)
    return ids


def resolves(identifier: str, test_ids: set[str]) -> bool:
    return any(tid == identifier or tid.startswith(identifier + ".")
               for tid in test_ids)


def main() -> int:
    mapping = load(AC_MAP)
    test_ids = collect_test_ids()
    failures: list[str] = []

    for req_id, spec in mapping.items():
        path = ROOT / spec["path"]
        criteria = parse_acceptance_ids(path)
        mapped = spec.get("criteria", {})
        missing = [ac for ac in criteria if ac not in mapped]
        orphaned = [ac for ac in mapped if ac not in criteria]
        if missing:
            failures.append("%s: unmapped criteria %s" % (req_id, ", ".join(missing)))
        if orphaned:
            failures.append("%s: mappings not present in REQ: %s"
                            % (req_id, ", ".join(orphaned)))
        for ac in criteria:
            identifiers = mapped.get(ac) or []
            if not identifiers:
                failures.append("%s %s: no mapped test" % (req_id, ac))
                continue
            for identifier in identifiers:
                if not resolves(identifier, test_ids):
                    failures.append("%s %s: unknown test identifier %s"
                                    % (req_id, ac, identifier))
        print("%s: %d criteria, %d mapped identifiers"
              % (req_id, len(criteria), sum(len(v) for v in mapped.values())))

    if failures:
        print("\nAC map check failed:", file=sys.stderr)
        for failure in failures:
            print(" - " + failure, file=sys.stderr)
        return 1
    print("AC map check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
