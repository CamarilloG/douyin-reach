"""
CRUD 与去重逻辑。
- 视频：按 (task_id, aweme_id) 唯一，已存在则跳过评论拉取。
- 评论：按 (video_id, cid) 去重；cid 为空时按 (video_id, user_id, content) 去重。
- 用户：按 sec_uid 唯一，已存在则 UPDATE。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from . import db
from .models import make_progress_snapshot

_TS = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 任务 ----------
def _normalize_template(template: Any) -> str:
    """统一把模板字段写库时归一化为 JSON 数组字符串。
    支持 str / list / 已是 JSON 数组字符串 三种入参。空则写空字符串。"""
    if template is None or template == "":
        return ""
    if isinstance(template, list):
        return json.dumps([str(x) for x in template if str(x).strip()], ensure_ascii=False)
    s = str(template).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return json.dumps([str(x) for x in arr if str(x).strip()], ensure_ascii=False)
        except Exception:
            pass
    return json.dumps([s], ensure_ascii=False)


def task_create(
    conn: sqlite3.Connection,
    name: str,
    *,
    auto_send: bool = False,
    max_comments_per_video: int = 50,
    max_videos_per_keyword: int = 50,
    max_scrolls_per_keyword: int = 20,
    video_timeout: int = 30,
    sort_mode: str = "general",
    publish_time: str = "unlimited",
    publish_time_start: Optional[str] = None,
    publish_time_end: Optional[str] = None,
    video_duration: str = "unlimited",
    search_scope: str = "unlimited",
    content_form: str = "unlimited",
    filter_enabled: bool = True,
    retry_limit: int = 2,
    template: Any = "",
    send_interval: int = 30,
    daily_limit: int = 100,
    task_limit: int = 500,
) -> int:
    now = _TS()
    # dm_channel 列保留在 schema 中(兼容旧库),走 DEFAULT 'main',不再作为参数
    cur = conn.execute(
        """INSERT INTO tasks (
            name, status, auto_send, max_comments_per_video,
            max_videos_per_keyword, max_scrolls_per_keyword,
            video_timeout, sort_mode, publish_time, publish_time_start, publish_time_end,
            video_duration, search_scope, content_form, filter_enabled, retry_limit,
            template, send_interval, daily_limit, task_limit, created_at, updated_at
        ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            1 if auto_send else 0,
            max_comments_per_video,
            max_videos_per_keyword,
            max_scrolls_per_keyword,
            video_timeout,
            sort_mode,
            publish_time,
            publish_time_start,
            publish_time_end,
            video_duration,
            search_scope,
            content_form,
            1 if filter_enabled else 0,
            retry_limit,
            _normalize_template(template),
            send_interval,
            daily_limit,
            task_limit,
            now,
            now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def task_get(conn: sqlite3.Connection, task_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_dict(row) if row else None


def task_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def task_update(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    name: Optional[str] = None,
    auto_send: Optional[bool] = None,
    max_comments_per_video: Optional[int] = None,
    max_videos_per_keyword: Optional[int] = None,
    max_scrolls_per_keyword: Optional[int] = None,
    video_timeout: Optional[int] = None,
    sort_mode: Optional[str] = None,
    publish_time: Optional[str] = None,
    publish_time_start: Optional[str] = None,
    publish_time_end: Optional[str] = None,
    video_duration: Optional[str] = None,
    search_scope: Optional[str] = None,
    content_form: Optional[str] = None,
    filter_enabled: Optional[bool] = None,
    retry_limit: Optional[int] = None,
    template: Any = None,
    send_interval: Optional[int] = None,
    daily_limit: Optional[int] = None,
    task_limit: Optional[int] = None,
) -> bool:
    t = task_get(conn, task_id)
    if not t:
        return False
    updates: list[str] = []
    args: list[Any] = []

    def add(col: str, val: Any) -> None:
        updates.append(f"{col} = ?")
        args.append(val)

    if name is not None:
        add("name", name)
    if auto_send is not None:
        add("auto_send", 1 if auto_send else 0)
    if max_comments_per_video is not None:
        add("max_comments_per_video", max_comments_per_video)
    if max_videos_per_keyword is not None:
        add("max_videos_per_keyword", max_videos_per_keyword)
    if max_scrolls_per_keyword is not None:
        add("max_scrolls_per_keyword", max_scrolls_per_keyword)
    if video_timeout is not None:
        add("video_timeout", video_timeout)
    if sort_mode is not None:
        add("sort_mode", sort_mode)
    if publish_time is not None:
        add("publish_time", publish_time)
    if publish_time_start is not None:
        add("publish_time_start", publish_time_start)
    if publish_time_end is not None:
        add("publish_time_end", publish_time_end)
    if video_duration is not None:
        add("video_duration", video_duration)
    if search_scope is not None:
        add("search_scope", search_scope)
    if content_form is not None:
        add("content_form", content_form)
    if filter_enabled is not None:
        add("filter_enabled", 1 if filter_enabled else 0)
    if retry_limit is not None:
        add("retry_limit", retry_limit)
    if template is not None:
        add("template", _normalize_template(template))
    if send_interval is not None:
        add("send_interval", send_interval)
    if daily_limit is not None:
        add("daily_limit", daily_limit)
    if task_limit is not None:
        add("task_limit", task_limit)

    if not updates:
        return True
    args.append(_TS())
    args.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(updates)}, updated_at = ? WHERE id = ?", args)
    conn.commit()
    return True


def task_set_status(conn: sqlite3.Connection, task_id: int, status: str, last_error: Optional[str] = None) -> bool:
    cur = conn.execute(
        "UPDATE tasks SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
        (status, last_error or "", _TS(), task_id),
    )
    conn.commit()
    return cur.rowcount > 0


def task_set_progress_snapshot(conn: sqlite3.Connection, task_id: int, snapshot: dict[str, Any]) -> bool:
    cur = conn.execute(
        "UPDATE tasks SET progress_snapshot = ?, updated_at = ? WHERE id = ?",
        (json.dumps(snapshot, ensure_ascii=False), _TS(), task_id),
    )
    conn.commit()
    return cur.rowcount > 0


def task_delete(conn: sqlite3.Connection, task_id: int) -> bool:
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------- 任务关键词 ----------
def task_keywords_set(conn: sqlite3.Connection, task_id: int, keywords: list[str]) -> None:
    conn.execute("DELETE FROM task_keywords WHERE task_id = ?", (task_id,))
    for i, kw in enumerate(keywords):
        if kw and kw.strip():
            conn.execute(
                "INSERT INTO task_keywords (task_id, keyword, sort_order) VALUES (?, ?, ?)",
                (task_id, kw.strip(), i),
            )
    conn.commit()


def task_keywords_get(conn: sqlite3.Connection, task_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT keyword FROM task_keywords WHERE task_id = ? ORDER BY sort_order",
        (task_id,),
    ).fetchall()
    return [r[0] for r in rows]


# ---------- 任务规则（M4：whitelist / blacklist / regex_include / regex_exclude）----------
_RULE_TYPES = ("whitelist", "blacklist", "regex_include", "regex_exclude")


def task_rules_set(conn: sqlite3.Connection, task_id: int, rules: dict[str, list[str]]) -> None:
    """写入规则，格式与 API 一致：{ whitelist, blacklist, regex_include, regex_exclude }。"""
    conn.execute("DELETE FROM task_rules WHERE task_id = ?", (task_id,))
    for rt in _RULE_TYPES:
        patterns = rules.get(rt) or []
        if not isinstance(patterns, list):
            continue
        for pattern in patterns:
            s = str(pattern).strip() if pattern else ""
            if s:
                conn.execute(
                    "INSERT INTO task_rules (task_id, rule_type, pattern) VALUES (?, ?, ?)",
                    (task_id, rt, s),
                )
    conn.commit()


def task_rules_get(conn: sqlite3.Connection, task_id: int) -> dict[str, list[str]]:
    """返回与 API 一致的规则格式。"""
    rows = conn.execute(
        "SELECT rule_type, pattern FROM task_rules WHERE task_id = ? ORDER BY id",
        (task_id,),
    ).fetchall()
    out: dict[str, list[str]] = {rt: [] for rt in _RULE_TYPES}
    for r in rows:
        rt, pat = r[0], r[1]
        if rt in out and pat:
            out[rt].append(pat)
    return out


# ---------- 视频（去重：task_id + aweme_id）----------
def video_ensure(
    conn: sqlite3.Connection,
    task_id: int,
    aweme_id: str,
    *,
    title: Optional[str] = None,
    url: Optional[str] = None,
    author_nickname: Optional[str] = None,
    author_sec_uid: Optional[str] = None,
    like_count: Optional[int] = None,
    comment_count: Optional[int] = None,
) -> int:
    """存在则返回已有 id，否则插入并返回 id。"""
    row = conn.execute("SELECT id FROM videos WHERE task_id = ? AND aweme_id = ?", (task_id, aweme_id)).fetchone()
    if row:
        return row[0]
    now = _TS()
    cur = conn.execute(
        """INSERT INTO videos (task_id, aweme_id, title, url, author_nickname, author_sec_uid, like_count, comment_count, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, aweme_id, title or "", url or "", author_nickname or "", author_sec_uid or "", like_count, comment_count, now),
    )
    conn.commit()
    return cur.lastrowid


def video_get_existing_aweme_ids(conn: sqlite3.Connection, task_id: int) -> set[str]:
    rows = conn.execute("SELECT aweme_id FROM videos WHERE task_id = ?", (task_id,)).fetchall()
    return {r[0] for r in rows}


# ---------- 用户（按 sec_uid 唯一，存在则更新）----------
def user_ensure(
    conn: sqlite3.Connection,
    sec_uid: str,
    *,
    nickname: Optional[str] = None,
    profile_url: Optional[str] = None,
    follower_count: Optional[int] = None,
    following_count: Optional[int] = None,
    bio: Optional[str] = None,
    is_verified: bool = False,
) -> int:
    now = _TS()
    row = conn.execute("SELECT id FROM users WHERE sec_uid = ?", (sec_uid,)).fetchone()
    if row:
        uid = row[0]
        parts = []
        args = []
        if nickname is not None:
            parts.append("nickname = ?")
            args.append(nickname)
        if profile_url is not None:
            parts.append("profile_url = ?")
            args.append(profile_url)
        if follower_count is not None:
            parts.append("follower_count = ?")
            args.append(follower_count)
        if following_count is not None:
            parts.append("following_count = ?")
            args.append(following_count)
        if bio is not None:
            parts.append("bio = ?")
            args.append(bio)
        parts.append("is_verified = ?")
        args.append(1 if is_verified else 0)
        parts.append("updated_at = ?")
        args.append(now)
        args.append(uid)
        conn.execute(f"UPDATE users SET {', '.join(parts)} WHERE id = ?", args)
        conn.commit()
        return uid
    cur = conn.execute(
        """INSERT INTO users (sec_uid, nickname, profile_url, follower_count, following_count, bio, is_verified, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sec_uid, nickname or "", profile_url or "", follower_count, following_count, bio or "", 1 if is_verified else 0, now, now),
    )
    conn.commit()
    return cur.lastrowid


# ---------- 评论（去重：同一 video_id 下 cid 或 (user_id+content)）----------
def comment_ensure(
    conn: sqlite3.Connection,
    video_id: int,
    user_id: int,
    content: str,
    *,
    cid: Optional[str] = None,
    digg_count: Optional[int] = None,
    reply_count: Optional[int] = None,
    created_time: Optional[int] = None,
) -> Optional[int]:
    """已存在（同 video_id + cid 或 同 video_id + user_id + content）则返回 None，否则插入并返回 id。"""
    if cid:
        row = conn.execute("SELECT id FROM comments WHERE video_id = ? AND cid = ?", (video_id, cid)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM comments WHERE video_id = ? AND user_id = ? AND content = ?",
            (video_id, user_id, content),
        ).fetchone()
    if row:
        return None
    now = _TS()
    cur = conn.execute(
        """INSERT INTO comments (video_id, cid, user_id, content, digg_count, reply_count, created_time, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (video_id, cid or "", user_id, content or "", digg_count, reply_count, created_time, now),
    )
    conn.commit()
    return cur.lastrowid


# ---------- 操作日志 ----------
def log_insert(conn: sqlite3.Connection, task_id: Optional[int], level: str, module: str, message: str) -> None:
    conn.execute(
        "INSERT INTO operation_logs (task_id, level, module, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, level, module, message, _TS()),
    )
    conn.commit()


# ---------- 待触达名单 ----------
def target_list_insert(
    conn: sqlite3.Connection,
    task_id: int,
    user_id: int,
    comment_id: int | None,
    matched_rule: str | None,
) -> int:
    now = _TS()
    cur = conn.execute(
        """INSERT INTO target_list (task_id, user_id, comment_id, matched_rule, selected, created_at)
        VALUES (?, ?, ?, ?, 1, ?)""",
        (task_id, user_id, comment_id, matched_rule or "", now),
    )
    conn.commit()
    return cur.lastrowid


def target_list_clear(conn: sqlite3.Connection, task_id: int) -> None:
    # send_records.target_id 外键引用 target_list.id，直接 DELETE 会 FOREIGN KEY 违规。
    # 先把所有引用置 NULL（保留 send_records 历史），再删 target_list。
    conn.execute(
        "UPDATE send_records SET target_id = NULL WHERE task_id = ? AND target_id IS NOT NULL",
        (task_id,),
    )
    conn.execute("DELETE FROM target_list WHERE task_id = ?", (task_id,))
    conn.commit()


def target_list_exists_user(conn: sqlite3.Connection, task_id: int, user_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM target_list WHERE task_id = ? AND user_id = ? LIMIT 1",
        (task_id, user_id),
    ).fetchone()
    return row is not None


def target_list_count(conn: sqlite3.Connection, task_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM target_list WHERE task_id = ?", (task_id,)).fetchone()[0]


def target_list_paged(
    conn: sqlite3.Connection,
    task_id: int,
    page: int = 1,
    page_size: int = 20,
    send_status: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int]:
    """分页获取待触达名单,含用户/评论/视频/发送状态。返回 (items, total)。

    send_status: None=全部, "unsent"=未发, "sent"=已发, "failed"=失败

    实现说明: 用 CTE 把 send_records 按 task_id 预过滤后 PARTITION BY user_id 取最新一条,
    避免老实现在 WHERE/SELECT 各算一次相关子查询。CTE 在 SQLite 3.25+ 上可用。
    """
    # 派生发送状态的过滤条件,count 和 list 共用
    if send_status == "sent":
        status_filter = " AND ls.status = 'success'"
    elif send_status == "failed":
        status_filter = " AND ls.status = 'failed'"
    elif send_status == "unsent":
        status_filter = " AND ls.status IS NULL"
    else:
        status_filter = ""

    cte = """
    WITH latest_send AS (
        SELECT user_id, status,
               ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) AS rn
        FROM send_records
        WHERE task_id = ?
    )
    """

    count_sql = f"""
    {cte}
    SELECT COUNT(*)
    FROM target_list tl
    LEFT JOIN latest_send ls ON ls.user_id = tl.user_id AND ls.rn = 1
    WHERE tl.task_id = ?{status_filter}
    """
    total_row = conn.execute(count_sql, (task_id, task_id)).fetchone()
    total = total_row[0] if total_row else 0

    offset = max(0, (page - 1) * page_size)
    list_sql = f"""
    {cte}
    SELECT tl.id, tl.user_id, tl.comment_id, tl.matched_rule, tl.selected, tl.created_at,
           u.nickname, u.profile_url, u.follower_count, u.bio,
           c.content AS comment_content,
           v.title AS video_title,
           ls.status AS sr_status
    FROM target_list tl
    JOIN users u ON tl.user_id = u.id
    LEFT JOIN comments c ON tl.comment_id = c.id
    LEFT JOIN videos v ON c.video_id = v.id
    LEFT JOIN latest_send ls ON ls.user_id = tl.user_id AND ls.rn = 1
    WHERE tl.task_id = ?{status_filter}
    ORDER BY tl.id DESC
    LIMIT ? OFFSET ?
    """
    rows = conn.execute(list_sql, (task_id, task_id, page_size, offset)).fetchall()

    items = []
    for r in rows:
        sr_status = r[12] if len(r) > 12 else None
        derived = "sent" if sr_status == "success" else ("failed" if sr_status == "failed" else "unsent")
        items.append({
            "id": r[0],
            "user_id": r[1],
            "comment_id": r[2],
            "matched_rule": r[3] or "",
            "selected": bool(r[4]),
            "created_at": r[5],
            "nickname": r[6] or "",
            "profile_url": r[7] or "",
            "fans_count": r[8] or 0,
            "bio": r[9] or "",
            "comment_text": r[10] or "",
            "source_video_title": r[11] or "",
            "send_status": derived,
        })
    return items, total


def target_list_all_for_export(
    conn: sqlite3.Connection,
    task_id: int,
) -> list[dict[str, Any]]:
    """全量获取待触达名单（不分页），用于 CSV 导出。"""
    cte = """
    WITH latest_send AS (
        SELECT user_id, status,
               ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) AS rn
        FROM send_records
        WHERE task_id = ?
    )
    """
    sql = f"""
    {cte}
    SELECT tl.id, tl.user_id, tl.comment_id, tl.matched_rule, tl.selected, tl.created_at,
           u.nickname, u.profile_url, u.follower_count, u.bio,
           c.content AS comment_content,
           v.title AS video_title,
           ls.status AS sr_status
    FROM target_list tl
    JOIN users u ON tl.user_id = u.id
    LEFT JOIN comments c ON tl.comment_id = c.id
    LEFT JOIN videos v ON c.video_id = v.id
    LEFT JOIN latest_send ls ON ls.user_id = tl.user_id AND ls.rn = 1
    WHERE tl.task_id = ?
    ORDER BY tl.id DESC
    """
    rows = conn.execute(sql, (task_id, task_id)).fetchall()
    items = []
    for r in rows:
        sr_status = r[12] if len(r) > 12 else None
        derived = "sent" if sr_status == "success" else ("failed" if sr_status == "failed" else "unsent")
        items.append({
            "id": r[0], "user_id": r[1], "comment_id": r[2],
            "matched_rule": r[3] or "", "selected": bool(r[4]), "created_at": r[5],
            "nickname": r[6] or "", "profile_url": r[7] or "",
            "fans_count": r[8] or 0, "bio": r[9] or "",
            "comment_text": r[10] or "", "source_video_title": r[11] or "",
            "send_status": derived,
        })
    return items


def send_records_all_for_export(
    conn: sqlite3.Connection,
    task_id: int,
) -> list[dict[str, Any]]:
    """全量获取发送历史（不分页），用于 CSV 导出。"""
    rows = conn.execute(
        """SELECT sr.id, sr.user_id, sr.task_id, sr.message_sent, sr.status,
                  sr.failure_reason, sr.sent_at, u.nickname, sr.channel
           FROM send_records sr
           JOIN users u ON sr.user_id = u.id
           WHERE sr.task_id = ?
           ORDER BY sr.id DESC""",
        (task_id,),
    ).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r[0], "user_id": r[1], "task_id": r[2],
            "message_sent": r[3] or "", "status": r[4],
            "reason": r[5] or "", "time": r[6] or "",
            "nickname": r[7] or "",
            "channel": r[8] or "main",
        })
    return items


def target_list_update_selection(
    conn: sqlite3.Connection, task_id: int, user_ids: list[int], selected: bool
) -> bool:
    if not user_ids:
        return True
    placeholders = ",".join("?" * len(user_ids))
    cur = conn.execute(
        f"UPDATE target_list SET selected = ? WHERE task_id = ? AND user_id IN ({placeholders})",
        [1 if selected else 0, task_id] + user_ids,
    )
    conn.commit()
    return cur.rowcount >= 0


# ---------- 采集数据（供 M4 筛选）----------
def task_comments_with_users(
    conn: sqlite3.Connection, task_id: int
) -> list[tuple[int, int, str, str, str, str | None]]:
    """获取任务下所有评论及对应用户，用于规则筛选。返回 [(comment_id, user_id, content, sec_uid, nickname, bio), ...]，按 comment_id 降序（最新优先）。"""
    rows = conn.execute(
        """SELECT c.id, c.user_id, c.content, u.sec_uid, u.nickname, u.bio
           FROM comments c
           JOIN videos v ON c.video_id = v.id
           JOIN users u ON c.user_id = u.id
           WHERE v.task_id = ?
           ORDER BY c.id DESC""",
        (task_id,),
    ).fetchall()
    return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]


# ---------- 发送记录（M5 使用）----------
def send_record_insert(
    conn: sqlite3.Connection,
    task_id: int,
    user_id: int,
    target_id: int | None,
    message_sent: str,
    status: str,
    *,
    failure_reason: str | None = None,
    retry_count: int = 0,
    channel: str = "main",
) -> int:
    """插入发送记录。status: success / failed / skipped。channel 固定为 main（历史记录可能存有 creator）。"""
    now = _TS()
    sent_at = now if status == "success" else None
    cur = conn.execute(
        """INSERT INTO send_records (task_id, user_id, target_id, message_sent, status, failure_reason, retry_count, sent_at, channel)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, user_id, target_id, message_sent, status, failure_reason or "", retry_count, sent_at, channel),
    )
    conn.commit()
    return cur.lastrowid


def send_records_daily_count(conn: sqlite3.Connection) -> int:
    """当日成功发送数（跨任务）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) FROM send_records WHERE status = 'success' AND sent_at IS NOT NULL AND date(sent_at) = ?",
        (today,),
    ).fetchone()
    return row[0] if row else 0


def send_records_task_count(conn: sqlite3.Connection, task_id: int) -> int:
    """本任务成功发送数。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM send_records WHERE task_id = ? AND status = 'success'",
        (task_id,),
    ).fetchone()
    return row[0] if row else 0


def target_list_pending_for_send(
    conn: sqlite3.Connection,
    task_id: int,
    auto_send: bool,
    limit: int = 100,
    exclude_user_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """获取待发送名单。

    排除规则:
    - 排除 status='success' (已成功) 和 status='skipped' (不可重试的业务失败,
      如用户不存在/隐私账号) 的用户。
    - failed 的用户保留以支持跨运行重试 — 修复风控/模板等问题后停掉重启,
      上次失败的人应该被重新捞起来。daily_limit / task_limit 兜底防滥发。

    exclude_user_ids: 本次运行中已处理(成功或失败)的 user_id 集合,
    用于避免同一次运行内对同一个失败用户无限重取。

    auto_send=True 取全部未成功; auto_send=False 仅取 selected=1 且未成功。
    """
    keyword_sub = "(SELECT keyword FROM task_keywords WHERE task_id = tl.task_id ORDER BY sort_order LIMIT 1)"
    base = f"""SELECT tl.id, tl.user_id, tl.comment_id, u.sec_uid, u.nickname,
                      c.content, v.title, {keyword_sub}
               FROM target_list tl
               JOIN users u ON tl.user_id = u.id
               LEFT JOIN comments c ON tl.comment_id = c.id
               LEFT JOIN videos v ON c.video_id = v.id
               WHERE tl.task_id = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM send_records sr
                     WHERE sr.task_id = tl.task_id
                       AND sr.user_id = tl.user_id
                       AND sr.status IN ('success', 'skipped')
                 )"""
    if not auto_send:
        base += " AND tl.selected = 1"
    params: list = [task_id]
    if exclude_user_ids:
        placeholders = ",".join("?" * len(exclude_user_ids))
        base += f" AND tl.user_id NOT IN ({placeholders})"
        params.extend(exclude_user_ids)
    base += " ORDER BY tl.id ASC LIMIT ?"
    params.append(limit)
    rows = conn.execute(base, params).fetchall()
    out = []
    for r in rows:
        out.append({
            "target_id": r[0],
            "user_id": r[1],
            "comment_id": r[2],
            "sec_uid": r[3],
            "nickname": r[4] or "",
            "comment_text": r[5] or "",
            "video_title": r[6] or "",
            "keyword": r[7] or "",
        })
    return out


def target_list_pending_for_send_count(
    conn: sqlite3.Connection,
    task_id: int,
    auto_send: bool,
) -> int:
    """统计真实可发送队列大小,与 target_list_pending_for_send 的过滤规则保持一致。

    用于 get_send_progress 显示 pending,避免 total - success - failed 算术失真。
    """
    sql = """SELECT COUNT(*) FROM target_list tl
             WHERE tl.task_id = ?
               AND NOT EXISTS (
                   SELECT 1 FROM send_records sr
                   WHERE sr.task_id = tl.task_id
                     AND sr.user_id = tl.user_id
                     AND sr.status IN ('success', 'skipped')
               )"""
    if not auto_send:
        sql += " AND tl.selected = 1"
    row = conn.execute(sql, (task_id,)).fetchone()
    return row[0] if row else 0


def send_records_paged(
    conn: sqlite3.Connection,
    task_id: int,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """分页获取发送历史。返回 (items, total)。"""
    where = "WHERE task_id = ?"
    args: list = [task_id]
    if status:
        where += " AND status = ?"
        args.append(status)
    total = conn.execute(f"SELECT COUNT(*) FROM send_records {where}", args).fetchone()[0]
    offset = max(0, (page - 1) * page_size)
    args.extend([page_size, offset])
    rows = conn.execute(
        f"""SELECT sr.id, sr.user_id, sr.task_id, sr.message_sent, sr.status, sr.failure_reason, sr.sent_at,
                   u.nickname, sr.channel
            FROM send_records sr
            JOIN users u ON sr.user_id = u.id
            {where}
            ORDER BY sr.id DESC
            LIMIT ? OFFSET ?""",
        args,
    ).fetchall()
    task_names = {}
    items = []
    for r in rows:
        tid = r[2]
        if tid and tid not in task_names:
            t = conn.execute("SELECT name FROM tasks WHERE id = ?", (tid,)).fetchone()
            task_names[tid] = t[0] if t else ""
        items.append({
            "id": r[0],
            "user_id": r[1],
            "task_id": tid,
            "task_name": task_names.get(tid, ""),
            "message_sent": r[3] or "",
            "status": r[4],
            "reason": r[5] or "",
            "time": r[6] or "",
            "nickname": r[7] or "",
            "channel": r[8] or "main",
        })
    return items, total


# ---------- 发送记录（用于历史校验）----------
def send_record_exists(
    conn: sqlite3.Connection, user_id: int, task_id: int | None, scope: str = "task"
) -> bool:
    """检查该用户是否已发过私信。scope=task 仅查本任务，scope=global 查全部。"""
    if scope == "global":
        row = conn.execute(
            "SELECT 1 FROM send_records WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM send_records WHERE task_id = ? AND user_id = ? LIMIT 1",
            (task_id, user_id),
        ).fetchone()
    return row is not None


# ---------- 操作日志 ----------
def log_get(conn: sqlite3.Connection, task_id: int, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, task_id, level, module, message, created_at FROM operation_logs WHERE task_id = ? ORDER BY id DESC LIMIT ?",
        (task_id, limit),
    ).fetchall()
    return [
        {"id": r[0], "task_id": r[1], "level": r[2], "module": r[3], "message": r[4], "time": r[5]}
        for r in rows
    ]


def log_clear(conn: sqlite3.Connection, task_id: int) -> int:
    """删除指定任务的所有 operation_logs,返回被删行数。"""
    cur = conn.execute("DELETE FROM operation_logs WHERE task_id = ?", (task_id,))
    conn.commit()
    return cur.rowcount or 0


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), row))


# ---------- 任务执行记录（每次启动一条 run） ----------
def task_execution_start(conn: sqlite3.Connection, task_id: int) -> int:
    now = _TS()
    cur = conn.execute(
        """INSERT INTO task_executions (task_id, started_at, status)
           VALUES (?, ?, 'running')""",
        (task_id, now),
    )
    conn.commit()
    return cur.lastrowid


def task_execution_update(
    conn: sqlite3.Connection,
    exec_id: int,
    *,
    videos_collected: Optional[int] = None,
    comments_collected: Optional[int] = None,
    users_matched: Optional[int] = None,
    sent_success: Optional[int] = None,
    sent_failed: Optional[int] = None,
) -> None:
    """部分更新计数（绝对值，不是增量）。"""
    parts: list[str] = []
    args: list[Any] = []
    for col, val in (
        ("videos_collected", videos_collected),
        ("comments_collected", comments_collected),
        ("users_matched", users_matched),
        ("sent_success", sent_success),
        ("sent_failed", sent_failed),
    ):
        if val is not None:
            parts.append(f"{col} = ?")
            args.append(val)
    if not parts:
        return
    args.append(exec_id)
    conn.execute(f"UPDATE task_executions SET {', '.join(parts)} WHERE id = ?", args)
    conn.commit()


def task_execution_finish(
    conn: sqlite3.Connection,
    exec_id: int,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """status: completed/failed/stopped。"""
    conn.execute(
        """UPDATE task_executions
           SET ended_at = ?, status = ?, error_message = ?
           WHERE id = ?""",
        (_TS(), status, error_message or "", exec_id),
    )
    conn.commit()


def task_executions_list(
    conn: sqlite3.Connection,
    task_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int]:
    where_parts: list[str] = []
    args: list[Any] = []
    if task_id is not None:
        where_parts.append("te.task_id = ?")
        args.append(task_id)
    if start_date:
        where_parts.append("te.started_at >= ?")
        args.append(start_date)
    if end_date:
        where_parts.append("te.started_at <= ?")
        args.append(end_date)
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM task_executions te {where}", args
    ).fetchone()[0]
    offset = max(0, (page - 1) * page_size)
    rows = conn.execute(
        f"""SELECT te.id, te.task_id, te.started_at, te.ended_at, te.status,
                   te.videos_collected, te.comments_collected, te.users_matched,
                   te.sent_success, te.sent_failed, te.error_message,
                   t.name
            FROM task_executions te
            LEFT JOIN tasks t ON te.task_id = t.id
            {where}
            ORDER BY te.id DESC
            LIMIT ? OFFSET ?""",
        args + [page_size, offset],
    ).fetchall()
    items = [
        {
            "id": r[0],
            "task_id": r[1],
            "started_at": r[2],
            "ended_at": r[3] or "",
            "status": r[4],
            "videos_collected": r[5] or 0,
            "comments_collected": r[6] or 0,
            "users_matched": r[7] or 0,
            "sent_success": r[8] or 0,
            "sent_failed": r[9] or 0,
            "error_message": r[10] or "",
            "task_name": r[11] or "",
        }
        for r in rows
    ]
    return items, total


def task_execution_delete(conn: sqlite3.Connection, exec_id: int) -> bool:
    cur = conn.execute("DELETE FROM task_executions WHERE id = ?", (exec_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------- 任务模板（保存任务表单 payload，便于复用） ----------
def task_template_save(conn: sqlite3.Connection, name: str, payload: dict[str, Any]) -> int:
    """保存或覆盖（按 name 唯一）。"""
    now = _TS()
    row = conn.execute("SELECT id FROM task_templates WHERE name = ?", (name,)).fetchone()
    payload_str = json.dumps(payload, ensure_ascii=False)
    if row:
        conn.execute(
            "UPDATE task_templates SET payload = ?, created_at = ? WHERE id = ?",
            (payload_str, now, row[0]),
        )
        conn.commit()
        return row[0]
    cur = conn.execute(
        "INSERT INTO task_templates (name, payload, created_at) VALUES (?, ?, ?)",
        (name, payload_str, now),
    )
    conn.commit()
    return cur.lastrowid


def task_template_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, created_at FROM task_templates ORDER BY id DESC"
    ).fetchall()
    return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]


def task_template_get(conn: sqlite3.Connection, template_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id, name, payload, created_at FROM task_templates WHERE id = ?",
        (template_id,),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[2])
    except Exception:
        payload = {}
    return {"id": row[0], "name": row[1], "payload": payload, "created_at": row[3]}


def task_template_delete(conn: sqlite3.Connection, template_id: int) -> bool:
    cur = conn.execute("DELETE FROM task_templates WHERE id = ?", (template_id,))
    conn.commit()
    return cur.rowcount > 0
