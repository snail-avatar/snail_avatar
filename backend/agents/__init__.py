# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
子Agent 入口模块

所有领域子Agent 都通过此模块统一导出

注意：以数字开头的包名无法使用标准 from ... import 语法，
需要使用 importlib.import_module() 动态导入
"""

import importlib as _importlib

_mod_generic = _importlib.import_module("snail_avatar.backend.agents.core.agent_base.generic_workflow_agent")
GenericWorkflowAgent = getattr(_mod_generic, "GenericWorkflowAgent")

EconomyAgent = GenericWorkflowAgent
PowerAgent = GenericWorkflowAgent

__all__ = [
    "EconomyAgent",
    "PowerAgent",
    "GenericWorkflowAgent",
]
