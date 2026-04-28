"""
应用版本号 - 单一来源 (Single Source of Truth)。

修改这里就同步生效:
- 后端 RealApi.get_app_version()       → 前端 SettingsView 关于卡片
- 前端 App.vue 标题旁的版本徽章
- douyin_reach.spec → 打包产物文件名
- main.py → 窗口标题
- pyproject.toml(可选)

版本规则(PEP 440):
- 0.x.x  开发期
- 0.x.xbN  beta 版本(如 0.1.0b1)
- 1.0.0  正式发布
"""
from __future__ import annotations

VERSION = "0.1.0b7"
APP_NAME = "抖音助手"


def get_version_string() -> str:
    """带 v 前缀的展示版本,如 v0.1.0b1。"""
    return f"v{VERSION}"


def get_filename_version() -> str:
    """文件名安全的版本字符串,如 0.1.0b1。"""
    return VERSION
