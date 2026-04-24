"""
分步调试模式：每步输出步骤名并等待人工/AI 确认后继续。
环境变量 DOUYIN_REACH_DEBUG_STEP=1 时启用；需配合 CDP 9222 或 run_cdp_monitor、Chrome DevTools MCP 等浏览器监控进程进行确认。
"""
from __future__ import annotations

import os
import sys


def is_enabled() -> bool:
    """是否启用分步调试模式。"""
    return os.getenv("DOUYIN_REACH_DEBUG_STEP", "").lower() in ("1", "true", "yes")


def step(name: str, detail: str = "") -> None:
    """
    输出当前步骤名，并等待确认后继续。
    确认方式：在控制台按 Enter（人工）或 AI 通过 MCP/监控工具确认后由人工按 Enter。
    """
    if not is_enabled():
        return
    msg = f"\n[STEP] {name}"
    if detail:
        msg += f" | {detail}"
    msg += "\n  请开启浏览器监控(CDP/MCP)确认后按 Enter 继续..."
    print(msg, flush=True)
    try:
        sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        pass
