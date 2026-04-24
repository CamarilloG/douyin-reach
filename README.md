# Douyin Reach（抖音助手）

按关键词检索抖音视频 → 提取评论与用户信息 → 规则筛选 → 私信触达。

## ⚠️ 重要提示

**如果遇到 HTTP 502 错误**，请设置环境变量：
```bash
# Windows
set NO_PROXY=localhost,127.0.0.1

# Linux/Mac
export NO_PROXY=localhost,127.0.0.1
```

或使用提供的启动脚本 `启动Web服务器.bat`（已自动配置）。

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

## 首次运行

### 方式1: CDP 远程调试模式（推荐）

**优势**: 浏览器窗口可见，可实时观察采集过程，方便调试和手动干预。

1. **完成安装**：执行 `python scripts/setup_env.py` 或按上文手动安装。
2. **启动调试浏览器**：双击运行 `启动调试浏览器.bat`
3. **登录抖音**：在打开的浏览器中扫码登录抖音
4. **启动应用**：运行 `python main.py` 或 `start.bat`
5. **创建任务**：在「任务管理」中创建任务，配置关键词、规则、私信模板
6. **开始采集**：启动采集，可在浏览器窗口中实时观察

### 方式2: 自动启动模式（传统）

1. **完成安装**：执行 `python scripts/setup_env.py` 或按上文手动安装。
2. **启动应用**：`cd src/frontend && npm run build && cd ../.. && python main.py`
3. **登录抖音**：进入「系统设置」页，点击「打开登录浏览器」，用抖音扫码完成登录。Cookie 将保存至 `data/douyin_storage_state.json`，重启后自动登录。
4. **创建任务**：在「任务管理」中创建任务，配置关键词（如「测试」）、规则、私信模板。
5. **采集 → 筛选 → 发送**：启动采集 → 完成后执行筛选 → 在「名单审核」中勾选用户 → 确认发送。

## 配置项

| 环境变量 | 说明 |
|----------|------|
| `DOUYIN_REACH_DEV=1` | 开发模式，加载 http://localhost:5173（需先 `npm run dev`） |
| `DOUYIN_REACH_MOCK=1` | 使用 Mock 后端（无真实采集/发送） |
| `DOUYIN_CDP_URL=http://localhost:9222` | CDP 连接地址（远程调试模式） |
| `DOUYIN_REACH_CDP_PORT=9222` | 自动启动模式下的 CDP 端口 |

**应用内配置**（系统设置）：`data/settings.json` 保存发送间隔、日/任务上限、风控参数、AI 相关预留字段。

## 常见问题

| 问题 | 处理 |
|------|------|
| 桌面窗口无法启动 | Windows 需安装 [Microsoft C++ 生成工具](https://visualstudio.microsoft.com/visual-cpp-build-tools/) 以编译 pywebview 依赖；或使用 `pip install playwright python-dotenv` 先装核心依赖 |
| 创建任务无响应 | 若用 Mock，确认 `DOUYIN_REACH_MOCK=1`；若用 Real，检查前端 bridge 是否获取到 api（开发模式下需先 `npm run dev` 再启动 main.py） |
| 采集/发送提示未登录 | 在系统设置中打开登录浏览器，完成抖音扫码 |
| 导出 CSV 保存对话框未弹出 | 在 pywebview 环境下会弹出；脚本/无窗口模式下需传入保存路径 |

## 免责与合规

使用本工具请遵守抖音平台规则及当地法律法规。滥用可能导致账号限流或封禁，风险由使用者自行承担。

## 技术栈

- 桌面 GUI：pywebview + Vue 3
- 浏览器自动化：Playwright（抖音 PC 网页版）
- 存储：SQLite
- 筛选：关键词/正则（MVP）；后续可选云端 AI

## 仓库

GitHub: https://github.com/CamarilloG/douyin-reach
