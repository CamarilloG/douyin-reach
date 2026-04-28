# License 校验模块（离线 Ed25519 签名 + 7 天有效期 + 机器指纹绑定 + 防时钟回拨）
from .verifier import (
    LicenseError,
    LicenseInfo,
    activate_and_persist,
    verify_license_or_die,
    verify_token,
)
from .fingerprint import get_machine_fingerprint

__all__ = [
    "LicenseError",
    "LicenseInfo",
    "activate_and_persist",
    "verify_license_or_die",
    "verify_token",
    "get_machine_fingerprint",
]
