# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : _get_node_info_base.py
# @Desc    : 抽象基类：获取节点输入输出详情
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
抽象基类：获取节点输入输出详情

所有需要查询节点详细信息的计算型 agent 都可以继承此类。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase


class AbstractGetNodeInfoFunction(FunctionBase):
    """获取节点输入输出详情的抽象基类"""

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
                            "description": "要查询的节点ID，如 'node_5_EVEnergyConsumption'",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀，如 'evlto'",
                        },
                    },
                    "required": ["node_id", "vehicle_suffix"],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> str:
        node_id = args.get("node_id", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        lines = ["=" * 60]
        lines.append(f"[{cls.tool_title}]")
        lines.append("=" * 60)
        lines.append("")

        if not node_id or not vehicle_suffix:
            lines.append("  参数错误：必须提供 node_id 和 vehicle_suffix。")
            lines.append("=" * 60)
            return "\n".join(lines)

        lines.append(f"  目标车型: {vehicle_suffix}")
        lines.append(f"  查询节点: {node_id}")
        lines.append("")

        # 获取工作流实例：从 context(Agent 实例)获取已缓存的工作流，确保复用已计算的状态
        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)

        if workflow is None:
            lines.append("  错误：无法加载工作流实例。")
            lines.append("  提示：请确保 Agent 已正确初始化并导入了车型数据。")
            lines.append("=" * 60)
            return "\n".join(lines)

        from ..node_query_helper import get_node_inputs_outputs

        info = get_node_inputs_outputs(workflow, node_id)

        if not info.get("node_found"):
            lines.append(f"  错误：未找到节点 '{node_id}'。")
            lines.append(f"  提示：请检查节点ID是否正确，可先调用 list_workflows 获取工作流中的节点列表。")
            lines.append("=" * 60)
            return "\n".join(lines)

        lines.append(f"  节点ID: {info['node_id']}")
        if info.get("node_display_name"):
            lines.append(f"  节点名称: {info['node_display_name']}")
        if info.get("node_category"):
            lines.append(f"  节点分类: {info['node_category']}")
        if info.get("node_description"):
            lines.append(f"  节点描述: {info['node_description']}")
        if info.get("upstream_nodes"):
            lines.append(f"  上游依赖: {', '.join(info['upstream_nodes'])}")

        # SSTS 输入
        ssts_inputs = info.get("ssts_inputs", {})
        if ssts_inputs:
            lines.append("")
            lines.append(f"  SSTS 输入变量（共 {len(ssts_inputs)} 个）：")
            for var_name, var_info in ssts_inputs.items():
                lines.append(f"    • {var_name}")
                if var_info.get("description") and var_info["description"] != var_name:
                    lines.append(f"      描述: {var_info['description']}")
                if var_info.get("unit"):
                    lines.append(f"      单位: {var_info['unit']}")
                lines.append(f"      当前值: {var_info.get('current_value', '未设置')}")
                # 显示完整的 db_key（用于 modify_ssts_and_recalculate）
                if var_info.get("db_key"):
                    lines.append(f"      db_key: {var_info['db_key']}")
                    lines.append(f"      修改方式: 可调用参数修改工具，db_key='{var_info['db_key']}', value=新值")

        # 中间变量输入
        inter_inputs = info.get("intermediate_inputs", {})
        if inter_inputs:
            lines.append("")
            lines.append(f"  中间变量输入（共 {len(inter_inputs)} 个）：")
            for var_name, var_info in inter_inputs.items():
                lines.append(f"    • {var_name}")
                if var_info.get("type"):
                    lines.append(f"      类型: {var_info['type']}")
                lines.append(f"      当前值: {var_info.get('current_value', '未计算')}")

        # 中间变量输出
        inter_outputs = info.get("intermediate_outputs", {})
        if inter_outputs:
            lines.append("")
            lines.append(f"  中间变量输出（共 {len(inter_outputs)} 个）：")
            for var_name, var_info in inter_outputs.items():
                lines.append(f"    • {var_name}")
                if var_info.get("description") and var_info["description"] != var_name:
                    lines.append(f"      描述: {var_info['description']}")
                if var_info.get("unit"):
                    lines.append(f"      单位: {var_info['unit']}")
                lines.append(f"      当前值: {var_info.get('current_value', '未计算')}")

        # VTS 输出
        vts_outputs = info.get("vts_outputs", {})
        if vts_outputs:
            lines.append("")
            lines.append(f"  VTS 输出参数（共 {len(vts_outputs)} 个）：")
            for var_name, var_info in vts_outputs.items():
                lines.append(f"    • {var_name}")
                lines.append(f"      db_key: {var_info.get('db_key', '')}")
                if var_info.get("unit"):
                    lines.append(f"      单位: {var_info['unit']}")
                lines.append(f"      当前值: {var_info.get('current_value', '未计算')}")

        lines.append("")
        lines.append(f"  提示：可查询节点输出工具查看某个输出变量的详细值。")

        lines.append("=" * 60)
        return "\n".join(lines)
