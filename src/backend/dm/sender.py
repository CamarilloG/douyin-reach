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

            # body.cloneNode(true) 这种重操作绝不能在 store 直驱前调用 —— 实测它会同步
            # 阻塞主线程几百 ms,期间 conversationStore 异步初始化时序错位,导致 trigger_via_store
            # 拿到陈旧 store 或 wait_for_function 超时。对齐 _light_touch_main 的顺序后稳定性回升。
            t_btn0 = time.monotonic()  # 给"按钮点击"[计时] 一个 fallback 基准（DOM 兜底里会重置）

            # ========== 合并检测 helper（仅在 DOM 兜底路径里调用）==========
            # 按钮查找逻辑跟创作者通道 sender_creator._light_touch_main 对齐(2026-05 调研后修正):
            #   - 文本从 span.semi-button-content 精确取(Semi 设计系统类,稳定)
            #   - 黑名单 [data-e2e="im-entry"]: 顶栏的"私信"包装,click 后跳全局消息中心,不弹浮窗
            #   - 黑名单 [data-e2e="im-dialog"]: 浮窗内可能也有自引用的"私信"按钮
            #   - 可见性用 computed style 判,不用 offsetParent(fixed 定位会被误杀)
            #   - 诊断候选: 失败时附带所有命中"私信"文本的 button(含不可见+黑名单)+容器路径
            async def _run_dom_precheck() -> tuple[Optional[dict[str, Any]], Optional[SendResult]]:
                """合并 evaluate (含 newbie 关闭 / 风控 / 验证码 / 私信按钮查找)。
                返回 (combined_dict, fatal_result)。fatal_result 非 None 时调用方应直接 return。
                注意 body.cloneNode(true) 是个重操作,会同步阻塞主线程几百 ms,因此**绝不能**
                在 store 直驱前调用 (会让 conversationStore 异步初始化时序错位)。
                """
                _t0 = time.monotonic()
                _combined = await page.evaluate("""(args) => {
                const [dangerTexts, captchaSelectors, newbieText, userDetailSel] = args;
                const result = {
                    newbieFound: false,
                    dangerText: null,
                    captchaSelector: null,
                    dmButtons: [],
                    diagCandidates: [],
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

                // 4. 私信按钮查找(对齐创作者通道写法)
                const allDocBtns = Array.from(document.querySelectorAll('button'));
                const detailEl = document.querySelector(userDetailSel);

                const extractText = (btn) => {
                    // 优先 Semi 的 span.semi-button-content,文本干净;fallback btn.textContent
                    const span = btn.querySelector('span[class*="semi-button-content"]');
                    if (span) return (span.textContent || '').trim();
                    return (btn.textContent || '').trim();
                };

                const describeContainer = (btn) => {
                    const anchors = [
                        '[data-e2e="user-detail"]', '[data-e2e="user-info"]',
                        '[data-e2e="im-entry"]', '[data-e2e="im-dialog"]'
                    ];
                    for (const a of anchors) {
                        if (btn.closest(a)) return a;
                    }
                    return '(other)';
                };

                for (const btn of allDocBtns) {
                    const text = extractText(btn);
                    if (text !== '私信') continue;
                    // 黑名单: 顶部导航 / 浮窗自引用 (click 后跳消息中心或冒泡到自身,绝不会弹浮窗)
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
                        visible, inDetail,
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        container: describeContainer(btn)
                    });

                    if (!visible) continue;
                    result.dmButtons.push({
                        index: globalIndex,
                        y: rect.y,
                        inDetail,
                        priority: inDetail ? 0 : 1
                    });
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
                    sel.USER_DETAIL_CONTAINER,
                ])
                logger.info("[计时] 合并检测 %.1fs | 新手引导=%s 风控=%s 验证码=%s 候选=%d 可见可选=%d",
                            time.monotonic() - _t0,
                            _combined.get("newbieFound"),
                            _combined.get("dangerText"),
                            _combined.get("captchaSelector"),
                            len(_combined.get("diagCandidates", [])),
                            len(_combined.get("dmButtons", [])))
                # 风控/验证码 → 致命结果
                if _combined.get("dangerText"):
                    self._browser._risk_state.trigger_danger(
                        f"页面出现危险文案: {_combined['dangerText']} | snippet={_combined.get('pageSnippet', '')}"
                    )
                    return None, SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason="检测到验证码/风控浮层，请手动完成验证",
                        retryable=True,
                    )
                if _combined.get("captchaSelector"):
                    self._browser._risk_state.trigger_danger(
                        f"检测到验证码浮层: {_combined['captchaSelector']}"
                    )
                    return None, SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason="检测到验证码/风控浮层，请手动完成验证",
                        retryable=True,
                    )
                return _combined, None

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

            # ---------- 兜底: DOM click (对齐创作者通道写法) ----------
            if not opened:
                # 现在才做合并 evaluate (store 直驱失败时才付出 cloneNode 重操作的代价)
                combined, fail_result = await _run_dom_precheck()
                if fail_result is not None:
                    return fail_result
                assert combined is not None  # for type checkers
                t_btn0 = time.monotonic()  # 给后续按钮点击 [计时] 一个准确基准
                candidates_raw = combined.get("dmButtons", [])
                diag_first = combined.get("diagCandidates", [])

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
                    # 页面可能还在渲染，轮询等待私信按钮出现 (作用域和文本提取与首次一致)
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
                    for _retry in range(6):  # 6 × 0.5s = 3s
                        await asyncio.sleep(0.5)
                        try:
                            r = await page.evaluate(_JS_FIND_DM_BTNS, sel.USER_DETAIL_CONTAINER)
                            candidates_raw = r.get("buttons", []) if isinstance(r, dict) else []
                            last_diag = r.get("diag", []) if isinstance(r, dict) else []
                        except Exception:
                            candidates_raw = []
                        if candidates_raw:
                            logger.info("[计时] 按钮重试 %d 次后找到 | 额外等待 %.1fs", _retry + 1, (_retry + 1) * 0.5)
                            break
                    diag_first = last_diag

                if not candidates_raw:
                    page_text = ""
                    try:
                        page_text = await page.evaluate("() => (document.body.innerText || '').slice(0, 500)")
                    except Exception:
                        pass
                    if "用户不存在" in page_text or "该页面" in page_text or "无法访问" in page_text:
                        logger.warning("无私信按钮(用户不可达) | URL=%s | 页面摘要: %s", current_url, page_text[:100])
                        return SendResult(
                            success=False,
                            failure_type="business",
                            failure_reason="用户页面不可访问（不存在或隐私账号）",
                            retryable=False,
                        )
                    # 诊断候选(让你能看清是"完全没找到带'私信'文字的 button"还是"找到了但被黑名单/不可见过滤")
                    diag_summary = [
                        f"idx={d.get('index')} visible={d.get('visible')} inDetail={d.get('inDetail')} "
                        f"size={d.get('w')}x{d.get('h')} container={d.get('container', '?')}"
                        for d in (diag_first or [])
                    ]
                    logger.warning(
                        "[主站] 私信按钮未找到 | URL=%s | 候选(%d)=%s | 页面摘要: %s",
                        current_url, len(diag_first or []),
                        " ; ".join(diag_summary) if diag_summary else "空",
                        page_text[:200],
                    )
                    return SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason="未找到可见的私信按钮",
                        retryable=True,
                    )

                # 排序：先按 priority（user-detail 内优先），再按 y 坐标大
                candidates_raw.sort(key=lambda c: (c["priority"], -c.get("y", 0)))
                chosen = candidates_raw[0]
                # ⚠️ 关键 bug fix: chosen.index 来自 Array.from(querySelectorAll('button')),
                # 旧代码用 page.locator('button, [role="button"]').nth(idx) 索引集合不一致,
                # 会点到错的 role="button" 元素 (如顶栏 div), click 后无浮窗弹出。
                dm_btn = page.locator("button").nth(chosen["index"])
                logger.info("[主站] 私信按钮选中 | index=%d y=%.0f inDetail=%s 候选数=%d",
                            chosen["index"], chosen.get("y", 0), chosen.get("inDetail"),
                            len(candidates_raw))

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

                # 浮窗等待：完全对齐创作者通道 _light_touch_main 的稳定模式。
                # 12s 首次等待 → 失败时 dispatch_event + force click 双管齐下 → 8s 二次等待。
                # （之前曾改为 8s 单次 fail-fast 给外层 retry，但失败率显著上升 ——
                # 调研后确认第一次 click 经常因页面事件 handler 未绑定完而无效，
                # 浮窗根本没渲染（debug HTML 印证），不存在"toggle 关浮窗"的风险。
                # 第二次配合更长等待 + force + dispatch_event 才能稳定触发。）
                opened = await _wait_popup(12000)
                popup_method = "DOM 首次等待" if opened else ""
                if not opened:
                    logger.info("首次等待浮窗失败(12s)，再发一次 click + dispatch_event")
                    try:
                        await dm_btn.dispatch_event("click")
                    except Exception:
                        pass
                    try:
                        await dm_btn.click(timeout=3000, force=True)
                    except Exception:
                        pass
                    opened = await _wait_popup(8000)
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
                # 诊断详情：记录每个候选 selector 当前是否在 DOM 中、是否可见、bbox。
                # 这样能直接看出"selector 漂移 vs 浮窗 mount 中 vs 浮窗压根没触发"。
                diag: dict[str, Any] = {}
                for name, s in [
                    ("im-dialog", sel.DM_DIALOG_SELECTOR),
                    ("msg-input", sel.DM_MSG_INPUT_CONTAINER),
                    ("input(e2e)", sel.DM_INPUT_SELECTOR),
                    ("input(alt)", sel.DM_INPUT_SELECTOR_ALT),
                    ("send-btn", sel.DM_SEND_BTN_SELECTOR),
                ]:
                    try:
                        el = page.locator(s).first
                        cnt = await el.count()
                        if cnt == 0:
                            diag[name] = "absent"
                            continue
                        try:
                            visible = await el.is_visible()
                            box = await el.bounding_box()
                            diag[name] = {
                                "visible": visible,
                                "w": int(box["width"]) if box else 0,
                                "h": int(box["height"]) if box else 0,
                            }
                        except Exception as _e:
                            diag[name] = f"present-noprobe({_e!r})"
                    except Exception as _e:
                        diag[name] = f"err({_e!r})"
                try:
                    cur_url = page.url
                except Exception:
                    cur_url = "?"
                logger.warning(
                    "[计时] 浮窗打开失败 %.1fs | URL=%s | click=%s | 候选探测=%s",
                    t_popup - t_click, cur_url, click_method, diag,
                )
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
                    failure_reason="未找到私信输入框（msg-input 容器或 Slate 编辑器缺失）",
                    retryable=True,
                )

            # 输入文本 — 对齐创作者通道 _insert_message 的 execCommand 路径。
            # 之前用 press_sequentially（逐字符按键）在 Slate.js 编辑器上会出现"视觉有文字
            # 但 Slate 内部 model 是空"的 false-input — 此时发送按钮不变红 (publishRedBtn)，
            # click 是 no-op，浮窗一直停在"已开但没发出"的死状态，结果 _detect_send_result
            # 4.5s 超时。execCommand('insertText') + 主动 dispatch InputEvent 是 Slate / DraftJS
            # 都接受的标准路径，创作者通道实测稳定。
            t_input0 = time.monotonic()
            try:
                injected = await page.evaluate(
                    """(payload) => {
                        const {selector, altSelector, text} = payload;
                        const el = document.querySelector(selector) || document.querySelector(altSelector);
                        if (!el) return { ok: false, reason: 'no-editor' };
                        el.focus();
                        // 全选清空（防止上次残留）
                        const range = document.createRange();
                        range.selectNodeContents(el);
                        const selObj = window.getSelection();
                        selObj.removeAllRanges();
                        selObj.addRange(range);
                        try { document.execCommand('delete', false); } catch (_) {}
                        // 插入文本（execCommand 在 contenteditable / Slate / DraftJS 都生效）
                        const inserted = document.execCommand('insertText', false, text);
                        // 主动 dispatch InputEvent 同步框架内部 model
                        el.dispatchEvent(new InputEvent('input', {
                            bubbles: true, inputType: 'insertText', data: text,
                        }));
                        return { ok: !!inserted, reason: inserted ? null : 'execCommand-returned-false' };
                    }""",
                    {
                        "selector": sel.DM_INPUT_SELECTOR,
                        "altSelector": sel.DM_INPUT_SELECTOR_ALT,
                        "text": message,
                    },
                )
            except Exception as e:
                logger.warning("注入文本异常: %s", e)
                injected = {"ok": False, "reason": f"exception:{e}"}
            if not isinstance(injected, dict) or not injected.get("ok"):
                # execCommand 注入失败 → fallback 到 press_sequentially（逐字符按键）
                logger.info("execCommand 注入未生效 (%s), fallback press_sequentially",
                            (injected or {}).get("reason"))
                try:
                    await input_el.click(timeout=3000)
                    await asyncio.sleep(0.2)
                    await input_el.press_sequentially(message, delay=30)
                except Exception as e:
                    return SendResult(
                        success=False,
                        failure_type="technical",
                        failure_reason=f"输入文本失败：{e}",
                        retryable=True,
                    )
            await asyncio.sleep(0.3)

            # 等发送按钮"激活"（svg class 含 Red/Active/Enabled 任一）—
            # 创作者通道走 button.disabled 判定，主站 svg 没有 disabled 属性，
            # 抖音用 class "messageMsgInputpublishRedBtn" 表达激活态。
            # 5s 内未变红 → 输入没真正进入 Slate state，发送会是 no-op，提前失败。
            send_method = "unknown"
            try:
                await page.wait_for_function(
                    """(args) => {
                        const [selector, pattern] = args;
                        const btn = document.querySelector(selector);
                        if (!btn) return false;
                        const cls = btn.getAttribute('class') || '';
                        return new RegExp(pattern).test(cls);
                    }""",
                    arg=[sel.DM_SEND_BTN_SELECTOR, sel.DM_SEND_BTN_ACTIVE_PATTERN],
                    timeout=5000,
                )
                send_btn_ready = True
            except Exception:
                send_btn_ready = False
                logger.warning("[主站] 发送按钮 5s 未激活（class 未含 Red/Active）— 输入可能未进 Slate state")

            send_btn = page.locator(sel.DM_SEND_BTN_SELECTOR).first
            if await send_btn.count() == 0:
                send_btn = page.locator(f'.{sel.DM_SEND_BTN_CLASS}').first

            if not send_btn_ready and await send_btn.count() == 0:
                # 既没激活也找不到按钮 → 用 Enter 兜底
                await input_el.press("Enter")
                send_method = "Enter键(兜底)"
            elif not send_btn_ready:
                # 找到按钮但未激活 → 仍尝试 click（Enter 偶尔不生效），失败由结果检测兜底
                try:
                    await send_btn.click(timeout=3000, force=True)
                    send_method = "发送按钮(未激活强点)"
                except Exception:
                    await input_el.press("Enter")
                    send_method = "Enter键(强点失败兜底)"
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
        检测发送结果：toast 红字 → 浮窗内失败文案 → 浮窗内 needle 命中。

        关键事实：
        - 「只能发送一条消息」是静态提示，不是失败标志。
        - 真正的失败信号有两类：
          1) Semi Design 红字 toast (`.semi-toast-error` 等)
          2) 浮窗内文案命中 DM_FAIL_PHRASES 任一短语
             （"操作太频繁/对方设置/已达上限/已被拉黑/陌生人消息已禁用/网络异常..."）
        - 成功判定：浮窗本体（im-dialog 或 msg-input）的 innerText 含 needle 前缀。
          之前用 [data-e2e="im-entry"] 顶栏容器或 body fallback，body 太宽，
          可能误命中评论区/footer 同字。

        失败 retryable=True：技术失败 / 限速可重试。
        失败 retryable=False：业务约束（拒收/拉黑/禁用）短期内重试无意义，跳过。
        """
        needle = (sent_message or "").strip()
        needle_prefix = needle[:10] if len(needle) >= 10 else needle

        # 失败短语分类：哪些是"业务限制不重试"，哪些是"技术失败可重试"。
        # 业务限制 = 即便重试 100 次结果一样（对方设置/拉黑/陌生人单条限制 / 敏感词 / 账号风控），
        # 直接标 retryable=False 跳到下一个用户，省外层 retry_limit 的等待时间。
        BUSINESS_PHRASES = {
            # 对方拒收 / 隐私 / 黑名单
            "对方设置了", "对方设置不接收", "对方拒绝接收",
            "无法向其发送", "陌生人消息已禁用", "已被对方拉黑", "已禁言",
            # 陌生人单条限制（2026-05 实测：第二次起 WS 服务端拒收 stranger_one_msg_limit）
            "不能再发送消息", "不能再发送",
            # 敏感词 / 内容审核（text_block）
            "内容违规", "包含敏感", "审核未通过",
            # 账号风控（risk_user）— 重试也救不了，需要换号或人工解封
            "账号存在异常",
        }

        _JS_DETECT = """(args) => {
            const [needle, prefix, failPhrases, toastSelectors] = args;
            const out = { result: 'pending', reason: null, hit: null };

            // 1) Toast 红字（最强信号，portal 通常在 body 末尾）
            for (const sel of toastSelectors) {
                const t = document.querySelector(sel);
                if (!t) continue;
                const r = t.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                const txt = (t.textContent || '').trim();
                if (txt) {
                    out.result = 'fail';
                    out.reason = 'toast';
                    out.hit = sel + ': ' + txt.slice(0, 80);
                    return out;
                }
            }

            // 2) 浮窗本体（不是 im-entry 顶栏，是 im-dialog / msg-input 浮窗内）
            const dialog = document.querySelector('[data-e2e="im-dialog"]');
            const msgInput = document.querySelector('[data-e2e="msg-input"]');
            const popup = dialog || msgInput;
            if (!popup) return out;  // 浮窗都消失了 → pending（继续等）
            const popupText = popup.innerText || '';

            // 失败短语扫描
            for (const phrase of failPhrases) {
                if (!phrase) continue;
                if (popupText.includes(phrase)) {
                    out.result = 'fail';
                    out.reason = 'phrase';
                    out.hit = phrase;
                    return out;
                }
            }

            // 3) 视觉失败信号：聊天区出现红色 ❗ 图标（class 含 error/failed/warning/danger）。
            // 调研发现：陌生人单条限制等服务端拒收场景下，气泡左侧会渲染红 ❗ —
            // 客户端乐观渲染会让 needle 命中浮窗 innerText（成功假象），但红 ❗ 不会变。
            // 必须先于 needle 命中检测。
            const errIcon = popup.querySelector(
                '[class*="msg-error"], [class*="MsgError"], [class*="message-error"],' +
                '[class*="send-fail"], [class*="SendFail"], [class*="msg-fail"],' +
                'svg[class*="error"], svg[class*="Error"], svg[class*="warning"]'
            );
            if (errIcon) {
                const r = errIcon.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    out.result = 'fail';
                    out.reason = 'icon';
                    out.hit = (errIcon.getAttribute('class') || '').slice(0, 80);
                    return out;
                }
            }

            // 4) 成功判定：浮窗内出现刚发送的文本（前缀也算）
            if (needle && (popupText.includes(needle) || (prefix && popupText.includes(prefix)))) {
                out.result = 'success';
                return out;
            }
            return out;
        }"""

        last_pending_reason: Optional[str] = None
        for _ in range(15):  # 15 × 0.3s ≈ 4.5s
            await asyncio.sleep(0.3)
            try:
                r = await page.evaluate(
                    _JS_DETECT,
                    [
                        needle,
                        needle_prefix,
                        list(sel.DM_FAIL_PHRASES),
                        list(sel.DM_TOAST_ERROR_SELECTORS),
                    ],
                )
                if not isinstance(r, dict):
                    continue
                state = r.get("result")
                if state == "success":
                    return SendResult(success=True, failure_type=None, failure_reason=None, retryable=False)
                if state == "fail":
                    reason_kind = r.get("reason") or "?"
                    hit = r.get("hit") or "?"
                    # 业务短语命中 → 不可重试（节省外层 retry 时间）
                    is_business = (
                        reason_kind == "phrase"
                        and any(b in hit for b in BUSINESS_PHRASES)
                    )
                    logger.warning(
                        "[主站] 发送失败信号 | 类型=%s | 命中=%s | retryable=%s",
                        reason_kind, hit, not is_business,
                    )
                    return SendResult(
                        success=False,
                        failure_type="business" if is_business else "technical",
                        failure_reason=f"{reason_kind}: {hit}",
                        retryable=not is_business,
                    )
                last_pending_reason = "no-popup" if r.get("reason") is None else r.get("reason")
            except Exception:
                pass
        logger.warning(
            "[主站] 发送结果检测超时 4.5s | 最后状态=%s | needle_prefix=%r",
            last_pending_reason, needle_prefix,
        )
        return SendResult(
            success=False,
            failure_type="technical",
            failure_reason="发送超时，未检测到结果",
            retryable=True,
        )
