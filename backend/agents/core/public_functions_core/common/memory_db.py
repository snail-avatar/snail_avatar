# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : memory_db.py
# @Desc    : 跨 Agent 共享模块：MemoryDatabase 依赖注入（唯一权威存储槽）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
跨 Agent 共享模块：MemoryDatabase 依赖注入

定位：**全局唯一权威存储槽**。所有代码（FastAPI 路由层 / agents 工具层）
都应该从这里读/写 MemoryDatabase 实例。

写入路径：
  A. FastAPI 路由层：dependencies.set_memory_database() → set_memory_db()
  B. open_project_file 工具（agents/）：加载 Excel → set_memory_db()

读取路径：
  - FastAPI 路由层：dependencies.get_memory_database() → 委托本模块 get_memory_db()
  - agents 工具层：直接 from ...common.memory_db import get_memory_db
"""

from __future__ import annotations

from typing import Any, Optional

# ==========================================================================
# 唯一权威存储槽
# ==========================================================================
_memory_db_ref: Any = None


def set_memory_db(db) -> None:
    """写入唯一权威槽"""
    global _memory_db_ref
    _memory_db_ref = db


def get_memory_db() -> Optional[Any]:
    """获取数据库引用

    返回:
        Optional[Any]: MemoryDatabase 实例（确保有 file_path），未找到时返回 None
    """
    global _memory_db_ref

    if _memory_db_ref is not None and getattr(_memory_db_ref, "file_path", None):
        return _memory_db_ref

    return None
