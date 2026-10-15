# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : expert_agent_base.py
# @Desc    : 通用专家知识检索Agent基类（配置驱动）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
通用专家知识检索Agent基类

基于配置文件驱动，无需编写Python代码即可新增专家知识检索Agent。

继承关系：
    GenericExpertAgent -> LLMConversationAgent

配置方式：
    在 agent_dir/config/*.yaml 中配置 tools 和 ui_config 段落
"""

from __future__ import annotations

import os
import yaml

from snail_avatar.backend.agents.core.agent_base import LLMConversationAgent
from snail_avatar.backend.agents.core.public_functions_core.function_factory import FunctionFactory


class GenericExpertAgent(LLMConversationAgent):
    """通用专家知识检索Agent（配置驱动）"""

    MAX_TOOL_ROUNDS = 5
    NEEDS_MEMORY_DB = False
    # 专家型 Agent 每次调用前清空历史，确保查询独立
    CLEAR_HISTORY_ON_CALL = True

    def __init__(self, agent_dir: str, yaml_filename: str):
        config_path = os.path.join(agent_dir, "config", yaml_filename)
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        tools_config = config.get("tools", [])
        create_registry_fn = lambda: FunctionFactory.create_registry(tools_config, agent_dir)

        super().__init__(
            agent_dir=agent_dir,
            yaml_filename=yaml_filename,
            create_registry_fn=create_registry_fn,
            memory_db=None,
            vehicle_suffix="",
        )

        self._ui_config = config.get("ui_config", {})
        self._agent_dir = agent_dir