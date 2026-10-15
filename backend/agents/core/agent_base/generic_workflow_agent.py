# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : generic_workflow_agent.py
# @Desc    : 配置驱动的通用工作流计算Agent基类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
通用工作流计算Agent基类（配置驱动）

继承关系：
    GenericWorkflowAgent -> WorkflowAgentBase -> VTSComputeAgent -> LLMConversationAgent

用法：
    通过YAML配置文件定义Agent，无需编写Python代码：
    - agent_id: "economy_agent"
    - vts_category: "经济性"
    - vts_priority: 20
    - panel_id: "eco"
    - workflow_config: { nodes_pkg_path, vehicle_info_field, ... }
    - tools: [ { type: "run_full_calculation", name: "...", ... }, ... ]
"""

from __future__ import annotations

import os
import yaml
from typing import Any, Dict, Optional

from snail_avatar.backend.agents.core.agent_base.workflow_agent_base import WorkflowAgentBase


class GenericWorkflowAgent(WorkflowAgentBase):
    """配置驱动的通用工作流计算Agent

    从YAML配置文件读取所有配置，支持：
    - VTS计算自动注册（vts_category, vts_priority）
    - 工作流配置（nodes_pkg_path, vehicle_info_field, etc.）
    - 工具函数自动注册（通过WorkflowFunctionFactory）
    """

    def __init__(self, agent_dir: str, yaml_filename: str):
        """初始化通用工作流Agent

        Args:
            agent_dir: Agent目录路径
            yaml_filename: YAML配置文件名
        """
        config_path = os.path.join(agent_dir, "config", yaml_filename)
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self._yaml_config = config

        vts_category = config.get("vts_category", "")
        vts_priority = config.get("vts_priority", 100)
        panel_id = config.get("panel_id", "")

        self.vts_category = vts_category
        self.vts_priority = vts_priority
        self.panel_id = panel_id

        runtime_config = config.get("agent_runtime_config", {})
        self.MAX_TOOL_ROUNDS = runtime_config.get("max_tool_rounds", 8)
        self.NEEDS_MEMORY_DB = runtime_config.get("needs_memory_db", True)

        self._agent_dir = agent_dir

        tools_config = config.get("tools", [])

        def _create_registry_fn() -> Any:
            from snail_avatar.backend.agents.core.public_functions_core.workflow.workflow_function_factory import (
                WorkflowFunctionFactory,
            )

            return WorkflowFunctionFactory.create_registry(tools_config, agent_dir, panel_id, vts_category)

        super().__init__(
            agent_dir=agent_dir,
            yaml_filename=yaml_filename,
            create_registry_fn=_create_registry_fn,
        )

    def get_workflow_config(self) -> Dict[str, Any]:
        """返回工作流构建所需的配置参数

        Returns:
            工作流配置字典
        """
        workflow_config = self._yaml_config.get("workflow_config", {})
        workflow_config.setdefault("yaml_filename", self._yaml_config.get("agent_id", "") + ".yaml")
        return workflow_config

