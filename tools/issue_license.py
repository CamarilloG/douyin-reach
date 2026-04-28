"""签发 license.key 的离线 CLI（仅签发方使用）。

依赖私钥：~/.douyin_reach_keys/license_signing_ed25519.pem（PKCS8/PEM, 无加密）。
私钥不入仓库，丢失需重新生成密钥对并替换 src/backend/license/keys.py 内置公钥。

用法示例：
    python tools/issue_license.py \\
        --licensee "示例公司" \\
        --fingerprint <对方机器指纹> \\
        --days 7 \\
        --out license.key

参数：
    --licensee     被授权方名称（任意字符串，仅作展示与审计）
    --fingerprint  目标机器指纹（对方运行 tools/get_fingerprint.py 拿到）
    --days         有效天数，默认 7
    --out          输出文件路径，默认 ./license.key
    --key          私钥路径，默认 ~/.douyin_reach_keys/license_signing_ed25519.pem

GUI 版：tools/license_studio.py（建议日常使用）。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _issuer_core import DEFAULT_KEY_PATH, IssuerError, issue, load_private_key


def main() -> None:
    p = argparse.ArgumentParser(description="签发 license.key（Ed25519 离线签名）")
    p.add_argument("--licensee", required=True, help="被授权方名称")
    p.add_argument("--fingerprint", required=True, help="目标机器指纹（32 hex）")
    p.add_argument("--days", type=int, default=7, help="有效天数（默认 7）")
    p.add_argument("--out", default="license.key", help="输出路径（默认 ./license.key）")
    p.add_argument("--key", default=str(DEFAULT_KEY_PATH), help="私钥路径")
    args = p.parse_args()

    try:
        priv = load_private_key(Path(args.key))
        result = issue(
            licensee=args.licensee,
            fingerprint=args.fingerprint,
            days=args.days,
            private_key=priv,
        )
    except IssuerError as e:
        raise SystemExit(str(e))

    out_path = Path(args.out)
    out_path.write_text(result.file_text, encoding="utf-8")

    s = result.summary
    print(f"已签发：{out_path.resolve()}")
    print(f"  licensee   : {s['licensee']}")
    print(f"  fingerprint: {s['fingerprint']}")
    print(f"  issued_at  : {s['issued_at']}")
    print(f"  expires_at : {s['expires_at']}（{s['days']} 天）")
    print(f"  license_id : {s['license_id']}")
    print()
    print("交付方式（任选其一）：")
    print(f"  方式 A · 文件：将 {out_path.name} 发给客户，客户在软件激活蒙版选「选择文件」加载。")
    print("  方式 B · 激活码：把下方一行 base64 字符串复制给客户，客户在激活蒙版选「粘贴激活码」。")
    print()
    print("---激活码 (base64)---")
    print(result.token_b64)
    print("---------------------")


if __name__ == "__main__":
    main()
