# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_process_get_vehicle_display_name.py
# @Desc    : Public Function: 获取车型显示名称
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function a101: 获取车型显示名称

根据 instance_key 从 memory_db 中查找车型显示名称。
用于 pre_computed_attrs 配置中的 vehicle_display_name 属性获取。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_vehicle_name_by_key


class A101ProcessGetVehicleDisplayName(AtomicFunction):
    """获取车型显示名称 Public Function"""

    name: str = "get_vehicle_display_name"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "根据 instance_key 查找车型显示名称。\n"
                    "从 memory_db.vehsuffix 中查找匹配的车型条目。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instance_key": {
                            "type": "string",
                            "description": "实例标识（如 '车型名_后缀'）",
                        },
                        "memory_db": {
                            "type": "object",
                            "description": "MemoryDatabase 实例（含 vehsuffix 属性）",
                        },
                    },
                    "required": ["instance_key", "memory_db"],
                },
            },
            "metadata": {
                "type": "data_query",
                "pubfn_index": "a101",
                "function_purpose": "获取车型显示名称",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """根据 instance_key 查找车型显示名称

        从 memory_db.vehsuffix 中查找匹配的车型条目，返回其显示名称。
        匹配方式：后缀精确匹配优先，其次是车型名包含在 instance_key 中。

        Args:
            args: 参数字典，需包含 instance_key 和 memory_db
            context: 上下文对象

        Returns:
            str: 车型显示名称（如 "增程车型（WLTC）"），找不到时返回 instance_key
        """
        instance_key = args.get("instance_key", "")
        db = args.get("memory_db")

        return get_vehicle_name_by_key(db, instance_key)