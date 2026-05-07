"""抖音助手（Douyin Reach）桌面入口。
启动 pywebview 窗口并加载 Vue 前端；暴露 Api 给前端通过 JS-Python bridge 调用。

支持两种运行模式:
- 开发模式: python main.py    → 加载 src/frontend/dist 或 vite dev server
- 冻结模式: 双击 exe          → 从 _MEIPASS/frontend_dist 加载,数据写入 exe 同目录 ./data/

启动期防御策略（fail-closed + 友好提示）:
1. 顶层 main() 用 try/except 包住整个启动序列。任何未预料异常 → 弹原生 MessageBox 后退出，
   避免客户看到黑窗一闪而过。
2. license 校验段单独捕获非 LicenseError 异常（如 cryptography 内部错误、winreg 异常等），
   转换为 internal_error 注入到激活蒙版而不是让进程崩溃。
3. 即便授权模块整体异常，软件也会"启动到激活蒙版状态"，主功能保持不可用（fail-closed）。
"""
from __future__ import annotations

import logging
import os
import sys
import traceback

# 保证从项目根目录运行时可导入 src.backend(冻结模式下 PyInstaller 已自动处理 sys.path)
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 默认日志级别 INFO:私信发送 store 直驱路径、浏览器引擎降级、风控状态等诊断信息
# 都是 logger.info,默认 WARNING 会全部静默,排错时不可用。
# 设置 DOUYIN_REACH_LOG=DEBUG 可进一步打开 DEBUG。
_LOG_LEVEL = os.getenv("DOUYIN_REACH_LOG", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def _show_fatal_and_exit(message: str, details: str = "") -> None:
    """启动期不可恢复错误：弹 Windows MessageBox（带详细信息）后退出。
    设置 DOUYIN_REACH_NO_DIALOG=1 时跳过弹框（CI / headless / 仿真）。
    """
    title = "抖音助手 启动失败"
    body = message
    if details:
        body += "\n\n--- 详细信息（可截图发给软件提供方） ---\n" + details
    print(f"[FATAL] {body}", file=sys.stderr)
    if os.getenv("DOUYIN_REACH_NO_DIALOG", "").lower() not in ("1", "true", "yes"):
        try:
            import ctypes  # type: ignore[import-not-found]

            # MB_OK | MB_ICONERROR | MB_SYSTEMMODAL = 0x10 | 0x1000
            ctypes.windll.user32.MessageBoxW(0, body, title, 0x10 | 0x1000)
        except Exception:
            pass
    sys.exit(1)


def main() -> None:
    """顶层入口：包住整个启动序列，任何未捕获异常 → 友好弹窗。"""
    try:
        _main_inner()
    except SystemExit:
        raise
    except BaseException as e:  # 包括 KeyboardInterrupt 等罕见路径
        _show_fatal_and_exit(
            f"软件启动遇到意外错误：\n{type(e).__name__}: {e}",
            details=traceback.format_exc(),
        )


def _main_inner() -> None:
    # 关键依赖按顺序导入；任一失败由 main() 兜底转成友好弹窗
    import webview

    from src.backend.utils.paths import (
        ensure_data_dirs,
        get_data_root,
        get_frontend_dist_path,
    )
    from src.backend.api.real import RealApi
    from src.backend.version import VERSION, APP_NAME

    # license 模块单独导入并兜底：缺 cryptography / 模块结构错位等场景，
    # 不应让进程崩溃，而是降级为"未激活 + 内部错误提示"，让蒙版告诉客户该联系谁。
    try:
        from src.backend.license import LicenseError, verify_license_or_die
    except Exception as e:
        LicenseError = None  # type: ignore[assignment]
        verify_license_or_die = None  # type: ignore[assignment]
        license_import_error = (
            "internal_error",
            "授权模块加载失败（运行环境异常），请联系软件提供方：\n"
            f"{type(e).__name__}: {e}",
        )
    else:
        license_import_error = None

    data_root = ensure_data_dirs()
    print(f"[启动] {APP_NAME} v{VERSION} | 数据目录: {data_root}")

    # 商业版授权校验：通过 → 注入 LicenseInfo；失败 → 注入失败原因供激活蒙版处理。
    license_info = None
    license_error: tuple[str, str] | None = None

    if license_import_error is not None:
        license_error = license_import_error
        print(f"[License] IMPORT FAIL: {license_import_error[1]}")
    else:
        try:
            license_info = verify_license_or_die(data_root)
            print(
                f"[License] OK | licensee={license_info.licensee} | "
                f"expires_at={license_info.expires_at.isoformat()}"
            )
        except LicenseError as e:  # type: ignore[misc]
            license_error = (e.code, e.message)
            print(f"[License] FAIL ({e.code}): {e.message}")
        except Exception as e:
            # cryptography 内部错误 / IO 异常 / winreg 异常等。fail-closed：
            # 不冒泡导致进程崩溃，转成 internal_error 让蒙版兜住。
            tb = traceback.format_exc()
            license_error = (
                "internal_error",
                "授权校验过程发生内部错误，请联系软件提供方：\n"
                f"{type(e).__name__}: {e}",
            )
            print(f"[License] INTERNAL ERROR:\n{tb}", file=sys.stderr)

    api = RealApi()
    if hasattr(api, "set_license"):
        api.set_license(license_info, license_error)

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
