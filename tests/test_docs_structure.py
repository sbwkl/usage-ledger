from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocsStructureTest(unittest.TestCase):
    def test_required_docs_structure_exists(self):
        required = [
            "AGENTS.md",
            "ARCHITECTURE.md",
            "docs/design-docs/index.md",
            "docs/design-docs/core-beliefs.md",
            "docs/exec-plans/active/.gitkeep",
            "docs/exec-plans/completed/.gitkeep",
            "docs/exec-plans/tech-debt-tracker.md",
            "docs/generated/db-schema.md",
            "docs/product-specs/index.md",
            "docs/requirements/REQ-0001-usage-ledger.md",
            "docs/requirements/REQ-0002-testing.md",
            "docs/changes/CHG-0001-docs-alignment.md",
            "docs/adr/ADR-0001-source-of-truth-db-as-archive.md",
            "docs/rfcs/README.md",
            "docs/DESIGN.md",
            "docs/FRONTEND.md",
            "docs/PLANS.md",
            "docs/PRODUCT_SENSE.md",
            "docs/QUALITY_SCORE.md",
            "docs/RELIABILITY.md",
            "docs/SECURITY.md",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual(missing, [], "missing required docs: %s" % ", ".join(missing))

    def test_legacy_docs_at_root_of_docs_are_moved(self):
        legacy = [
            "docs/ARCHITECTURE.md",
            "docs/README.md",
            "docs/RESEARCH.md",
            "docs/PROBE.md",
            "docs/DISCUSSION.md",
            "docs/QODER-DESIGN.md",
            "docs/QODER-CREDITS-DESIGN.md",
            "docs/TRAE-CN-DESIGN.md",
            "docs/TRAE-CN-CREDITS-DESIGN.md",
            "docs/CLINE-DESIGN.md",
        ]
        present = [path for path in legacy if (ROOT / path).is_file()]
        self.assertEqual(present, [], "legacy docs still present: %s" % ", ".join(present))

    def test_agents_doc_map_uses_required_structure(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for needle in [
            "## 文档地图（真相在这里）",
            "ARCHITECTURE.md",
            "docs/design-docs/index.md",
            "docs/exec-plans/active/",
            "docs/exec-plans/completed/",
            "docs/exec-plans/tech-debt-tracker.md",
            "docs/generated/db-schema.md",
            "docs/product-specs/",
            "docs/references/",
            "docs/DESIGN.md / FRONTEND.md",
        ]:
            self.assertIn(needle, text)

    def test_agents_has_new_development_process(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for needle in [
            "## 开发流程（每个新特性都必须遵守）",
            "从最新 main 切分支",
            "本地有未提交改动时用 worktree",
            "TDD 开发",
            "提交前静态检查（强制）",
            "用临时分支做集成测试",
            "需求补充 / 修改的处理",
            "创建 PR 供人工审核",
            "集成测试用临时分支，测完即删，不保留长期集成分支",
        ]:
            self.assertIn(needle, text)
        self.assertNotIn("集成走 `sit`", text)


if __name__ == "__main__":
    unittest.main()
