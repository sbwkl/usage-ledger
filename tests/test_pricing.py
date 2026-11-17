import ast
import unittest
from pathlib import Path

from src.usage_ledger import pricing


class PricingAliasesTest(unittest.TestCase):
    def test_aliases_literal_has_no_duplicate_keys(self):
        source = Path(pricing.__file__).read_text(encoding="utf-8")
        dicts = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "ALIASES" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ]
        self.assertEqual(len(dicts), 1)
        keys = [key.value for key in dicts[0].keys]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        self.assertEqual(duplicates, [], "ALIASES 存在重复键：%s" % duplicates)

    def test_normalize_model_maps_free_alias(self):
        self.assertEqual(
            pricing.normalize_model("minimax/minimax-m3.1-flash:free"),
            "minimax-m3.1-flash")
        self.assertEqual(pricing.normalize_model("unknown-model"), "unknown-model")


if __name__ == "__main__":
    unittest.main()