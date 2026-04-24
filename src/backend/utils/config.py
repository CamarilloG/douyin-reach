"""
全局配置：读写 JSON 文件，供设置页与 RealApi 使用。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .paths import get_data_path


def _default_path() -> str:
    return get_data_path("settings.json")


_DEFAULTS = {
    "send_interval": 30,
    "daily_limit": 100,
    "risk_warning_pause": 600,
    "risk_danger_stop": True,
    "linear_collection": True,  # 采集线性流程（首页搜索→点击卡片→返回），False 回退到 goto 批量模式
    "ai_api_key": "",
    "ai_endpoint": "",
    "ai_model": "",
    "browser_path": "",
    "cdp_url": "http://127.0.0.1:9222",
    "cdp_enabled": True,  # 方案 C: 默认接管系统 Chrome
}


def get_settings(path: str | None = None) -> dict[str, Any]:
    p = path or _default_path()
    if not os.path.isfile(p):
        return dict(_DEFAULTS)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = dict(_DEFAULTS)
        for k in _DEFAULTS:
            if k in data:
                out[k] = data[k]
        return out
    except Exception:
        return dict(_DEFAULTS)


def update_settings(data: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    current = get_settings(path)
    p = path or _default_path()
    for k in _DEFAULTS:
        if k in data:
            current[k] = data[k]
    try:
        os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return current
