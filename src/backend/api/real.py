"""
真实 API 实现：对接数据层与任务流水线，符合 M1 Api 契约。
M6 GUI 集成：默认使用，支持事件推送、导出对话框、登录与配置。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .api import Api
from src.backend.data import db, crud
from src.backend.task import pipeline, send_pipeline
from src.backend.filter import run_filter as _run_filter
from src.backend.utils.config import get_settings as _get_settings, update_settings as _update_settings


def _task_to_api(
    task: dict[str, Any], keywords: list[str], rules: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    """将 DB 任务行 + 关键词列表 转为前端所需格式（与 Mock 一致）。"""
    # template 在 DB 里现在存的是 JSON 数组字符串，前端需要 list[str]
    raw_tpl = task.get("template") or ""
    tpl_list: list[str] = []
    if raw_tpl:
        s = str(raw_tpl).strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    tpl_list = [str(x) for x in arr]
            except Exception:
                tpl_list = [s]
        else:
            tpl_list = [s]
    return {
        "id": task["id"],
        "name": task["name"],
        "keywords": keywords,
        "status": task["status"],
        "max_comments_per_video": task["max_comments_per_video"],
        "max_videos_per_keyword": task["max_videos_per_keyword"],
        "max_scrolls_per_keyword": task["max_scrolls_per_keyword"],
        "video_timeout": task.get("video_timeout", 30),
        "sort_mode": task.get("sort_mode", "general"),
        "publish_time": task.get("publish_time", "unlimited"),
        "publish_time_start": task.get("publish_time_start"),
        "publish_time_end": task.get("publish_time_end"),
        "video_duration": task.get("video_duration", "unlimited"),
        "search_scope": task.get("search_scope", "unlimited"),
        "content_form": task.get("content_form", "unlimited"),
        "filter_enabled": bool(task.get("filter_enabled", 1)),
        "retry_limit": task.get("retry_limit", 2),
        "rules": rules or {
            "whitelist": [],
            "blacklist": [],
            "regex_include": [],
            "regex_exclude": [],
        },
        "template": tpl_list,  # list[str]，便于前端直接编辑
        "send_interval": task["send_interval"],
        "daily_limit": task["daily_limit"],
        "task_limit": task["task_limit"],
        "dm_channel": task.get("dm_channel") or "main",
        "auto_send": bool(task.get("auto_send")),
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }


class RealApi(Api):
    def __init__(self) -> None:
        db.init_schema()
        self._window = None  # pywebview 窗口，用于 evaluate_js 与 create_file_dialog
        self._license_info = None  # main.py 启动校验通过后注入
        self._license_error: tuple[str, str] | None = None  # 启动校验失败时的 (code, message)

    def set_window(self, window) -> None:
        """M6：注入 pywebview 窗口，供事件推送与保存对话框使用。"""
        self._window = window

    def set_license(self, info, error: tuple[str, str] | None = None) -> None:
        """main.py 启动校验后注入：
        - 通过 → info=LicenseInfo, error=None
        - 失败 → info=None, error=(code, message)
        """
        self._license_info = info
        self._license_error = error

    def _push_event(self, event_type: str, data: dict) -> None:
        """向前端推送 CustomEvent，用于实时进度等。"""
        if not self._window:
            return
        try:
            payload = json.dumps(data, ensure_ascii=False)
            js = f"window.dispatchEvent(new CustomEvent('{event_type}', {{detail: {payload}}}));"
            self._window.evaluate_js(js)
        except Exception:
            pass

    def get_tasks(self) -> list[dict[str, Any]]:
        conn = db.get_connection()
        try:
            tasks = crud.task_list(conn)
            out = []
            for t in tasks:
                kw = crud.task_keywords_get(conn, t["id"])
                rules = crud.task_rules_get(conn, t["id"])
                out.append(_task_to_api(dict(t), kw, rules))
            return out
        finally:
            conn.close()

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return None
            kw = crud.task_keywords_get(conn, task_id)
            rules = crud.task_rules_get(conn, task_id)
            return _task_to_api(dict(t), kw, rules)
        finally:
            conn.close()

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        conn = db.get_connection()
        try:
            tid = crud.task_create(
                conn,
                data.get("name", "未命名任务"),
                auto_send=bool(data.get("auto_send", False)),
                max_comments_per_video=int(data.get("max_comments_per_video", 50)),
                max_videos_per_keyword=int(data.get("max_videos_per_keyword", 50)),
                max_scrolls_per_keyword=int(data.get("max_scrolls_per_keyword", 20)),
                video_timeout=int(data.get("video_timeout", 30)),
                sort_mode=data.get("sort_mode", "general") or "general",
                publish_time=data.get("publish_time", "unlimited") or "unlimited",
                publish_time_start=data.get("publish_time_start"),
                publish_time_end=data.get("publish_time_end"),
                video_duration=data.get("video_duration", "unlimited") or "unlimited",
                search_scope=data.get("search_scope", "unlimited") or "unlimited",
                content_form=data.get("content_form", "unlimited") or "unlimited",
                filter_enabled=bool(data.get("filter_enabled", True)),
                retry_limit=int(data.get("retry_limit", 2)),
                template=data.get("template", ""),
                send_interval=int(data.get("send_interval", 30)),
                daily_limit=int(data.get("daily_limit", 100)),
                task_limit=int(data.get("task_limit", 500)),
                dm_channel=(data.get("dm_channel") or "main"),
            )
            keywords = data.get("keywords") or []
            if isinstance(keywords, list):
                crud.task_keywords_set(conn, tid, [str(k) for k in keywords])
            rules = data.get("rules")
            if isinstance(rules, dict):
                crud.task_rules_set(conn, tid, rules)
            task = crud.task_get(conn, tid)
            kw = crud.task_keywords_get(conn, tid)
            rules = crud.task_rules_get(conn, tid)
            return _task_to_api(dict(task), kw, rules)
        finally:
            conn.close()

    def update_task(self, task_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        conn = db.get_connection()
        try:
            if not crud.task_get(conn, task_id):
                return None
            crud.task_update(
                conn,
                task_id,
                name=data.get("name"),
                auto_send=data.get("auto_send") if "auto_send" in data else None,
                max_comments_per_video=data.get("max_comments_per_video"),
                max_videos_per_keyword=data.get("max_videos_per_keyword"),
                max_scrolls_per_keyword=data.get("max_scrolls_per_keyword"),
                video_timeout=data.get("video_timeout"),
                sort_mode=data.get("sort_mode"),
                publish_time=data.get("publish_time"),
                publish_time_start=data.get("publish_time_start") if "publish_time_start" in data else None,
                publish_time_end=data.get("publish_time_end") if "publish_time_end" in data else None,
                video_duration=data.get("video_duration"),
                search_scope=data.get("search_scope"),
                content_form=data.get("content_form"),
                filter_enabled=data.get("filter_enabled") if "filter_enabled" in data else None,
                retry_limit=data.get("retry_limit"),
                template=data.get("template") if "template" in data else None,
                send_interval=data.get("send_interval"),
                daily_limit=data.get("daily_limit"),
                task_limit=data.get("task_limit"),
                dm_channel=data.get("dm_channel") if "dm_channel" in data else None,
            )
            if "keywords" in data:
                kw = data["keywords"] if isinstance(data["keywords"], list) else []
                crud.task_keywords_set(conn, task_id, [str(k) for k in kw])
            if "rules" in data and isinstance(data["rules"], dict):
                crud.task_rules_set(conn, task_id, data["rules"])
            t = crud.task_get(conn, task_id)
            keywords = crud.task_keywords_get(conn, task_id)
            rules = crud.task_rules_get(conn, task_id)
            return _task_to_api(dict(t), keywords, rules)
        finally:
            conn.close()

    def delete_task(self, task_id: int) -> bool:
        conn = db.get_connection()
        try:
            return crud.task_delete(conn, task_id)
        finally:
            conn.close()

    def start_collection(self, task_id: int) -> bool:
        return pipeline.run_collection(task_id)

    def pause_collection(self, task_id: int) -> bool:
        return pipeline.pause_collection(task_id)

    def stop_collection(self, task_id: int) -> bool:
        return pipeline.stop_collection(task_id)

    def get_collection_progress(self, task_id: int) -> dict[str, Any] | None:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return None
            raw = t.get("progress_snapshot")
            snapshot = {}
            if raw:
                try:
                    snapshot = json.loads(raw)
                except Exception:
                    pass
            # 私信发送统计（用于进程监控数字卡片）
            # pending 必须与发送链路的入队规则一致(selected/auto_send/仅排除 success)
            total_target = crud.target_list_count(conn, task_id)
            sent_success = crud.send_records_task_count(conn, task_id)
            failed_row = conn.execute(
                "SELECT COUNT(*) FROM send_records WHERE task_id = ? AND status = 'failed'",
                (task_id,),
            ).fetchone()
            sent_failed = failed_row[0] if failed_row else 0
            skipped_row = conn.execute(
                "SELECT COUNT(*) FROM send_records WHERE task_id = ? AND status = 'skipped'",
                (task_id,),
            ).fetchone()
            sent_skipped = skipped_row[0] if skipped_row else 0
            users_matched = total_target
            auto_send = bool(t.get("auto_send"))
            sent_pending = crud.target_list_pending_for_send_count(conn, task_id, auto_send)
            return {
                "task_id": task_id,
                "status": t["status"],
                "last_error": t.get("last_error") or "",
                "current_keyword": snapshot.get("current_keyword", ""),
                "current_keyword_index": snapshot.get("current_keyword_index", 0),
                "total_keywords": snapshot.get("total_keywords", 0),
                "processed_videos": len(snapshot.get("processed_video_ids") or []),
                "total_videos": snapshot.get("total_videos_found", 0),
                "collected_comments": snapshot.get("total_comments_collected", 0),
                "collected_users": snapshot.get("total_users_collected", 0),
                "users_matched": users_matched,
                "sent_success": sent_success,
                "sent_failed": sent_failed,
                "sent_skipped": sent_skipped,
                "sent_pending": sent_pending,
            }
        finally:
            conn.close()

    def get_logs(self, task_id: int, limit: int = 100) -> list[dict[str, Any]]:
        conn = db.get_connection()
        try:
            return crud.log_get(conn, task_id, limit=limit)
        finally:
            conn.close()

    def clear_logs(self, task_id: int) -> dict[str, Any]:
        conn = db.get_connection()
        try:
            deleted = crud.log_clear(conn, task_id)
            return {"ok": True, "deleted": deleted}
        except Exception as e:
            return {"ok": False, "deleted": 0, "error": str(e)}
        finally:
            conn.close()

    def run_filter(self, task_id: int) -> dict[str, Any]:
        """执行筛选。返回 {ok, count, error} 以便前端展示。"""
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return {"ok": False, "count": 0, "error": "任务不存在"}
        finally:
            conn.close()
        try:
            ok, count = _run_filter(task_id, scope="task")
            if not ok:
                return {"ok": False, "count": 0, "error": "筛选失败"}
            return {"ok": True, "count": count, "error": ""}
        except Exception as e:
            return {"ok": False, "count": 0, "error": str(e)}

    def get_target_users(
        self,
        task_id: int,
        page: int = 1,
        page_size: int = 20,
        send_status: str | None = None,
    ) -> dict[str, Any]:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            items, total = crud.target_list_paged(conn, task_id, page, page_size, send_status=send_status)
            return {"items": items, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    def update_user_selection(
        self, task_id: int, user_ids: list[int], selected: bool
    ) -> bool:
        conn = db.get_connection()
        try:
            crud.target_list_update_selection(conn, task_id, user_ids, selected)
            return True
        finally:
            conn.close()

    def export_target_users(self, task_id: int, file_path: str) -> str:
        import csv

        path = file_path if file_path else None
        if not path and self._window:
            import webview

            try:
                path = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=f"task_{task_id}_list.csv",
                    file_types=("CSV (*.csv)",),
                )
            except Exception:
                path = None
        if path and isinstance(path, (list, tuple)):
            path = path[0] if path else None
        if not path:
            return ""  # 用户取消对话框时不写入
        conn = db.get_connection()
        try:
            items = crud.target_list_all_for_export(conn, task_id)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "user_id", "nickname", "profile_url", "comment_text",
                    "source_video_title", "matched_rule", "selected", "fans_count", "bio"
                ])
                w.writeheader()
                for it in items:
                    w.writerow({
                        "user_id": it.get("user_id"),
                        "nickname": it.get("nickname", ""),
                        "profile_url": it.get("profile_url", ""),
                        "comment_text": it.get("comment_text", ""),
                        "source_video_title": it.get("source_video_title", ""),
                        "matched_rule": it.get("matched_rule", ""),
                        "selected": "是" if it.get("selected") else "否",
                        "fans_count": it.get("fans_count", 0),
                        "bio": it.get("bio", ""),
                    })
        finally:
            conn.close()
        return path

    def start_sending(self, task_id: int) -> dict[str, Any]:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return {"ok": False, "error": "任务不存在"}
            status = t["status"]
            selected = conn.execute(
                "SELECT COUNT(*) FROM target_list WHERE task_id = ? AND selected = 1",
                (task_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        if selected <= 0:
            return {"ok": False, "error": "没有勾选任何目标用户,请到「采集明细」勾选后再启动"}
        ok = send_pipeline.run_sending(task_id)
        if not ok:
            return {"ok": False, "error": f"任务当前状态 '{status}' 不允许启动发送(或已有任务在发送中)"}
        return {"ok": True}

    def pause_sending(self, task_id: int) -> bool:
        return send_pipeline.pause_sending(task_id)

    def stop_sending(self, task_id: int) -> bool:
        return send_pipeline.stop_sending(task_id)

    def get_send_progress(self, task_id: int) -> dict[str, Any] | None:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return None
            success = crud.send_records_task_count(conn, task_id)
            failed_rows = conn.execute(
                "SELECT COUNT(*) FROM send_records WHERE task_id = ? AND status = 'failed'",
                (task_id,),
            ).fetchone()
            failed = failed_rows[0] if failed_rows else 0
            skipped_rows = conn.execute(
                "SELECT COUNT(*) FROM send_records WHERE task_id = ? AND status = 'skipped'",
                (task_id,),
            ).fetchone()
            skipped = skipped_rows[0] if skipped_rows else 0
            # pending 必须与 sender 实际能取到的队列保持一致:
            # 受 selected/auto_send 和 success/skipped 排除规则共同约束。
            auto_send = bool(t.get("auto_send"))
            pending = crud.target_list_pending_for_send_count(conn, task_id, auto_send)
            sending = 1 if t["status"] == "sending" else 0
            return {"pending": pending, "sending": sending, "success": success, "failed": failed, "skipped": skipped}
        finally:
            conn.close()

    def get_send_history(
        self,
        task_id: int,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> dict[str, Any]:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            items, total = crud.send_records_paged(conn, task_id, page, page_size, status)
            return {"items": items, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    def export_send_history(self, task_id: int, file_path: str) -> str:
        import csv

        path = file_path if file_path else None
        if not path and self._window:
            import webview

            try:
                path = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=f"send_history_{task_id}.csv",
                    file_types=("CSV (*.csv)",),
                )
            except Exception:
                path = None
        if path and isinstance(path, (list, tuple)):
            path = path[0] if path else None
        if not path:
            return ""  # 用户取消对话框或未选路径
        conn = db.get_connection()
        try:
            items = crud.send_records_all_for_export(conn, task_id)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "time", "nickname", "user_id", "channel", "message_sent", "status", "reason"
                ])
                w.writeheader()
                for it in items:
                    w.writerow({
                        "time": it.get("time", ""),
                        "nickname": it.get("nickname", ""),
                        "user_id": it.get("user_id", ""),
                        "channel": it.get("channel", "main"),
                        "message_sent": it.get("message_sent", ""),
                        "status": it.get("status", ""),
                        "reason": it.get("reason", ""),
                    })
        finally:
            conn.close()
        return path

    def get_settings(self) -> dict[str, Any]:
        return _get_settings()

    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        return _update_settings(data)

    # ---------- 任务执行历史 ----------
    def get_task_executions(
        self,
        task_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        conn = db.get_connection()
        try:
            items, total = crud.task_executions_list(
                conn, task_id=task_id, page=page, page_size=page_size,
                start_date=start_date, end_date=end_date,
            )
            return {"items": items, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    def delete_task_execution(self, exec_id: int) -> bool:
        conn = db.get_connection()
        try:
            return crud.task_execution_delete(conn, exec_id)
        finally:
            conn.close()

    # ---------- 任务复制 ----------
    def duplicate_task(self, task_id: int) -> dict[str, Any] | None:
        conn = db.get_connection()
        try:
            t = crud.task_get(conn, task_id)
            if not t:
                return None
            kw = crud.task_keywords_get(conn, task_id)
            rules = crud.task_rules_get(conn, task_id)
            new_id = crud.task_create(
                conn,
                f"{t['name']} - 副本",
                auto_send=bool(t.get("auto_send")),
                max_comments_per_video=t.get("max_comments_per_video", 50),
                max_videos_per_keyword=t.get("max_videos_per_keyword", 50),
                max_scrolls_per_keyword=t.get("max_scrolls_per_keyword", 20),
                video_timeout=t.get("video_timeout", 30),
                sort_mode=t.get("sort_mode", "general") or "general",
                publish_time=t.get("publish_time", "unlimited") or "unlimited",
                publish_time_start=t.get("publish_time_start"),
                publish_time_end=t.get("publish_time_end"),
                video_duration=t.get("video_duration", "unlimited") or "unlimited",
                search_scope=t.get("search_scope", "unlimited") or "unlimited",
                content_form=t.get("content_form", "unlimited") or "unlimited",
                filter_enabled=bool(t.get("filter_enabled", 1)),
                retry_limit=t.get("retry_limit", 2),
                template=t.get("template") or "",
                send_interval=t.get("send_interval", 30),
                daily_limit=t.get("daily_limit", 100),
                task_limit=t.get("task_limit", 500),
            )
            if kw:
                crud.task_keywords_set(conn, new_id, kw)
            if rules:
                crud.task_rules_set(conn, new_id, rules)
            new_t = crud.task_get(conn, new_id)
            return _task_to_api(dict(new_t), kw, rules)
        finally:
            conn.close()

    # ---------- 任务模板 ----------
    def save_task_template(self, name: str, payload: dict[str, Any]) -> int:
        conn = db.get_connection()
        try:
            return crud.task_template_save(conn, name, payload)
        finally:
            conn.close()

    def list_task_templates(self) -> list[dict[str, Any]]:
        conn = db.get_connection()
        try:
            return crud.task_template_list(conn)
        finally:
            conn.close()

    def load_task_template(self, template_id: int) -> dict[str, Any] | None:
        conn = db.get_connection()
        try:
            row = crud.task_template_get(conn, template_id)
            if not row:
                return None
            return {"id": row["id"], "name": row["name"], "payload": row.get("payload") or {}}
        finally:
            conn.close()

    def delete_task_template(self, template_id: int) -> bool:
        conn = db.get_connection()
        try:
            return crud.task_template_delete(conn, template_id)
        finally:
            conn.close()

    # ---------- 应用版本 ----------
    def get_app_version(self) -> dict[str, Any]:
        from src.backend.version import VERSION, APP_NAME
        return {"version": VERSION, "name": APP_NAME}

    # ---------- 商业授权 ----------
    def get_license_info(self) -> dict[str, Any]:
        """返回当前授权状态。
        - valid=True → 含完整 license 详情
        - valid=False → reason_code/reason_message 标识失败原因，前端据此显示激活蒙版
        无论哪种状态都包含 fingerprint，便于客户复制后回传给签发方。
        """
        from src.backend.license import get_machine_fingerprint

        fingerprint = get_machine_fingerprint()

        info = self._license_info
        if info is None:
            code, msg = self._license_error or ("missing", "未找到激活文件，请使用激活码完成首次激活。")
            return {
                "valid": False,
                "reason_code": code,
                "reason_message": msg,
                "fingerprint": fingerprint,
            }

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        seconds_left = (info.expires_at - now).total_seconds()
        days_left = max(0, int(seconds_left // 86400))
        expired = seconds_left <= 0
        return {
            "valid": True,
            "licensee": info.licensee,
            "license_id": info.license_id,
            "fingerprint": fingerprint,
            "issued_at": info.issued_at.isoformat().replace("+00:00", "Z"),
            "expires_at": info.expires_at.isoformat().replace("+00:00", "Z"),
            "days_left": days_left,
            "expired": expired,
        }

    def activate_license(self, token: str) -> dict[str, Any]:
        """前端激活蒙版调用：粘贴激活码 / 文件内容 → 校验 → 写入 data/license.key。
        token 接受三种输入：
          1. 完整 license.key 文件 JSON（"{\"data\":...}"）
          2. base64 编码的 JSON 一行激活码
          3. 上述任一形式带空白/换行（容错）
        返回 {ok, error, info} —— ok=True 时 info 含 LicenseInfo 字段。
        """
        from src.backend.license import LicenseError, activate_and_persist
        from src.backend.utils.paths import get_data_root

        try:
            info = activate_and_persist(token, get_data_root())
        except LicenseError as e:
            return {"ok": False, "error_code": e.code, "error_message": e.message}
        # 注入到当前进程，前端无需重启即可看到生效
        self._license_info = info
        self._license_error = None
        return {
            "ok": True,
            "info": self.get_license_info(),
        }

    def deactivate_license(self) -> dict[str, Any]:
        """退出当前授权：删除 data/license.key + data/.license_state，重置内存状态。
        前端调用后应 reload 页面或重新查询 get_license_info，让激活蒙版重新出现。
        返回 {ok, error}。
        """
        from src.backend.utils.paths import get_data_path

        license_path = get_data_path("license.key")
        state_path = get_data_path(".license_state")
        errors = []
        for p in (license_path, state_path):
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError as e:
                errors.append(f"{p}: {e}")

        # 不论文件清理是否完全成功，内存里的授权状态都重置（双保险）
        self._license_info = None
        self._license_error = ("missing", "已退出授权，请重新激活后继续使用。")

        if errors:
            return {"ok": False, "error": "; ".join(errors)}
        return {"ok": True}

    def pick_license_file(self) -> dict[str, Any]:
        """打开原生文件选择对话框，返回选中文件的内容字符串。
        前端的"选择文件"按钮调用此方法后，把返回的 content 直接传给 activate_license。
        返回 {ok, content, error} —— ok=False 时表示用户取消或读取失败。
        """
        if not self._window:
            return {"ok": False, "error": "窗口未就绪"}
        try:
            import webview

            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("授权文件 (*.key;*.json;*.txt)", "All files (*.*)"),
            )
        except Exception as e:
            return {"ok": False, "error": f"打开对话框失败：{e}"}
        if not paths:
            return {"ok": False, "error": "已取消"}
        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return {"ok": False, "error": f"读取文件失败：{e}"}
        return {"ok": True, "content": content, "path": path}
