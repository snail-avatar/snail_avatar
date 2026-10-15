# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_list_vehicles.py
# @Desc    : Function：列出可用车型（含 instance_key）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function：列出所有可执行目标值定义的车型

LLM 通过此工具获取合法车型列表和对应的 instance_key，
用于后续调用 run_target_definition_flow 时传入正确的 vehicle_name 参数。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import collect_vehicles


class ListVehiclesFunction(FunctionBase):
    """列出所有可执行目标值定义的车型"""

    name = "list_target_definition_vehicles"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "列出所有可执行目标值定义流程的车型。返回每个车型的中文名和 instance_key（memorycore key），后续调用 run_target_definition_flow 时 vehicle_name 参数必须使用 instance_key 值。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": "当前未加载数据（memory_db 为空），请先导入 Excel 数据文件。"}

        names, name_to_mc_key = collect_vehicles(db)
        if not names:
            return {"type": "text", "content": "未找到任何车型数据。请确认已导入包含 memorycore 的 Excel 文件。"}

        items = []
        for name in names:
            mc_key = name_to_mc_key.get(name, name)
            items.append(f"{name} (memorycore key: {mc_key})")

        return {
            "type": "list",
            "title": "可执行目标值定义的车型列表",
            "content": items,
            "summary": {"count": len(names)},
        }


ALL_FUNCTIONS = [
    ListVehiclesFunction,
]
