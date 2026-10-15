# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 001_pubfn_list_sub_agents.py
# @Desc    : Public Function: 列出系统中所有可用的子 Agent 信息
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 001: 列出子 Agent 信息

列出系统中所有已配置的子 Agent，包括 Agent ID、名称、功能描述、
路由关键词等信息。作为 public function 可被所有 Agent
和 Step 通过注册获得调用权限。

返回结构化数据（List[Dict]），框架自动适配 LLM 工具和 Step 数据源两种场景。
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.tools.routing import get_agent_router


class PubfnListSubAgents(FunctionBase):
    """列出系统中所有已配置的子 Agent 信息"""

    name = "list_all_sub_agents"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "列出当前系统中所有已配置的子 Agent，包括 Agent ID、名称、功能描述、"
                               "路由关键词等信息。当用户询问有哪些子 Agent、或需要了解子 Agent 的"
                               "功能范围与能力时，应调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            "metadata": {
                "type": "agent_query",
                "pubfn_index": "001",
            }
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> List[Dict[str, Any]]:
        """执行 Agent 发现，返回结构化数据列表

        返回格式: [{agent_id, agent_name, agent_description, routing_keywords}, ...]
        框架会自动将其标准化为 {"type": "list", "content": [...]}，
        同时生成 LLM 友好的文本版本。
        """
        router = get_agent_router()
        all_ids = router.get_all_agent_ids()
        if not all_ids:
            return []

        main_id = "main_agent"
        available_agents = []

        for agent_id in all_ids:
            if agent_id == main_id:
                continue

            config = router.get_agent_config(agent_id)
            if not config:
                continue

            available_agents.append({
                "agent_id": agent_id,
                "agent_name": config.get("agent_name", agent_id),
                "agent_description": config.get("agent_description", ""),
                "routing_keywords": config.get("routing_keywords", []),
            })

        return available_agents


# 向后兼容别名
ListSubAgentsFunction = PubfnListSubAgents