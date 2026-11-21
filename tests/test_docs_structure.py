from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DOCS_DIRS = {
    "design-docs",
    "exec-plans",
    "generated",
    "product-specs",
    "references",
}


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

    def test_docs_top_level_dirs_match_spec(self):
        actual = {p.name for p in (ROOT / "docs").iterdir() if p.is_dir()}
        self.assertEqual(actual, ALLOWED_DOCS_DIRS,
                         "unexpected docs dirs: %s; missing: %s"
                         % (sorted(actual - ALLOWED_DOCS_DIRS),
                            sorted(ALLOWED_DOCS_DIRS - actual)))

    def test_legacy_artifact_dirs_are_moved(self):
        legacy_files = [
            "docs/requirements/REQ-0001-usage-ledger.md",
            "docs/requirements/REQ-0002-testing.md",
            "docs/changes/CHG-0001-docs-alignment.md",
            "docs/changes/CHG-0020-docs-structure-and-dev-process.md",
            "docs/adr/ADR-0001-source-of-truth-db-as-archive.md",
            "docs/rfcs/README.md",
        ]
        present = [path for path in legacy_files if (ROOT / path).is_file()]
        self.assertEqual(present, [], "legacy artifacts still present: %s" % ", ".join(present))

    def test_requirements_are_under_product_specs(self):
        for name in ["REQ-0001-usage-ledger.md", "REQ-0002-testing.md"]:
            self.assertTrue((ROOT / "docs" / "product-specs" / name).is_file(), name)

    def test_changes_are_under_exec_plans_completed(self):
        self.assertTrue((ROOT / "docs" / "exec-plans" / "completed" / "CHG-0001-docs-alignment.md").is_file())
        self.assertTrue((ROOT / "docs" / "exec-plans" / "completed" / "CHG-0020-docs-structure-and-dev-process.md").is_file())

    def test_adr_is_under_design_docs(self):
        self.assertTrue((ROOT / "docs" / "design-docs" / "ADR-0001-source-of-truth-db-as-archive.md").is_file())
        self.assertTrue((ROOT / "docs" / "design-docs" / "ADR-0002-pull-collection-no-daemon.md").is_file())

    def test_rfc_is_under_design_docs(self):
        self.assertTrue((ROOT / "docs" / "design-docs" / "rfcs" / "README.md").is_file())

    def test_agents_doc_map_uses_new_artifact_locations(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for needle in [
            "docs/product-specs/REQ-0001-usage-ledger.md",
            "docs/exec-plans/completed/CHG-0001-docs-alignment.md",
            "docs/design-docs/ADR-0001-source-of-truth-db-as-archive.md",
            "docs/design-docs/rfcs/README.md",
            "docs/exec-plans/active/",
            "docs/generated/db-schema.md",
        ]:
            self.assertIn(needle, text)
        for forbidden in ["`docs/requirements/`", "`docs/changes/`", "`docs/adr/`", "`docs/rfcs/`"]:
            self.assertNotIn(forbidden, text)

    def test_ac_map_points_to_new_requirement_location(self):
        import json
        payload = json.loads((ROOT / "tests" / "ac_map.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["REQ-0001"]["path"],
                         "docs/product-specs/REQ-0001-usage-ledger.md")


if __name__ == "__main__":
    unittest.main()
