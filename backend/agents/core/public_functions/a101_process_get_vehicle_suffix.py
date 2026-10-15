# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_process_get_vehicle_suffix.py
# @Desc    : Public Function: 获取车型后缀
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function a101: 获取车型后缀

从 instance_key 中提取车型后缀（如从 "增程车型_reevlto" 中提取 "reevlto"）。
用于 pre_computed_attrs 配置中的 vehicle_suffix 属性获取。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101ProcessGetVehicleSuffix(AtomicFunction):
    """获取车型后缀 Public Function"""

    name: str = "get_vehicle_suffix"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "从 instance_key 中提取车型后缀。\n"
                    "例如：'增程车型（WLTC）_reevlto' -> 'reevlto'"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instance_key": {
                            "type": "string",
                            "description": "实例标识（如 '车型名_后缀'）",
                        },
                    },
                    "required": ["instance_key"],
                },
            },
            "metadata": {
                "type": "data_transform",
                "pubfn_index": "a101",
                "function_purpose": "获取车型后缀",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """从 instance_key 中提取车型后缀

        使用 rsplit 从后往前分割，避免车型名含下划线时解析错误。

        Args:
            args: 参数字典，需包含 instance_key
            context: 上下文对象

        Returns:
            str: 车型后缀
        """
        instance_key = args.get("instance_key", "")

        if not instance_key:
            return ""

        # 使用 rsplit 从后往前分割，取最后一段作为后缀
        # 这样可以避免车型名本身包含下划线的情况
        if "_" in instance_key:
            return instance_key.rsplit("_", 1)[-1]

        return instance_key