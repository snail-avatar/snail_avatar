# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : target_definition_agent.py
# @Desc    : 目标值定义 Agent - function calling 驱动 ProcessContext 执行
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
TargetDefinitionAgent - 目标值定义 Agent（function calling 模式）

角色定位:
  "目标值定义专家" —— 通过 function calling 驱动 ProcessContext 执行完整的
  整车目标值（VTS/SSTS）定义流程，最终输出 FINAL_SUMMARY 总结报告。

能力:
  1. LLM 自主决策：从车型列表匹配用户意图中的 instance_key
  2. 调用 ProcessContext.run_flow(instance_key=xxx) 执行流程
  3. 自动提取 FINAL_SUMMARY 结果并返回

执行流程:
  用户输入 → agent_router 路由 → send_message()
    → LLM _run_tool_calling_loop:
        Round 1: list_target_definition_vehicles() → 获取车型列表
        Round 2: run_target_definition_flow(vehicle_name=instance_key) → 执行流程 + 提取总结
        Round 3: LLM 基于工具结果生成自然语言回复

继承关系:
  直接继承 LLMConversationAgent（不继承 VTSComputeAgent，不注册 VTS 计算链）

与现有 target_definition_panel.py 不冲突：
  - Agent 创建独立的 ProcessContext 实例（不共享 panel 的）
  - 两者是独立入口，互不干扰
  - FINAL_SUMMARY 结果通过 AgentMessageLogger 传递给 agent_message_panel
"""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from snail_avatar.backend.agents.core.agent_base import LLMConversationAgent

from .functions import create_default_registry


# ==========================================================================
# Agent 主类
# ==========================================================================

class TargetDefinitionAgent(LLMConversationAgent):
    """目标值定义 Agent - function calling 驱动 ProcessContext 执行"""

    # ------------------------------------------------------------------
    # 类属性（可被 YAML agent_runtime_config 覆盖）
    # ------------------------------------------------------------------

    # function calling 循环最大轮数：list_vehicles + run_flow + 可能的总结
    MAX_TOOL_ROUNDS = 5

    # 需要 memory_db（function 内部通过 get_memory_db() 获取）
    NEEDS_MEMORY_DB = True

    # 每次调用前清空历史（命令型 Agent，每次目标值定义独立执行）
    CLEAR_HISTORY_ON_CALL = True

    # ------------------------------------------------------------------
    # __init__
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__(
            agent_dir=os.path.dirname(__file__),
            yaml_filename="target_definition.yaml",
            create_registry_fn=create_default_registry,
            memory_db=None,
            vehicle_suffix="",
        )
