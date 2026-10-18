# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : _get_workflow_info_base.py
# @Desc    : 抽象基类：获取工作流详情
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
抽象基类：获取工作流详情

所有需要查询工作流详情的计算型 agent 都可以继承此类。
子类需要设置 name、description、tool_title 和提供获取工作流的方式。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db


class AbstractGetWorkflowInfoFunction(FunctionBase):
    """获取工作流详情的抽象基类"""

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
                        "workflow_id": {
                            "type": "string",
                            "description": "工作流ID，如 'EV_ECO_CALC'",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀，如 'evlto'，用于加载匹配的工作流数据",
                        },
                    },
                    "required": ["workflow_id"],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> str:
        workflow_id = args.get("workflow_id", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        lines = ["=" * 60]
        lines.append(f"[{cls.tool_title}]")
        lines.append("-" * 60)

        if not workflow_id:
            lines.append("  参数错误：必须提供 workflow_id。")
            lines.append("=" * 60)
            return "\n".join(lines)

        db = get_memory_db()
        if db is None:
            lines.append("  错误：未初始化 MemoryDatabase 引用。")
            lines.append("=" * 60)
            return "\n".join(lines)

        lines.append(f"  目标工作流: {workflow_id}")
        if vehicle_suffix:
            lines.append(f"  目标车型后缀: {vehicle_suffix}")
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

        # 提取节点信息
        from ..node_query_helper import (
    extract_vts_params_from_workflow,
    get_workflow_node_list,
)

        nodes = get_workflow_node_list(workflow)
        vts_params = extract_vts_params_from_workflow(workflow)

        lines.append(f"  工作流包含 {len(nodes)} 个节点：")
        lines.append("")

        for node in nodes:
            lines.append(f"    • 节点ID: {node['node_id']}")
            lines.append(f"      名称: {node['node_display_name']}")
            if node.get("node_category"):
                lines.append(f"      分类: {node['node_category']}")
            if node.get("node_description"):
                lines.append(f"      描述: {node['node_description']}")
            lines.append(f"      SSTS输入: {node['ssts_input_count']} 个, 中间变量输出: {node['intermediate_output_count']} 个")
            if node.get("has_vts_output"):
                lines.append(f"      输出VTS参数: 是")
            if node.get("upstream_nodes"):
                lines.append(f"      上游依赖: {', '.join(node['upstream_nodes'])}")
            lines.append("")

        if vts_params:
            lines.append(f"  工作流输出的VTS参数（共 {len(vts_params)} 个）：")
            lines.append("")
            for var_name, info in vts_params.items():
                lines.append(f"    • {var_name}")
                lines.append(f"      db_key: {info.get('db_key', '')}")
                lines.append(f"      节点: {info.get('node_id', '')}")
                if info.get("unit"):
                    lines.append(f"      单位: {info['unit']}")
                lines.append(f"      当前值: {info.get('current_value', '未计算')}")
                lines.append("")
        else:
            lines.append("  本工作流未定义VTS输出参数。")

        lines.append(f"  提示：可查询节点信息工具查看某个节点的详细输入输出。")

        lines.append("=" * 60)
        return "\n".join(lines)
