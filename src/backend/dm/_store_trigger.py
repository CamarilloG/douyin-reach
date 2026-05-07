"""主站私信浮窗的 store 直驱触发（共用工具）。

背景（2026-04-21 调研，docs/DOM调研.txt）：
抖音主站用户页挂载了 MobX 的 `window.conversationStore`，点击「私信」按钮的
唯一可观测副作用是 `setCurConversation("0:1:<min>:<max>")`。只要拿到
`from_uid` / `to_uid`，就能直接调 store 触发浮窗挂载，**完全不走 DOM**。

适用场景：
- 主站 DMSender：跳过"找按钮 → scroll → click → 重试 click"链路，省 5–15s/条
- 创作者 CreatorDMSender 的 _light_touch_main：同上，仅做"轻触发"

成功仅代表 setCurConversation 被调成功，**不代表浮窗已展开**。展开判定见
`wait_popup_ready()` —— 必须用两道闸（容器尺寸 + 系统提示文字），否则会出现
"selector visible 命中但内部组件还在异步 mount" 的 false positive。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from src.backend.browser import selectors as sel

logger = logging.getLogger(__name__)


async def trigger_via_store(page: Any, sec_uid: str) -> tuple[bool, Optional[str]]:
    """通过 window.conversationStore.setCurConversation 触发私信浮窗。

    返回 (是否触发成功, 失败原因) — 失败时调用方应回落到 DOM click 路径。
    """
    # 1) 等 conversationStore 挂载（SPA 异步初始化最多 10s）
    try:
        await page.wait_for_function(
            "() => typeof window.conversationStore === 'object' && window.conversationStore !== null "
            "&& typeof window.conversationStore.setCurConversation === 'function'",
            timeout=10000,
        )
    except Exception:
        return False, "conversationStore_not_ready"

    # 2) 抠 from_uid/to_uid → BigInt 升序排序拼 conv_id → setCurConversation
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
        "store 直驱已调 setCurConversation | convId=%s fromUid=%s toUid=%s",
        result.get("convId"),
        result.get("fromUid"),
        result.get("toUid"),
    )
    return True, None


async def wait_popup_ready(
    page: Any,
    *,
    expand_timeout: int = 10000,
    hint_timeout: int = 2000,
    fallback_buffer_s: float = 2.0,
) -> bool:
    """store 直驱后等浮窗"真正可交互"——与创作者通道 _wait_dialog_and_hint 同款两道闸。

    1) 容器尺寸闸：[data-e2e="im-dialog"] 的 boundingClientRect width/height > 100。
       必要不充分:外壳撑开 ≠ 内部组件 mount 完。
    2) 系统提示文字闸:浮窗 innerText 包含 "只能发送一条"(陌生人会话必出)。
       这是浮窗内部组件 mount 完成的可靠信号。捕获不到则给固定 2s 缓冲(老会话/
       熟人会话不会有"只能发送一条"提示)。

    返回 True 仅当容器尺寸闸通过(尺寸不达标返回 False,调用方应回落 DOM click)。
    传 expand_timeout=0 跳过闸 1(浮窗已通过 click 路径打开,尺寸已经 OK 的场景)。
    """
    # 闸 1:容器尺寸 > 100×100 (expand_timeout=0 时跳过)
    if expand_timeout > 0:
        try:
            await page.wait_for_function(
                """(s) => {
                    const d = document.querySelector(s);
                    if (!d) return false;
                    const r = d.getBoundingClientRect();
                    return r.width > 100 && r.height > 100;
                }""",
                arg=sel.DM_DIALOG_SELECTOR,
                timeout=expand_timeout,
            )
        except Exception:
            return False

    # 闸 2:系统提示文字 / 固定缓冲
    try:
        await page.wait_for_function(
            """(args) => {
                const [dialogSel, keyword] = args;
                const c = document.querySelector(dialogSel);
                if (!c) return false;
                return (c.innerText || '').includes(keyword);
            }""",
            arg=[sel.DM_DIALOG_SELECTOR, sel.DM_ONE_MSG_LIMIT],
            timeout=hint_timeout,
        )
        logger.debug("浮窗系统提示已出现 -> 内部组件 mount 完成")
    except Exception:
        logger.debug("未捕获「%s」提示(可能是老会话),回落固定 %.1fs 缓冲", sel.DM_ONE_MSG_LIMIT, fallback_buffer_s)
        await asyncio.sleep(fallback_buffer_s)
    return True
