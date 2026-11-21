"""Qoder 模型内部键 → 界面显示名。

显示名分三层解析，优先级 高 → 低：

1. i18n：Qoder 自带 dynamic-text 的 `model.<key>.label`，内置模型的权威文案，
   随 Qoder 升级自动更新，无需手工维护；优先级最高，避免被启发式学习覆盖。
2. learned：从 Qoder 计费缓存（`model_category`）按会话学习到的显示名，
   只填补 i18n 未收录的服务器下发键（如 `qmodel_latest_preview`）。
3. seed：内置静态兜底，仅在 i18n / learned 都取不到时使用（离线、CI、旧版 IDE）。

这样新增内置模型由 i18n 自动覆盖，新增服务器模型由 learned 自动覆盖，
静态表退化为离线兜底，不再需要逐个人工映射。
"""

from __future__ import annotations

import json
import os

# 离线 / CI / 旧版 IDE 兜底：i18n 与 learned 都不可用时的静态种子。
QODER_MODEL_LABELS = {
    "auto": "Auto",
    "ultimate": "Ultimate",
    "fast": "Fast",
    "efficient": "Efficient",
    "lite": "Lite",
    "performance": "Performance",
    "cmodel": "Cantus",
    "dmodel": "DeepSeek-V4-Pro",
    "dfmodel": "DeepSeek-Flash",
    "gmodel": "GLM-5.3",
    "gfmodel": "GLM-5.3-Flash",
    "kmodel": "Kimi-K2.8-Preview",
    "kmodel_latest": "Kimi-K3.1-Pro",
    "mmodel": "MiniMax-M3.1-Flash",
    "qmodel": "Qwen3.7-Plus",
    "qmodel_latest": "Qwen3.7-Max",
    "qmodel_38max": "Qwen3.8-Max",
    "qfmodel": "Qwen3.8-Flash",
    "smodel": "Sonus",
    "gm51model": "GLM-5.2",
}

_I18N_SUFFIX = ".label"
_I18N_PREFIX = "model."


def _iter_en_labels(data) -> dict[str, str]:
    """从 dynamic-text JSON 的 en 段提取 {model_key: label}。

    兼容两种结构：顶层 `{"en": {...}}` 与 `{"data": {"en": {...}}}`。
    """
    if not isinstance(data, dict):
        return {}
    block = data.get("en")
    if not isinstance(block, dict):
        nested = data.get("data")
        block = nested.get("en") if isinstance(nested, dict) else None
    if not isinstance(block, dict):
        return {}
    labels: dict[str, str] = {}
    for key, value in block.items():
        if (isinstance(key, str) and isinstance(value, str)
                and key.startswith(_I18N_PREFIX) and key.endswith(_I18N_SUFFIX)):
            model_key = key[len(_I18N_PREFIX):-len(_I18N_SUFFIX)]
            if model_key:
                labels[model_key] = value
    return labels


def load_i18n_labels_file(path: str) -> dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return _iter_en_labels(data)


def default_i18n_paths(home: str | None = None,
                       app_dirs: tuple[str, ...] = ("/Applications",)) -> list[str]:
    """Qoder dynamic-text 候选路径，按优先级 高 → 低。

    - 环境变量 `USAGE_LEDGER_QODER_I18N`（os.pathsep 分隔）显式覆盖全部路径
      （测试密闭或无标准安装时使用）；
    - 否则：App 安装目录下的 dynamic-text（`app_dirs`，默认 `/Applications`，
      与源数据 home 解耦——`USAGE_LEDGER_SOURCE_HOME` 只改数据目录，不影响 App 安装位置）
      + 用户目录下的运行时副本。
    """
    env = os.environ.get("USAGE_LEDGER_QODER_I18N")
    if env is not None:
        return [p for p in env.split(os.pathsep) if p]
    home = home or os.path.expanduser("~")
    paths: list[str] = []
    for base in app_dirs:
        for app in ("Qoder.app", "Qoder IDE.app"):
            candidate = os.path.join(
                base, app, "Contents", "Resources", "dynamic-text", "qoder.json")
            if os.path.exists(candidate):
                paths.append(candidate)
    live = os.path.join(home, "Library", "Application Support",
                        "com.qoder.app.stable", "dynamic-text", "qoder.v1.json")
    if os.path.exists(live):
        paths.append(live)
    return paths


def load_i18n_labels(paths: list[str] | None = None,
                     home: str | None = None) -> dict[str, str]:
    """按优先级合并多个 dynamic-text 文件；先出现者优先（不覆盖已收录键）。"""
    if paths is None:
        paths = default_i18n_paths(home)
    labels: dict[str, str] = {}
    for path in paths:
        for key, value in load_i18n_labels_file(path).items():
            labels.setdefault(key, value)
    return labels


def resolve_labels(i18n: dict[str, str] | None = None,
                   learned: dict[str, str] | None = None) -> dict[str, str]:
    """合并三层，优先级 高 → 低：i18n（Qoder 权威文案） > learned（计费学习） > 静态种子。

    i18n 是 Qoder 自带的事实源，优先级最高，避免计费学习的启发式结果覆盖它；
    learned 只填补 i18n 未收录的服务器下发键（如 `qmodel_latest_preview`）。
    """
    merged = dict(QODER_MODEL_LABELS)
    if learned:
        merged.update(learned)
    if i18n:
        merged.update(i18n)
    return merged


def qoder_model_label(model: str | None, labels: dict[str, str] | None = None) -> str:
    if not model:
        return "unknown"
    key = str(model).strip()
    if labels is not None:
        return labels.get(key) or QODER_MODEL_LABELS.get(key, key)
    return QODER_MODEL_LABELS.get(key, key)