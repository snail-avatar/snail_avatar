# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : VTS_SSTS_agent 包 - VTS 状态分析 Agent
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS_SSTS_agent 包 - VTS 状态分析 Agent

对外暴露 VtsSstsAgent 类，供 agent_router 懒加载：
    agent_id = "vts_ssts_agent"
    类名  = VtsSstsAgent（"".join(word.capitalize() for word in agent_id.split("_"))）
"""

from .vts_ssts_agent import VtsSstsAgent

__all__ = ["VtsSstsAgent"]
