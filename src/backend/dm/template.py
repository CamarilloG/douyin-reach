"""
私信模板:多条轮询 + 原文输出。

设计:占位符 / 变量替换功能已移除(2026-04 决策),模板原文即最终发送内容。
若需要按用户区分,请在「任务管理」里多写几条模板放进数组,发送时按用户索引轮询。

tasks.template 列存的是 JSON 数组字符串(也兼容旧的裸字符串)。
render_template 入口兼容 str / list / JSON 字符串三种形态。
"""
from __future__ import annotations

import json
from typing import Any


def parse_templates(template: Any) -> list[str]:
    """把 task.template 入参归一为字符串列表。
    支持 list / JSON 数组字符串 / 裸字符串 / None。空值返回空列表。"""
    if template is None or template == "":
        return []
    if isinstance(template, list):
        return [str(x) for x in template if str(x).strip()]
    s = str(template).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x) for x in arr if str(x).strip()]
        except Exception:
            pass
    return [s]


def pick_template(template: Any, index: int) -> str:
    """按 index 轮询取模板。空列表返回空串。"""
    items = parse_templates(template)
    if not items:
        return ""
    return items[index % len(items)]


def render_template(template: Any, *, index: int = 0, **_ignored: Any) -> str:
    """返回模板原文。多模板时按 index 轮询。

    **kwargs 仅作向后兼容(老调用还会传 nickname/comment_text 等),全部忽略。
    """
    return pick_template(template, index)
