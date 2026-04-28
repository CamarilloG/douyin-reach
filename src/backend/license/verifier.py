"""License 校验入口。

调用 verify_license_or_die() 在 main.py 启动最前面执行：
通过 → 静默返回；失败 → 抛 LicenseError，由调用方决定弹窗 / 退出。

License 文件格式（data/license.key, JSON）::

    {
      "data": {
        "license_id": "<uuid>",
        "licensee": "XX 公司",
        "fingerprint": "<32 hex>",
        "issued_at": "2026-04-28T10:00:00Z",
        "expires_at": "2026-05-05T10:00:00Z"
      },
      "signature": "<base64 Ed25519 sig over canonical-json(data)>"
    }

签名内容：data 部分按 sort_keys + 紧凑分隔符序列化后的 UTF-8 字节。
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature

from .fingerprint import get_machine_fingerprint
from .keys import get_public_key
from .state import LicenseState, load_state, save_state

LICENSE_FILENAME = "license.key"


class LicenseError(Exception):
    """通用许可证错误。message 用于直接展示给用户。"""

    def __init__(self, message: str, *, code: str = "license_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LicenseInfo:
    license_id: str
    licensee: str
    fingerprint: str
    issued_at: datetime
    expires_at: datetime


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonical_data_bytes(data: dict) -> bytes:
    """与签发 CLI 共用：稳定序列化用于签名/验签。"""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _verify_blob(blob: dict) -> LicenseInfo:
    """校验已解析为 dict 的 license blob（不做指纹/有效期检查，仅签名 + 字段）。"""
    try:
        data = blob["data"]
        sig_b64 = blob["signature"]
    except (KeyError, TypeError) as e:
        raise LicenseError(f"许可证内容缺失字段：{e}", code="malformed") from e

    try:
        sig = base64.b64decode(sig_b64)
        get_public_key().verify(sig, canonical_data_bytes(data))
    except (InvalidSignature, ValueError) as e:
        raise LicenseError("许可证签名无效，可能已被篡改或来源不可信。", code="bad_signature") from e

    try:
        return LicenseInfo(
            license_id=str(data["license_id"]),
            licensee=str(data["licensee"]),
            fingerprint=str(data["fingerprint"]),
            issued_at=_parse_iso(data["issued_at"]),
            expires_at=_parse_iso(data["expires_at"]),
        )
    except (KeyError, ValueError) as e:
        raise LicenseError(f"许可证字段缺失或非法：{e}", code="malformed") from e


def _parse_token_or_json(raw: str) -> dict:
    """接受三种输入：
    1. 完整 license.key 文件 JSON 字符串
    2. base64 编码的 JSON（一行激活码）
    3. 带空白/换行的 base64（容错）
    """
    s = raw.strip()
    if not s:
        raise LicenseError("激活码为空。", code="empty")

    # 优先按 JSON 解析
    if s.startswith("{"):
        try:
            return json.loads(s)
        except ValueError as e:
            raise LicenseError(f"激活码 JSON 解析失败：{e}", code="malformed") from e

    # 否则按 base64 处理（去除所有空白/换行，宽容粘贴时的格式破坏）
    compact = "".join(s.split())
    try:
        decoded = base64.b64decode(compact, validate=False)
        return json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise LicenseError("激活码格式错误：既不是合法 JSON，也不是 base64 编码。", code="malformed") from e


def verify_token(raw: str) -> LicenseInfo:
    """对外：校验激活码（base64 或 JSON），含签名/指纹/有效期/防回拨。
    用于"粘贴激活码"/"选文件"流程；不写文件。校验通过后由 activate_and_persist 写入。
    """
    blob = _parse_token_or_json(raw)
    info = _verify_blob(blob)

    fp = get_machine_fingerprint()
    if info.fingerprint != fp:
        raise LicenseError(
            "本机器未授权使用此许可证。\n"
            f"许可证绑定的指纹：{info.fingerprint}\n"
            f"当前机器指纹：    {fp}\n\n"
            "请向软件提供方提供本机指纹以重新签发。",
            code="fingerprint_mismatch",
        )
    now = datetime.now(timezone.utc)
    if now > info.expires_at:
        raise LicenseError(
            "许可证已过期。\n"
            f"过期时间：{info.expires_at.isoformat()}\n\n"
            "请联系软件提供方续期。",
            code="expired",
        )
    return info


def activate_and_persist(raw: str, data_root: str) -> LicenseInfo:
    """校验 token 通过后，原样写入 data/license.key（采用规范化 JSON），并返回 LicenseInfo。
    若校验失败抛 LicenseError，文件不会被写入或覆盖。
    """
    info = verify_token(raw)
    blob = _parse_token_or_json(raw)  # 已通过校验，可放心再次解析
    license_path = os.path.join(data_root, LICENSE_FILENAME)
    os.makedirs(data_root, exist_ok=True)
    tmp = license_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False, indent=2)
    os.replace(tmp, license_path)
    return info


def _read_and_verify(license_path: str) -> LicenseInfo:
    if not os.path.isfile(license_path):
        raise LicenseError(
            "未找到激活文件，请使用激活码完成首次激活。",
            code="missing",
        )
    try:
        with open(license_path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError) as e:
        raise LicenseError(f"许可证文件格式错误：{e}", code="malformed") from e
    return _verify_blob(blob)


def verify_license_or_die(data_root: str) -> LicenseInfo:
    """执行完整校验：签名 → 机器指纹 → 有效期（含时钟回拨防护）。

    通过则更新 .license_state 并返回 LicenseInfo；失败抛 LicenseError。
    """
    license_path = os.path.join(data_root, LICENSE_FILENAME)
    info = _read_and_verify(license_path)

    fp = get_machine_fingerprint()
    if info.fingerprint != fp:
        raise LicenseError(
            "本机器未授权使用此许可证。\n"
            f"许可证绑定的指纹：{info.fingerprint}\n"
            f"当前机器指纹：    {fp}\n\n"
            "请向软件提供方提供本机指纹以重新签发。",
            code="fingerprint_mismatch",
        )

    now = datetime.now(timezone.utc)
    state = load_state(data_root, info.license_id, fp)
    last_seen = state.last_seen_ts if state else info.issued_at
    effective_now = max(now, last_seen)

    if effective_now > info.expires_at:
        raise LicenseError(
            "许可证已过期。\n"
            f"过期时间：{info.expires_at.isoformat()}\n\n"
            "请联系软件提供方续期。",
            code="expired",
        )

    save_state(
        data_root,
        LicenseState(license_id=info.license_id, last_seen_ts=effective_now),
        fp,
    )
    return info
