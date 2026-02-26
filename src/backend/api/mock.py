"""
Mock 实现：与 Api 接口一致，返回硬编码/随机数据，供 M1 前端开发与演示。
M6 时替换为真实后端。
"""
from __future__ import annotations

import random
import time
from typing import Any

from .api import Api


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _rule_config(whitelist: list[str] | None = None, blacklist: list[str] | None = None) -> dict:
    return {
        "whitelist": whitelist or ["咨询", "想了解"],
        "blacklist": blacklist or ["广告"],
        "regex_include": [],
        "regex_exclude": [],
    }


def _task(tid: int, name: str, status: str = "pending", **kwargs: Any) -> dict:
    base = {
        "id": tid,
        "name": name,
        "keywords": ["关键词A", "关键词B"],
        "status": status,
        "max_comments_per_video": 50,
        "rules": _rule_config(),
        "template": "你好 {nickname}，看到你对「{video_title}」的评论，欢迎进一步了解～",
        "send_interval": 30,
        "daily_limit": 100,
        "task_limit": 500,
        "auto_send": False,
        "created_at": _ts(),
        "updated_at": _ts(),
    }
    base.update(kwargs)
    return base


class MockApi(Api):
    def __init__(self) -> None:
        self._tasks: dict[int, dict] = {
            1: _task(1, "示例任务一", "collected"),
            2: _task(2, "示例任务二", "pending"),
            3: _task(3, "采集中的任务", "collecting", keywords=["美妆", "护肤"]),
        }
        self._next_id = 4
        self._login_status = {"logged_in": True, "username": "mock_user", "expires_at": None}
        self._settings = {
            "send_interval": 30,
            "daily_limit": 100,
            "risk_warning_pause": 600,
            "risk_danger_stop": True,
            "ai_api_key": "sk-***",
            "ai_endpoint": "https://api.openai.com/v1",
            "ai_model": "gpt-4",
        }

    def get_tasks(self) -> list[dict[str, Any]]:
        return list(self._tasks.values())

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        tid = self._next_id
        self._next_id += 1
        name = data.get("name", f"任务{tid}")
        task = _task(tid, name, "pending", **{k: data[k] for k in data if k in (
            "keywords", "max_comments_per_video", "rules", "template",
            "send_interval", "daily_limit", "task_limit", "auto_send"
        )})
        self._tasks[tid] = task
        return task

    def update_task(self, task_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        if task_id not in self._tasks:
            return None
        t = self._tasks[task_id]
        for k in ("name", "keywords", "max_comments_per_video", "rules", "template",
                  "send_interval", "daily_limit", "task_limit", "auto_send"):
            if k in data:
                t[k] = data[k]
        t["updated_at"] = _ts()
        return t

    def delete_task(self, task_id: int) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def start_collection(self, task_id: int) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "collecting"
            return True
        return False

    def pause_collection(self, task_id: int) -> bool:
        if task_id in self._tasks and self._tasks[task_id]["status"] == "collecting":
            self._tasks[task_id]["status"] = "paused"
            return True
        return False

    def stop_collection(self, task_id: int) -> bool:
        if task_id in self._tasks:
            s = self._tasks[task_id]["status"]
            if s == "collecting" or s == "paused":
                self._tasks[task_id]["status"] = "collected"
            return True
        return False

    def get_collection_progress(self, task_id: int) -> dict[str, Any] | None:
        if task_id not in self._tasks:
            return None
        return {
            "task_id": task_id,
            "status": self._tasks[task_id]["status"],
            "current_keyword": "美妆",
            "current_keyword_index": 1,
            "total_keywords": 2,
            "processed_videos": 12,
            "total_videos": 30,
            "collected_comments": 128,
            "collected_users": 45,
        }

    def get_logs(self, task_id: int, limit: int = 100) -> list[dict[str, Any]]:
        levels = ["info", "info", "info", "warn", "error"]
        return [
            {
                "time": _ts(),
                "level": random.choice(levels),
                "message": f"Mock 日志 #{i}: 已处理视频 {i * 3}，采集评论 {i * 10}",
            }
            for i in range(min(limit, 15))
        ]

    def run_filter(self, task_id: int) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "filtered"
            return True
        return False

    def get_target_users(
        self, task_id: int, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        total = 28
        start = (page - 1) * page_size
        items = []
        for i in range(min(page_size, max(0, total - start))):
            uid = start + i + 1
            items.append({
                "id": uid,
                "nickname": f"用户{uid}",
                "profile_url": f"https://www.douyin.com/user/MS0{uid}",
                "comment_text": "想了解怎么购买，求私信",
                "source_video_title": "示例视频标题",
                "matched_rule": "白名单: 想了解",
                "selected": uid % 2 == 0,
                "send_status": "unsent" if uid % 3 != 0 else "sent",
                "fans_count": random.randint(100, 50000),
            })
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update_user_selection(
        self, task_id: int, user_ids: list[int], selected: bool
    ) -> bool:
        return True

    def export_target_users(self, task_id: int, file_path: str) -> str:
        return file_path or f"data/export_task_{task_id}.csv"

    def start_sending(self, task_id: int) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "sending"
            return True
        return False

    def pause_sending(self, task_id: int) -> bool:
        return True

    def stop_sending(self, task_id: int) -> bool:
        if task_id in self._tasks and self._tasks[task_id]["status"] == "sending":
            self._tasks[task_id]["status"] = "filtered"
        return True

    def get_send_progress(self, task_id: int) -> dict[str, Any] | None:
        return {
            "pending": 10,
            "sending": 1,
            "success": 5,
            "failed": 2,
        }

    def get_send_history(
        self,
        task_id: int,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> dict[str, Any]:
        total = 8
        items = [
            {
                "id": i,
                "time": _ts(),
                "nickname": f"用户{i}",
                "task_id": task_id,
                "task_name": self._tasks.get(task_id, {}).get("name", "任务"),
                "status": "success" if i % 3 != 0 else "failed",
                "reason": None if i % 3 != 0 else "风控限制",
            }
            for i in range(1, min(page_size + 1, total + 1))
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def export_send_history(self, task_id: int, file_path: str) -> str:
        return file_path or f"data/send_history_{task_id}.csv"

    def open_login_browser(self) -> bool:
        return True

    def check_login_status(self) -> dict[str, Any]:
        return dict(self._login_status)

    def get_settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        self._settings.update({k: v for k, v in data.items() if k in self._settings})
        return dict(self._settings)
