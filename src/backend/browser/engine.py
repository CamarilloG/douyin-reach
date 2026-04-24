from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Optional
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from . import selectors as sel
from .risk import RiskConfig, RiskLevel, RiskState

logger = logging.getLogger(__name__)

from src.backend.utils.paths import get_data_path

_DEFAULT_STORAGE_PATH = get_data_path("douyin_storage_state.json")
_DEBUG_LOG_PATH = get_data_path("debug-a4e257.log")


def _debug_log(location: str, message: str, data: dict[str, Any], hypothesis_id: str) -> None:
    try:
        payload = {
            "sessionId": "a4e257",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _is_browser_closed_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "closed" in msg or "connection" in msg or "target page" in msg


def _is_technical_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    markers = (
        "connection closed",
        "socket.send",
        "target closed",
        "target page",
        "browser has been disconnected",
        "context has been destroyed",
        "timeout",
        "timed out",
        "net::err_",
        "page.goto",
    )
    return any(marker in msg for marker in markers)


def _detect_windows_default_browser() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id = str(winreg.QueryValueEx(key, "ProgId")[0]).lower()
    except Exception:
        return None

    if "chrome" in prog_id:
        return "chrome"
    if "edge" in prog_id or "mse" in prog_id:
        return "edge"
    return None


def _candidate_browser_paths(preferred: str | None = None) -> list[tuple[str, str]]:
    candidates = {
        "chrome": [
            os.path.join(os.getenv("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
        ],
        "edge": [
            os.path.join(os.getenv("PROGRAMFILES", r"C:\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
            shutil.which("msedge"),
            shutil.which("msedge.exe"),
        ],
    }

    order: list[str] = []
    if preferred in ("chrome", "edge"):
        order.append(preferred)
    for name in ("chrome", "edge"):
        if name not in order:
            order.append(name)

    seen: set[str] = set()
    resolved: list[tuple[str, str]] = []
    for name in order:
        for path in candidates[name]:
            if not path:
                continue
            norm = os.path.normcase(os.path.abspath(path))
            if norm in seen:
                continue
            seen.add(norm)
            resolved.append((name, path))
    return resolved


def _find_system_browser_path() -> tuple[str, str]:
    explicit_path = os.getenv("DOUYIN_BROWSER_PATH")
    if explicit_path:
        explicit_path = os.path.abspath(explicit_path)
        if os.path.isfile(explicit_path):
            browser_name = "edge" if "msedge" in os.path.basename(explicit_path).lower() else "chrome"
            return browser_name, explicit_path
        raise RuntimeError(f"DOUYIN_BROWSER_PATH does not exist: {explicit_path}")

    preferred = os.getenv("DOUYIN_BROWSER_PREFERENCE", "").strip().lower() or _detect_windows_default_browser()
    for name, path in _candidate_browser_paths(preferred):
        if os.path.isfile(path):
            return name, path

    raise RuntimeError(
        "No supported system browser was found. Install Google Chrome or Microsoft Edge, "
        "or set DOUYIN_BROWSER_PATH to the browser executable."
    )


class BrowserEngine:
    def __init__(
        self,
        *,
        headless: bool = False,
        storage_path: str | None = None,
        risk_config: RiskConfig | None = None,
        browser_log_path: str | None = None,
        cdp_url: str | None = None,
        use_new_page: bool = False,
    ) -> None:
        self._headless = headless
        self._storage_path = storage_path or _DEFAULT_STORAGE_PATH
        self._risk_config = risk_config or RiskConfig()
        self._browser_log_path = browser_log_path
        self._risk_state = RiskState(self._risk_config)
        self._cdp_url = cdp_url or os.getenv("DOUYIN_CDP_URL", "http://localhost:9222")
        self._use_new_page = use_new_page
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._creator_page: Page | None = None
        self._browser_process: subprocess.Popen | None = None
        self._owns_browser_process = False
        self._consecutive_not_found = 0

    async def _connect_to_existing_cdp(self) -> bool:
        try:
            logger.info("尝试连接 CDP: %s", self._cdp_url)
            self._browser = await self._playwright.chromium.connect_over_cdp(self._cdp_url)
            logger.info("已连接到现有浏览器实例")
            return True
        except Exception as e:
            logger.warning("连接 CDP 失败: %s", e)
            return False

    async def _attach_connected_browser(self) -> None:
        assert self._browser is not None
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
            if self._use_new_page:
                # 独立标签页模式：始终新开 tab，不抢占已有页面
                self._page = await self._context.new_page()
            else:
                pages = self._context.pages
                self._page = pages[0] if pages else await self._context.new_page()
            return

        opts: dict[str, Any] = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
        }
        if os.path.isfile(self._storage_path):
            opts["storage_state"] = self._storage_path
        self._context = await self._browser.new_context(**opts)
        self._page = await self._context.new_page()

    async def _launch_system_browser_via_cdp(self, headless: bool) -> None:
        browser_name, browser_path = _find_system_browser_path()
        cdp_port = os.getenv("DOUYIN_REACH_CDP_PORT", "9222")
        profile_dir = get_data_path(f"{browser_name}_automation_profile")
        os.makedirs(profile_dir, exist_ok=True)

        args = [
            browser_path,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            sel.BASE_URL,
        ]
        if browser_name == "edge":
            args.append("--disable-features=msEdgeSidebarV2")
        if headless:
            args.append("--headless=new")

        logger.info("启动系统浏览器: %s (%s)", browser_name, browser_path)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0
        self._browser_process = subprocess.Popen(args, creationflags=creationflags)
        self._owns_browser_process = True

        deadline = time.time() + 20
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(self._cdp_url)
                logger.info("已连接到新启动的 %s 浏览器", browser_name)
                return
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.5)

        raise RuntimeError(f"Unable to connect to the launched system browser over CDP: {last_error}")

    async def launch(self, headless: bool | None = None) -> None:
        if self._browser:
            return

        self._playwright = await async_playwright().start()
        use_headless = headless if headless is not None else self._headless

        if not await self._connect_to_existing_cdp():
            await self._launch_system_browser_via_cdp(use_headless)

        await self._attach_connected_browser()
        if self._browser_log_path:
            self._attach_browser_log_listeners()
        if self._page and not self._page.url.startswith("https://www.douyin.com"):
            await self._page.goto(sel.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await self._risk_state.delay_page()
        await self._dismiss_newbie_guide()
        await self._check_danger_texts()

    def _attach_browser_log_listeners(self) -> None:
        if not self._page or not self._browser_log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._browser_log_path)) or ".", exist_ok=True)
        except Exception:
            pass
        log_path = self._browser_log_path

        def _write(kind: str, text: str) -> None:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] [{kind}] {text}\n")
            except Exception:
                pass

        self._page.on("console", lambda msg: _write("console", f"{msg.type}: {msg.text}"))
        self._page.on("pageerror", lambda err: _write("pageerror", str(err)))
        self._page.on("requestfailed", lambda req: _write("requestfailed", f"{req.url} {req.failure}"))
        _write("sys", "browser log listeners attached")

    async def _dismiss_newbie_guide(self) -> None:
        if not self._page:
            return
        try:
            btn = self._page.get_by_text(sel.NEWBIE_GUIDE_DISMISS_TEXT, exact=True).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(timeout=3000)
                await self._risk_state.delay_normal()
        except Exception as e:
            logger.debug("关闭新手引导失败: %s", e)

    async def _check_danger_texts(self) -> None:
        if not self._page:
            return
        try:
            # 取页面文本时必须排除 UGC 区域(评论列表/视频描述/私信会话/搜索结果卡片),
            # 否则用户评论里出现 "验证码"/"账号异常" 等中文常用词会被误判为风控文案。
            # 2026-04-10 实测: 任务 75 因评论里 "我这样验证码都得看好几遍" 被误触发 DANGER。
            visible_text = await self._page.evaluate(
                """
                () => {
                  const body = document.body;
                  if (!body) return "";
                  // clone 避免破坏真实 DOM
                  const clone = body.cloneNode(true);
                  const ugcSelectors = [
                    '[data-e2e="comment-list"]',
                    '[data-e2e="comment-item"]',
                    '.comment-mainContent',
                    '[data-e2e="video-desc"]',
                    '[data-e2e="modal-video-container"] [data-e2e="video-desc"]',
                    '[data-e2e="im-dialog"]',
                    '.public-DraftEditor-content',
                    '.search-result-card',
                  ];
                  for (const sel of ugcSelectors) {
                    for (const el of clone.querySelectorAll(sel)) {
                      el.remove();
                    }
                  }
                  return clone.innerText || "";
                }
                """
            )
            for text in getattr(sel, "DANGER_PAGE_TEXTS", ()):
                if text and text in visible_text:
                    idx = visible_text.find(text)
                    snippet = visible_text[max(0, idx - 60): idx + 120]
                    self._risk_state.trigger_danger(f"页面出现危险文案: {text} | snippet={snippet}")
                    return
            for selector in getattr(sel, "CAPTCHA_DOM_SELECTORS", ()):
                locator = self._page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    snippet = ""
                    try:
                        snippet = ((await locator.text_content()) or "")[:120]
                    except Exception:
                        pass
                    self._risk_state.trigger_danger(f"检测到验证码浮层: {selector} | text={snippet}")
                    return
        except Exception as e:
            logger.debug("检测危险状态失败: %s", e)

    async def check_page_danger(self) -> None:
        await self._check_danger_texts()

    async def dismiss_newbie_guide(self) -> None:
        await self._dismiss_newbie_guide()

    async def _check_login_required(self) -> bool:
        """
        运行中的登录态检查：仅依赖 DOM 信号（登录浮层 / 浮层文案）。

        不再调用 session API — API 返回的 JSON 结构存在多种变体，容易误报未登录；
        启动阶段的 check_session() 已对 session 做过权威校验，运行中只要 DOM 上
        没有登录浮层，就认为仍处于登录态。
        """
        if not self._page:
            return False
        try:
            login_panel = self._page.locator(getattr(sel, "LOGIN_PANEL_SELECTOR", '[id^="login-full-panel"]')).first
            if await login_panel.count() > 0 and await login_panel.is_visible():
                self._risk_state.trigger_danger("检测到登录浮层: login-full-panel")
                return True
            visible_text = await self._page.evaluate(
                """
                () => {
                  const body = document.body;
                  return body ? (body.innerText || "") : "";
                }
                """
            )
            for text in getattr(sel, "LOGIN_OVERLAY_TEXTS", ()):
                if text and text in visible_text:
                    self._risk_state.trigger_danger(f"检测到登录浮层文案: {text}")
                    return True
        except Exception as e:
            logger.debug("检测登录状态失败: %s", e)
        return False

    def _on_element_not_found(self, selector_desc: str) -> bool:
        self._consecutive_not_found += 1
        if self._consecutive_not_found >= 3:
            self._risk_state.trigger_warning(f"连续元素未找到: {selector_desc}")
            self._consecutive_not_found = 0
        return self._risk_state.level == RiskLevel.DANGER

    def _on_element_found(self) -> None:
        self._consecutive_not_found = 0

    async def check_session(self) -> bool:
        if self._context:
            try:
                if await self._check_session_no_navigate():
                    return True
            except Exception as e:
                logger.debug("session API 校验异常: %s", e)
        if not self._page:
            return False
        try:
            content = await self._page.content()
            if "私信" in content or "退出登录" in content:
                return True
        except Exception:
            pass
        return False

    async def _check_session_no_navigate(self) -> bool:
        """
        登录态校验（不跳转页面）。

        2026-04 调整：user/settings 返回体已不再含 user/user_id 字段，统一结构为
          登录：{"landing_reason":"user_landing_recommend_default","status_code":0}
          未登录：{"set_info":"...","landing_reason":"user_setting_landing_channel","extra":{...},"status_code":0}
        因此以 cookie 为主信号 + API 响应特征为辅验证。
        """
        if not self._context:
            return False
        try:
            cookies = await self._context.cookies()
        except Exception as e:
            _debug_log("engine.py:_check_session_no_navigate", "cookies fetch error", {"error": str(e)}, "H1")
            cookies = []
        cookie_map = {c.get("name"): (c.get("value") or "") for c in cookies if isinstance(c, dict)}
        has_auth_cookie = any(cookie_map.get(name) for name in ("sessionid", "sid_tt", "sid_guard"))

        api_status = None
        api_keys: list[str] = []
        looks_logged_in = False
        try:
            resp = await self._context.request.get(sel.USER_SETTINGS_API, timeout=15000)
            api_status = resp.status
            if resp.status == 200:
                body = await resp.json()
                if isinstance(body, dict):
                    api_keys = list(body.keys())
                    # 兼容旧格式
                    if body.get("user") is not None or body.get("user_id") is not None:
                        looks_logged_in = True
                    elif isinstance(body.get("data"), dict) and body["data"].get("user") is not None:
                        looks_logged_in = True
                    else:
                        # 新格式特征：未登录响应有 set_info / extra；登录响应只有 landing_reason + status_code
                        is_logged_out_shape = "set_info" in body or "extra" in body
                        looks_logged_in = not is_logged_out_shape
        except Exception as e:
            _debug_log("engine.py:_check_session_no_navigate", "api call exception", {"error": str(e)}, "H1")

        # 判定：有 auth cookie + API 不是明显未登录形态 → 视为登录
        result = bool(has_auth_cookie) and (api_status != 200 or looks_logged_in)
        # 或：没 cookie 但 API 明确返回 user 字段的老格式 → 也信
        if not result and looks_logged_in and api_status == 200 and (
            "user" in api_keys or "user_id" in api_keys
        ):
            result = True
        _debug_log(
            "engine.py:_check_session_no_navigate",
            "session check result",
            {
                "status": api_status,
                "result": result,
                "has_auth_cookie": has_auth_cookie,
                "looks_logged_in": looks_logged_in,
                "keys": api_keys,
            },
            "H2",
        )
        return result

    async def login(self) -> bool:
        if not self._page:
            return False
        try:
            await self._page.goto(sel.BASE_URL, wait_until="domcontentloaded", timeout=15000)
            await self._risk_state.delay_page()
            login_panel = self._page.locator(getattr(sel, "LOGIN_PANEL_SELECTOR", '[id^="login-full-panel"]')).first
            try:
                await login_panel.wait_for(state="attached", timeout=5000)
            except Exception:
                pass
            if await login_panel.count() == 0:
                logout_btn = self._page.get_by_text("退出登录", exact=False).first
                if await logout_btn.count() > 0 and await logout_btn.is_visible():
                    return True
                login_btn = self._page.get_by_text("登录", exact=True).first
                if await login_btn.count() > 0:
                    await login_btn.click(timeout=5000)
            await self._risk_state.delay_page()
            for _ in range(120):
                if await self._check_session_no_navigate():
                    await self._save_storage_state()
                    self._risk_state.reset_to_normal()
                    return True
                await asyncio.sleep(1)
            logger.warning("登录超时")
            return False
        except Exception as e:
            logger.exception("登录流程异常: %s", e)
            return False

    async def _save_storage_state(self) -> None:
        if not self._context:
            return
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            await self._context.storage_state(path=self._storage_path)
            logger.info("已保存会话: %s", self._storage_path)
        except Exception as e:
            if _is_browser_closed_error(e):
                logger.debug("浏览器已关闭，跳过保存会话")
            else:
                logger.exception("保存会话失败: %s", e)

    async def _click_search_tab_video(self) -> None:
        if not self._page:
            return
        try:
            tab = self._page.locator(f'span[data-key="{sel.SEARCH_TAB_VIDEO_DATA_KEY}"]').first
            if await tab.count() > 0:
                await tab.click(timeout=5000)
                await self._risk_state.delay_page()
                return
            by_text = self._page.get_by_text(sel.SEARCH_TAB_VIDEO, exact=True).first
            if await by_text.count() > 0:
                await by_text.click(timeout=5000)
                await self._risk_state.delay_page()
        except Exception as e:
            logger.debug("点击视频 Tab 失败: %s", e)

    # 任务字段值 → 抖音筛选面板里的中文文案
    # 注意：每个分组里都有一个"不限/综合排序"是默认项，无需点击
    _FILTER_TEXT_MAP: dict[str, dict[str, str]] = {
        "sort_mode": {
            "general": "综合排序",
            "most_like": "最多点赞",
            "latest": "最新发布",
        },
        "publish_time": {
            "unlimited": "不限",
            "day": "一天内",
            "week": "一周内",
            "half_year": "半年内",
            "custom": "自定义",
        },
        "video_duration": {
            "unlimited": "不限",
            "lt1m": "1分钟以下",
            "1to5m": "1-5分钟",
            "gt5m": "5分钟以上",
        },
        "search_scope": {
            "unlimited": "不限",
            "following": "关注的人",
            "viewed": "最近看过",
            "not_viewed": "还未看过",
        },
        "content_form": {
            "unlimited": "不限",
            "video": "视频",
            "image_text": "图文",
        },
    }
    # 这些值视为"默认项",不需要点击
    _FILTER_DEFAULT_VALUES: set[str] = {"general", "unlimited", "", "all"}

    async def _apply_search_filters_via_dom(self, task_config: dict[str, Any]) -> None:
        """通过 DOM 点击搜索结果页右上角的筛选面板,把任务里配置的筛选项落到页面上。

        背景: 抖音 PC 网页版的筛选实际不修改 URL,前端通过 JS 直接走 API,
        因此 build_search_url 仅作为首屏提示。要保证筛选生效必须再做一次 DOM 点击。

        触发陷阱(2026-04 调研): 普通 click() 会被吞,必须用 dispatchEvent。
        """
        if not self._page:
            return

        wanted: list[str] = []
        for field, mapping in self._FILTER_TEXT_MAP.items():
            raw = task_config.get(field)
            if raw is None:
                continue
            val = str(raw).strip()
            if not val or val in self._FILTER_DEFAULT_VALUES:
                continue
            text = mapping.get(val)
            if not text:
                logger.debug("筛选字段 %s 取值 %s 未在映射表中,跳过", field, val)
                continue
            if val == "custom":
                # 自定义日期目前未支持 DOM 选择(日期选择器结构未调研)
                logger.warning("publish_time=custom 暂不支持通过 DOM 应用,跳过")
                continue
            wanted.append(text)

        if not wanted:
            return

        try:
            # 一次 evaluate 完成: 打开面板 → 点选项 → 关闭面板
            result = await self._page.evaluate(
                """
                async (wantedTexts) => {
                    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                    const fire = (el) => el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));

                    // 1. 找筛选按钮 (span.QfeM8ow3 文本为"筛选")
                    let btn = null;
                    const candidates = document.querySelectorAll('span.QfeM8ow3, div.jjU9T0dQ span');
                    for (const c of candidates) {
                        if ((c.textContent || '').trim() === '筛选') { btn = c; break; }
                    }
                    if (!btn) {
                        // 兜底: 全页面找文本"筛选"的 span
                        for (const c of document.querySelectorAll('span')) {
                            if ((c.textContent || '').trim() === '筛选' && c.offsetWidth > 0) { btn = c; break; }
                        }
                    }
                    if (!btn) return { ok: false, reason: 'filter_button_not_found' };

                    fire(btn);

                    // 2. 等面板出现
                    let panel = null;
                    for (let i = 0; i < 20; i++) {
                        await sleep(100);
                        panel = document.querySelector('div.AZGfZJ4J');
                        if (panel) break;
                    }
                    if (!panel) {
                        // 兜底: 找包含选项 span.eXMmo3JR 的容器
                        const opt = document.querySelector('span.eXMmo3JR');
                        if (opt) {
                            panel = opt.closest('div.AZGfZJ4J') || opt.parentElement?.parentElement?.parentElement;
                        }
                    }
                    if (!panel) return { ok: false, reason: 'panel_not_found' };

                    // 3. 收集所有 (groupLabel, optionSpan) 对
                    const allOptions = panel.querySelectorAll('span.eXMmo3JR');
                    const matched = [];
                    const notFound = [];
                    for (const text of wantedTexts) {
                        let hit = null;
                        for (const opt of allOptions) {
                            if ((opt.textContent || '').trim() === text) { hit = opt; break; }
                        }
                        if (hit) {
                            // 已选中就跳过
                            if (!hit.classList.contains('sDNqBVWH')) {
                                fire(hit);
                                matched.push(text);
                                await sleep(150);
                            } else {
                                matched.push(text + '(already)');
                            }
                        } else {
                            notFound.push(text);
                        }
                    }

                    await sleep(200);
                    // 4. 关闭面板: 再次点击筛选按钮
                    try { fire(btn); } catch(e) {}
                    await sleep(200);

                    return { ok: true, applied: matched, missing: notFound };
                }
                """,
                wanted,
            )
        except Exception as e:
            logger.warning("调用筛选面板 evaluate 失败: %s", e)
            return

        if isinstance(result, dict):
            if result.get("ok"):
                logger.info(
                    "已通过 DOM 应用筛选: applied=%s missing=%s",
                    result.get("applied"),
                    result.get("missing"),
                )
            else:
                logger.warning("DOM 筛选未生效: %s", result.get("reason"))
        # 给页面一点时间加载新结果
        await self._risk_state.delay_page()

    async def search_via_homepage(
        self, keyword: str, task_config: dict[str, Any] | None = None
    ) -> bool:
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return False
        if await self._check_login_required():
            return False
        if task_config:
            # 默认走综合 tab（首屏更稳，后续 _click_search_tab_video 切到视频 tab）；
            # filter_duration / search_scope / content_form 在综合 tab 下不通过 URL 生效，
            # 需要后续通过 DOM 面板点击补齐。
            url = sel.build_search_url(
                keyword,
                sort_mode=task_config.get("sort_mode", "general") or "general",
                publish_time=task_config.get("publish_time", "unlimited") or "unlimited",
                publish_time_start=task_config.get("publish_time_start"),
                publish_time_end=task_config.get("publish_time_end"),
                video_duration=task_config.get("video_duration", "unlimited") or "unlimited",
                search_scope=task_config.get("search_scope", "unlimited") or "unlimited",
                content_form=task_config.get("content_form", "unlimited") or "unlimited",
                tab="general",
            )
        else:
            url = sel.SEARCH_URL_TEMPLATE.format(keyword=quote(keyword))
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await self._risk_state.delay_page()
            await self._dismiss_newbie_guide()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER:
                return False
            await self._click_search_tab_video()
            await self._page.wait_for_selector('a[href*="/video/"]', timeout=15000, state="attached")
            if task_config:
                try:
                    await self._apply_search_filters_via_dom(task_config)
                except Exception as e:
                    logger.warning("DOM 应用筛选条件失败: %s", e)
            return True
        except Exception as e:
            logger.warning("进入搜索结果页失败: %s", e)
            return False

    async def get_visible_video_cards(self) -> list[dict[str, Any]]:
        if not self._page:
            return []
        try:
            # 陷阱：搜索结果卡片里一个 aweme_id 通常对应两个 <a href="/video/xxx">：
            #   1) 第一个是图片/封面链接，text_content 为空
            #   2) 第二个是标题链接，text_content 就是视频标题
            # 之前的实现按 aweme_id 去重只保留第一个 link，导致 title 永远为空。
            # 新实现：收集所有 video 链接，按 aweme_id 合并，取其中任一非空 text 作为 title。
            items = await self._page.evaluate(
                """
                () => {
                    const results = {};
                    const links = document.querySelectorAll('a[href*="/video/"]');
                    for (const a of links) {
                        const m = (a.getAttribute('href') || '').match(/\\/video\\/([A-Za-z0-9]+)/);
                        if (!m) continue;
                        const id = m[1];
                        if (!results[id]) {
                            results[id] = { aweme_id: id, title: '', author_nickname: '', author_sec_uid: '' };
                        }
                        const txt = (a.innerText || a.textContent || '').trim();
                        if (txt && !results[id].title) {
                            results[id].title = txt;
                        }
                        // title 属性 / aria-label 兜底
                        if (!results[id].title) {
                            const t = a.getAttribute('title') || a.getAttribute('aria-label') || '';
                            if (t.trim()) results[id].title = t.trim();
                        }
                        // 顺便找同一个祖先卡片内的作者
                        if (!results[id].author_sec_uid) {
                            let card = a.closest('li') || a.closest('[class*="card"]') || a.parentElement;
                            for (let i = 0; i < 5 && card; i++) {
                                const ua = card.querySelector && card.querySelector('a[href*="/user/"]');
                                if (ua) {
                                    const um = (ua.getAttribute('href') || '').match(/\\/user\\/([A-Za-z0-9_-]+)/);
                                    if (um) results[id].author_sec_uid = um[1];
                                    const name = (ua.innerText || ua.textContent || '').replace(/@/g, '').trim();
                                    if (name) results[id].author_nickname = name;
                                    break;
                                }
                                card = card.parentElement;
                            }
                        }
                    }
                    return Object.values(results);
                }
                """
            )
        except Exception as e:
            logger.debug("读取可见视频卡片失败: %s", e)
            return []

        videos: list[dict[str, Any]] = []
        for it in items or []:
            aweme_id = (it.get("aweme_id") or "").strip()
            if not aweme_id:
                continue
            title = (it.get("title") or "").strip()
            videos.append(
                {
                    "aweme_id": aweme_id,
                    "title": title or None,
                    "author_nickname": (it.get("author_nickname") or "").strip() or None,
                    "author_sec_uid": (it.get("author_sec_uid") or "").strip() or None,
                    "like_count_text": None,
                    "video_url": sel.VIDEO_URL_TEMPLATE.format(aweme_id=aweme_id),
                }
            )
        return videos

    async def scroll_search_results_to_load_more(self) -> None:
        if not self._page:
            return
        await self._page.evaluate("window.scrollBy(0, window.innerHeight)")
        await self._risk_state.delay_normal()

    async def search_videos(
        self, keyword: str, max_count: int, task_config: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not await self.search_via_homepage(keyword, task_config=task_config):
            return []
        videos: list[dict[str, Any]] = []
        seen_aweme: set[str] = set()
        scroll_attempts = 0
        while len(videos) < max_count and scroll_attempts < 20:
            current = await self.get_visible_video_cards()
            for video in current:
                aweme_id = video.get("aweme_id") or ""
                if not aweme_id or aweme_id in seen_aweme:
                    continue
                seen_aweme.add(aweme_id)
                videos.append(video)
                if len(videos) >= max_count:
                    break
            if len(videos) >= max_count:
                break
            await self.scroll_search_results_to_load_more()
            scroll_attempts += 1
        return videos[:max_count]

    async def click_video_card_and_enter(self, aweme_id: str) -> bool:
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return False
        try:
            await self._page.goto(sel.VIDEO_URL_TEMPLATE.format(aweme_id=aweme_id), wait_until="domcontentloaded", timeout=20000)
            await self._risk_state.delay_page()
            await self._dismiss_newbie_guide()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER or await self._check_login_required():
                return False
            await self._page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self._risk_state.delay_normal()
            return "/video/" in self._page.url
        except Exception as e:
            logger.debug("进入视频详情失败: %s", e)
            if not _is_technical_error(e):
                self._risk_state.trigger_warning(f"进入视频详情失败: {e}")
            return False

    async def _scroll_comment_container(self) -> str:
        """滚动评论区到底部。返回状态: 'loading' / 'end' / 'has_more' / 'no_container'。

        根据调研:抖音视频页有两种模式
        - Modal 模式(搜索→点击进入):评论区 [data-e2e="comment-list"] 自身可滚动 (overflowY=scroll)
        - Standalone 模式(/video/{id}):评论区 overflowY=visible,实际滚动容器是 .route-scroll-container
        通过 computed style 自动判别,统一用 scrollTop = scrollHeight 触发懒加载。
        """
        if not self._page:
            return "no_container"
        try:
            return await self._page.evaluate(
                """
                () => {
                    const list = document.querySelector('[data-e2e="comment-list"]');
                    if (!list) return 'no_container';
                    const style = window.getComputedStyle(list);
                    const selfScroll = (style.overflowY === 'scroll' || style.overflowY === 'auto')
                                       && list.scrollHeight > list.clientHeight + 5;
                    let target = null;
                    if (selfScroll) {
                        target = list;
                    } else {
                        target = document.querySelector('.route-scroll-container')
                                || document.scrollingElement
                                || document.documentElement;
                    }
                    target.scrollTop = target.scrollHeight;
                    // 同时给 list 自己也试一下,容错
                    if (target !== list) {
                        try { list.scrollTop = list.scrollHeight; } catch(e){}
                    }
                    const last = list.lastElementChild;
                    if (!last) return 'has_more';
                    const txt = (last.textContent || '').trim();
                    if (txt.includes('暂时没有更多评论') || txt.includes('没有更多')) return 'end';
                    if (txt.includes('加载中')) return 'loading';
                    return 'has_more';
                }
                """
            )
        except Exception as e:
            if _is_browser_closed_error(e):
                return "no_container"
            logger.debug("滚动评论容器失败: %s", e)
            return "has_more"

    # JS:一次性把所有评论项的 sec_uid/nickname/text 提取出来,可选 offset 增量
    _COMMENTS_EXTRACT_JS = """
        (offset) => {
            const items = document.querySelectorAll('div[data-e2e="comment-item"]');
            const out = [];
            const start = Math.max(0, offset || 0);
            for (let i = start; i < items.length; i++) {
                const item = items[i];
                const link = item.querySelector('a[href*="/user/"]');
                if (!link) continue;
                const href = link.getAttribute('href') || '';
                const m = href.match(/\\/user\\/([A-Za-z0-9_-]+)/);
                if (!m) continue;
                const sec_uid = m[1];
                const nickname = (link.textContent || '').replace('@', '').trim();
                if (!nickname) continue;
                let text = (item.textContent || '').trim();
                if (text.indexOf(nickname) === 0) text = text.slice(nickname.length);
                text = text.replace(/^[\\s：:·,，]+/, '').replace(/\\s+/g, ' ').trim();
                if (!text || text === nickname || text.length > 500) continue;
                out.push({ sec_uid: sec_uid, nickname: nickname, text: text });
            }
            return { total: items.length, items: out };
        }
    """

    # JS:滚动后等待 item 数增长(快网早返回,慢网兜底超时)
    _COMMENTS_WAIT_JS = """
        async (prevCount) => {
            const start = Date.now();
            while (Date.now() - start < 1500) {
                const n = document.querySelectorAll('div[data-e2e="comment-item"]').length;
                if (n > prevCount) return n;
                await new Promise(r => setTimeout(r, 100));
            }
            return document.querySelectorAll('div[data-e2e="comment-item"]').length;
        }
    """

    async def _parse_comments_from_page(self, max_count: int) -> list[dict[str, Any]]:
        if not self._page:
            return []
        comments: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        processed_items = 0  # JS 端已扫描过的 item 数,增量解析的 offset
        prev_count = 0
        stale_rounds = 0
        scroll_attempts = 0
        max_scrolls = 40  # 配合单 evaluate 抓取,40 轮足够覆盖 ~500 条

        while len(comments) < max_count and scroll_attempts < max_scrolls:
            # 节流: 每 5 轮做一次危险文案检查; 入口已经做过一次
            if scroll_attempts > 0 and scroll_attempts % 5 == 0:
                await self._check_danger_texts()
                if self._risk_state.level == RiskLevel.DANGER:
                    break

            # 单次 evaluate 增量提取(只看 processed_items 之后的新 item)
            try:
                result = await self._page.evaluate(self._COMMENTS_EXTRACT_JS, processed_items)
            except Exception as e:
                if _is_browser_closed_error(e):
                    break
                logger.debug("批量解析评论失败: %s", e)
                result = {"total": processed_items, "items": []}

            new_items = result.get("items", []) if isinstance(result, dict) else []
            total_items = int(result.get("total", processed_items)) if isinstance(result, dict) else processed_items
            processed_items = total_items

            for row in new_items:
                if len(comments) >= max_count:
                    break
                sec_uid = row.get("sec_uid") or ""
                nickname = row.get("nickname") or ""
                text = row.get("text") or ""
                if not sec_uid or not nickname or not text:
                    continue
                key = (sec_uid, text)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                comments.append(
                    {
                        "cid": None,
                        "text": text,
                        "commenter_nickname": nickname,
                        "commenter_sec_uid": sec_uid,
                        "profile_url": sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid),
                        "like_count_text": None,
                        "create_time_text": None,
                    }
                )

            if len(comments) == prev_count:
                stale_rounds += 1
            else:
                stale_rounds = 0
                prev_count = len(comments)

            if len(comments) >= max_count:
                break

            status = await self._scroll_comment_container()
            scroll_attempts += 1

            if status == "no_container":
                break
            if status == "end":
                # 已到底,再做一次增量解析兜底然后退出
                try:
                    tail = await self._page.evaluate(self._COMMENTS_EXTRACT_JS, processed_items)
                    for row in (tail.get("items", []) if isinstance(tail, dict) else []):
                        sec_uid = row.get("sec_uid") or ""
                        nickname = row.get("nickname") or ""
                        text = row.get("text") or ""
                        if not sec_uid or not nickname or not text:
                            continue
                        key = (sec_uid, text)
                        if key in seen_keys or len(comments) >= max_count:
                            continue
                        seen_keys.add(key)
                        comments.append(
                            {
                                "cid": None,
                                "text": text,
                                "commenter_nickname": nickname,
                                "commenter_sec_uid": sec_uid,
                                "profile_url": sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid),
                                "like_count_text": None,
                                "create_time_text": None,
                            }
                        )
                except Exception as e:
                    logger.debug("末轮兜底解析失败: %s", e)
                break

            if status == "loading":
                # 还在加载, 用 page 级延迟兜底
                await self._risk_state.delay_page()
            else:
                # 等 item 数增长(早返回); 失败则降级到固定 action 延迟
                try:
                    await self._page.evaluate(self._COMMENTS_WAIT_JS, processed_items)
                except Exception:
                    await self._risk_state.delay_action()

            if stale_rounds >= 3:
                break

        return comments[:max_count]

    async def fetch_comments_on_current_page(self, max_count: int) -> list[dict[str, Any]]:
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return []
        if await self._check_login_required():
            return []
        try:
            await self._risk_state.delay_normal()
            await self._page.evaluate("window.scrollBy({top: 150, behavior: 'smooth'})")
            await self._risk_state.delay_normal()
            return await self._parse_comments_from_page(max_count)
        except Exception as e:
            if _is_browser_closed_error(e):
                return []
            logger.exception("当前页评论解析异常: %s", e)
            if not _is_technical_error(e):
                self._risk_state.trigger_warning(f"解析评论异常: {e}")
            return []

    async def fetch_comments(self, video_url: str, max_count: int) -> list[dict[str, Any]]:
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return []
        if await self._check_login_required():
            return []
        try:
            await self._page.goto(video_url, wait_until="domcontentloaded", timeout=20000)
            await self._risk_state.delay_page()
            await self._dismiss_newbie_guide()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER or await self._check_login_required():
                return []
            return await self.fetch_comments_on_current_page(max_count)
        except Exception as e:
            logger.exception("抓取评论异常: %s", e)
            if not _is_technical_error(e):
                self._risk_state.trigger_warning(f"抓取评论异常: {e}")
            return []

    async def navigate_back(self) -> bool:
        if not self._page:
            return False
        try:
            await self._page.go_back(wait_until="domcontentloaded", timeout=15000)
            await self._risk_state.delay_normal()
            return True
        except Exception as e:
            logger.debug("返回上一页失败: %s", e)
            return False

    async def fetch_user_info(self, sec_uid: str) -> dict[str, Any]:
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return {}
        if await self._check_login_required():
            return {}
        url = sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await self._risk_state.delay_page()
            await self._dismiss_newbie_guide()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER or await self._check_login_required():
                return {}
            info: dict[str, Any] = {
                "sec_uid": sec_uid,
                "profile_url": url,
                "nickname": None,
                "fans_count": None,
                "following_count": None,
                "description": None,
                "verified": None,
            }
            try:
                heading = self._page.get_by_role("heading", level=1).first
                if await heading.count() > 0:
                    info["nickname"] = (await heading.text_content()) or ""
            except Exception:
                pass
            return info
        except Exception as e:
            logger.warning("抓取用户信息异常: %s", e)
            return {}

    async def ensure_creator_tab(self) -> Page:
        """确保创作者中心 chat 页面已打开；首次调用时新建 tab，后续复用。

        加载失败时**不缓存**空白 page，并向上抛出异常 —— 让 send_pipeline 能明确
        识别并中止，而不是在空白页上继续做后续操作。
        """
        if self._creator_page and not self._creator_page.is_closed():
            return self._creator_page
        if not self._context:
            raise RuntimeError("BrowserContext 未就绪，无法打开创作者中心 tab")
        page = await self._context.new_page()
        try:
            await page.goto(sel.CREATOR_CHAT_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            logger.warning("创作者中心 chat 页加载失败: %s", e)
            try:
                await page.close()
            except Exception:
                pass
            raise RuntimeError(f"创作者中心 chat 页加载失败: {e}") from e
        self._creator_page = page
        return page

    async def close_creator_tab(self) -> None:
        if self._creator_page and not self._creator_page.is_closed():
            try:
                await self._creator_page.close()
            except Exception as e:
                if not _is_browser_closed_error(e):
                    logger.warning("关闭创作者中心 tab 失败: %s", e)
        self._creator_page = None

    def get_risk_level(self) -> RiskLevel:
        return self._risk_state.level

    def get_last_risk_reason(self) -> str:
        return self._risk_state.last_reason

    def set_risk_callbacks(
        self,
        on_warning: Optional[Callable[[str], None]] = None,
        on_danger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._risk_state.set_callbacks(on_warning=on_warning, on_danger=on_danger)

    async def close(self, keep_browser_open: bool = False) -> None:
        if self._context:
            await self._save_storage_state()
        if keep_browser_open:
            logger.info("已保存会话，保持浏览器打开供用户继续处理")
            return
        # 独立标签页模式：只关闭自己开的 tab，不关浏览器/context
        if self._use_new_page:
            await self.close_creator_tab()
            if self._page:
                try:
                    await self._page.close()
                except Exception as e:
                    if not _is_browser_closed_error(e):
                        logger.warning("关闭标签页失败: %s", e)
                self._page = None
            # 断开 Playwright CDP 连接（不终止浏览器进程）
            try:
                if self._playwright:
                    await self._playwright.stop()
            except Exception as e:
                if not _is_browser_closed_error(e):
                    logger.warning("停止 Playwright 失败: %s", e)
            self._playwright = None
            self._browser = None
            self._context = None
            logger.info("标签页已关闭（浏览器保持运行）")
            return
        await self.close_creator_tab()
        try:
            if self._browser and self._owns_browser_process:
                await self._browser.close()
        except Exception as e:
            if not _is_browser_closed_error(e):
                logger.warning("关闭浏览器失败: %s", e)
        if self._browser_process and self._owns_browser_process:
            try:
                self._browser_process.terminate()
            except Exception:
                pass
        self._browser_process = None
        self._owns_browser_process = False
        self._browser = None
        self._context = None
        self._page = None
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            if not _is_browser_closed_error(e):
                logger.warning("停止 Playwright 失败: %s", e)
        self._playwright = None
        logger.info("浏览器已关闭")
