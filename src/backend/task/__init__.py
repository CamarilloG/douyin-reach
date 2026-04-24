"""
任务编排：状态机、采集流水线、断点续跑。
M3 产出：state、pipeline。
"""
from __future__ import annotations

from .state import TaskStatus, set_task_status, ensure_transition, get_current_collecting_task
from .pipeline import run_collection

__all__ = [
    "TaskStatus",
    "set_task_status",
    "ensure_transition",
    "get_current_collecting_task",
    "run_collection",
]
