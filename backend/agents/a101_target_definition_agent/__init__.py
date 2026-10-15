# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : TargetDefinitionAgent 包 - 目标值定义 Agent
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
TargetDefinitionAgent 包 - 目标值定义 Agent

对外暴露 TargetDefinitionAgent 类，供 agent_router 懒加载：
    agent_id = "target_definition_agent"
    类名  = TargetDefinitionAgent（"".join(word.capitalize() for word in agent_id.split("_"))）
"""

from .target_definition_agent import TargetDefinitionAgent

__all__ = ["TargetDefinitionAgent"]
