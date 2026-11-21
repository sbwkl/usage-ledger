from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DOCS_DIRS = {"design-docs", "exec-plans", "generated", "product-specs", "references"}


class DocsStructureTest(unittest.TestCase):
    def test_required_docs_structure_exists(self):
        required = [
            "AGENTS.md", "ARCHITECTURE.md",
            "docs/design-docs/index.md", "docs/design-docs/core-beliefs.md",
            "docs/exec-plans/active/.gitkeep", "docs/exec-plans/completed/.gitkeep",
            "docs/exec-plans/tech-debt-tracker.md", "docs/generated/db-schema.md",
            "docs/product-specs/index.md", "docs/product-specs/usage-ledger.md",
            "docs/DESIGN.md", "docs/FRONTEND.md", "docs/PLANS.md",
            "docs/PRODUCT_SENSE.md", "docs/QUALITY_SCORE.md",
            "docs/RELIABILITY.md", "docs/SECURITY.md",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual(missing, [], "missing required docs: %s" % ", ".join(missing))

    def test_docs_top_level_dirs_match_spec(self):
        actual = {p.name for p in (ROOT / "docs").iterdir() if p.is_dir()}
        self.assertEqual(actual, ALLOWED_DOCS_DIRS)

    def test_old_req_files_are_gone(self):
        for p in ["docs/product-specs/REQ-0001-usage-ledger.md", "docs/product-specs/REQ-0002-testing.md"]:
            self.assertFalse((ROOT / p).exists(), p)

    def test_changes_are_under_exec_plans_completed(self):
        self.assertTrue((ROOT / "docs/exec-plans/completed/CHG-0001-docs-alignment.md").is_file())

    def test_adr_and_rfc_are_under_design_docs(self):
        self.assertTrue((ROOT / "docs/design-docs/ADR-0001-source-of-truth-db-as-archive.md").is_file())
        self.assertTrue((ROOT / "docs/design-docs/rfcs/README.md").is_file())

    def test_product_spec_is_positioned_as_product_spec(self):
        text = (ROOT / "docs/product-specs/usage-ledger.md").read_text(encoding="utf-8")
        self.assertIn("# 产品规格：usage-ledger", text)
        self.assertIn("| 原需求卡 | REQ-0001 |", text)
        self.assertIn("## 5. 验收标准（EARS）", text)

    def test_testing_system_is_in_architecture(self):
        arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("## 9. 测试体系", arch)
        self.assertIn("REQ-0002", arch)
        self.assertIn("测试分层", arch)

    def test_agents_points_to_new_product_spec(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("docs/product-specs/usage-ledger.md", text)
        self.assertNotIn("docs/product-specs/REQ-0001-usage-ledger.md", text)
        self.assertNotIn("REQ-0002-testing.md", text)

    def test_ac_map_points_to_new_product_spec(self):
        payload = json.loads((ROOT / "tests" / "ac_map.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["REQ-0001"]["path"], "docs/product-specs/usage-ledger.md")


if __name__ == "__main__":
    unittest.main()
