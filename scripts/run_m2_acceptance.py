"""
M2 验收脚本：登录 → 搜索关键词 → 获取视频列表 → 拉取评论与用户信息。
在项目根目录执行：python scripts/run_m2_acceptance.py
需已安装 playwright 并执行过 playwright install chromium。

如需 MCP 实时监测本脚本启动的浏览器：
  1. 设置环境变量 DOUYIN_REACH_CDP_PORT=9222 后运行（如 set DOUYIN_REACH_CDP_PORT=9222 && python scripts/run_m2_acceptance.py）
  2. 在 Cursor 中将 Chrome DevTools MCP 的连接目标设为 http://localhost:9222（或对应 CDP 端点）
  3. 验收运行期间可用 list_pages、take_snapshot、take_screenshot 等工具监测该实例
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# 保证从项目根目录运行时可导入 src.backend
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 确保 data 目录存在
os.makedirs(os.path.join(_ROOT, "data"), exist_ok=True)

# Windows 控制台默认 cp1252 无法输出中文，改为 utf-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


async def main() -> None:
    from src.backend.browser import BrowserEngine

    # 启用完整浏览器日志与 MCP 监测：DOUYIN_REACH_SAVE_BROWSER_LOG=1 或 DOUYIN_REACH_CDP_PORT=9222 即写浏览器日志
    save_browser_log = os.getenv("DOUYIN_REACH_SAVE_BROWSER_LOG", "").lower() in ("1", "true", "yes")
    cdp_port = os.getenv("DOUYIN_REACH_CDP_PORT", "")
    if not save_browser_log and cdp_port.isdigit():
        save_browser_log = True  # 开 CDP 时默认保存浏览器日志便于调试
    log_path = None
    if save_browser_log:
        from datetime import datetime
        logs_dir = os.path.join(_ROOT, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, f"acceptance-browser-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
        print(f"浏览器日志将写入: {log_path}")

    engine = BrowserEngine(headless=False, browser_log_path=log_path)
    try:
        print("启动浏览器并打开抖音首页...")
        await engine.launch()
        print("校验 session...")
        if await engine.check_session():
            print("当前已登录，跳过登录步骤。")
        else:
            print("未检测到有效登录，请在浏览器中完成扫码/密码登录。")
            ok = await engine.login()
            if not ok:
                print("登录未完成或超时，退出。")
                return
            print("登录成功，已保存会话。")

        print("搜索关键词「测试」，最多 5 条视频...")
        videos = await engine.search_videos("测试", 5)
        print(f"  得到 {len(videos)} 条视频。")
        for i, v in enumerate(videos[:3], 1):
            print(f"  [{i}] {v.get('title') or v.get('aweme_id')} | 作者: {v.get('author_nickname')}")

        if not videos:
            print("无视频结果，验收结束。")
            return

        first_url = videos[0].get("video_url")
        if first_url:
            print(f"进入首条视频拉取评论（最多 10 条）: {first_url}")
            comments = await engine.fetch_comments(first_url, 10)
            print(f"  得到 {len(comments)} 条一级评论。")
            for j, c in enumerate(comments[:5], 1):
                print(f"  [{j}] {c.get('commenter_nickname')}: {c.get('text', '')[:40]}...")

            if comments:
                sec_uid = comments[0].get("commenter_sec_uid")
                if sec_uid:
                    print(f"补全首条评论用户信息: sec_uid={sec_uid[:20]}...")
                    info = await engine.fetch_user_info(sec_uid)
                    print(f"  昵称: {info.get('nickname')}")

        print("验收流程执行完毕。")
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
