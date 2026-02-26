# Douyin Reach（抖音助手）

按关键词检索抖音视频 → 提取评论与用户信息 → 规则筛选 → 私信触达。

## 文档

- [总览与索引](docs/00-总览与索引.md)
- [阶段 0 环境与文档](docs/01-阶段0-环境与文档.md)
- [阶段 1 GUI 原型与架构](docs/02-阶段1-GUI原型与架构设计.md)

## 环境要求

- **Python** 3.10～3.12（推荐；3.14 下部分依赖需编译）
- **Node.js** 18+（仅前端构建：npm + package.json）
- **Playwright** 浏览器：安装后执行 `playwright install chromium`
- **Windows**：桌面壳依赖 pywebview，需安装 [Microsoft C++ 生成工具](https://visualstudio.microsoft.com/visual-cpp-build-tools/) 以编译 pythonnet；或仅用「前端开发模式」在浏览器中开发界面（见下）。

## 安装与运行

### 0. 一键配置（推荐）

在项目根目录执行，自动创建 venv、安装后端依赖、安装 Playwright Chromium、创建 data/logs、前端 npm install：

```bash
python scripts/setup_env.py
```

若完整 `pip install -r requirements.txt` 失败（如 Windows 编码或 pywebview 编译问题），脚本会自动改为只装 `playwright` 与 `python-dotenv`。

### 1. 后端（手动）

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

若在 Windows 上安装 pywebview 失败，可先只装：`pip install playwright python-dotenv`，桌面壳稍后补装；或使用「前端开发模式」在浏览器中打开界面。

### 2. 前端（开发时）

```bash
cd src/frontend
npm install
npm run dev
```

### 3. 启动桌面应用

**开发模式**（前端已执行 `npm run dev` 时）：

```bash
set DOUYIN_REACH_DEV=1
python main.py
```

主窗口将加载 http://localhost:5173，并暴露 `window.pywebview.api` 供前端调用。

**仅前端、无桌面壳**（未安装 pywebview 或 pythonnet 时）：  
在浏览器中打开 http://localhost:5173。此时 API 不可用，仅用于界面开发与联调。

**生产模式**（先构建再启动）：

```bash
cd src/frontend && npm run build && cd ../..
python main.py
```

主窗口将加载本地 `dist/index.html`。

## 技术栈

- 桌面 GUI：pywebview + Vue 3
- 浏览器自动化：Playwright（抖音 PC 网页版）
- 存储：SQLite
- 筛选：关键词/正则（MVP）；后续可选云端 AI

## 仓库

GitHub: https://github.com/CamarilloG/douyin-reach
