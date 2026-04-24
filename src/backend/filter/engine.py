"""
规则引擎（M4）：关键词/正则规则筛选、去重与历史校验。
执行顺序：黑名单 → 白名单/正则包含 → 正则排除。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from src.backend.data import db, crud


def _get_rules_by_type(rules: dict[str, list[str]]) -> tuple[list[str], list[str], list[re.Pattern], list[re.Pattern]]:
    """解析规则：黑名单、白名单、正则包含、正则排除。正则预编译。"""
    blacklist = [s for s in (rules.get("blacklist") or []) if s and str(s).strip()]
    whitelist = [s for s in (rules.get("whitelist") or []) if s and str(s).strip()]
    regex_include = []
    for p in rules.get("regex_include") or []:
        if p:
            try:
                regex_include.append(re.compile(str(p)))
            except re.error:
                pass
    regex_exclude = []
    for p in rules.get("regex_exclude") or []:
        if p:
            try:
                regex_exclude.append(re.compile(str(p)))
            except re.error:
                pass
    return blacklist, whitelist, regex_include, regex_exclude


def apply_rules(
    content: str,
    nickname: str,
    bio: str | None,
    rules: dict[str, list[str]],
) -> tuple[bool, str]:
    """
    对单条数据执行规则匹配。
    返回 (是否通过, 命中规则描述)。
    执行顺序：① 黑名单 → ② 白名单/正则包含（至少命中其一）→ ③ 正则排除。
    """
    text = f"{content} {nickname} {bio or ''}"
    blacklist, whitelist, regex_include, regex_exclude = _get_rules_by_type(rules)

    # 无任何规则时一律拒绝,避免"未筛选"状态下全量用户流入 target_list →
    # 私信发送队列。要让用户进入待触达名单,必须至少配一条正向规则
    # (whitelist / regex_include)。
    if not whitelist and not regex_include:
        return False, "未配置筛选规则（需至少一条白名单或正则包含）"

    # ① 黑名单
    for p in blacklist:
        if p in text:
            return False, f"黑名单: {p}"

    # ② 白名单或正则包含至少命中其一
    wl_matched = any(p in text for p in whitelist)
    ri_matched = any(rx.search(text) for rx in regex_include)
    if not wl_matched and not ri_matched:
        return False, "未命中白名单或正则包含"

    matched_desc = ""
    if wl_matched:
        for p in whitelist:
            if p in text:
                matched_desc = f"白名单: {p}"
                break
    if not matched_desc and ri_matched:
        for rx in regex_include:
            m = rx.search(text)
            if m:
                matched_desc = f"正则包含: {rx.pattern}"
                break

    # ③ 正则排除
    for rx in regex_exclude:
        if rx.search(text):
            return False, f"正则排除: {rx.pattern}"

    return True, matched_desc or "规则通过"


def check_duplicate(
    conn: Any,
    task_id: int,
    user_id: int,
    scope: str = "task",
) -> bool:
    """
    检查用户是否已在待触达名单或已发过私信。
    scope=task 仅查本任务 target_list + 本任务 send_records；
    scope=global 查本任务 target_list + 全局 send_records。
    返回 True 表示重复（应跳过）。
    """
    if crud.target_list_exists_user(conn, task_id, user_id):
        return True
    if crud.send_record_exists(conn, user_id, task_id, scope=scope):
        return True
    return False


def run_filter(
    task_id: int,
    *,
    scope: str = "task",
) -> tuple[bool, int]:
    """
    对任务的已采集数据执行规则筛选，写入 target_list。
    返回 (ok, 名单条数)。同一用户仅保留一条（优先最新评论）。

    注意：筛选与任务状态机解耦——不再调用 ensure_transition / set_task_status。
    原因：筛选只是对 comments/users 的只读聚合 + 写 target_list，跟采集/发送生命周期
    无关，应该允许在 collected / paused / error / filtered 任何状态下反复重跑（便于
    调整规则后重新生成名单），而不是被 paused→filtering 的转换表堵死。
    """
    conn = db.get_connection()
    try:
        task = crud.task_get(conn, task_id)
        if not task:
            return False, 0

        crud.target_list_clear(conn, task_id)

        rules = crud.task_rules_get(conn, task_id)
        rows = crud.task_comments_with_users(conn, task_id)
        seen_sec_uid: set[str] = set()
        count = 0

        for comment_id, user_id, content, sec_uid, nickname, bio in rows:
            if sec_uid in seen_sec_uid:
                continue
            if check_duplicate(conn, task_id, user_id, scope=scope):
                continue
            passed, matched_rule = apply_rules(content, nickname or "", bio, rules)
            if not passed:
                continue
            crud.target_list_insert(
                conn, task_id, user_id, comment_id, matched_rule
            )
            seen_sec_uid.add(sec_uid)
            count += 1

        crud.log_insert(conn, task_id, "info", "filter", f"筛选完成，待触达 {count} 人")
        return True, count
    finally:
        conn.close()
