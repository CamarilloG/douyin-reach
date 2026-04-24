"""
采集流水线：按任务→关键词→搜索视频→逐视频拉评论→入库，更新进度快照，支持断点续跑与去重。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any, Optional

import sqlite3

from src.backend.data import db, crud
from src.backend.data.models import make_progress_snapshot
from src.backend.browser import BrowserEngine
from src.backend.browser.risk import RiskLevel
from src.backend.utils import debug_step
from src.backend.utils.config import get_settings as get_config
from .state import (
    TaskStatus,
    ensure_transition,
    set_task_status,
    claim_collecting,
    release_collecting,
    get_current_collecting_task,
)

logger = logging.getLogger(__name__)


def _conn():
    return db.get_connection()


def _task_status(task_id: int) -> Optional[str]:
    conn = _conn()
    try:
        t = crud.task_get(conn, task_id)
        return t["status"] if t else None
    finally:
        conn.close()


def _snapshot(task_id: int) -> dict[str, Any]:
    conn = _conn()
    try:
        t = crud.task_get(conn, task_id)
        if not t or not t.get("progress_snapshot"):
            return {}
        import json
        try:
            return json.loads(t["progress_snapshot"])
        except Exception:
            return {}
    finally:
        conn.close()


def run_collection(task_id: int) -> bool:
    """
    在后台线程中执行采集流水线；start_collection 调用后立即返回。
    返回 True 表示已成功启动（或已在运行），False 表示无法启动（状态/并发不允许）。
    """
    status = _task_status(task_id)
    if status is None:
        return False
    # collecting：若本任务正在采集则直接返回；若为僵死状态（线程已退出）则允许重启
    if status == TaskStatus.collecting.value:
        if get_current_collecting_task() == task_id:
            return True  # 已在采集中，无需重复启动
        if not claim_collecting(task_id):
            logger.warning("已有其他任务在采集中，无法启动任务 %s", task_id)
            return False
    else:
        if not ensure_transition(status, TaskStatus.collecting.value):
            logger.warning("任务 %s 状态 %s 不允许启动采集", task_id, status)
            return False
        if not claim_collecting(task_id):
            logger.warning("已有其他任务在采集中，无法启动任务 %s", task_id)
            return False

    def _run() -> None:
        try:
            asyncio.run(_run_collection_async(task_id))
        except Exception as e:
            logger.exception("采集流水线异常: %s", e)
            err_conn = _conn()
            try:
                crud.task_set_status(err_conn, task_id, TaskStatus.error.value, last_error=str(e))
                crud.log_insert(err_conn, task_id, "error", "pipeline", str(e))
            finally:
                err_conn.close()
        finally:
            # 唯一释放点:绑定到后台线程生命周期,避免新任务在旧浏览器收尾期间抢占
            release_collecting(task_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    set_task_status(task_id, TaskStatus.collecting.value)
    return True


async def _run_collection_async(task_id: int) -> None:
    conn = _conn()
    task = crud.task_get(conn, task_id)
    if not task:
        return  # 锁由 _run finally 释放
    keywords = crud.task_keywords_get(conn, task_id)
    if not keywords:
        crud.log_insert(conn, task_id, "warning", "pipeline", "无关键词，采集结束")
        set_task_status(task_id, TaskStatus.collected.value)
        conn.close()
        return

    # 创建一条 task_execution 记录，全程累加视频/评论计数
    exec_id = crud.task_execution_start(conn, task_id)

    max_comments = task.get("max_comments_per_video") or 50
    max_videos_per_kw = task.get("max_videos_per_keyword") or 50
    max_scrolls_per_kw = task.get("max_scrolls_per_keyword") or 20
    snapshot = _snapshot(task_id)
    # 存储口径: current_keyword_index 现在是"已开始/正在处理的第几个关键词" (1-based)。
    # 老快照里写的是 0-based,这里读出来后做一次兼容: 若 < 1 则视为 0 (resume 从头开始)。
    raw_kw_idx = snapshot.get("current_keyword_index", 0) or 0
    # 老快照 0-based / 新快照 1-based 都映射回循环起点(0-based)。
    # 旧:0=未开始 → start=0; 1=正在第二个 → start=1
    # 新:0=未开始 → start=0; 1=正在第一个 → start=0; 2=正在第二个 → start=1
    start_kw_index = max(0, raw_kw_idx - 1) if raw_kw_idx >= 1 else 0
    processed_aweme_ids = set(snapshot.get("processed_video_ids") or [])
    # 跨关键词累计的"已发现"视频集合(并集),作为视频进度的分母。
    # 老快照不存这个字段,fallback 到 processed 集合(下界,后续滚动时会增长)。
    total_videos_seen_all_kw: set[str] = set(snapshot.get("total_videos_seen_all_kw") or processed_aweme_ids)
    total_comments = snapshot.get("total_comments_collected", 0)
    total_users = snapshot.get("total_users_collected", 0)
    existing_aweme = set(crud.video_get_existing_aweme_ids(conn, task_id))

    engine = BrowserEngine()
    danger_triggered: dict[str, bool] = {"stop": False}
    naturally_finished = False  # 是否走到了关键词全循环结束的"自然完成"分支

    def _on_danger(reason: str) -> None:
        danger_triggered["stop"] = True
        c = _conn()
        try:
            detail = reason or "风控危险"
            crud.log_insert(c, task_id, "error", "pipeline", f"风控危险: {detail}")
            crud.task_set_status(c, task_id, TaskStatus.error.value, last_error=detail)
        finally:
            c.close()

    def _on_warning(reason: str) -> None:
        """风控预警时写入 log，便于 GUI 轮询展示。"""
        c = _conn()
        try:
            crud.log_insert(c, task_id, "warning", "pipeline", reason or "风控预警")
        finally:
            c.close()

    try:
        debug_step.step("pipeline_launch", "启动浏览器、加载 Cookie、打开抖音首页")
        await engine.launch()
        engine.set_risk_callbacks(on_warning=_on_warning, on_danger=_on_danger)
        debug_step.step("pipeline_check_session", "请求 user/settings 校验 session")
        if not await engine.check_session():
            crud.log_insert(conn, task_id, "error", "pipeline", "未登录或 session 失效")
            set_task_status(task_id, TaskStatus.error.value, last_error="未登录或 session 失效")
            return

        use_linear = bool(get_config().get("linear_collection", True))

        for kw_index in range(start_kw_index, len(keywords)):
            keyword = keywords[kw_index]
            if _task_status(task_id) != TaskStatus.collecting.value:
                return

            crud.log_insert(conn, task_id, "info", "pipeline", f"搜索关键词: {keyword}")
            debug_step.step("pipeline_search_keyword", f"关键词[{kw_index+1}/{len(keywords)}]: {keyword}")

            if use_linear:
                ok = await engine.search_via_homepage(keyword, task_config=task)
                if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                    return
                if not ok:
                    crud.log_insert(conn, task_id, "warning", "pipeline", f"关键词 {keyword} 搜索进入失败，跳过")
                    continue
                seen_aweme_this_kw: set[str] = set()
                scroll_attempts = 0
                v_idx = 0

                while scroll_attempts < max_scrolls_per_kw:
                    if _task_status(task_id) != TaskStatus.collecting.value:
                        return
                    videos = await engine.get_visible_video_cards()
                    if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                        return

                    processed_any = False
                    for v in videos:
                        if _task_status(task_id) != TaskStatus.collecting.value:
                            return
                        aweme_id = v.get("aweme_id") or ""
                        if not aweme_id:
                            continue
                        if aweme_id in processed_aweme_ids or aweme_id in existing_aweme or aweme_id in seen_aweme_this_kw:
                            continue
                        if len(seen_aweme_this_kw) >= max_videos_per_kw:
                            break
                        seen_aweme_this_kw.add(aweme_id)
                        total_videos_seen_all_kw.add(aweme_id)
                        video_url = v.get("video_url") or ""
                        if not video_url:
                            continue

                        v_idx += 1
                        debug_step.step("pipeline_fetch_video", f"视频 aweme_id={aweme_id} 线性流程")
                        ok = await engine.click_video_card_and_enter(aweme_id)
                        if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                            return
                        if not ok:
                            crud.log_insert(conn, task_id, "warning", "pipeline", f"视频 {aweme_id} 点击失败（可能被遮挡），跳过")
                            continue

                        comments_data = await engine.fetch_comments_on_current_page(max_comments)
                        if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                            return

                        if not crud.task_get(conn, task_id):
                            crud.log_insert(conn, task_id, "warning", "pipeline", "任务已被删除，停止采集")
                            return

                        try:
                            video_internal_id = crud.video_ensure(
                                conn,
                                task_id,
                                aweme_id,
                                title=v.get("title"),
                                url=video_url,
                                author_nickname=v.get("author_nickname"),
                                author_sec_uid=v.get("author_sec_uid"),
                            )
                        except sqlite3.IntegrityError as ie:
                            crud.log_insert(conn, task_id, "error", "pipeline", f"入库失败（可能任务已删除）: {ie}")
                            return
                        for c in comments_data:
                            sec_uid = (c.get("commenter_sec_uid") or "").strip()
                            if not sec_uid:
                                continue
                            user_id = crud.user_ensure(
                                conn,
                                sec_uid,
                                nickname=c.get("commenter_nickname"),
                                profile_url=c.get("profile_url"),
                            )
                            content = (c.get("text") or "").strip()
                            if not content:
                                continue
                            new_id = crud.comment_ensure(
                                conn,
                                video_internal_id,
                                user_id,
                                content,
                                cid=c.get("cid"),
                            )
                            if new_id is not None:
                                total_comments += 1
                        total_users_collected = conn.execute(
                            """SELECT COUNT(DISTINCT c.user_id) FROM comments c
                               JOIN videos v ON c.video_id = v.id WHERE v.task_id = ? AND c.user_id IS NOT NULL""",
                            (task_id,),
                        ).fetchone()[0]

                        processed_aweme_ids.add(aweme_id)
                        processed_any = True
                        crud.log_insert(conn, task_id, "info", "pipeline", f"视频 {aweme_id} 采集 {len(comments_data)} 条评论")
                        snapshot = make_progress_snapshot(
                            phase="collecting",
                            # 1-based: 第 kw_index+1 个关键词正在处理
                            current_keyword_index=kw_index + 1,
                            total_keywords=len(keywords),
                            current_keyword=keyword,
                            processed_video_ids=list(processed_aweme_ids),
                            current_video_index=v_idx,
                            # 全任务累计已发现视频数(分母),前端用 processed_videos / total_videos
                            total_videos_found=len(total_videos_seen_all_kw),
                            total_videos_seen_all_kw=list(total_videos_seen_all_kw),
                            total_comments_collected=total_comments,
                            total_users_collected=total_users_collected,
                            last_updated=datetime.now().isoformat(),
                        )
                        crud.task_set_progress_snapshot(conn, task_id, snapshot)
                        crud.task_execution_update(
                            conn, exec_id,
                            videos_collected=len(processed_aweme_ids),
                            comments_collected=total_comments,
                        )

                        back_ok = await engine.navigate_back()
                        await asyncio.sleep(1)
                        if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                            return
                        if not back_ok:
                            crud.log_insert(conn, task_id, "warning", "pipeline", f"返回搜索页失败,尝试重新搜索关键词 {keyword}")
                            recover = await engine.search_via_homepage(keyword, task_config=task)
                            if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                                return
                            if not recover:
                                crud.log_insert(conn, task_id, "warning", "pipeline", f"重搜 {keyword} 失败,跳到下一关键词")
                                break  # 跳出 while scroll_attempts, 进入下一个关键词

                    if not processed_any and len(seen_aweme_this_kw) >= max_videos_per_kw:
                        break
                    await engine.scroll_search_results_to_load_more()
                    scroll_attempts += 1
                    if len(seen_aweme_this_kw) >= max_videos_per_kw:
                        break
            else:
                videos = await engine.search_videos(keyword, max_count=max_videos_per_kw, task_config=task)
                if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                    return
                total_videos_for_kw = len(videos)
                # 把本关键词搜出来的视频全部并入"全任务已发现集合",作为进度分母
                for _v in videos:
                    _aid = _v.get("aweme_id") or ""
                    if _aid:
                        total_videos_seen_all_kw.add(_aid)

                for v_idx, v in enumerate(videos):
                    if _task_status(task_id) != TaskStatus.collecting.value:
                        return
                    aweme_id = v.get("aweme_id") or ""
                    if not aweme_id:
                        continue
                    if aweme_id in processed_aweme_ids or aweme_id in existing_aweme:
                        continue

                    video_url = v.get("video_url") or ""
                    if not video_url:
                        continue

                    debug_step.step("pipeline_fetch_video", f"视频[{v_idx+1}/{total_videos_for_kw}] aweme_id={aweme_id}")
                    comments_data = await engine.fetch_comments(video_url, max_count=max_comments)
                    if danger_triggered["stop"] or engine.get_risk_level() == RiskLevel.DANGER:
                        return

                    if not crud.task_get(conn, task_id):
                        return

                    try:
                        video_internal_id = crud.video_ensure(
                            conn,
                            task_id,
                            aweme_id,
                            title=v.get("title"),
                            url=video_url,
                            author_nickname=v.get("author_nickname"),
                            author_sec_uid=v.get("author_sec_uid"),
                        )
                    except sqlite3.IntegrityError as ie:
                        crud.log_insert(conn, task_id, "error", "pipeline", f"入库失败（可能任务已删除）: {ie}")
                        return
                    for c in comments_data:
                        sec_uid = (c.get("commenter_sec_uid") or "").strip()
                        if not sec_uid:
                            continue
                        user_id = crud.user_ensure(
                            conn,
                            sec_uid,
                            nickname=c.get("commenter_nickname"),
                            profile_url=c.get("profile_url"),
                        )
                        content = (c.get("text") or "").strip()
                        if not content:
                            continue
                        new_id = crud.comment_ensure(
                            conn,
                            video_internal_id,
                            user_id,
                            content,
                            cid=c.get("cid"),
                        )
                        if new_id is not None:
                            total_comments += 1
                    total_users_collected = conn.execute(
                        """SELECT COUNT(DISTINCT c.user_id) FROM comments c
                           JOIN videos v ON c.video_id = v.id WHERE v.task_id = ? AND c.user_id IS NOT NULL""",
                        (task_id,),
                    ).fetchone()[0]

                    processed_aweme_ids.add(aweme_id)
                    crud.log_insert(conn, task_id, "info", "pipeline", f"视频 {aweme_id} 采集 {len(comments_data)} 条评论")
                    snapshot = make_progress_snapshot(
                        phase="collecting",
                        current_keyword_index=kw_index + 1,
                        total_keywords=len(keywords),
                        current_keyword=keyword,
                        processed_video_ids=list(processed_aweme_ids),
                        current_video_index=v_idx + 1,
                        total_videos_found=len(total_videos_seen_all_kw),
                        total_videos_seen_all_kw=list(total_videos_seen_all_kw),
                        total_comments_collected=total_comments,
                        total_users_collected=total_users_collected,
                        last_updated=datetime.now().isoformat(),
                    )
                    crud.task_set_progress_snapshot(conn, task_id, snapshot)
                    crud.task_execution_update(
                        conn, exec_id,
                        videos_collected=len(processed_aweme_ids),
                        comments_collected=total_comments,
                    )

        debug_step.step("pipeline_done", "采集完成或中途暂停/停止")
        # 走到这里说明 for-keywords 自然结束(没有 early return)
        naturally_finished = True
        status_now = _task_status(task_id)
        if status_now == TaskStatus.collecting.value:
            set_task_status(task_id, TaskStatus.collected.value)
            # 自动筛选：如果任务开启了 filter_enabled，采集完成后自动执行 run_filter
            if task.get("filter_enabled"):
                try:
                    from src.backend.filter.engine import run_filter as _run_filter
                    ok, count = _run_filter(task_id)
                    if ok:
                        c3 = _conn()
                        try:
                            crud.log_insert(c3, task_id, "info", "pipeline", f"自动筛选完成，命中 {count} 人")
                        finally:
                            c3.close()
                        logger.info("任务 %s 自动筛选完成，命中 %d 人", task_id, count)
                    else:
                        logger.warning("任务 %s 自动筛选执行失败", task_id)
                except Exception as e:
                    logger.warning("任务 %s 自动筛选异常: %s", task_id, e)
    finally:
        # 写入 execution 终态: 区分自然完成 / 用户停止 / 风控失败 / 异常
        try:
            c2 = _conn()
            try:
                t2 = crud.task_get(c2, task_id)
            finally:
                c2.close()
            final_status_db = (t2 or {}).get("status") if t2 else None
            last_err = (t2 or {}).get("last_error") if t2 else None

            if danger_triggered["stop"]:
                final_status, err_msg = "failed", "风控危险中止"
            elif final_status_db == TaskStatus.error.value:
                final_status, err_msg = "failed", last_err or "采集异常"
            elif naturally_finished and final_status_db == TaskStatus.collected.value:
                final_status, err_msg = "completed", None
            elif final_status_db in (
                TaskStatus.paused.value,
                TaskStatus.collected.value,
                TaskStatus.filtered.value,
            ):
                final_status, err_msg = "stopped", None
            else:
                final_status, err_msg = "stopped", f"异常退出, task.status={final_status_db}"
            crud.task_execution_finish(conn, exec_id, final_status, error_message=err_msg)
        except Exception as e:
            logger.warning("task_execution_finish 失败: %s", e)
        try:
            if danger_triggered["stop"]:
                debug_step.step("pipeline_danger", "风控危险，保存会话并保持浏览器打开供用户处理")
                c = _conn()
                try:
                    crud.log_insert(c, task_id, "info", "pipeline", "请在当前浏览器中完成验证码，完成后可重新启动采集")
                finally:
                    c.close()
                await engine.close(keep_browser_open=True)
            else:
                debug_step.step("pipeline_close", "保存会话、关闭浏览器")
                await engine.close()
        except Exception as e:
            if "closed" not in str(e).lower() and "connection" not in str(e).lower():
                logger.exception("采集流水线收尾异常: %s", e)
        finally:
            conn.close()


def pause_collection(task_id: int) -> bool:
    """将任务置为暂停（仅当当前为 collecting 时有效）。"""
    status = _task_status(task_id)
    if not ensure_transition(status or "", TaskStatus.paused.value):
        return False
    set_task_status(task_id, TaskStatus.paused.value)
    return True


def stop_collection(task_id: int) -> bool:
    """停止采集: 仅设状态,锁由后台线程的 finally 释放。

    背景: 之前在这里立即 release_collecting,会导致后台线程还在收尾(关浏览器/落库)
    时新任务就能 claim 成功,造成两个浏览器自动化流程短时间重叠。
    """
    status = _task_status(task_id)
    if status not in (TaskStatus.collecting.value, TaskStatus.paused.value):
        return False
    set_task_status(task_id, TaskStatus.collected.value)
    return True
