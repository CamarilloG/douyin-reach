"""
API 契约：pywebview 暴露给前端的接口。
所有方法供 window.pywebview.api.xxx 调用，返回可 JSON 序列化的 dict/list。
"""
from __future__ import annotations

from typing import Any


class Api:
    """前后端桥接 API。M1 使用 MockApi 实现，M6 切换为真实实现。"""

    # ---------- 任务管理 ----------
    def get_tasks(self) -> list[dict[str, Any]]:
        """获取所有任务列表。"""
        raise NotImplementedError

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        """获取单个任务详情。"""
        raise NotImplementedError

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        """创建任务。"""
        raise NotImplementedError

    def update_task(self, task_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """更新任务配置。"""
        raise NotImplementedError

    def delete_task(self, task_id: int) -> bool:
        """删除任务。"""
        raise NotImplementedError

    # ---------- 采集控制 ----------
    def start_collection(self, task_id: int) -> bool:
        """启动采集。"""
        raise NotImplementedError

    def pause_collection(self, task_id: int) -> bool:
        """暂停采集。"""
        raise NotImplementedError

    def stop_collection(self, task_id: int) -> bool:
        """停止采集。"""
        raise NotImplementedError

    def get_collection_progress(self, task_id: int) -> dict[str, Any] | None:
        """获取采集进度快照。"""
        raise NotImplementedError

    def get_logs(self, task_id: int, limit: int = 100) -> list[dict[str, Any]]:
        """获取任务日志。"""
        raise NotImplementedError

    # ---------- 筛选与名单 ----------
    def run_filter(self, task_id: int) -> bool:
        """对已采集任务执行规则筛选。"""
        raise NotImplementedError

    def get_target_users(
        self, task_id: int, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """分页获取待触达名单。"""
        raise NotImplementedError

    def update_user_selection(
        self, task_id: int, user_ids: list[int], selected: bool
    ) -> bool:
        """批量勾选/取消勾选。"""
        raise NotImplementedError

    def export_target_users(self, task_id: int, file_path: str) -> str:
        """导出名单为 CSV，返回文件路径。"""
        raise NotImplementedError

    # ---------- 私信发送 ----------
    def start_sending(self, task_id: int) -> bool:
        """启动发送。"""
        raise NotImplementedError

    def pause_sending(self, task_id: int) -> bool:
        """暂停发送。"""
        raise NotImplementedError

    def stop_sending(self, task_id: int) -> bool:
        """停止发送。"""
        raise NotImplementedError

    def get_send_progress(self, task_id: int) -> dict[str, Any] | None:
        """发送进度（待发/发送中/成功/失败）。"""
        raise NotImplementedError

    def get_send_history(
        self,
        task_id: int,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> dict[str, Any]:
        """分页获取发送历史。"""
        raise NotImplementedError

    def export_send_history(self, task_id: int, file_path: str) -> str:
        """导出发送历史为 CSV。"""
        raise NotImplementedError

    # ---------- 系统与账号 ----------
    def open_login_browser(self) -> bool:
        """打开浏览器触发登录流程。"""
        raise NotImplementedError

    def check_login_status(self) -> dict[str, Any]:
        """检查当前登录状态。"""
        raise NotImplementedError

    def get_settings(self) -> dict[str, Any]:
        """获取全局设置。"""
        raise NotImplementedError

    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """更新全局设置。"""
        raise NotImplementedError
