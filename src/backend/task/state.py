"""
任务状态机：状态枚举、合法转换、并发保护（同一时刻仅一个任务 collecting/sending）。
"""
from __future__ import annotations

import threading
from enum import Enum
from typing import Optional

from src.backend.data import db, crud

# 合法转换表（§3.2）
# collected→collecting：停止后可再次启动采集（断点续跑/继续采集）
_ALLOWED: dict[str, set[str]] = {
    "pending": {"collecting"},
    "collecting": {"paused", "collected", "error"},
    "paused": {"collecting", "pending", "sending"},
    "collected": {"filtering", "collecting", "sending"},
    "filtering": {"filtered", "error"},
    "filtered": {"sending"},
    "sending": {"paused", "completed", "error"},
    "completed": {"sending"},
    "error": {"collecting", "sending"},
}


class TaskStatus(str, Enum):
    pending = "pending"
    collecting = "collecting"
    paused = "paused"
    collected = "collected"
    filtering = "filtering"
    filtered = "filtered"
    sending = "sending"
    completed = "completed"
    error = "error"


# 并发保护：仅允许一个任务处于 collecting 或 sending
_lock = threading.Lock()
_current_collecting: Optional[int] = None
_current_sending: Optional[int] = None


def get_current_collecting_task() -> Optional[int]:
    with _lock:
        return _current_collecting


def get_current_sending_task() -> Optional[int]:
    with _lock:
        return _current_sending


def _claim_collecting(task_id: int) -> bool:
    """若当前无采集任务则占用并返回 True，否则返回 False。"""
    global _current_collecting
    with _lock:
        if _current_collecting is not None and _current_collecting != task_id:
            return False
        _current_collecting = task_id
        return True


def _release_collecting(task_id: int) -> None:
    global _current_collecting
    with _lock:
        if _current_collecting == task_id:
            _current_collecting = None


def _claim_sending(task_id: int) -> bool:
    global _current_sending
    with _lock:
        if _current_sending is not None and _current_sending != task_id:
            return False
        _current_sending = task_id
        return True


def _release_sending(task_id: int) -> None:
    global _current_sending
    with _lock:
        if _current_sending == task_id:
            _current_sending = None


def ensure_transition(from_status: str, to_status: str) -> bool:
    """是否允许从 from_status 转到 to_status。"""
    return to_status in _ALLOWED.get(from_status, set())


def set_task_status(task_id: int, new_status: str, last_error: Optional[str] = None) -> bool:
    """更新任务状态（不校验转换合法性，由调用方保证）。写入 DB。"""
    conn = db.get_connection()
    try:
        return crud.task_set_status(conn, task_id, new_status, last_error)
    finally:
        conn.close()


def claim_collecting(task_id: int) -> bool:
    """采集前调用：若当前无其他采集任务则占用并返回 True。"""
    return _claim_collecting(task_id)


def release_collecting(task_id: int) -> None:
    """采集结束/暂停后调用。"""
    _release_collecting(task_id)


def claim_sending(task_id: int) -> bool:
    """发送前调用。"""
    return _claim_sending(task_id)


def release_sending(task_id: int) -> None:
    _release_sending(task_id)
