# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : _get_param_base.py
# @Desc    : 抽象基类：按 db_key 读取单个参数值
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
抽象基类：按 db_key 读取单个参数值

所有需要按 db_key 读取参数值的 agent 都可以继承此类。
子类只需设置 name、description、tool_title 等属性。
"""

from __future__ import annotations

from typing import Any

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db
from ...common.db_data_helper import read_param_by_db_key


class AbstractGetParamByDbKeyFunction(FunctionBase):
    """按 db_key 读取单个参数值的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

    @classmethod
    def get_schema(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "db_key": {
                            "type": "string",
                            "description": "参数的 db_key 标识，如 'e_dc_result_evlto'",
                        },
                    },
                    "required": ["db_key"],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> str:
        db_key = args.get("db_key", "")

        lines = ["=" * 60]
        lines.append(f"[{cls.tool_title}]")
        lines.append("-" * 60)

        if not db_key:
            lines.append("  参数错误：必须提供 db_key 参数。")
            lines.append("=" * 60)
            return "\n".join(lines)

        db = get_memory_db()
        if db is None:
            lines.append("  错误：未初始化 MemoryDatabase 引用。")
            lines.append("=" * 60)
            return "\n".join(lines)

        lines.append(f"  查询 db_key: {db_key}")
        lines.append("")

        value = read_param_by_db_key(db, db_key)
        lines.append(f"  参数值: {value}")
        lines.append("")
        lines.append(f"  提示：可将此值用于后续对比分析或写入目标值对比。")

        lines.append("=" * 60)
        return "\n".join(lines)
