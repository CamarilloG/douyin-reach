"""
抖音助手（Douyin Reach）桌面入口。
启动 pywebview 窗口并加载 Vue 前端；暴露 Api 给前端通过 JS-Python bridge 调用。
"""
from __future__ import annotations

import os
import sys

# 保证从项目根目录运行时可导入 src.backend
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    import webview

    from src.backend.api import MockApi

    api = MockApi()
    frontend_dir = os.path.join(_ROOT, "src", "frontend")
    dist_path = os.path.join(frontend_dir, "dist", "index.html")
    use_dev = os.getenv("DOUYIN_REACH_DEV", "").lower() in ("1", "true", "yes")

    if use_dev:
        url = "http://localhost:5173"
        print("开发模式：请确保前端已运行 (cd src/frontend && npm run dev)")
    elif os.path.isfile(dist_path):
        url = os.path.join(frontend_dir, "dist", "index.html")
    else:
        url = "http://localhost:5173"
        print("未找到 dist，使用开发地址。若前端未启动请先: cd src/frontend && npm run dev")

    window = webview.create_window(
        "抖音助手",
        url=url,
        width=1280,
        height=800,
        js_api=api,
        resizable=True,
    )
    webview.start(debug=use_dev)


if __name__ == "__main__":
    main()
