"""
创作者中心私信发送（通道切换，Phase 1 DOM 模式）。

链路：主站 /user/{sec_uid} → 点「私信」按钮触发会话在服务端建立 → 切到创作者中心
chat tab → 按昵称（或列表首条）定位新会话 → contenteditable 输入 → 点发送 → 验气泡。

关键事实（来自 docs/DOM调研.txt 实测）：
- 创作者中心 chat 页是 Semi Design（div contenteditable，不是 DraftJS）
- DOM 不含 sec_uid 锚点，会话定位只能按昵称 / 顺序 / 时间戳
- 所有 hash 类名均使用 [class*="..."] 前缀匹配，抗发版漂移
- imapi.douyin.com 与 www.douyin.com 共享 .douyin.com 主域 cookie，无需额外登录
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from src.backend.browser import BrowserEngine
from src.backend.browser import selectors as sel
from src.backend.browser.risk import RiskLevel

from .sender import SendResult

logger = logging.getLogger(__name__)

_SYNC_WAIT_MAX = 8.0          # 会话从主站同步到创作者中心的最长等待
_SEND_BTN_WAIT = 5.0          # 发送按钮从 disabled 激活的最长等待
_BUBBLE_VERIFY_WAIT = 3.0     # 发送后验证气泡最新文本的最长等待


class CreatorDMSender:
    """创作者中心私信发送器，DOM 自动化。"""

    def __init__(self, browser: BrowserEngine) -> None:
        self._browser = browser
        self._send_count = 0

    def render_message(self, template: Any, *, index: int = 0, **_ignored: Any) -> str:
        from .template import render_template
        return render_template(template, index=index)

    async def send_dm(self, sec_uid: str, nickname: str, message: str) -> SendResult:
        """
        通过创作者中心发送私信。比主站 sender 多一个 nickname 参数（DOM 无 sec_uid 锚点）。
        """
        main_page = self._browser._page if hasattr(self._browser, "_page") else None
        if not main_page:
            return SendResult(
                success=False,
                failure_type="technical",
                failure_reason="浏览器未就绪",
                retryable=True,
            )
        if self._browser.get_risk_level() == RiskLevel.DANGER:
            return SendResult(
                success=False,
                failure_type="technical",
                failure_reason="风控危险态，暂停发送",
                retryable=True,
            )
        if not nickname:
            return SendResult(
                success=False,
                failure_type="business",
                failure_reason="缺少昵称，创作者中心通道无法定位会话",
                retryable=False,
            )

        try:
            t0 = time.monotonic()
            trigger_ok, trigger_fail = await self._light_touch_main(main_page, sec_uid)
            if not trigger_ok:
                return trigger_fail  # type: ignore[return-value]
            t_touch = time.monotonic()
            logger.info("[创作者] 主站轻触发 %.1fs | sec_uid=%s", t_touch - t0, sec_uid[:20])

            creator_page = await self._browser.ensure_creator_tab()
            await creator_page.bring_to_front()
            await asyncio.sleep(0.3)

            # 首轮快速轮询；没等到就强制 reload 一次再试（防止 websocket 断连 / 页面假死）
            matched = await self._wait_conversation(creator_page, nickname, _SYNC_WAIT_MAX)
            if not matched:
                logger.info("[创作者] 首轮同步超时，reload 后重试一次")
                try:
                    await creator_page.reload(wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.8)
                except Exception:
                    pass
                matched = await self._wait_conversation(creator_page, nickname, _SYNC_WAIT_MAX)
            if not matched:
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason=f"会话同步超时（昵称「{nickname}」未在创作者中心出现）",
                    retryable=True,
                )
            t_sync = time.monotonic()
            logger.info("[创作者] 会话同步 %.1fs | nickname=%s", t_sync - t_touch, nickname)

            clicked = await self._click_conversation(creator_page, nickname)
            if not clicked:
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="点击会话失败",
                    retryable=True,
                )

            inserted = await self._insert_message(creator_page, message)
            if not inserted:
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="插入消息文本失败（输入框未就绪）",
                    retryable=True,
                )

            send_clicked = await self._click_send(creator_page)
            if not send_clicked:
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason=f"发送按钮 {_SEND_BTN_WAIT}s 未激活",
                    retryable=True,
                )
            t_send = time.monotonic()
            logger.info("[创作者] 输入+发送 %.1fs | 长度=%d", t_send - t_sync, len(message))

            result = await self._verify_result(creator_page, message)
            logger.info(
                "[创作者] 总耗时 %.1fs | 结果: %s",
                time.monotonic() - t0,
                "成功" if result.success else f"失败({result.failure_reason})",
            )
            self._send_count += 1
            return result
        except Exception as e:
            logger.warning("创作者通道发送异常: %s", e)
            return SendResult(
                success=False,
                failure_type="technical",
                failure_reason=str(e),
                retryable=True,
            )

    # ---------------- 主站轻触发 ----------------
    async def _light_touch_main(
        self, page: Any, sec_uid: str
    ) -> tuple[bool, Optional[SendResult]]:
        """打开主站用户页 → 点私信按钮 → 等浮窗出现 → 立刻返回，不输入不发送。

        整体检测逻辑与主站 DMSender.send_dm 对齐（新手引导关闭、风控文案扫描、
        按钮 3s 轮询查找、"用户不存在"识别），避免重复踩坑。
        """
        url = sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason=f"主站用户页加载失败: {e}",
                retryable=True,
            )

        try:
            await page.wait_for_selector(
                '[data-e2e="user-detail"], .author-card, button:has-text("私信")',
                state="visible",
                timeout=10000,
            )
        except Exception:
            pass
        await asyncio.sleep(0.3)

        # 用户主页不可访问（跳到别处）
        current_url = page.url
        if "/user/" not in current_url:
            return False, SendResult(
                success=False,
                failure_type="business",
                failure_reason="用户主页不可访问（可能已注销或为隐私账号）",
                retryable=False,
            )

        # ===== Store 直驱（首选路径，零 DOM 依赖）=====
        # 基于 2026-04-21 调研：主站页面挂载 MobX 的 window.conversationStore，
        # 点击私信按钮的唯一可观测副作用是 setCurConversation("0:1:<min>:<max>")。
        # 只要能拿到 from_uid / to_uid 就能直接调 store 触发浮窗挂载，完全不走 DOM。
        store_ok, store_err = await self._trigger_via_store(page, sec_uid)
        if store_ok:
            logger.info("[创作者] store 直驱成功，跳过 DOM 点击")
            return await self._wait_dialog_and_hint(page)
        logger.info("[创作者] store 直驱不可用(%s)，回退到 DOM 点击路径", store_err)

        # ===== DOM 点击兜底路径 =====
        # 合并检测：新手引导 + 风控文案 + 验证码 + 按钮查找（单次 CDP 往返）
        # 按钮定位策略（参考原始 HTML 2026-04-21）：
        #   <button class="semi-button semi-button-secondary ..." type="button" aria-disabled="false">
        #     <span class="semi-button-content" x-semi-prop="children">私信</span>
        #   </button>
        # 要点：
        #   - 作用域：全页面 <button>（不强制 user-detail — 容器 hash 可能已变；但优先排序）
        #   - 文本从 span.semi-button-content 取（Semi 设计系统类，稳定）
        #   - 黑名单：im-entry（顶部导航"私信"p 元素）/ im-dialog（浮窗自引用）
        #   - 可见：size > 0 + computed style 可见（不用 offsetParent：fixed 定位会误杀）
        #   - 诊断：失败时附带所有候选（含不可见的）+ 容器路径摘要，便于下一轮定位
        try:
            combined = await page.evaluate(
                """(args) => {
                    const [dangerTexts, captchaSelectors, newbieText, userDetailSel] = args;
                    const result = {
                        newbieFound: false,
                        dangerText: null,
                        captchaSelector: null,
                        dmButtons: [],
                        diagCandidates: [],
                        pageSnippet: ''
                    };

                    // 1. 新手引导关闭
                    const allElems = document.querySelectorAll('button, [role="button"], a, span');
                    for (const el of allElems) {
                        if ((el.textContent || '').trim() === newbieText) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0 && el.offsetParent !== null) {
                                el.click();
                                result.newbieFound = true;
                                break;
                            }
                        }
                    }

                    // 2. 风控文案扫描
                    const body = document.body;
                    if (body) {
                        const clone = body.cloneNode(true);
                        const ugcSelectors = [
                            '[data-e2e="comment-list"]', '[data-e2e="comment-item"]',
                            '.comment-mainContent', '[data-e2e="video-desc"]',
                            '[data-e2e="modal-video-container"] [data-e2e="video-desc"]',
                            '[data-e2e="im-dialog"]', '.public-DraftEditor-content',
                            '.search-result-card',
                        ];
                        for (const s of ugcSelectors) {
                            for (const el of clone.querySelectorAll(s)) el.remove();
                        }
                        const visibleText = clone.innerText || '';
                        for (const dt of dangerTexts) {
                            if (dt && visibleText.includes(dt)) {
                                const idx = visibleText.indexOf(dt);
                                result.dangerText = dt;
                                result.pageSnippet = visibleText.slice(Math.max(0, idx - 60), idx + 120);
                                return result;
                            }
                        }
                    }

                    // 3. 验证码 DOM
                    for (const s of captchaSelectors) {
                        const el = document.querySelector(s);
                        if (el) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0 && el.offsetParent !== null) {
                                result.captchaSelector = s;
                                return result;
                            }
                        }
                    }

                    // 4. 私信按钮查找
                    const allDocBtns = Array.from(document.querySelectorAll('button'));
                    const detailEl = document.querySelector(userDetailSel);

                    const extractText = (btn) => {
                        // 优先从 Semi 的 span.semi-button-content 取；它是设计系统类，不带 hash
                        const span = btn.querySelector('span[class*="semi-button-content"]');
                        if (span) return (span.textContent || '').trim();
                        return (btn.textContent || '').trim();
                    };

                    const describeContainer = (btn) => {
                        // 优先命中 data-e2e 锚点
                        const anchors = [
                            '[data-e2e="user-detail"]', '[data-e2e="user-info"]',
                            '[data-e2e="im-entry"]', '[data-e2e="im-dialog"]'
                        ];
                        for (const a of anchors) {
                            if (btn.closest(a)) return a;
                        }
                        // 否则给出 3 级父节点标签 + 非 hash 类摘要
                        let p = btn.parentElement;
                        const path = [];
                        for (let d = 0; d < 3 && p; d++) {
                            const tag = p.tagName.toLowerCase();
                            const cls = (p.className || '').toString().split(/\\s+/)
                                .filter(c => c && !/^[A-Za-z]{1,3}[0-9]+[A-Za-z0-9]{3,}$/.test(c) &&
                                              !/[A-Za-z0-9]{6,}$/.test(c))
                                .slice(0, 2).join('.');
                            path.push(cls ? (tag + '.' + cls) : tag);
                            p = p.parentElement;
                        }
                        return path.join(' > ') || '(unknown)';
                    };

                    for (const btn of allDocBtns) {
                        const text = extractText(btn);
                        if (text !== '私信') continue;
                        // 黑名单：顶部导航 / 浮窗自引用
                        if (btn.closest('[data-e2e="im-entry"]')) continue;
                        if (btn.closest('[data-e2e="im-dialog"]')) continue;

                        const rect = btn.getBoundingClientRect();
                        const style = window.getComputedStyle(btn);
                        const visible = rect.width > 0 && rect.height > 0
                            && style.display !== 'none' && style.visibility !== 'hidden';
                        const inDetail = detailEl ? detailEl.contains(btn) : false;
                        const globalIndex = allDocBtns.indexOf(btn);

                        result.diagCandidates.push({
                            index: globalIndex,
                            visible,
                            inDetail,
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            container: describeContainer(btn),
                            className: (btn.className || '').toString().slice(0, 120)
                        });

                        if (!visible) continue;
                        result.dmButtons.push({
                            index: globalIndex,
                            y: rect.y,
                            inDetail,
                            priority: inDetail ? 0 : 1
                        });
                    }

                    if (result.dmButtons.length === 0) {
                        result.pageSnippet = (document.body.innerText || '').slice(0, 500);
                    }
                    return result;
                }""",
                [
                    list(sel.DANGER_PAGE_TEXTS),
                    list(sel.CAPTCHA_DOM_SELECTORS),
                    sel.NEWBIE_GUIDE_DISMISS_TEXT,
                    sel.USER_DETAIL_CONTAINER,
                ],
            )
        except Exception as e:
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason=f"合并检测异常: {e}",
                retryable=True,
            )

        if not isinstance(combined, dict):
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason="合并检测返回非预期类型（CDP 偶发断连）",
                retryable=True,
            )

        if combined.get("dangerText"):
            self._browser._risk_state.trigger_danger(
                f"页面出现危险文案: {combined['dangerText']} | snippet={combined.get('pageSnippet', '')}"
            )
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason="检测到验证码/风控浮层，请手动完成验证",
                retryable=True,
            )
        if combined.get("captchaSelector"):
            self._browser._risk_state.trigger_danger(
                f"检测到验证码浮层: {combined['captchaSelector']}"
            )
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason="检测到验证码/风控浮层，请手动完成验证",
                retryable=True,
            )

        candidates_raw = combined.get("dmButtons", [])
        diag_first = combined.get("diagCandidates", [])

        # 按钮未找到时轮询重试 3s（SPA 异步渲染兜底）
        if not candidates_raw:
            page_text = combined.get("pageSnippet", "")
            if any(k in page_text for k in ("用户不存在", "该页面", "无法访问")):
                logger.warning(
                    "[创作者] 用户不可达 | URL=%s | 页面摘要: %s", current_url, page_text[:100]
                )
                return False, SendResult(
                    success=False,
                    failure_type="business",
                    failure_reason="用户页面不可访问（不存在或隐私账号）",
                    retryable=False,
                )
            # 重试：用同样的宽作用域 + span.semi-button-content 文本
            _JS_FIND_DM_BTNS = """(userDetailSel) => {
                const out = { buttons: [], diag: [] };
                const allDocBtns = Array.from(document.querySelectorAll('button'));
                const detailEl = document.querySelector(userDetailSel);
                for (const btn of allDocBtns) {
                    const span = btn.querySelector('span[class*="semi-button-content"]');
                    const text = ((span ? span.textContent : btn.textContent) || '').trim();
                    if (text !== '私信') continue;
                    if (btn.closest('[data-e2e="im-entry"]')) continue;
                    if (btn.closest('[data-e2e="im-dialog"]')) continue;
                    const rect = btn.getBoundingClientRect();
                    const style = window.getComputedStyle(btn);
                    const visible = rect.width > 0 && rect.height > 0
                        && style.display !== 'none' && style.visibility !== 'hidden';
                    const inDetail = detailEl ? detailEl.contains(btn) : false;
                    const globalIndex = allDocBtns.indexOf(btn);
                    out.diag.push({
                        index: globalIndex, visible, inDetail,
                        w: Math.round(rect.width), h: Math.round(rect.height)
                    });
                    if (!visible) continue;
                    out.buttons.push({
                        index: globalIndex, y: rect.y,
                        inDetail, priority: inDetail ? 0 : 1
                    });
                }
                return out;
            }"""
            last_diag = diag_first
            for _retry in range(6):
                await asyncio.sleep(0.5)
                try:
                    r = await page.evaluate(_JS_FIND_DM_BTNS, sel.USER_DETAIL_CONTAINER)
                    candidates_raw = r.get("buttons", []) if isinstance(r, dict) else []
                    last_diag = r.get("diag", []) if isinstance(r, dict) else []
                except Exception:
                    candidates_raw = []
                if candidates_raw:
                    logger.info(
                        "[创作者] 按钮重试 %d 次后找到 | 额外等待 %.1fs",
                        _retry + 1,
                        (_retry + 1) * 0.5,
                    )
                    break
            diag_first = last_diag

        if not candidates_raw:
            snippet = ""
            try:
                snippet = await page.evaluate(
                    "() => (document.body.innerText || '').slice(0, 500)"
                )
            except Exception:
                pass
            if any(k in snippet for k in ("用户不存在", "该页面", "无法访问")):
                logger.warning(
                    "[创作者] 用户不可达(重试后) | URL=%s | 摘要: %s",
                    current_url,
                    snippet[:100],
                )
                return False, SendResult(
                    success=False,
                    failure_type="business",
                    failure_reason="用户页面不可访问（不存在或隐私账号）",
                    retryable=False,
                )
            # 诊断候选 —— 让你能看清是"完全没找到带'私信'文字的 button"还是"找到了但不可见/在黑名单容器里"
            diag_summary = [
                f"idx={d.get('index')} visible={d.get('visible')} inDetail={d.get('inDetail')} "
                f"size={d.get('w')}x{d.get('h')} container={d.get('container', '?')}"
                for d in (diag_first or [])
            ]
            logger.warning(
                "[创作者] 私信按钮未找到 | URL=%s | 候选(%d)=%s | 页面摘要: %s",
                current_url,
                len(diag_first or []),
                " ; ".join(diag_summary) if diag_summary else "空",
                snippet[:200],
            )
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason="用户主页未出现可见的私信按钮",
                retryable=True,
            )

        # 优先 inDetail=true 的，其次 y 坐标大的（更下方，通常就是资料卡）
        candidates_raw.sort(key=lambda c: (c.get("priority", 1), -c.get("y", 0)))
        chosen = candidates_raw[0]
        dm_btn = page.locator("button").nth(chosen["index"])
        logger.info(
            "[创作者] 私信按钮选中 | index=%d y=%.0f inDetail=%s 候选数=%d",
            chosen["index"],
            chosen.get("y", 0),
            chosen.get("inDetail"),
            len(candidates_raw),
        )
        try:
            await dm_btn.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        try:
            await dm_btn.click(timeout=5000)
        except Exception as e1:
            logger.warning("[创作者] 私信按钮 click 失败: %s，尝试 dispatch_event", e1)
            try:
                await dm_btn.dispatch_event("click")
            except Exception as e2:
                return False, SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason=f"点击私信按钮失败: {e2}",
                    retryable=True,
                )

        # DOM 点击路径的浮窗等待与系统提示等待，共用统一工具
        # （点击后首次 12s 未出现就再点一次，最多 8s 补等）
        opened = await self._wait_popup_visible(page, 12000)
        if not opened:
            try:
                await dm_btn.dispatch_event("click")
            except Exception:
                pass
            try:
                await dm_btn.click(timeout=3000, force=True)
            except Exception:
                pass
            opened = await self._wait_popup_visible(page, 8000)

        if not opened:
            return False, SendResult(
                success=False,
                failure_type="technical",
                failure_reason="主站私信浮窗打开超时（msg-input 未出现）",
                retryable=True,
            )
        return await self._wait_dialog_and_hint(page, already_opened=True)

    # ---------------- 轻触发共用工具 ----------------
    async def _wait_popup_visible(self, page: Any, timeout_ms: int) -> bool:
        """等私信浮窗出现（im-dialog 或 msg-input 任一即算）。"""
        popup_selector = ", ".join(
            [
                sel.DM_DIALOG_SELECTOR,
                sel.DM_INPUT_SELECTOR,
                sel.DM_INPUT_SELECTOR_ALT,
            ]
        )
        try:
            await page.wait_for_selector(popup_selector, state="visible", timeout=timeout_ms)
            return True
        except Exception:
            return False

    async def _wait_dialog_and_hint(
        self, page: Any, already_opened: bool = False
    ) -> tuple[bool, Optional[SendResult]]:
        """触发后统一等：im-dialog 实际尺寸 + 系统提示文字。返回 send_dm 需要的 tuple。"""
        if not already_opened:
            # store 路径下浮窗 DOM 早就存在但尺寸为 0，要等 setCurConversation 之后被展开
            try:
                await page.wait_for_function(
                    """(sel) => {
                        const d = document.querySelector(sel);
                        if (!d) return false;
                        const r = d.getBoundingClientRect();
                        return r.width > 100 && r.height > 100;
                    }""",
                    arg=sel.DM_DIALOG_SELECTOR,
                    timeout=10000,
                )
            except Exception:
                return False, SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="setCurConversation 后浮窗未展开（可能还有其它 state 控制 open/close）",
                    retryable=True,
                )

        # 等系统提示 —— 创作者中心会话同步的前提（陌生人会话必出）
        try:
            await page.wait_for_function(
                """(args) => {
                    const [dialogSel, keyword] = args;
                    const c = document.querySelector(dialogSel);
                    if (!c) return false;
                    return (c.innerText || '').includes(keyword);
                }""",
                arg=[sel.DM_DIALOG_SELECTOR, sel.DM_ONE_MSG_LIMIT],
                timeout=6000,
            )
            logger.info("[创作者] 主站系统提示已出现 -> 会话已同步到服务端")
        except Exception:
            logger.info("[创作者] 未捕获「只能发送一条」提示（可能是老会话），回落固定 2s 缓冲")
            await asyncio.sleep(2.0)
        return True, None

    # ---------------- Store 直驱 ----------------
    async def _trigger_via_store(
        self, page: Any, sec_uid: str
    ) -> tuple[bool, Optional[str]]:
        """通过 window.conversationStore.setCurConversation 直接打开浮窗。
        返回 (是否触发成功, 失败原因字符串 or None)。
        触发成功不代表浮窗已展开 —— 展开由 _wait_dialog_and_hint 校验。
        """
        # 1. 等 conversationStore 挂上（SPA 异步初始化最多 10s）
        try:
            await page.wait_for_function(
                "() => typeof window.conversationStore === 'object' && window.conversationStore !== null "
                "&& typeof window.conversationStore.setCurConversation === 'function'",
                timeout=10000,
            )
        except Exception:
            return False, "conversationStore_not_ready"

        # 2. 执行：抠 from_uid / to_uid → BigInt 排序 → setCurConversation
        result = await page.evaluate(
            """(secUid) => {
                const out = { ok: false, reason: null, fromUid: null, toUid: null, convId: null };
                const store = window.conversationStore;
                const uStore = window.userInfoStore;

                // --- 抠 from_uid / to_uid ---
                // 优先 userInfoStore，其次 SSR <script> 里的注入
                try {
                    const login = uStore && uStore.curLoginUserInfo;
                    if (login && login.uid) out.fromUid = String(login.uid);
                } catch (e) {}
                try {
                    if (uStore && typeof uStore.getUserBySecUid === 'function') {
                        const info = uStore.getUserBySecUid(secUid);
                        if (info && info.uid) out.toUid = String(info.uid);
                    }
                    if (!out.toUid && uStore && uStore.secUidToUidMap) {
                        const m = uStore.secUidToUidMap;
                        const v = (m && typeof m.get === 'function') ? m.get(secUid) : m[secUid];
                        if (v) out.toUid = String(v);
                    }
                } catch (e) {}
                if (!out.fromUid || !out.toUid) {
                    // SSR 兜底：兼容转义 \\\"to_uid\\\": 和非转义 "to_uid":
                    const scripts = [...document.querySelectorAll('script')].map(s => s.textContent || '');
                    const reFrom = /\\\\?"from_uid\\\\?"\\s*:\\s*\\\\?"?(\\d+)\\\\?"?/;
                    const reTo = /\\\\?"to_uid\\\\?"\\s*:\\s*\\\\?"?(\\d+)\\\\?"?/;
                    for (const s of scripts) {
                        if (!out.fromUid) { const m = s.match(reFrom); if (m) out.fromUid = m[1]; }
                        if (!out.toUid)   { const m = s.match(reTo);   if (m) out.toUid = m[1]; }
                        if (out.fromUid && out.toUid) break;
                    }
                }
                if (!out.fromUid || !out.toUid) {
                    out.reason = 'missing_uids';
                    return out;
                }

                // --- BigInt 升序排序拼 conversation_id ---
                let lo = out.fromUid, hi = out.toUid;
                try {
                    if (BigInt(lo) > BigInt(hi)) { const t = lo; lo = hi; hi = t; }
                } catch (e) {
                    out.reason = 'bigint_error:' + String(e);
                    return out;
                }
                out.convId = '0:1:' + lo + ':' + hi;

                // --- 调 store ---
                try {
                    if (typeof store.setEnterMethod === 'function') {
                        store.setEnterMethod('profile');
                    }
                    store.setCurConversation(out.convId);
                    out.ok = true;
                    return out;
                } catch (e) {
                    out.reason = 'set_cur_conversation_threw:' + String(e);
                    return out;
                }
            }""",
            sec_uid,
        )

        if not isinstance(result, dict):
            return False, "evaluate_returned_non_dict"
        if not result.get("ok"):
            return False, str(result.get("reason") or "unknown")
        logger.info(
            "[创作者] store 直驱已调 setCurConversation | convId=%s fromUid=%s toUid=%s",
            result.get("convId"),
            result.get("fromUid"),
            result.get("toUid"),
        )
        return True, None

    # ---------------- 创作者中心会话同步 ----------------
    @staticmethod
    def _norm_name(s: str) -> str:
        """昵称归一化：折叠空白、去零宽字符。创作者中心列表里的昵称可能与主站采集到的略有差异。"""
        if not s:
            return ""
        # 把连续空白（含 \u3000 全角空格等）折为单个普通空格
        import re as _re
        s = _re.sub(r"[\u200b-\u200f\ufeff]", "", s)  # 零宽/BOM
        s = _re.sub(r"\s+", " ", s).strip()
        return s

    async def _find_conversation_index(self, page: Any, nickname: str) -> int:
        """在会话列表里按昵称匹配。返回 li.semi-list-item 的索引；未找到 -1。

        匹配策略：先精确匹配，再归一化匹配，再包含匹配，重复时取最前（最新）。
        """
        js = """(name) => {
            const rows = Array.from(document.querySelectorAll('li.semi-list-item'));
            const norm = (s) => (s || '').replace(/[\\u200b-\\u200f\\ufeff]/g, '').replace(/\\s+/g, ' ').trim();
            const target = norm(name);
            let exactIdx = -1, normIdx = -1, containsIdx = -1;
            for (let i = 0; i < rows.length; i++) {
                const el = rows[i].querySelector('[class*="item-header-name"]');
                if (!el) continue;
                const raw = (el.textContent || '').trim();
                const n = norm(raw);
                if (raw === name && exactIdx < 0) exactIdx = i;
                if (n === target && normIdx < 0) normIdx = i;
                if (target && n.includes(target) && containsIdx < 0) containsIdx = i;
            }
            if (exactIdx >= 0) return exactIdx;
            if (normIdx >= 0) return normIdx;
            if (containsIdx >= 0) return containsIdx;
            return -1;
        }"""
        try:
            return int(await page.evaluate(js, nickname))
        except Exception:
            return -1

    async def _wait_conversation(self, page: Any, nickname: str, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if await self._find_conversation_index(page, nickname) >= 0:
                return True
            await asyncio.sleep(0.5)
        return False

    async def _click_conversation(self, page: Any, nickname: str) -> bool:
        """点进匹配的会话。用 Playwright 真实鼠标点击（Semi Design React onClick 对 JS click 不稳定）。"""
        idx = await self._find_conversation_index(page, nickname)
        if idx < 0:
            logger.warning("[创作者] 点击前会话消失: nickname=%s", nickname)
            return False
        row = page.locator("li.semi-list-item").nth(idx)
        try:
            await row.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        # 优先 Playwright 真实鼠标 click；失败再试 dispatch_event；都失败用 JS click 兜底。
        # 每次尝试后校验该 <li> 是否获得 active 类（服务端真正 onClick 触发路由切换的信号）。
        async def _active_ok() -> bool:
            # 短暂等待 active 类出现（200ms × 5 = 1s）
            for _ in range(5):
                try:
                    cls = await row.get_attribute("class")
                except Exception:
                    cls = None
                if cls and "active" in cls:
                    return True
                await asyncio.sleep(0.2)
            return False

        click_ok = False
        for attempt in ("click", "dispatch", "js"):
            try:
                if attempt == "click":
                    await row.click(timeout=3000)
                elif attempt == "dispatch":
                    await row.dispatch_event("click")
                else:
                    await page.evaluate(
                        "(el) => el.click()",
                        await row.element_handle(),
                    )
            except Exception as e:
                logger.warning("[创作者] 会话点击 %s 失败: %s", attempt, e)
                continue
            if await _active_ok():
                click_ok = True
                logger.info("[创作者] 会话点击成功 | 方式=%s（active 已激活）", attempt)
                break
            logger.info("[创作者] 会话 %s 已发事件但 active 未激活，换下一种", attempt)
        if not click_ok:
            logger.warning("[创作者] 所有点击方式都未使 <li> 获得 active 类")
            return False
        # 等输入框出现，表示聊天界面渲染完成（active 已确认，输入框应很快出现；超时 8s）
        try:
            await page.wait_for_selector(
                sel.CREATOR_INPUT_SELECTOR, state="visible", timeout=8000
            )
        except Exception:
            try:
                snippet = await page.evaluate(
                    "() => (document.body.innerText || '').slice(0, 300)"
                )
            except Exception:
                snippet = ""
            logger.warning("[创作者] active 已激活但输入框未出现 | 页面摘要: %s", snippet)
            return False
        return True

    # ---------------- 消息注入 ----------------
    async def _insert_message(self, page: Any, message: str) -> bool:
        try:
            ok = await page.evaluate(
                """(payload) => {
                    const {selector, text} = payload;
                    const el = document.querySelector(selector);
                    if (!el) return false;
                    el.focus();
                    // 先清空（防止上次残留）
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    const selObj = window.getSelection();
                    selObj.removeAllRanges();
                    selObj.addRange(range);
                    document.execCommand('delete', false);
                    // 插入文本
                    document.execCommand('insertText', false, text);
                    el.dispatchEvent(new InputEvent('input', {
                        bubbles: true,
                        inputType: 'insertText',
                        data: text,
                    }));
                    return true;
                }""",
                {"selector": sel.CREATOR_INPUT_SELECTOR, "text": message},
            )
        except Exception as e:
            logger.warning("注入文本异常: %s", e)
            return False
        return bool(ok)

    async def _click_send(self, page: Any) -> bool:
        """等发送按钮脱离 disabled → 点击。"""
        try:
            await page.wait_for_function(
                """(selector) => {
                    const btn = document.querySelector(selector);
                    return btn && !btn.disabled;
                }""",
                arg=sel.CREATOR_SEND_BTN_SELECTOR,
                timeout=int(_SEND_BTN_WAIT * 1000),
            )
        except Exception:
            return False
        try:
            await page.click(sel.CREATOR_SEND_BTN_SELECTOR, timeout=3000)
        except Exception as e:
            logger.warning("点击发送按钮异常: %s", e)
            return False
        return True

    # ---------------- 结果验证 ----------------
    async def _verify_result(self, page: Any, message: str) -> SendResult:
        """
        成功：聊天区最新气泡文本 == 刚发消息 + 无 error toast
        失败：出现 .semi-toast-error（取文案，business，不可重试）
        """
        needle = (message or "").strip()
        needle_prefix = needle[:20] if len(needle) > 20 else needle
        deadline = time.monotonic() + _BUBBLE_VERIFY_WAIT

        js_check = """(payload) => {
            const {bubbleSel, toastSel, needle, prefix} = payload;
            // 错误 toast 优先
            const toasts = document.querySelectorAll(toastSel);
            if (toasts.length > 0) {
                const texts = Array.from(toasts).map(n => (n.textContent || '').trim()).filter(Boolean);
                if (texts.length > 0) return {type: 'error', text: texts[texts.length - 1]};
            }
            // 气泡文本：先尝试 chat-bubble 前缀；如前缀不中，降级扫全聊天区
            const bubbles = document.querySelectorAll(bubbleSel);
            const list = bubbles.length > 0
                ? Array.from(bubbles)
                : Array.from(document.querySelectorAll('[class*="chat-"]'));
            for (let i = list.length - 1; i >= 0; i--) {
                const t = (list[i].textContent || '').trim();
                if (t && (t === needle || t.includes(needle) || (prefix && t.includes(prefix)))) {
                    return {type: 'success'};
                }
            }
            return {type: 'pending'};
        }"""

        while time.monotonic() < deadline:
            try:
                res = await page.evaluate(
                    js_check,
                    {
                        "bubbleSel": sel.CREATOR_MSG_BUBBLE,
                        "toastSel": sel.CREATOR_ERROR_TOAST,
                        "needle": needle,
                        "prefix": needle_prefix,
                    },
                )
                if not isinstance(res, dict):
                    continue  # CDP 偶发断连 / JS 返回异常，下一轮再试
                if res.get("type") == "success":
                    return SendResult(
                        success=True, failure_type=None, failure_reason=None, retryable=False
                    )
                if res.get("type") == "error":
                    return SendResult(
                        success=False,
                        failure_type="business",
                        failure_reason=f"创作者中心错误提示: {res.get('text', '')}",
                        retryable=False,
                    )
            except Exception:
                pass
            await asyncio.sleep(0.3)
        return SendResult(
            success=False,
            failure_type="technical",
            failure_reason=f"发送后 {_BUBBLE_VERIFY_WAIT}s 未检测到气泡或错误提示",
            retryable=True,
        )
