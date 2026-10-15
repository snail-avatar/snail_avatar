# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : list_vehicles.py
# @Desc    : 抽象基类：列出车型
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：列出车型

所有需要车型列表的 agent 都可以继承此类。
子类只需设置 name、description、tool_title 等属性。
"""

from __future__ import annotations

import json
from typing import Any

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db
from ...common.db_data_helper import collect_vehicles


class AbstractListVehiclesFunction(FunctionBase):
    """列出所有可用车型的抽象基类"""

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
                    "properties": {},
                    "required": [],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> str:
        db = get_memory_db()

        if db is None:
            return "错误：未初始化 MemoryDatabase 引用。请先初始化 agent。"

        names, name_to_mc_key = collect_vehicles(db)

        lines = ["=" * 60]
        lines.append(f"[{cls.tool_title}]")
        lines.append("-" * 60)

        if not names:
            lines.append("  未找到可用车型数据")
            lines.append("  提示：请确保 memorycore 中存在车型数据")
        else:
            lines.append(f"  共发现 {len(names)} 个车型：")
            lines.append("")
            for idx, name in enumerate(names, start=1):
                mc_key = name_to_mc_key.get(name, name)
                lines.append(f"    {idx}. {name}  (memorycore_key: {mc_key})")

            lines.append("")
            lines.append(f"  [车型名称可用于后续工具调用，如 '修改目标车辆:'")
            lines.append(f"  请记住 '车型+后缀' 的格式作为 vehicle_suffix 参数。")

        lines.append("=" * 60)
        result = "\n".join(lines)
        try:
            json.dumps({"tool_name": cls.name, "tool_args": args})
        except Exception:
            pass
        return result