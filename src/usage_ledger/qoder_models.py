"""Qoder 模型内部键 → 界面显示名。

键来自桌面端模型选择器（文案在 Qoder.app/Contents/Resources/dynamic-text/qoder.json），
旧 IDE 的 local.db 还会写入 gm51model 等历史键。未收录的键原样返回。
"""

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


def qoder_model_label(model: str | None) -> str:
    if not model:
        return "unknown"
    key = str(model).strip()
    return QODER_MODEL_LABELS.get(key, key)
