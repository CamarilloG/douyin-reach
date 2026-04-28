"""机器指纹生成。

组合稳定的硬件 / 系统标识做 SHA-256，截取 32 hex 作为指纹。
- MAC 地址（uuid.getnode）
- Windows: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid（系统级唯一 ID，重装系统才会变）
- 非 Windows: platform.node()

指纹仅用于授权绑定，无可逆信息泄露。
"""
from __future__ import annotations

import hashlib
import platform
import sys
import uuid


def _windows_machine_guid() -> str:
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as k:
            value, _ = winreg.QueryValueEx(k, "MachineGuid")
            return str(value)
    except OSError:
        return ""


def get_machine_fingerprint() -> str:
    parts: list[str] = []

    mac = uuid.getnode()
    # 当无法获取真实 MAC 时 uuid.getnode() 会随机生成 - 用第 41 位（multicast bit）粗判
    if (mac >> 40) & 0x01 == 0:
        parts.append(f"mac:{mac:012x}")

    if sys.platform == "win32":
        guid = _windows_machine_guid()
        if guid:
            parts.append(f"winguid:{guid}")

    parts.append(f"node:{platform.node()}")

    raw = "|".join(parts) if parts else "fallback:unknown"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:32]
