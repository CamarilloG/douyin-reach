"""
数据模型常量与进度快照结构。
表结构详见 docs/04-阶段3-数据层与任务编排.md §3.1。
"""
from __future__ import annotations

from typing import Any, TypedDict


# 进度快照 JSON 结构（§3.3）
# 字段口径(2026-04 修正):
#   current_keyword_index: 1-based,"当前正在处理的关键词序号"。0 = 未开始。
#   total_videos_found: 全任务累计已发现视频数(分母),不再是单关键词作用域。
#   total_videos_seen_all_kw: 全任务已发现视频 aweme_id 列表,用于 resume 时恢复分母。
class ProgressSnapshot(TypedDict, total=False):
    phase: str
    current_keyword_index: int
    total_keywords: int
    current_keyword: str
    processed_video_ids: list[str]
    current_video_index: int
    total_videos_found: int
    total_videos_seen_all_kw: list[str]
    total_comments_collected: int
    total_users_collected: int
    last_updated: str


def make_progress_snapshot(
    *,
    phase: str = "collecting",
    current_keyword_index: int = 0,
    total_keywords: int = 0,
    current_keyword: str = "",
    processed_video_ids: list[str] | None = None,
    current_video_index: int = 0,
    total_videos_found: int = 0,
    total_videos_seen_all_kw: list[str] | None = None,
    total_comments_collected: int = 0,
    total_users_collected: int = 0,
    last_updated: str = "",
) -> dict[str, Any]:
    """构造进度快照 dict，用于 JSON 序列化写入 tasks.progress_snapshot。"""
    import datetime
    snapshot: dict[str, Any] = {
        "phase": phase,
        "current_keyword_index": current_keyword_index,
        "total_keywords": total_keywords,
        "current_keyword": current_keyword or "",
        "processed_video_ids": list(processed_video_ids or []),
        "current_video_index": current_video_index,
        "total_videos_found": total_videos_found,
        "total_videos_seen_all_kw": list(total_videos_seen_all_kw or []),
        "total_comments_collected": total_comments_collected,
        "total_users_collected": total_users_collected,
        "last_updated": last_updated or datetime.datetime.now().isoformat(),
    }
    return snapshot
