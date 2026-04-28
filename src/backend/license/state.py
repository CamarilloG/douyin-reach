"""时钟回拨防护：维护历史最大时间戳到一个 HMAC 防篡改的状态文件。

文件位置：data/.license_state（与 license.key 同目录）。
- payload: { license_id, last_seen_ts (UTC ISO8601) }
- mac:     HMAC-SHA256(key=license_id+fingerprint, msg=payload_json)

读取时校验 MAC，写入时刷新 last_seen_ts = max(now, prev)。
即便用户回拨系统时间，effective_now 也不会倒退。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone


_STATE_FILENAME = ".license_state"


@dataclass
class LicenseState:
    license_id: str
    last_seen_ts: datetime  # UTC, tz-aware


def _state_path(data_root: str) -> str:
    return os.path.join(data_root, _STATE_FILENAME)


def _hmac_key(license_id: str, fingerprint: str) -> bytes:
    return f"{license_id}|{fingerprint}".encode("utf-8")


def _sign(payload_bytes: bytes, license_id: str, fingerprint: str) -> str:
    return hmac.new(_hmac_key(license_id, fingerprint), payload_bytes, hashlib.sha256).hexdigest()


def _parse_iso(s: str) -> datetime:
    # 容忍 'Z' 后缀
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_state(data_root: str, license_id: str, fingerprint: str) -> LicenseState | None:
    """读取状态文件；若不存在 / MAC 校验失败 / license_id 不匹配，返回 None。"""
    path = _state_path(data_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        payload = blob["payload"]
        mac = blob["mac"]
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = _sign(payload_bytes, license_id, fingerprint)
        if not hmac.compare_digest(mac, expected):
            return None
        if payload.get("license_id") != license_id:
            return None
        return LicenseState(
            license_id=license_id,
            last_seen_ts=_parse_iso(payload["last_seen_ts"]),
        )
    except (OSError, ValueError, KeyError):
        return None


def save_state(data_root: str, state: LicenseState, fingerprint: str) -> None:
    payload = {
        "license_id": state.license_id,
        "last_seen_ts": state.last_seen_ts.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    blob = {
        "payload": payload,
        "mac": _sign(payload_bytes, state.license_id, fingerprint),
    }
    path = _state_path(data_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False)
    os.replace(tmp, path)
