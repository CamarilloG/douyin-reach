# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 - 单文件 exe (--onefile),方案 C: 完全走 CDP 接管系统 Chrome。

用法:
    pyinstaller douyin_reach.spec --clean

产物:
    dist/抖音助手-v{VERSION}.exe   (单文件)

运行时数据:
    exe 同目录的 ./data/    (首次启动自动创建)
    包括 SQLite 库、settings.json、抖音登录态、Chrome 自动化 profile
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

# 从单一来源读版本号 (src/backend/version.py)
sys.path.insert(0, os.path.abspath('.'))
from src.backend.version import VERSION, APP_NAME  # noqa: E402

block_cipher = None

# Playwright 需要把 driver(node 子进程 + js)整体收集进来,
# 否则 from playwright.async_api import ... 会失败。
# Chromium 二进制不需要(我们走 CDP 接管系统 Chrome)。
playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all('playwright')

# 过滤掉 playwright 内置的 .local-browsers(chromium/firefox/webkit),减少体积
playwright_datas = [
    (src, dst) for (src, dst) in playwright_datas
    if '.local-browsers' not in src.replace('\\', '/')
]

# webview 需要把它的 JS 注入脚本一起带上
webview_datas = collect_data_files('webview')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=playwright_binaries,
    datas=[
        # 前端构建产物 → _MEIPASS/frontend_dist/
        ('src/frontend/dist', 'frontend_dist'),
        # 应用图标 → _MEIPASS/5oj5n-gaprv-001.ico (供 pywebview 运行时加载)
        ('5oj5n-gaprv-001.ico', '.'),
    ] + playwright_datas + webview_datas,
    hiddenimports=[
        'webview.platforms.winforms',
        'clr_loader',
        'pythonnet',
    ] + playwright_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'scipy',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'{APP_NAME}-v{VERSION}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # 隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='5oj5n-gaprv-001.ico',
)
