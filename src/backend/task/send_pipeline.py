"""
发送流水线（M5）：从 target_list 取待发用户，DOM 自动化发私信，限速与上限，失败分类与重试。
"""
from __future__ import annotations

import asyncio
import logging
import random
import threading
from datetime import datetime
from typing import Any, Optional

from src.backend.data import db, crud
from src.backend.browser import BrowserEngine
from src.backend.dm import DMSender, CreatorDMSender
from .state import (
    TaskStatus,
    ensure_transition,
    set_task_status,
    claim_sending,
    release_sending,
)

logger = logging.getLogger(__name__)

_SEND_INTERVAL_DEFAULT = 45
_INTERVAL_JITTER = 0.3
_DAILY_LIMIT_DEFAULT = 30
_TASK_LIMIT_DEFAULT = 50
# 外层重试上限（每个用户最多 1+_MAX_RETRY 次完整尝试，超出标记 failed 并跳到下一个）。
# 之前默认 2 + 单次 send_dm 最多 ~40s + 二次重试点击同一按钮 → 单用户最坏卡 ~140s，
# 视觉上像"反复操作同一用户"。改为 1：单用户最坏 ~60s，明显减少滞留。
# 用户可通过 task.retry_limit 字段覆盖（前端"任务编辑→失败重试上限"）。
_MAX_RETRY = 1
_RETRY_BACKOFF = 10.0

# 发送中暂停/停止标志（通过任务状态判断）
_stop_requested: dict[int, bool] = {}
_lock = threading.Lock()


def _conn():
    return db.get_connection()


def _task_status(task_id: int) -> Optional[str]:
    conn = _conn()
    try:
        t = crud.task_get(conn, task_id)
        return t["status"] if t else None
    finally:
        conn.close()


def _request_stop(task_id: int) -> None:
    with _lock:
        _stop_requested[task_id] = True


def _clear_stop(task_id: int) -> None:
    with _lock:
        _stop_requested.pop(task_id, None)


def _is_stopped(task_id: int) -> bool:
    with _lock:
        return _stop_requested.get(task_id, False)


def run_sending(task_id: int) -> bool:
    """启动发送流水线，后台线程执行。"""
    status = _task_status(task_id)
    if status is None:
        return False
    if not ensure_transition(status, TaskStatus.sending.value):
        logger.warning("任务 %s 状态 %s 不允许启动发送", task_id, status)
        return False
    if not claim_sending(task_id):
        logger.warning("已有其他任务在发送中，无法启动任务 %s", task_id)
        return False

    def _run() -> None:
        try:
            _clear_stop(task_id)
            asyncio.run(_run_sending_async(task_id))
        except Exception as e:
            logger.exception("发送流水线异常: %s", e)
            err_conn = _conn()
            try:
                crud.task_set_status(err_conn, task_id, TaskStatus.error.value, last_error=str(e))
                crud.log_insert(err_conn, task_id, "error", "send_pipeline", str(e))
            finally:
                err_conn.close()
        finally:
            # 唯一释放点:绑定到后台线程生命周期
            _clear_stop(task_id)
            release_sending(task_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    set_task_status(task_id, TaskStatus.sending.value)
    return True


async def _run_sending_async(task_id: int) -> None:
    conn = _conn()
    task = crud.task_get(conn, task_id)
    if not task:
        return  # 锁由 _run finally 释放
    auto_send = bool(task.get("auto_send"))
    # 模板字段已升级为 JSON 数组形式，原样传给 sender 由 render_message 解析
    template = task.get("template") or ""
    send_interval = task.get("send_interval") or _SEND_INTERVAL_DEFAULT
    daily_limit = task.get("daily_limit") or _DAILY_LIMIT_DEFAULT
    task_limit = task.get("task_limit") or _TASK_LIMIT_DEFAULT
    retry_limit = task.get("retry_limit")
    if retry_limit is None:
        retry_limit = _MAX_RETRY
    dm_channel = (task.get("dm_channel") or "main").strip() or "main"
    if dm_channel not in ("main", "creator"):
        dm_channel = "main"

    # 创建发送 execution 记录
    exec_id = crud.task_execution_start(conn, task_id)

    engine = BrowserEngine(use_new_page=True)
    try:
        await engine.launch()
        if not await engine.check_session():
            msg = "未登录抖音 / 登录已失效。请在已弹出的浏览器中扫码登录抖音，再重新点击「启动发送」。"
            crud.log_insert(conn, task_id, "error", "send_pipeline", msg)
            set_task_status(task_id, TaskStatus.error.value, last_error=msg)
            crud.task_execution_finish(conn, exec_id, "failed", msg)
            return

        if dm_channel == "creator":
            sender: Any = CreatorDMSender(engine)
            crud.log_insert(conn, task_id, "info", "send_pipeline", "发送通道: 创作者中心")
            # 提前打开创作者中心 tab：
            # 1) 让用户立刻看到；2) 避免每条首次进入时等加载；
            # 3) 作为"账号是否开通创作者身份 / 创作者后台是否可达"的前置校验 ——
            #    若这里失败，后续每条都会失败，应当立刻中止整个流水线。
            try:
                await engine.ensure_creator_tab()
                crud.log_insert(
                    conn, task_id, "info", "send_pipeline", "已打开创作者中心 chat 页（待发送触发后同步会话）"
                )
            except Exception as e:
                err_msg = f"创作者中心 chat 页打开失败: {e}"
                logger.warning(err_msg)
                crud.log_insert(conn, task_id, "error", "send_pipeline", err_msg)
                set_task_status(task_id, TaskStatus.error.value, last_error=err_msg)
                crud.task_execution_finish(conn, exec_id, "failed", err_msg)
                return
        else:
            sender = DMSender(engine)
            crud.log_insert(conn, task_id, "info", "send_pipeline", "发送通道: 主站")
        success_count = 0
        failed_count = 0
        send_index = 0  # 多模板轮询索引
        processed_user_ids: set[int] = set()  # 本次运行已处理(成功/失败)的用户,防止死循环

        while not _is_stopped(task_id):
            status_now = _task_status(task_id)
            if status_now != TaskStatus.sending.value:
                break

            # 检查限额
            daily_done = crud.send_records_daily_count(conn)
            task_done = crud.send_records_task_count(conn, task_id)
            if daily_done >= daily_limit:
                crud.log_insert(conn, task_id, "info", "send_pipeline", f"日上限 {daily_limit} 已达成，停止发送")
                break
            if task_done >= task_limit:
                crud.log_insert(conn, task_id, "info", "send_pipeline", f"任务上限 {task_limit} 已达成，停止发送")
                break

            pending = crud.target_list_pending_for_send(
                conn, task_id, auto_send, limit=1,
                exclude_user_ids=processed_user_ids or None,
            )
            if not pending:
                crud.log_insert(conn, task_id, "info", "send_pipeline", "待发名单已空，发送完成")
                break

            row = pending[0]
            sec_uid = row["sec_uid"]
            user_id = row["user_id"]
            target_id = row.get("target_id")
            nickname = row.get("nickname") or ""
            # 多模板按发送序号轮询(模板原文,不做变量替换)
            msg = sender.render_message(template, index=send_index)
            send_index += 1
            if not msg.strip():
                msg = "你好～"  # 兜底

            retry_count = 0
            result = None
            while retry_count <= retry_limit:
                if dm_channel == "creator":
                    result = await sender.send_dm(sec_uid, nickname, msg)
                else:
                    result = await sender.send_dm(sec_uid, msg)
                if result and result.success:
                    break
                if result and not result.retryable:
                    break
                retry_count += 1
                if retry_count <= retry_limit:
                    await asyncio.sleep(_RETRY_BACKOFF)

            # 不论成功/失败,标记该用户本次运行已处理,避免再次取到
            processed_user_ids.add(user_id)

            if result and result.success:
                crud.send_record_insert(
                    conn, task_id, user_id, target_id, msg, "success",
                    channel=dm_channel,
                )
                success_count += 1
                crud.log_insert(conn, task_id, "info", "send_pipeline", f"已向 {row.get('nickname', sec_uid)} 发送私信")
            else:
                reason = (result.failure_reason or "未知") if result else "未知"
                # 不可重试的业务失败(用户不存在/隐私账号等)标记为 skipped，后续运行永久跳过
                is_business_skip = result and not result.retryable and result.failure_type == "business"
                record_status = "skipped" if is_business_skip else "failed"
                crud.send_record_insert(
                    conn, task_id, user_id, target_id, msg or "", record_status,
                    failure_reason=reason, retry_count=retry_count,
                    channel=dm_channel,
                )
                failed_count += 1
                log_level = "info" if is_business_skip else "warn"
                skip_tag = "（已跳过）" if is_business_skip else ""
                crud.log_insert(conn, task_id, log_level, "send_pipeline",
                                f"发送失败{skip_tag}({row.get('nickname', sec_uid)}): {reason}")
            crud.task_execution_update(
                conn, exec_id,
                sent_success=success_count,
                sent_failed=failed_count,
            )

            # 间隔 + 随机抖动 ±30%
            jitter = 1.0 + (random.random() * 2 - 1) * _INTERVAL_JITTER
            wait_sec = max(1, int(send_interval * jitter))
            await asyncio.sleep(wait_sec)

        status_now = _task_status(task_id)
        if status_now == TaskStatus.sending.value:
            set_task_status(task_id, TaskStatus.completed.value)
            try:
                crud.task_execution_finish(conn, exec_id, "completed")
            except Exception as e:
                logger.warning("task_execution_finish 失败: %s", e)
        elif status_now == TaskStatus.error.value:
            try:
                t_now = crud.task_get(conn, task_id)
                err_msg = (t_now or {}).get("last_error") or "发送异常"
                crud.task_execution_finish(conn, exec_id, "failed", err_msg)
            except Exception as e:
                logger.warning("task_execution_finish 失败: %s", e)
        else:
            # paused/filtered/stopped 等中断
            try:
                crud.task_execution_finish(conn, exec_id, "stopped")
            except Exception as e:
                logger.warning("task_execution_finish 失败: %s", e)
    finally:
        try:
            await engine.close()
        except Exception:
            pass
        conn.close()


def pause_sending(task_id: int) -> bool:
    """暂停发送（置为 paused）。"""
    status = _task_status(task_id)
    if not ensure_transition(status or "", TaskStatus.paused.value):
        return False
    _request_stop(task_id)
    set_task_status(task_id, TaskStatus.paused.value)
    return True


def stop_sending(task_id: int) -> bool:
    """停止发送: 设停止标志 + 状态,锁由后台线程的 finally 释放。

    背景: 之前在这里立即 release_sending,会导致后台线程还在收尾(关浏览器/落库)
    时新任务就能 claim 成功,造成两个浏览器自动化流程短时间重叠。
    """
    status = _task_status(task_id)
    if status not in (TaskStatus.sending.value, TaskStatus.paused.value):
        return False
    _request_stop(task_id)
    set_task_status(task_id, TaskStatus.filtered.value)
    return True
