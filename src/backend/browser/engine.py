"""
浏览器自动化引擎：Playwright 驱动抖音 PC 网页版，登录、搜索、评论、用户信息与风控。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Callable, Optional
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from . import selectors as sel
from .risk import RiskConfig, RiskLevel, RiskState

logger = logging.getLogger(__name__)

# Cookie / 会话持久化路径（不纳入 git）
_DEFAULT_STORAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "data",
    "douyin_storage_state.json",
)

# #region agent log
_DEBUG_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "debug-a4e257.log",
)

def _debug_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    try:
        payload = {"sessionId": "a4e257", "timestamp": int(time.time() * 1000), "location": location, "message": message, "data": data, "hypothesisId": hypothesis_id}
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


class BrowserEngine:
    """
    对外暴露的浏览器自动化接口，供 M3 任务编排调用。
    所有方法均为 async，需在 asyncio 事件循环中运行。
    """

    def __init__(
        self,
        *,
        headless: bool = False,
        storage_path: str | None = None,
        risk_config: RiskConfig | None = None,
        browser_log_path: str | None = None,
    ) -> None:
        self._headless = headless
        self._storage_path = storage_path or _DEFAULT_STORAGE_PATH
        self._risk_config = risk_config or RiskConfig()
        self._browser_log_path = browser_log_path
        self._risk_state = RiskState(self._risk_config)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._consecutive_not_found = 0

    async def launch(self, headless: bool | None = None) -> None:
        """启动浏览器，加载已有 Cookie（若存在），打开抖音首页。"""
        if self._browser:
            return
        use_headless = headless if headless is not None else self._headless
        self._playwright = await async_playwright().start()
        launch_opts: dict[str, Any] = {"headless": use_headless}
        cdp_port = os.getenv("DOUYIN_REACH_CDP_PORT", "")
        if cdp_port.isdigit():
            launch_opts["args"] = [f"--remote-debugging-port={cdp_port}"]
            logger.info("CDP 端口已开启: %s（供 MCP 等工具连接监测）", cdp_port)
        self._browser = await self._playwright.chromium.launch(**launch_opts)
        opts: dict[str, Any] = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": "zh-CN",
        }
        if os.path.isfile(self._storage_path):
            opts["storage_state"] = self._storage_path
            logger.info("已加载持久化会话: %s", self._storage_path)
        self._context = await self._browser.new_context(**opts)
        self._page = await self._context.new_page()
        if self._browser_log_path:
            self._attach_browser_log_listeners()
        await self._page.goto(sel.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await self._risk_state.delay_page()
        await self._check_danger_texts()

    def _attach_browser_log_listeners(self) -> None:
        """将页面 console、pageerror、requestfailed 等写入 browser_log_path，供调试。"""
        if not self._page or not self._browser_log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._browser_log_path)) or ".", exist_ok=True)
        except Exception:
            pass
        log_path = self._browser_log_path

        def _write(typ: str, text: str) -> None:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] [{typ}] {text}\n")
            except Exception:
                pass

        def _on_console(msg):
            _write("console", f"{msg.type}: {msg.text}")

        def _on_pageerror(err):
            _write("pageerror", str(err))

        def _on_requestfailed(req):
            _write("requestfailed", f"{req.url} {req.failure}")

        self._page.on("console", _on_console)
        self._page.on("pageerror", _on_pageerror)
        self._page.on("requestfailed", _on_requestfailed)
        _write("sys", "browser log listeners attached")

    async def _check_danger_texts(self) -> None:
        """检测当前页是否出现危险文案（账号异常、验证码等）。"""
        if not self._page:
            return
        try:
            content = await self._page.content()
            for text in sel.DANGER_PAGE_TEXTS:
                if text in content:
                    self._risk_state.trigger_danger(f"页面出现「{text}」")
                    return
        except Exception as e:
            logger.debug("检测危险文案时出错: %s", e)

    def _on_element_not_found(self, selector_desc: str) -> bool:
        """元素未找到时调用：连续 2 次触发预警。"""
        self._consecutive_not_found += 1
        if self._consecutive_not_found >= 2:
            self._risk_state.trigger_warning(f"连续元素未找到: {selector_desc}")
            self._consecutive_not_found = 0
        return self._risk_state.level == RiskLevel.DANGER

    def _on_element_found(self) -> None:
        self._consecutive_not_found = 0

    async def check_session(self) -> bool:
        """校验当前 session 是否有效（请求 user/settings）。"""
        if not self._page:
            return False
        try:
            resp = await self._page.goto(
                sel.USER_SETTINGS_API,
                wait_until="commit",
                timeout=15000,
            )
            if not resp or resp.status != 200:
                # #region agent log
                _debug_log("engine.py:check_session", "resp invalid or non-200", {"resp_is_none": resp is None, "status": resp.status if resp else None}, "H1")
                # #endregion
                return False
            body = await resp.json()
            # 仅当响应中明确包含用户信息时视为已登录；status_code==0 仅表示接口成功，未登录时也可能为 0
            result = False
            if isinstance(body, dict):
                if "user" in body and body.get("user") is not None:
                    result = True
                elif body.get("user_id") is not None:
                    result = True
            # #region agent log
            _debug_log("engine.py:check_session", "session check result", {"resp_status": resp.status, "body_keys": list(body.keys()) if isinstance(body, dict) else type(body).__name__, "body_status_code": body.get("status_code") if isinstance(body, dict) else None, "has_user_key": "user" in body if isinstance(body, dict) else False, "user_id": body.get("user_id") if isinstance(body, dict) else None, "result": result}, "H1")
            # #endregion
            return result
        except Exception as e:
            logger.warning("session 校验请求异常: %s", e)
            # #region agent log
            _debug_log("engine.py:check_session", "session check exception", {"error": str(e)}, "H1")
            # #endregion
            return False

    async def _check_session_no_navigate(self) -> bool:
        """校验 session（用 request.get 请求接口，不改变当前页面）。用于 login() 轮询，避免反复 goto 导致页面无限刷新。"""
        if not self._context:
            return False
        try:
            resp = await self._context.request.get(sel.USER_SETTINGS_API, timeout=15000)
            if resp.status != 200:
                return False
            body = await resp.json()
            if isinstance(body, dict):
                if "user" in body and body.get("user") is not None:
                    return True
                if body.get("user_id") is not None:
                    return True
            return False
        except Exception:
            return False

    async def login(self) -> bool:
        """触发登录流程（打开登录层，等待用户扫码/输入），成功后持久化 Cookie。"""
        if not self._page:
            return False
        try:
            # check_session 会 goto(USER_SETTINGS_API)，当前页可能是接口页，需先回到首页再找登录按钮
            await self._page.goto(sel.BASE_URL, wait_until="domcontentloaded", timeout=15000)
            await self._risk_state.delay_page()
            # 未登录时抖音可能已自动弹出登录层（id^="login-full-panel"），若已在 DOM 中则视为已打开，仅等待用户完成登录
            login_panel = self._page.locator('[id^="login-full-panel"]').first
            try:
                await login_panel.wait_for(state="attached", timeout=5000)
            except Exception:
                pass
            panel_in_dom = await login_panel.count() > 0
            if not panel_in_dom:
                # 页面上有「退出登录」说明已登录，无需点击，直接返回成功
                logout_btn = self._page.get_by_text("退出登录", exact=False).first
                if await logout_btn.count() > 0:
                    try:
                        if await logout_btn.is_visible():
                            logger.info("检测到已登录状态（退出登录可见），跳过登录流程")
                            return True
                    except Exception:
                        pass
                # 只点击文案为「登录」的入口（exact=True 避免点到「退出登录」）
                login_btn = self._page.get_by_text("登录", exact=True).filter(has_not=self._page.locator('[id^="login-full-panel"]')).first
                try:
                    await login_btn.click(timeout=5000)
                except Exception as click_err:
                    # 无「登录」按钮可能已登录（如顶栏为「私信」「退出登录」）
                    if await self._page.get_by_text("私信", exact=False).first.count() > 0 or await self._page.get_by_text("退出登录", exact=False).first.count() > 0:
                        logger.info("未找到登录入口且页面含私信/退出登录，视为已登录")
                        return True
                    raise click_err
            await self._risk_state.delay_page()
            # 等待登录成功：用不跳转的请求轮询，避免 check_session() 的 goto 导致页面无限刷新
            for _ in range(120):  # 最多等约 2 分钟
                if await self._check_session_no_navigate():
                    break
                await asyncio.sleep(1)
            else:
                logger.warning("登录超时")
                return False
            await self._save_storage_state()
            self._risk_state.reset_to_normal()
            return True
        except Exception as e:
            logger.exception("登录流程异常: %s", e)
            return False

    async def _save_storage_state(self) -> None:
        """将会话持久化到文件。"""
        if not self._context:
            return
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            await self._context.storage_state(path=self._storage_path)
            logger.info("已保存会话: %s", self._storage_path)
        except Exception as e:
            logger.exception("保存会话失败: %s", e)

    async def search_videos(self, keyword: str, max_count: int) -> list[dict[str, Any]]:
        """搜索关键词，返回视频列表（标题、aweme_id、作者昵称、sec_uid、点赞数）。"""
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return []
        url = sel.SEARCH_URL_TEMPLATE.format(keyword=quote(keyword))
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await self._risk_state.delay_page()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER:
                return []

            # #region agent log
            _debug_log("engine.py:search_videos", "after goto search page", {"request_url": url, "page_url": self._page.url}, "H3")
            # #endregion

            # 搜索页默认可能在「综合」Tab，需切换到「视频」Tab 才有视频列表（09 文档：Tab 综合/视频/用户/直播）
            try:
                video_tab = self._page.get_by_role("tab", name=sel.SEARCH_TAB_VIDEO).first
                if await video_tab.count() > 0:
                    await video_tab.click(timeout=5000)
                    await self._risk_state.delay_page()
                    _debug_log("engine.py:search_videos", "clicked 视频 tab (role)", {"clicked": True}, "H5")
                else:
                    # 备用：按文案点击「视频」（可能为 link 或 div）
                    by_text = self._page.get_by_text("视频", exact=True).first
                    if await by_text.count() > 0:
                        await by_text.click(timeout=5000)
                        await self._risk_state.delay_page()
                        _debug_log("engine.py:search_videos", "clicked 视频 tab (text)", {"clicked": True}, "H5")
                    else:
                        _debug_log("engine.py:search_videos", "视频 tab not found", {"clicked": False}, "H5")
            except Exception as tab_err:
                _debug_log("engine.py:search_videos", "视频 tab click error", {"error": str(tab_err)[:200]}, "H5")

            # 调试：页面上所有含 video 的链接（任意 path 形式）
            try:
                any_video_links = await self._page.locator('a[href*="video"]').all()
                any_hrefs = []
                for lnk in any_video_links[:10]:
                    h = await lnk.get_attribute("href")
                    any_hrefs.append(h[:100] if h else None)
                _debug_log("engine.py:search_videos", "any a[href*='video']", {"count": len(any_video_links), "sample_hrefs": any_hrefs}, "H6")
            except Exception as e:
                _debug_log("engine.py:search_videos", "any video links error", {"error": str(e)[:150]}, "H6")

            # 等待搜索结果中的视频链接出现（页面可能动态加载）
            selector_found = False
            wait_err_msg = None
            try:
                await self._page.wait_for_selector('a[href*="/video/"]', timeout=15000, state="attached")
                selector_found = True
            except Exception as wait_err:
                wait_err_msg = str(wait_err)
                logger.debug("搜索页未在 15s 内出现视频链接，继续尝试解析")
            # #region agent log
            _debug_log("engine.py:search_videos", "wait_for_selector result", {"selector_found": selector_found, "wait_error": wait_err_msg[:200] if wait_err_msg else None}, "H3")
            # #endregion
            await self._risk_state.delay_normal()

            videos: list[dict[str, Any]] = []
            seen_aweme: set[str] = set()
            scroll_attempts = 0
            max_scrolls = 20

            while len(videos) < max_count and scroll_attempts < max_scrolls:
                # 解析当前屏视频链接：/video/<aweme_id>
                links = await self._page.locator('a[href*="/video/"]').all()
                # #region agent log
                if scroll_attempts == 0:
                    sample_hrefs = []
                    for i, lnk in enumerate(links[:5]):
                        try:
                            h = await lnk.get_attribute("href")
                            sample_hrefs.append(h[:80] if h and len(h) > 80 else h)
                        except Exception:
                            sample_hrefs.append(None)
                    _debug_log("engine.py:search_videos", "first loop links", {"links_count": len(links), "sample_hrefs": sample_hrefs}, "H4")
                # #endregion
                for link in links:
                    if len(videos) >= max_count:
                        break
                    try:
                        href = await link.get_attribute("href")
                        if not href or "/video/" not in href:
                            continue
                        m = re.search(r"/video/([A-Za-z0-9]+)", href)
                        if not m:
                            continue
                        aweme_id = m.group(1)
                        if aweme_id in seen_aweme:
                            continue
                        seen_aweme.add(aweme_id)
                        # 同卡片内尽量取标题、作者（父/兄弟节点）
                        title = ""
                        author_name = ""
                        author_sec_uid = ""
                        like_text = ""
                        try:
                            card = link.locator("xpath=ancestor::*[.//a[contains(@href,'/video/')]][1]")
                            title_el = card.get_by_role("paragraph").first
                            if await title_el.count() > 0:
                                title = (await title_el.text_content()) or ""
                            author_link = card.locator('a[href*="/user/"]').first
                            if await author_link.count() > 0:
                                author_name = (await author_link.text_content()) or ""
                                author_name = author_name.replace("@", "").strip()
                                u = await author_link.get_attribute("href")
                                if u and "/user/" in u:
                                    mu = re.search(r"/user/([A-Za-z0-9_-]+)", u)
                                    if mu:
                                        author_sec_uid = mu.group(1)
                        except Exception:
                            pass
                        videos.append({
                            "aweme_id": aweme_id,
                            "title": title.strip() or None,
                            "author_nickname": author_name or None,
                            "author_sec_uid": author_sec_uid or None,
                            "like_count_text": like_text or None,
                            "video_url": sel.VIDEO_URL_TEMPLATE.format(aweme_id=aweme_id),
                        })
                    except Exception as e:
                        logger.debug("解析视频卡片失败: %s", e)

                if len(videos) >= max_count:
                    break
                await self._page.evaluate("window.scrollBy(0, window.innerHeight)")
                await self._risk_state.delay_normal()
                scroll_attempts += 1

            return videos[:max_count]
        except Exception as e:
            logger.exception("搜索视频异常: %s", e)
            self._risk_state.trigger_warning(f"搜索异常: {e}")
            return []

    async def fetch_comments(
        self, video_url: str, max_count: int
    ) -> list[dict[str, Any]]:
        """拉取视频一级评论（cid、内容、昵称、sec_uid、点赞数、时间）。"""
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return []
        try:
            await self._page.goto(video_url, wait_until="domcontentloaded", timeout=20000)
            await self._risk_state.delay_page()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER:
                return []

            comments: list[dict[str, Any]] = []
            load_more_selector = f'button:has-text("{sel.COMMENT_LOAD_MORE_TEXT}")'
            scroll_attempts = 0

            while len(comments) < max_count and scroll_attempts < 30:
                # 点击「点击加载更多」
                try:
                    btn = self._page.locator(load_more_selector).first
                    if await btn.count() > 0:
                        await btn.click(timeout=3000)
                        await self._risk_state.delay_normal()
                except Exception:
                    pass

                # 解析评论区：用户 link + 评论正文（同一块内）
                # 评论区容器：包含「全部评论」或推荐视频之上的区域
                comment_links = await self._page.locator('div[class] a[href*="/user/"]').all()
                for link in comment_links:
                    if len(comments) >= max_count:
                        break
                    try:
                        href = await link.get_attribute("href")
                        if not href or "/user/" not in href:
                            continue
                        m = re.search(r"/user/([A-Za-z0-9_-]+)", href)
                        if not m:
                            continue
                        sec_uid = m.group(1)
                        nickname = (await link.text_content()) or ""
                        nickname = nickname.replace("@", "").strip()
                        # 找该 link 所在评论块内的正文（同父或兄弟中的文本）
                        parent = link.locator("xpath=ancestor::*[.//a[contains(@href,'/user/')]][1]")
                        text_el = parent.locator("p, span, div").filter(has_not=link).first
                        text = ""
                        if await text_el.count() > 0:
                            text = (await text_el.text_content()) or ""
                        text = text.strip()
                        if not text or len(text) > 500:
                            continue
                        # 简单去重：同一 sec_uid+text 只算一条
                        if any(c.get("commenter_sec_uid") == sec_uid and c.get("text") == text for c in comments):
                            continue
                        comments.append({
                            "cid": None,  # DOM 中无 cid，可选后续从接口补
                            "text": text,
                            "commenter_nickname": nickname,
                            "commenter_sec_uid": sec_uid,
                            "profile_url": sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid),
                            "like_count_text": None,
                            "create_time_text": None,
                        })
                    except Exception as e:
                        logger.debug("解析评论失败: %s", e)

                await self._page.evaluate("window.scrollBy(0, 400)")
                await self._risk_state.delay_normal()
                scroll_attempts += 1

            return comments[:max_count]
        except Exception as e:
            logger.exception("拉取评论异常: %s", e)
            self._risk_state.trigger_warning(f"拉取评论异常: {e}")
            return []

    async def fetch_user_info(self, sec_uid: str) -> dict[str, Any]:
        """从用户主页补全信息（粉丝数、关注数、简介、是否认证）。频率需由调用方控制。"""
        if not self._page or self._risk_state.level == RiskLevel.DANGER:
            return {}
        url = sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await self._risk_state.delay_page()
            await self._check_danger_texts()
            if self._risk_state.level == RiskLevel.DANGER:
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
            # 粉丝/关注/获赞 多为数字+文案，可按需用正则从页面文本提取
            return info
        except Exception as e:
            logger.warning("拉取用户信息异常: %s", e)
            return {}

    def get_risk_level(self) -> RiskLevel:
        """当前风控级别。"""
        return self._risk_state.level

    def set_risk_callbacks(
        self,
        on_warning: Optional[Callable[[], None]] = None,
        on_danger: Optional[Callable[[], None]] = None,
    ) -> None:
        """设置风控预警/危险回调（如通知前端）。"""
        self._risk_state.set_callbacks(on_warning=on_warning, on_danger=on_danger)

    async def close(self) -> None:
        """保存会话并关闭浏览器。"""
        if self._context:
            await self._save_storage_state()
        if self._browser:
            await self._browser.close()
            self._browser = None
        self._context = None
        self._page = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("浏览器已关闭")
