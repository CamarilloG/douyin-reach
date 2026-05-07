"""
SQLite 连接与建表。
数据库文件位于 <data_root>/douyin_reach.db,data_root 由 utils.paths 解析:
开发模式 = 项目根/data;exe 冻结模式 = exe 同目录/data。
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

from src.backend.utils.paths import get_data_path


def get_db_path() -> str:
    """数据库文件路径。"""
    return get_data_path("douyin_reach.db")


def get_connection(path: Optional[str] = None) -> sqlite3.Connection:
    """获取可读写连接。

    - WAL 模式: 允许"前端轮询读 + 后台线程写"完全并发,消除大部分 'database is locked'
    - busy_timeout=10000: SQL 层等锁兜底 10 秒
    - timeout=30: Python 端 retry 上限 30 秒
    - synchronous=NORMAL: 配合 WAL 提升写吞吐(单机本地数据库不需要 FULL)
    """
    p = path or get_db_path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    conn = sqlite3.connect(p, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # WAL 是数据库级配置,对同一文件只需 set 一次,但对每个 connection 设也无害
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_SCHEMA = """
-- 任务表
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    auto_send INTEGER NOT NULL DEFAULT 0,
    max_comments_per_video INTEGER NOT NULL DEFAULT 50,
    max_videos_per_keyword INTEGER NOT NULL DEFAULT 50,
    max_scrolls_per_keyword INTEGER NOT NULL DEFAULT 20,
    video_timeout INTEGER NOT NULL DEFAULT 30,
    sort_mode TEXT NOT NULL DEFAULT 'general',
    publish_time TEXT NOT NULL DEFAULT 'unlimited',
    publish_time_start TEXT,
    publish_time_end TEXT,
    video_duration TEXT NOT NULL DEFAULT 'unlimited',
    search_scope TEXT NOT NULL DEFAULT 'unlimited',
    content_form TEXT NOT NULL DEFAULT 'unlimited',
    filter_enabled INTEGER NOT NULL DEFAULT 1,
    retry_limit INTEGER NOT NULL DEFAULT 2,
    template TEXT,
    send_interval INTEGER NOT NULL DEFAULT 30,
    daily_limit INTEGER NOT NULL DEFAULT 100,
    task_limit INTEGER NOT NULL DEFAULT 500,
    dm_channel TEXT NOT NULL DEFAULT 'main',
    progress_snapshot TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 任务执行记录（每次启动一条 run）
CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    videos_collected INTEGER NOT NULL DEFAULT 0,
    comments_collected INTEGER NOT NULL DEFAULT 0,
    users_matched INTEGER NOT NULL DEFAULT 0,
    sent_success INTEGER NOT NULL DEFAULT 0,
    sent_failed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

-- 任务模板（保存任务表单 payload，便于复用）
CREATE TABLE IF NOT EXISTS task_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 任务关键词
CREATE TABLE IF NOT EXISTS task_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- 任务规则（M4 使用）
CREATE TABLE IF NOT EXISTS task_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL
);

-- 视频表（按 task_id + aweme_id 去重在应用层）
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    aweme_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    author_nickname TEXT,
    author_sec_uid TEXT,
    like_count INTEGER,
    comment_count INTEGER,
    collected_at TEXT NOT NULL,
    UNIQUE(task_id, aweme_id)
);

-- 用户表（全局按 sec_uid 唯一）
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_uid TEXT NOT NULL UNIQUE,
    nickname TEXT,
    profile_url TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    bio TEXT,
    is_verified INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 评论表（按 video 内部 id + cid 去重，cid 可为空则用 content+user 去重在应用层）
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    cid TEXT,
    user_id INTEGER REFERENCES users(id),
    content TEXT NOT NULL,
    digg_count INTEGER,
    reply_count INTEGER,
    created_time INTEGER,
    collected_at TEXT NOT NULL
);

-- 待触达名单
CREATE TABLE IF NOT EXISTS target_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    comment_id INTEGER REFERENCES comments(id),
    matched_rule TEXT,
    selected INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 发送记录
CREATE TABLE IF NOT EXISTS send_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    target_id INTEGER REFERENCES target_list(id),
    message_sent TEXT,
    status TEXT NOT NULL,
    failure_reason TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT,
    channel TEXT NOT NULL DEFAULT 'main'
);

-- 操作日志
CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    level TEXT NOT NULL,
    module TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_task_aweme ON videos(task_id, aweme_id);
CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id);
CREATE INDEX IF NOT EXISTS idx_target_list_task ON target_list(task_id);
CREATE INDEX IF NOT EXISTS idx_target_list_task_user ON target_list(task_id, user_id);
CREATE INDEX IF NOT EXISTS idx_send_records_task ON send_records(task_id);
CREATE INDEX IF NOT EXISTS idx_send_records_task_user ON send_records(task_id, user_id);
CREATE INDEX IF NOT EXISTS idx_operation_logs_task ON operation_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_task_exec_task ON task_executions(task_id, started_at DESC);
"""


def _migrate_tasks_columns(conn: sqlite3.Connection) -> None:
    """对已存在的 tasks 表补齐后加的列（SQLite 不支持 IF NOT EXISTS 加列）。"""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    to_add = [
        ("max_videos_per_keyword", "INTEGER NOT NULL DEFAULT 50"),
        ("max_scrolls_per_keyword", "INTEGER NOT NULL DEFAULT 20"),
        ("video_timeout", "INTEGER NOT NULL DEFAULT 30"),
        ("sort_mode", "TEXT NOT NULL DEFAULT 'general'"),
        ("publish_time", "TEXT NOT NULL DEFAULT 'unlimited'"),
        ("publish_time_start", "TEXT"),
        ("publish_time_end", "TEXT"),
        ("video_duration", "TEXT NOT NULL DEFAULT 'unlimited'"),
        ("search_scope", "TEXT NOT NULL DEFAULT 'unlimited'"),
        ("content_form", "TEXT NOT NULL DEFAULT 'unlimited'"),
        ("filter_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("retry_limit", "INTEGER NOT NULL DEFAULT 2"),
        ("dm_channel", "TEXT NOT NULL DEFAULT 'main'"),
    ]
    for name, decl in to_add:
        if name not in cols:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {decl}")
    # 旧 task.template 是裸字符串，统一升级为 JSON 数组
    import json as _json
    rows = conn.execute("SELECT id, template FROM tasks").fetchall()
    for row in rows:
        tpl = row[1]
        if tpl is None or tpl == "":
            continue
        s = str(tpl).strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                _json.loads(s)
                continue  # 已是 JSON 数组
            except Exception:
                pass
        new_val = _json.dumps([s], ensure_ascii=False)
        conn.execute("UPDATE tasks SET template = ? WHERE id = ?", (new_val, row[0]))
    conn.commit()


def _migrate_send_records_columns(conn: sqlite3.Connection) -> None:
    """对已存在的 send_records 表补齐 channel 列。"""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(send_records)").fetchall()}
    if "channel" not in cols:
        conn.execute(
            "ALTER TABLE send_records ADD COLUMN channel TEXT NOT NULL DEFAULT 'main'"
        )
    conn.commit()


def init_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """执行建表语句。若未传入 conn 则创建新连接并关闭。"""
    own = False
    if conn is None:
        conn = get_connection()
        own = True
    try:
        conn.executescript(_SCHEMA)
        _migrate_tasks_columns(conn)
        _migrate_send_records_columns(conn)
        conn.commit()
    finally:
        if own:
            conn.close()
