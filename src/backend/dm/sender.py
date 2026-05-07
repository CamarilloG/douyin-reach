"""
私信发送（M5）：DOM 自动化打开用户主页 → 点击私信 → 填入消息 → 发送 → 检测结果。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from src.backend.browser import BrowserEngine
from src.backend.browser import selectors as sel
from src.backend.browser.risk import RiskLevel
from ._store_trigger import trigger_via_store, wait_popup_ready

logger = logging.getLogger(__name__)

_DETECT_TIMEOUT = 5.0
_MAX_RETRY = 2
_RETRY_BACKOFF = 10.0


@dataclass
class SendResult:
    success: bool
    failure_type: Optional[str]  # technical / business / None
    failure_reason: Optional[str]
    retryable: bool


class DMSender:
    """私信发送器，基于 DOM 自动化。"""

    def __init__(self, browser: BrowserEngine) -> None:
        self._browser = browser
        self._send_count = 0

    def render_message(self, template: Any, *, index: int = 0, **_ignored: Any) -> str:
        """取最终消息文本。多模板按 index 轮询返回原文(不做变量替换)。"""
        from .template import render_template
        return render_template(template, index=index)

    async def send_dm(self, sec_uid: str, message: str) -> SendResult:
        """
        向指定用户发送私信。
        流程：打开用户主页 → 点击私信 → 定位输入框 → 填入消息 → 回车 → 检测结果。
        """
        page = self._browser._page if hasattr(self._browser, "_page") else None
        if not page:
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

        try:
            t0 = time.monotonic()
            url = sel.USER_URL_TEMPLATE.format(sec_uid=sec_uid)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # 等用户主页主要容器可见（visible 而非 attached，确保渲染完成）
            try:
                await page.wait_for_selector(
                    '[data-e2e="user-detail"], .author-card, button:has-text("私信")',
                    state="visible",
                    timeout=10000,
                )
            except Exception:
                pass
            await asyncio.sleep(0.3)
            t_page = time.monotonic()
            logger.info("[计时] 主页加载 %.1fs | sec_uid=%s", t_page - t0, sec_uid[:20])

            # 检查页面是否跳转到了错误页面(用户不存在/隐私账号)
            current_url = page.url
            if "/user/" not in current_url:
                logger.warning("用户主页跳转异常，当前URL: %s", current_url)
                return SendResult(
                    success=False,
                    failure_type="business",
                    failure_reason="用户主页不可访问（可能已注销或为隐私账号）",
                    retryable=False,
                )

            # ========== 合并检测：新手引导 + 风控 + 私信按钮，单次 evaluate ==========
            # 将原来的 dismiss_newbie_guide() (~3 CDP)、check_page_danger() (~7 CDP)、
            # 按钮查找 evaluate 合并为 1 次 CDP 往返，消除 5-10s 延迟。
            t_btn0 = time.monotonic()
            combined = await page.evaluate("""(args) => {
                const [dangerTexts, captchaSelectors, newbieText] = args;
                const result = {
                    newbieFound: false,
                    dangerText: null,
                    captchaSelector: null,
                    dmButtons: [],
                    pageSnippet: ''
                };

                // 1. 新手引导检测
                const allBtns = document.querySelectorAll('button, [role="button"], a, span');
                for (let i = 0; i < allBtns.length; i++) {
                    const el = allBtns[i];
                    if ((el.textContent || '').trim() === newbieText) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && el.offsetParent !== null) {
                            el.click();
                            result.newbieFound = true;
                            break;
                        }
                    }
                }

                // 2. 风控文案检测（排除 UGC 区域）
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
                    for (const sel of ugcSelectors) {
                        for (const el of clone.querySelectorAll(sel)) el.remove();
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

                // 3. 验证码 DOM 检测
                for (const sel of captchaSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && el.offsetParent !== null) {
                            result.captchaSelector = sel;
                            return result;
                        }
                    }
                }

                // 4. 私信按钮查找
                const btns = document.querySelectorAll('button, [role="button"]');
                for (let i = 0; i < btns.length; i++) {
                    const btn = btns[i];
                    const text = (btn.textContent || '').trim();
                    if (text !== '私信') continue;
                    const rect = btn.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (btn.offsetParent === null) continue;
                    const inDetail = !!btn.closest('[data-e2e="user-detail"]');
                    result.dmButtons.push({ index: i, priority: inDetail ? 0 : 1, y: rect.y });
                }

                // 5. 无按钮时取页面摘要（用于诊断）
                if (result.dmButtons.length === 0) {
                    result.pageSnippet = (document.body.innerText || '').slice(0, 500);
                }

                return result;
            }""", [
                list(sel.DANGER_PAGE_TEXTS),
                list(sel.CAPTCHA_DOM_SELECTORS),
                sel.NEWBIE_GUIDE_DISMISS_TEXT,
            ])
            logger.info("[计时] 合并检测 %.1fs | 新手引导=%s 风控=%s 验证码=%s 按钮数=%d",
                        time.monotonic() - t_btn0,
                        combined.get("newbieFound"),
                        combined.get("dangerText"),
                        combined.get("captchaSelector"),
                        len(combined.get("dmButtons", [])))

            # 处理风控检测结果
            if combined.get("dangerText"):
                self._browser._risk_state.trigger_danger(
                    f"页面出现危险文案: {combined['dangerText']} | snippet={combined.get('pageSnippet', '')}"
                )
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="检测到验证码/风控浮层，请手动完成验证",
                    retryable=True,
                )
            if combined.get("captchaSelector"):
                self._browser._risk_state.trigger_danger(
                    f"检测到验证码浮层: {combined['captchaSelector']}"
                )
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="检测到验证码/风控浮层，请手动完成验证",
                    retryable=True,
                )

            # ---------- 浮窗就绪等待器 (store 直驱与 DOM click 兜底两条路径共用) ----------
            _popup_selector = ", ".join([
                sel.DM_INPUT_SELECTOR,
                sel.DM_INPUT_SELECTOR_ALT,
                sel.DM_ENTRY_SELECTOR + " " + sel.DM_MSG_INPUT_CONTAINER,
            ])

            async def _wait_popup(timeout_ms: int) -> bool:
                try:
                    await page.wait_for_selector(_popup_selector, state="visible", timeout=timeout_ms)
                    return True
                except Exception:
                    return False

            # ---------- 首选: store 直驱 (零 DOM,省 5-15s/条) ----------
            # 与创作者通道 _light_touch_main 同款机制 (dm/_store_trigger.py)。
            # 直接调 window.conversationStore.setCurConversation 触发浮窗,
            # 跳过 "找按钮 → scroll → click → 失败重试 click" 整段链路,且抗按钮 hash 漂移。
            # 失败自动回落 DOM click 路径,fail-closed 行为完全不变。
            popup_method = ""
            click_method = "skip(store_direct)"
            t_store0 = time.monotonic()
            opened = False
            # store 直驱后浮窗"已可交互"判定 = 共用 wait_popup_ready (创作者通道实测稳定):
            #   闸 1: [data-e2e="im-dialog"] boundingClientRect > 100×100 (外壳撑开)
            #   闸 2: 浮窗 innerText 包含 "只能发送一条" (内部组件 mount 完成),
            #         捕获不到则固定 2s 缓冲 (老会话不会有此提示)
            # 之前漏抄闸 2 时,实测 input_el.click(3000ms) 在浮窗"半就绪"状态下 timeout。
            store_ok, store_err = await trigger_via_store(page, sec_uid)
            if store_ok:
                if await wait_popup_ready(page):
                    opened = True
                    popup_method = "store 直驱"
                    logger.info(
                        "[计时] store 直驱 + 浮窗就绪 %.1fs | 跳过 DOM 按钮点击",
                        time.monotonic() - t_store0,
                    )
                else:
                    logger.info(
                        "[计时] store 调用成功但浮窗 %.1fs 内未达可交互状态,回落 DOM click",
                        time.monotonic() - t_store0,
                    )
            else:
                logger.info("store 直驱不可用 (%s) | 走 DOM 兜底", store_err)

            t_click = time.monotonic()  # 给后续 [计时] 日志一个合理基准

            # ---------- 兜底: DOM click (原逻辑) ----------
            if not opened:
                candidates_raw = combined.get("dmButtons", [])

                # 按钮未找到时，可能是页面尚未渲染完成（SPA 异步加载），轮询重试最多 3s
                if not candidates_raw:
                    # 先检查是否明确为不可达用户（不需要重试）
                    page_text = combined.get("pageSnippet", "")
                    if "用户不存在" in page_text or "该页面" in page_text or "无法访问" in page_text:
                        logger.warning("无私信按钮(用户不可达) | URL=%s | 页面摘要: %s", current_url, page_text[:100])
                        return SendResult(
                            success=False,
                            failure_type="business",
                            failure_reason="用户页面不可访问（不存在或隐私账号）",
                            retryable=False,
                        )
                    # 页面可能还在渲染，轮询等待私信按钮出现
                    _JS_FIND_DM_BTNS = """() => {
                        const results = [];
                        const btns = document.querySelectorAll('button, [role="button"]');
                        for (let i = 0; i < btns.length; i++) {
                            const btn = btns[i];
                            const text = (btn.textContent || '').trim();
                            if (text !== '私信') continue;
                            const rect = btn.getBoundingClientRect();
                            if (rect.width <= 0 || rect.height <= 0) continue;
                            if (btn.offsetParent === null) continue;
                            const inDetail = !!btn.closest('[data-e2e="user-detail"]');
                            results.push({ index: i, priority: inDetail ? 0 : 1, y: rect.y });
                        }
                        return results;
                    }"""
                    for _retry in range(6):  # 6 × 0.5s = 3s
                        await asyncio.sleep(0.5)
                        candidates_raw = await page.evaluate(_JS_FIND_DM_BTNS)
                        if candidates_raw:
                            logger.info("[计时] 按钮重试 %d 次后找到 | 额外等待 %.1fs", _retry + 1, (_retry + 1) * 0.5)
                            break

                if not candidates_raw:
                    page_text = ""
                    try:
                        page_text = await page.evaluate("() => (document.body.innerText || '').slice(0, 500)")
                    except Exception:
                        pass
                    reason = "未找到可见的私信按钮"
                    if "用户不存在" in page_text or "该页面" in page_text or "无法访问" in page_text:
                        reason = "用户页面不可访问（不存在或隐私账号）"
                        logger.warning("无私信按钮(用户不可达) | URL=%s | 页面摘要: %s", current_url, page_text[:100])
                        return SendResult(
                            success=False,
                            failure_type="business",
                            failure_reason=reason,
                            retryable=False,
                        )
                    logger.warning("无私信按钮(重试后仍未找到) | URL=%s | 页面摘要: %s", current_url, page_text[:100])
                    return SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason=reason,
                        retryable=True,
                    )

                # 排序：先按 priority（user-detail 内优先），再按 y 坐标大
                candidates_raw.sort(key=lambda c: (c["priority"], -c.get("y", 0)))
                chosen = candidates_raw[0]
                dm_btn = page.locator('button, [role="button"]').nth(chosen["index"])
                logger.info("选中私信按钮: priority=%d, y=%.0f, 候选详情=%s",
                            chosen["priority"], chosen.get("y", 0), candidates_raw)

                try:
                    await dm_btn.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass

                # 点击并记录通过哪种方式成功
                click_method = "unknown"
                try:
                    await dm_btn.click(timeout=5000)
                    click_method = "click()"
                except Exception as e:
                    logger.warning("私信按钮常规 click 失败: %s，尝试 dispatch_event", e)
                    try:
                        await dm_btn.dispatch_event("click")
                        click_method = "dispatch_event"
                    except Exception as e2:
                        logger.warning("dispatch_event 也失败: %s", e2)
                        click_method = "both_failed"
                t_click = time.monotonic()
                logger.info("[计时] 按钮点击 %.1fs | 方式: %s", t_click - t_btn0, click_method)

                opened = await _wait_popup(15000)
                popup_method = "DOM 首次等待" if opened else ""
                if not opened:
                    logger.info("首次等待浮窗失败(15s)，重试点击")
                    try:
                        await dm_btn.dispatch_event("click")
                    except Exception:
                        pass
                    try:
                        await dm_btn.click(timeout=3000, force=True)
                    except Exception:
                        pass
                    opened = await _wait_popup(10000)
                    if opened:
                        popup_method = "DOM 重试点击后等待"

            t_popup = time.monotonic()
            if opened:
                # 检测实际匹配到哪个选择器
                matched_sel = "unknown"
                for name, s in [
                    ("DM_INPUT_SELECTOR", sel.DM_INPUT_SELECTOR),
                    ("DM_INPUT_SELECTOR_ALT", sel.DM_INPUT_SELECTOR_ALT),
                    ("DM_ENTRY+MSG_INPUT", sel.DM_ENTRY_SELECTOR + " " + sel.DM_MSG_INPUT_CONTAINER),
                ]:
                    try:
                        el = page.locator(s).first
                        if await el.count() > 0 and await el.is_visible():
                            matched_sel = name
                            break
                    except Exception:
                        continue
                logger.info("[计时] 浮窗打开 %.1fs | 途径: %s | 匹配选择器: %s | 按钮点击方式: %s",
                            t_popup - t_click, popup_method, matched_sel, click_method)
            else:
                logger.warning("[计时] 浮窗打开失败 %.1fs | 已重试", t_popup - t_click)
                # 抓页面 HTML 留证,供下一次排查 DOM 漂移 / 登录态 / 用户不可达
                try:
                    from src.backend.utils.paths import get_data_path

                    snap_path = get_data_path(f"debug_dm_popup_fail_{sec_uid[:16]}.html")
                    snap_html = await page.content()
                    with open(snap_path, "w", encoding="utf-8") as f:
                        f.write(snap_html)
                    logger.warning("[诊断] 已抓页面 HTML 留证:%s", snap_path)
                except Exception as _snap_err:
                    logger.debug("抓 popup-fail 快照失败: %s", _snap_err)
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="私信浮窗打开超时（msg-input 未出现）",
                    retryable=True,
                )

            self._send_count += 1
            if self._send_count % 5 == 1:  # 每 5 条检查一次（首条必检）
                await self._browser.check_page_danger()
                if self._browser.get_risk_level() == RiskLevel.DANGER:
                    return SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason="检测到验证码/风控浮层，请手动完成验证",
                        retryable=True,
                    )

            # 定位私信输入框：OR 选择器合并两级候选，单次 CDP 往返。
            # 搜索框是 <input>（非 contenteditable），天然不会命中。
            input_el = page.locator(f"{sel.DM_INPUT_SELECTOR}, {sel.DM_INPUT_SELECTOR_ALT}").first
            if await input_el.count() == 0:
                return SendResult(
                    success=False,
                    failure_type="technical",
                    failure_reason="未找到私信输入框（msg-input 容器或 DraftJS 容器缺失）",
                    retryable=True,
                )

            # contenteditable div 需用 click + type 而非 fill
            t_input0 = time.monotonic()
            await input_el.click(timeout=3000)
            await asyncio.sleep(0.2)
            await input_el.press_sequentially(message, delay=30)
            await asyncio.sleep(0.3)

            # 点击发送按钮（<span class="e2e-send-msg-btn">，无 disabled，直接 click）
            send_method = "unknown"
            send_btn = page.locator(sel.DM_SEND_BTN_SELECTOR).first
            if await send_btn.count() == 0:
                send_btn = page.locator(f'.{sel.DM_SEND_BTN_CLASS}').first
            if await send_btn.count() == 0:
                await input_el.press("Enter")
                send_method = "Enter键"
            else:
                await send_btn.click(timeout=3000)
                send_method = "发送按钮"
            t_send = time.monotonic()
            logger.info("[计时] 输入+发送 %.1fs | 发送方式: %s | 消息长度: %d",
                        t_send - t_input0, send_method, len(message))

            # 检测发送结果
            result = await self._detect_send_result(page, message)
            t_total = time.monotonic()
            logger.info("[计时] 结果检测 %.1fs | 总耗时 %.1fs | 结果: %s",
                        t_total - t_send, t_total - t0,
                        "成功" if result.success else f"失败({result.failure_reason})")
            return result
        except Exception as e:
            logger.warning("发送私信异常: %s", e)
            return SendResult(
                success=False,
                failure_type="technical",
                failure_reason=str(e),
                retryable=True,
            )

    async def _detect_send_result(self, page: Any, sent_message: str) -> SendResult:
        """
        检测发送结果：优先看成功标志，再看失败文案。

        关键事实：
        - 「只能发送一条消息」是静态提示，不是失败标志。
        - 真正的失败会出现「发送失败」红字 toast。
        - 成功判定：IM 对话区出现我们刚发送的文本前缀。
        - 使用 page.evaluate 替代 page.content()，仅扫描 IM 容器内文本，
          避免序列化整个 DOM（数百 KB/次）。轮询间隔 300ms（总预算 ~4.5s）。
        """
        needle = (sent_message or "").strip()
        needle_prefix = needle[:10] if len(needle) >= 10 else needle

        _JS_DETECT = """(args) => {
            const [needle, prefix] = args;
            const c = document.querySelector('[data-e2e="im-entry"]') || document.body;
            const t = c.innerText || '';
            if (needle && (t.includes(needle) || (prefix && t.includes(prefix)))) return 'success';
            if (t.includes('发送失败')) return 'fail';
            return 'pending';
        }"""

        for _ in range(15):  # 15 × 0.3s ≈ 4.5s
            await asyncio.sleep(0.3)
            try:
                result = await page.evaluate(_JS_DETECT, [needle, needle_prefix])
                if result == "success":
                    return SendResult(success=True, failure_type=None, failure_reason=None, retryable=False)
                if result == "fail":
                    return SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason="发送失败",
                        retryable=True,
                    )
            except Exception:
                pass
        return SendResult(
            success=False,
            failure_type="technical",
            failure_reason="发送超时，未检测到结果",
            retryable=True,
        )
