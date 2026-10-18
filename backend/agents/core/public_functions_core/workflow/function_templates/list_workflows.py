# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : list_workflows.py
# @Desc    : 抽象基类：列出工作流
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：列出工作流

所有需要列出工作流的计算型 agent 都可以继承此类。
工作流列表从 context(Agent 实例)获取，确保只返回已导入车型数据后动态创建的工作流。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase


class AbstractListWorkflowsFunction(FunctionBase):
    """列出所有工作流的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

    @classmethod
    def _discover_workflows(cls, context: Any) -> list[dict[str, Any]]:
        """从 context 获取工作流列表"""
        if context is not None and hasattr(context, "list_workflows"):
            return context.list_workflows()
        return []

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
        lines = ["=" * 60]
        lines.append(f"[{cls.tool_title}]")
        lines.append("-" * 60)

        workflows = cls._discover_workflows(context)

        if not workflows:
            lines.append("  未找到可用的工作流配置。")
            lines.append("  提示：请确保 Agent 已正确初始化并导入了车型数据。")
            lines.append("=" * 60)
            return "\n".join(lines)

        lines.append(f"  共发现 {len(workflows)} 个工作流：")
        lines.append("")

        for idx, wf in enumerate(workflows, start=1):
            lines.append(f"  {idx}. 工作流ID: {wf.get('workflow_id', 'unknown')}")
            lines.append(f"     工作流名称: {wf.get('workflow_name', '未知')}")
            lines.append(f"     能源类型: {wf.get('energy_type', 'unknown')}")
            lines.append(f"     描述: {wf.get('description', '无')}")
            lines.append(f"     节点数量: {wf.get('node_count', 0)}")
            conditions = wf.get('conditions', [])
            if conditions:
                lines.append(f"     支持工况: {', '.join(conditions)}")
            lines.append("")

        lines.append(f"  提示：可查询工作流详情工具查看某个工作流的具体信息。")

        lines.append("=" * 60)
        return "\n".join(lines)