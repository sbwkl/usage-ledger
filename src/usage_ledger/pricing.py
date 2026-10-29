from __future__ import annotations

ALIASES = {
    "space-bunny-free": "space-bunny-free",
    "kimi-for-coding": "kimi-for-coding",
    "stealth/space-bunny-alpha": "space-bunny-alpha",
    "minimax/minimax-m3.1-flash:free": "minimax-m3.1-flash",
    "deepseek-v4-flash-free": "deepseek-v4-flash",
    "deepseek-v4.1-flash-free": "deepseek-v4.1-flash",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "nemotron-3-ultra",
    "step-5-preview-free": "step-5-preview",
    "nemotron-3-ultra-free": "nemotron-3-ultra",
    "nemotron-3.5-lightning-free": "nemotron-3.5-lightning",
    "big-pickle": "big-pickle",
    "ox-alpha": "ox-alpha",
    "stealth/ox-alpha": "ox-alpha",
    "openrouter/free": "openrouter/free",
    "gpt-5.6-terra": "gpt-5.6-terra",
    "gpt-5.6-sol": "gpt-5.6-sol",
    "gpt-5.5": "gpt-5.5",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "minimax/minimax-m3:free": "minimax-m3",
    "kilo-auto/free": "kilo-auto",
    "minimax/minimax-m3.1-flash:free": "minimax-m3.1-flash",
}

# Prices USD per 1M tokens; unknown -> None
PRICES = {
    "gpt-5.5": {"input": None, "output": None, "cache_read": None, "cache_write": None, "reasoning": None},
}


def normalize_model(model: str) -> str:
    return ALIASES.get(model, model)


def cost_for_record(rec) -> tuple[float | None, str]:
    return None, "unknown"
