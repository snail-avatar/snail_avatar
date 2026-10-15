# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_list_vehicles.py
# @Desc    : Function 1：列出所有可用车型
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function 1：列出所有可用车型
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import collect_vehicles


class ListVehiclesFunction(FunctionBase):
    """列出所有可用车型及其后缀"""

    name = "list_all_vehicles"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "列出当前系统中所有可用车型，包括车型名称和对应的车型后缀（memorycore key）。当用户询问"
                               "有哪些车型可用、或需要指定车型时，应先调用此工具。",
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
            return {"type": "text", "content": "未找到任何车型数据。请确认 memory_db 中已加载 vehsuffix 和 memorycore。"}

        items = []
        for name in names:
            mc_key = name_to_mc_key.get(name, name)
            items.append(f"{name} (memorycore key: {mc_key})")

        return {
            "type": "list",
            "title": "当前可用车型",
            "content": items,
            "summary": {"count": len(names)},
        }


ALL_FUNCTIONS = [
    ListVehiclesFunction,
]
