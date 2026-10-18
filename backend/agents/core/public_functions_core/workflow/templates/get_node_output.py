# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : _get_node_output_base.py
# @Desc    : 抽象基类：获取节点某个输出变量值
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
抽象基类：获取节点某个输出变量值

所有需要查询节点输出值的计算型 agent 都可以继承此类。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db


class AbstractGetNodeOutputFunction(FunctionBase):
    """获取节点某个输出变量值的抽象基类"""

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
                        "node_id": {
                            "type": "string",
                            "description": "节点ID，如 'node_5_EVEnergyConsumption'",
                        },
                        "output_var_name": {
                            "type": "string",
                            "description": "输出变量名，如 'e_dc'",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀，如 'evlto'",
                        },
                    },
                    "required": ["node_id", "output_var_name"],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> str:
        node_id = args.get("node_id", "")
        output_var_name = args.get("output_var_name", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        lines = ["=" * 60]
        lines.append(f"[{cls.tool_title}]")
        lines.append("-" * 60)

        if not node_id or not output_var_name:
            lines.append("  参数错误：必须提供 node_id 和 output_var_name。")
            lines.append("=" * 60)
            return "\n".join(lines)

        db = get_memory_db()
        if db is None:
            lines.append("  错误：未初始化 MemoryDatabase 引用。")
            lines.append("=" * 60)
            return "\n".join(lines)

        # 获取工作流实例：从 context(Agent 实例)获取已缓存的工作流，确保复用已计算的状态
        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)

        if workflow is None:
            lines.append("  错误：无法加载工作流实例。")
            lines.append("  提示：请确保 Agent 已正确初始化并导入了车型数据。")
            lines.append("=" * 60)
            return "\n".join(lines)

        from ..node_query_helper import get_node_output_value

        result = get_node_output_value(workflow, node_id, output_var_name)

        lines.append(f"  节点ID: {node_id}")
        lines.append(f"  输出变量: {output_var_name}")
        lines.append("")

        if not result.get("node_found"):
            lines.append(f"  错误：未找到节点 '{node_id}'。")
            lines.append("=" * 60)
            return "\n".join(lines)

        if not result.get("var_found"):
            lines.append(f"  错误：节点 '{node_id}' 未找到输出变量 '{output_var_name}'。")
            lines.append(f"  提示：可先查询节点信息工具，查看该节点的所有输出变量。")
            lines.append("=" * 60)
            return "\n".join(lines)

        lines.append(f"  值类型: {result.get('type', 'unknown')}")
        if result.get("unit"):
            lines.append(f"  单位: {result['unit']}")

        value = result.get("value")
        if isinstance(value, (int, float)):
            lines.append(f"  当前值: {value:.6g}")
        elif isinstance(value, str):
            lines.append(f"  当前值: {value}")
        elif hasattr(value, "value") and hasattr(value, "time"):
            lines.append(f"  当前值: [时间序列数据]")
            stats = result.get("stats", {})
            if stats:
                if "length" in stats:
                    lines.append(f"    数据点数量: {stats['length']}")
                if "min" in stats:
                    lines.append(f"    最小值: {stats['min']:.6g}")
                if "max" in stats:
                    lines.append(f"    最大值: {stats['max']:.6g}")
                if "mean" in stats:
                    lines.append(f"    平均值: {stats['mean']:.6g}")
        else:
            lines.append(f"  当前值: {value}")

        lines.append("")
        lines.append(f"  提示：可将此值用于后续分析或对比。")

        lines.append("=" * 60)
        return "\n".join(lines)
