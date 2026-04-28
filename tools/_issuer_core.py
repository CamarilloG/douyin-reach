"""签发流程的核心函数，供 CLI（issue_license.py）和 GUI（license_studio.py）共用。

仅供签发方本地使用，需要私钥：~/.douyin_reach_keys/license_signing_ed25519.pem
"""
from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# 允许从仓库根直接运行
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.backend.license.verifier import canonical_data_bytes  # noqa: E402

DEFAULT_KEY_PATH = Path.home() / ".douyin_reach_keys" / "license_signing_ed25519.pem"
FINGERPRINT_HEX_LEN = 32


class IssuerError(Exception):
    """签发过程的友好错误，message 直接展示给签发人。"""


@dataclass
class IssuedLicense:
    blob: dict       # { data, signature } 完整对象
    file_text: str   # 漂亮缩进的 license.key 文件内容
    token_b64: str   # 一行 base64 激活码
    summary: dict    # 用于 UI 展示：licensee/fingerprint/issued_at/expires_at/license_id/days


def load_private_key(path: Path | str) -> Ed25519PrivateKey:
    p = Path(path)
    if not p.is_file():
        raise IssuerError(f"私钥不存在：{p}")
    try:
        key = serialization.load_pem_private_key(p.read_bytes(), password=None)
    except Exception as e:
        raise IssuerError(f"私钥读取失败：{e}") from e
    if not isinstance(key, Ed25519PrivateKey):
        raise IssuerError(f"私钥类型错误（需要 Ed25519）：{type(key).__name__}")
    return key


def validate_fingerprint(raw: str) -> str:
    fp = (raw or "").strip().lower()
    if len(fp) != FINGERPRINT_HEX_LEN or any(c not in "0123456789abcdef" for c in fp):
        raise IssuerError(f"指纹格式错误（需 {FINGERPRINT_HEX_LEN} 位十六进制）：{raw!r}")
    return fp


def issue(
    *,
    licensee: str,
    fingerprint: str,
    days: int,
    private_key: Ed25519PrivateKey,
) -> IssuedLicense:
    licensee = (licensee or "").strip()
    if not licensee:
        raise IssuerError("被授权方不能为空。")
    if days <= 0:
        raise IssuerError("有效天数必须为正整数。")
    fp = validate_fingerprint(fingerprint)

    issued_at = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = issued_at + timedelta(days=days)

    data = {
        "license_id": str(uuid.uuid4()),
        "licensee": licensee,
        "fingerprint": fp,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }
    sig = private_key.sign(canonical_data_bytes(data))
    blob = {"data": data, "signature": base64.b64encode(sig).decode("ascii")}

    file_text = json.dumps(blob, ensure_ascii=False, indent=2)
    compact_json = json.dumps(blob, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token_b64 = base64.b64encode(compact_json).decode("ascii")

    return IssuedLicense(
        blob=blob,
        file_text=file_text,
        token_b64=token_b64,
        summary={
            "licensee": licensee,
            "fingerprint": fp,
            "issued_at": data["issued_at"],
            "expires_at": data["expires_at"],
            "license_id": data["license_id"],
            "days": days,
        },
    )
