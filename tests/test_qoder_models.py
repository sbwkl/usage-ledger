import json
import os
import tempfile
import unittest

from src.usage_ledger.qoder_models import (QODER_MODEL_LABELS, default_i18n_paths,
                                           load_i18n_labels,
                                           load_i18n_labels_file, qoder_model_label,
                                           resolve_labels)


class QoderModelLabelTest(unittest.TestCase):
    def test_static_seed_maps_builtins(self):
        self.assertEqual(qoder_model_label("dfmodel"), "DeepSeek-Flash")
        self.assertEqual(qoder_model_label("gfmodel"), "GLM-5.3-Flash")
        self.assertEqual(qoder_model_label("qmodel_38max"), "Qwen3.8-Max")
        self.assertEqual(qoder_model_label("qmodel_latest"), "Qwen3.7-Max")

    def test_legacy_key_and_unknown_fallback(self):
        self.assertEqual(qoder_model_label("gm51model"), "GLM-5.2")
        self.assertEqual(qoder_model_label("experts-auto"), "experts-auto")
        self.assertEqual(qoder_model_label(None), "unknown")

    def test_labels_argument_overrides_seed(self):
        labels = resolve_labels({"dfmodel": "DeepSeek-V4-Flash"},
                                {"qmodel_latest_preview": "Qwen4-Max-Preview"})
        self.assertEqual(qoder_model_label("dfmodel", labels), "DeepSeek-V4-Flash")
        self.assertEqual(qoder_model_label("qmodel_latest_preview", labels),
                         "Qwen4-Max-Preview")
        # 未在 labels 中的键回退到静态种子
        self.assertEqual(qoder_model_label("gfmodel", labels), "GLM-5.3-Flash")


class I18nLabelTest(unittest.TestCase):
    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_parses_top_level_en_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "qoder.json")
            self._write(path, {"en": {"model.qmodel.label": "Qwen3.7-Plus",
                                      "model.qmodel.detail": "x",
                                      "other": "y"}})
            self.assertEqual(load_i18n_labels_file(path),
                             {"qmodel": "Qwen3.7-Plus"})

    def test_parses_nested_data_en_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "qoder.v1.json")
            self._write(path, {"version": "1.0", "data": {
                "en": {"model.qmodel_latest_preview.label": "Qwen4-Max-Preview"}}})
            self.assertEqual(load_i18n_labels_file(path),
                             {"qmodel_latest_preview": "Qwen4-Max-Preview"})

    def test_missing_or_broken_file_is_empty(self):
        self.assertEqual(load_i18n_labels_file("/no/such/file.json"), {})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            self.assertEqual(load_i18n_labels_file(path), {})

    def test_merge_prefers_earlier_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = os.path.join(tmp, "app.json")
            live = os.path.join(tmp, "live.json")
            self._write(app, {"en": {"model.qmodel_latest.label": "Qwen3.7-Max"}})
            self._write(live, {"data": {"en": {
                "model.qmodel_latest.label": "StaleName",
                "model.qmodel.label": "Qwen3.7-Plus"}}})
            labels = load_i18n_labels([app, live])
            self.assertEqual(labels["qmodel_latest"], "Qwen3.7-Max")
            self.assertEqual(labels["qmodel"], "Qwen3.7-Plus")

    def test_env_override_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "only.json")
            self._write(path, {"en": {"model.gfmodel.label": "GLM-5.3-Flash"}})
            old = os.environ.get("USAGE_LEDGER_QODER_I18N")
            os.environ["USAGE_LEDGER_QODER_I18N"] = path
            try:
                self.assertEqual(load_i18n_labels(), {"gfmodel": "GLM-5.3-Flash"})
            finally:
                if old is None:
                    os.environ.pop("USAGE_LEDGER_QODER_I18N", None)
                else:
                    os.environ["USAGE_LEDGER_QODER_I18N"] = old

    def test_seed_contains_no_preview_key(self):
        # 服务器下发键不应写进静态种子，靠 i18n / learned 覆盖
        self.assertNotIn("qmodel_latest_preview", QODER_MODEL_LABELS)

    def test_default_paths_app_bundle_and_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = os.path.join(tmp, "apps")
            app_json = os.path.join(app_dir, "Qoder.app", "Contents", "Resources",
                                    "dynamic-text", "qoder.json")
            os.makedirs(os.path.dirname(app_json))
            self._write(app_json, {"en": {}})
            old_home = os.environ.pop("USAGE_LEDGER_SOURCE_HOME", None)
            old_env = os.environ.pop("USAGE_LEDGER_QODER_I18N", None)
            try:
                paths = default_i18n_paths(home=tmp, app_dirs=(app_dir,))
            finally:
                if old_home is not None:
                    os.environ["USAGE_LEDGER_SOURCE_HOME"] = old_home
                if old_env is not None:
                    os.environ["USAGE_LEDGER_QODER_I18N"] = old_env
            self.assertIn(app_json, paths)

    def test_source_home_does_not_disable_app_bundle(self):
        # SOURCE_HOME 只改数据目录，不应禁用 App 安装目录下的 dynamic-text。
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = os.path.join(tmp, "apps")
            app_json = os.path.join(app_dir, "Qoder.app", "Contents", "Resources",
                                    "dynamic-text", "qoder.json")
            os.makedirs(os.path.dirname(app_json))
            self._write(app_json, {"en": {"model.qmodel.label": "Qwen3.7-Plus"}})
            old_home = os.environ.get("USAGE_LEDGER_SOURCE_HOME")
            old_env = os.environ.pop("USAGE_LEDGER_QODER_I18N", None)
            os.environ["USAGE_LEDGER_SOURCE_HOME"] = "/tmp/fake-data-home"
            try:
                paths = default_i18n_paths(home=tmp, app_dirs=(app_dir,))
                labels = load_i18n_labels(paths)
            finally:
                if old_home is None:
                    os.environ.pop("USAGE_LEDGER_SOURCE_HOME", None)
                else:
                    os.environ["USAGE_LEDGER_SOURCE_HOME"] = old_home
                if old_env is not None:
                    os.environ["USAGE_LEDGER_QODER_I18N"] = old_env
            self.assertIn(app_json, paths)
            self.assertEqual(labels.get("qmodel"), "Qwen3.7-Plus")

    def test_explicit_i18n_env_disables_app_bundle(self):
        # 显式设置 USAGE_LEDGER_QODER_I18N="" 用于测试密闭 / 无标准安装场景。
        old_home = os.environ.pop("USAGE_LEDGER_SOURCE_HOME", None)
        old_env = os.environ.get("USAGE_LEDGER_QODER_I18N")
        os.environ["USAGE_LEDGER_QODER_I18N"] = ""
        try:
            self.assertEqual(default_i18n_paths(home="/tmp/x"), [])
        finally:
            if old_home is not None:
                os.environ["USAGE_LEDGER_SOURCE_HOME"] = old_home
            if old_env is None:
                os.environ.pop("USAGE_LEDGER_QODER_I18N", None)
            else:
                os.environ["USAGE_LEDGER_QODER_I18N"] = old_env


if __name__ == "__main__":
    unittest.main()