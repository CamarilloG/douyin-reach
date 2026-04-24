"""
运行时数据目录解析。

优先级:
1. 环境变量 DOUYIN_REACH_DATA(便于多实例 / 绿色版自定义)
2. 冻结(PyInstaller)模式 → exe 同目录的 ./data/
3. 开发模式 → 项目根的 ./data/

任何模块都通过 get_data_path("xxx.db") 取路径,
不要再用 os.path.join(_ROOT, "data", ...)。
"""
from __future__ import annotations

import os
import sys


def _detect_data_root() -> str:
    env = os.environ.get("DOUYIN_REACH_DATA", "").strip()
    if env:
        return os.path.abspath(env)

    if getattr(sys, "frozen", False):
        # PyInstaller / Nuitka 冻结模式: exe 同目录
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        return os.path.join(exe_dir, "data")

    # 开发模式: backend/utils 上四级 = 项目根
    here = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
    return os.path.join(project_root, "data")


_DATA_ROOT: str | None = None


def get_data_root() -> str:
    """运行时数据根目录。首次调用时确定,之后缓存。"""
    global _DATA_ROOT
    if _DATA_ROOT is None:
        _DATA_ROOT = _detect_data_root()
    return _DATA_ROOT


def get_data_path(*parts: str) -> str:
    """data 目录下的子路径,自动拼接。不创建目录(由调用方按需 makedirs)。"""
    return os.path.join(get_data_root(), *parts)


def ensure_data_dirs() -> str:
    """启动时调用一次:确保 data 根目录存在,返回路径。"""
    root = get_data_root()
    os.makedirs(root, exist_ok=True)
    return root


def get_frontend_dist_path() -> str:
    """前端构建产物 index.html 路径。
    冻结模式下走 _MEIPASS/frontend_dist/index.html,
    开发模式下走 src/frontend/dist/index.html。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.join(meipass, "frontend_dist", "index.html")
    here = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
    return os.path.join(project_root, "src", "frontend", "dist", "index.html")
