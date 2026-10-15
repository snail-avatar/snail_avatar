# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : generic_ssts_workflow_agent.py
# @Desc    : 配置驱动的通用 SSTS 工作流 Agent（Phase 1：基础框架）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
配置驱动的通用 SSTS 工作流 Agent

继承关系：
    GenericSSTSWorkflowAgent -> SSTSWorkflowAgentBase -> WorkflowAgentBase -> VTSComputeAgent -> LLMConversationAgent

与 GenericWorkflowAgent（VTS 用）完全对称，所有 SSTS 扩展能力（沙箱、文件夹自动检测等）
由 SSTSWorkflowAgentBase 自动提供。子类只需要提供 YAML 配置文件。

用法（a401_energy_regeneration 的 agent YAML 配置）：
    agent_id: "energy_regeneration"
    ssts_category: "能量回收"          # ← SSTS 专属，用于自动注册
    panel_id: "energy_regen"
    sandbox_config:
      load_paths: ["Motor/**", "Brake/**"]
      auto_detect: true
    workflow_config: { nodes_pkg_path, vehicle_info_field, ... }
    tools: [...]
"""

from __future__ import annotations

import os
import yaml
from typing import Any, Dict

from snail_avatar.backend.agents.core.agent_base.ssts_compute_agent import SSTSWorkflowAgentBase


class GenericSSTSWorkflowAgent(SSTSWorkflowAgentBase):
    """配置驱动的通用 SSTS 工作流 Agent

    从 YAML 配置文件读取所有配置，支持：
    - SSTS 自动注册（ssts_category, is_ssts_agent）
    - 可选 VTS 注册（vts_category, vts_priority；is_vts_agent=True 时启用）
    - 沙箱配置（sandbox_config: load_paths / auto_detect / auto_commit）
    - 工作流配置（nodes_pkg_path, vehicle_info_field, etc.）
    - 工具函数自动注册
    """

    def __init__(self, agent_dir: str, yaml_filename: str):
        """初始化通用 SSTS 工作流 Agent

        Args:
            agent_dir: Agent 目录路径
            yaml_filename: Agent 主配置 YAML 文件名
        """
        config_path = os.path.join(agent_dir, "config", yaml_filename)
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self._yaml_config = config

        # ----- SSTS 注册属性（从 YAML 读取）-----
        ssts_category = config.get("ssts_category", "")
        self.is_ssts_agent = bool(ssts_category)
        self.ssts_category = ssts_category

        # ----- 可选 VTS 注册 -----
        vts_category = config.get("vts_category", "")
        vts_priority = config.get("vts_priority", 100)
        panel_id = config.get("panel_id", "")

        # 如果设置了 vts_category，声明参与 VTS 统一计算
        if vts_category:
            self.is_vts_agent = True
            self.vts_category = vts_category
            self.vts_priority = vts_priority

        self.panel_id = panel_id

        # ----- SSTS 专属配置 -----
        self.sandbox_config = config.get("sandbox_config", {
            "load_paths": [],
            "auto_detect": True,
        })

        runtime_config = config.get("agent_runtime_config", {})
        self.MAX_TOOL_ROUNDS = runtime_config.get("max_tool_rounds", 8)
        self.NEEDS_MEMORY_DB = runtime_config.get("needs_memory_db", True)

        self._agent_dir = agent_dir

        tools_config = config.get("tools", [])

        def _create_registry_fn() -> Any:
            from snail_avatar.backend.agents.core.public_functions_core.workflow.workflow_function_factory import (
                WorkflowFunctionFactory,
            )
            return WorkflowFunctionFactory.create_registry(tools_config, agent_dir, panel_id, ssts_category or vts_category)

        super().__init__(
            agent_dir=agent_dir,
            yaml_filename=yaml_filename,
            create_registry_fn=_create_registry_fn,
        )

    def get_workflow_config(self) -> Dict[str, Any]:
        """返回工作流构建所需的配置参数"""
        workflow_config = self._yaml_config.get("workflow_config", {})
        workflow_config.setdefault("yaml_filename", self._yaml_config.get("agent_id", "") + ".yaml")
        return workflow_config



