"""
数据层：SQLite 模型与存储。
M3 产出：建表、连接、CRUD、去重逻辑。
"""
from __future__ import annotations

from .db import get_connection, get_db_path, init_schema
from . import crud
from . import models

__all__ = [
    "get_connection",
    "get_db_path",
    "init_schema",
    "crud",
    "models",
]
