"""
抖音助手（Douyin Reach）桌面入口。
启动 pywebview 窗口并加载 Vue 前端；暴露 Api 给前端通过 JS-Python bridge 调用。

支持两种运行模式:
- 开发模式: python main.py    → 加载 src/frontend/dist 或 vite dev server
- 冻结模式: 双击 exe          → 从 _MEIPASS/frontend_dist 加载,数据写入 exe 同目录 ./data/
"""
from __future__ import annotations

import os
import sys

# 保证从项目根目录运行时可导入 src.backend(冻结模式下 PyInstaller 已自动处理 sys.path)
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    import webview

    from src.backend.utils.paths import (
        ensure_data_dirs,
        get_data_root,
        get_frontend_dist_path,
    )
    from src.backend.api.real import RealApi
    from src.backend.version import VERSION, APP_NAME

    # 启动时确保数据目录存在(冻结模式 = exe 同目录/data)
    data_root = ensure_data_dirs()
    print(f"[启动] {APP_NAME} v{VERSION} | 数据目录: {data_root}")

    api = RealApi()

    use_dev = os.getenv("DOUYIN_REACH_DEV", "").lower() in ("1", "true", "yes")
    dist_path = get_frontend_dist_path()

    if use_dev:
        url = "http://localhost:5173"
        print("开发模式：请确保前端已运行 (cd src/frontend && npm run dev)")
    elif os.path.isfile(dist_path):
        url = dist_path
        print(f"[启动] 加载前端: {dist_path}")
    else:
        url = "http://localhost:5173"
        print(f"未找到 dist ({dist_path})，使用开发地址。若前端未启动请先: cd src/frontend && npm run dev")

    window = webview.create_window(
        f"{APP_NAME} v{VERSION}",
        url=url,
        width=1280,
        height=800,
        js_api=api,
        resizable=True,
    )
    if hasattr(api, "set_window"):
        api.set_window(window)

    # 应用图标:冻结模式从 _MEIPASS 取,开发模式从项目根取
    icon_name = "5oj5n-gaprv-001.ico"
    if getattr(sys, "frozen", False):
        icon_path = os.path.join(getattr(sys, "_MEIPASS", _ROOT), icon_name)
    else:
        icon_path = os.path.join(_ROOT, icon_name)
    icon_kwargs = {"icon": icon_path} if os.path.isfile(icon_path) else {}

    webview.start(debug=use_dev, **icon_kwargs)


if __name__ == "__main__":
    main()
