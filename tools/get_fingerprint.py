"""商业团队 / 终端用户运行：在目标机器上打印机器指纹。

用法：
    python tools/get_fingerprint.py

或在打包后的环境，直接执行 exe 同目录的本脚本。
将打印的指纹回传给签发方，签发方用 tools/issue_license.py 生成绑定该机器的 license.key。
"""
from __future__ import annotations

import os
import sys

# 允许从仓库根直接运行
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.backend.license.fingerprint import get_machine_fingerprint  # noqa: E402


def main() -> None:
    fp = get_machine_fingerprint()
    print("机器指纹（请完整复制后回传给签发方）：")
    print()
    print(fp)
    print()


if __name__ == "__main__":
    main()
