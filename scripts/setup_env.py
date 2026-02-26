"""
自动执行项目相关配置：创建 venv、安装后端依赖、安装 Playwright Chromium、创建 data/logs、可选前端 npm install。
在项目根目录执行：python scripts/setup_env.py
"""
from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> bool:
    cwd = cwd or _ROOT
    env = dict(env) if env else dict(os.environ)
    # 避免 Windows 下 pip 读 requirements.txt 时 gbk 解码错误
    env.setdefault("PYTHONUTF8", "1")
    try:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [失败] 退出码 {e.returncode}")
        return False


def main() -> None:
    os.chdir(_ROOT)
    print("项目根目录:", _ROOT)

    # 1. venv
    venv_dir = os.path.join(_ROOT, "venv")
    pip = os.path.join(venv_dir, "Scripts", "pip.exe") if sys.platform == "win32" else os.path.join(venv_dir, "bin", "pip")
    python_venv = os.path.join(venv_dir, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(venv_dir, "bin", "python")

    if not os.path.isdir(venv_dir):
        print("\n1. 创建 venv...")
        if run([sys.executable, "-m", "venv", venv_dir]):
            print("  venv 创建成功。")
        else:
            print("  venv 创建失败，退出。")
            sys.exit(1)
    else:
        print("\n1. venv 已存在，跳过。")

    # 2. pip install
    print("\n2. 安装后端依赖...")
    if run([pip, "install", "-r", "requirements.txt"]):
        print("  pip install -r requirements.txt 成功。")
    else:
        print("  完整安装失败，尝试仅安装 playwright + python-dotenv...")
        if run([pip, "install", "playwright", "python-dotenv"]):
            print("  playwright + python-dotenv 安装成功（pywebview 未装，可稍后补装）。")
        else:
            print("  备用安装失败，退出。")
            sys.exit(1)

    # 3. playwright install chromium
    print("\n3. 安装 Playwright Chromium...")
    if run([python_venv, "-m", "playwright", "install", "chromium"]):
        print("  playwright install chromium 成功。")
    else:
        print("  playwright install chromium 失败，M2 验收脚本可能无法运行。")
        sys.exit(1)

    # 4. data / logs
    for name in ("data", "logs"):
        d = os.path.join(_ROOT, name)
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            print(f"\n4. 已创建目录: {name}/")
    if os.path.isdir(os.path.join(_ROOT, "data")) and os.path.isdir(os.path.join(_ROOT, "logs")):
        print("   data/ 与 logs/ 已就绪。")

    # 5. 前端（可选）
    frontend = os.path.join(_ROOT, "src", "frontend")
    if os.path.isdir(frontend) and os.path.isfile(os.path.join(frontend, "package.json")):
        print("\n5. 前端依赖 (npm install)...")
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        if run([npm, "install"], cwd=frontend):
            print("  npm install 成功。")
        else:
            print("  npm install 失败，可稍后手动在 src/frontend 下执行。")

    print("\n配置执行完毕。验收可运行: python scripts/run_m2_acceptance.py")
    print("（若需 MCP 监测浏览器，先设置 DOUYIN_REACH_CDP_PORT=9222 再运行验收脚本。）")


if __name__ == "__main__":
    main()
