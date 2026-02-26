"""
CDP 实例监控脚本：轮询浏览器调试端口，将页面列表写入 logs，供验收调试与 MCP 对照。
用法（在项目根目录）：
  1. 先在一个终端启动验收并开启 CDP：set DOUYIN_REACH_CDP_PORT=9222 && python scripts/run_m2_acceptance.py
  2. 在另一个终端运行本脚本：python scripts/run_cdp_monitor.py
  3. 验收结束后按 Ctrl+C 停止本脚本；或本脚本检测到 9222 无响应时自动退出。
环境变量：DOUYIN_REACH_CDP_PORT 默认 9222。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

LOGS_DIR = os.path.join(_ROOT, "logs")
INTERVAL_SEC = 15


def main() -> None:
    port = os.getenv("DOUYIN_REACH_CDP_PORT", "9222").strip()
    if not port.isdigit():
        port = "9222"
    url = f"http://127.0.0.1:{port}/json/list"
    os.makedirs(LOGS_DIR, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(LOGS_DIR, f"cdp-pages-{run_id}.log")
    print(f"CDP 实例监控已启动，每 {INTERVAL_SEC}s 轮询 {url}，写入 {log_path}")
    try:
        while True:
            ts = datetime.now().strftime("%H:%M:%S")
            try:
                req = Request(url)
                with urlopen(req, timeout=5) as r:
                    data = json.loads(r.read().decode())
                # 每条记录一行：时间戳 + JSON（便于 grep/解析）
                line = json.dumps({"ts": ts, "pages": data}, ensure_ascii=False) + "\n"
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(line)
                count = len(data) if isinstance(data, list) else 0
                print(f"[{ts}] 页面数: {count}")
            except URLError as e:
                print(f"[{ts}] 无法连接 CDP ({url}): {e}")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": ts, "error": str(e)}, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[{ts}] 错误: {e}")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": ts, "error": str(e)}, ensure_ascii=False) + "\n")
            time.sleep(INTERVAL_SEC)
    except KeyboardInterrupt:
        print("监控已停止。")


if __name__ == "__main__":
    main()
