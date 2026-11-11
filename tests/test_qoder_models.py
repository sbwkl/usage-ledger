import unittest

from src.usage_ledger.qoder_models import qoder_model_label


class QoderModelLabelTest(unittest.TestCase):
    def test_current_keys_map_to_display_names(self):
        self.assertEqual(qoder_model_label("dfmodel"), "DeepSeek-Flash")
        self.assertEqual(qoder_model_label("gfmodel"), "GLM-5.3-Flash")
        self.assertEqual(qoder_model_label("qmodel_38max"), "Qwen3.8-Max")
        self.assertEqual(qoder_model_label("qmodel_latest"), "Qwen3.7-Max")

    def test_legacy_key_and_unknown_fallback(self):
        self.assertEqual(qoder_model_label("gm51model"), "GLM-5.2")
        self.assertEqual(qoder_model_label("experts-auto"), "experts-auto")
        self.assertEqual(qoder_model_label(None), "unknown")


if __name__ == "__main__":
    unittest.main()
