"""License 验签公钥（Ed25519, raw 32B base64）。

私钥保存在签发方本地（~/.douyin_reach_keys/license_signing_ed25519.pem），
绝不入仓库；这里仅嵌入公钥，用于运行时验签。
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# 与 ~/.douyin_reach_keys/license_signing_ed25519.pem 配对的公钥（raw, base64）
_PUBLIC_KEY_B64 = "Kzwvd6nB3jaaQIQLohlblTfUjVgrjxcqLFp6r2TLEiQ="


def get_public_key() -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(_PUBLIC_KEY_B64))
