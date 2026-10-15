# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Workflow 编排层共享抽象基类

所有工作流相关组件的公共底座，包含：
- calc_nodes_base.py:  计算节点基类
- workflow_base.py:   编排层基类（WorkflowNode, WorkflowGraph, WorkflowExecutor）

【架构约定】
- 计算节点 / 工作流从这里导入基类
- Agent 基类请从 snail_avatar.backend.agents.core.agent_base 导入
- 这个目录只放抽象，不放具体业务实现
"""
from .calc_nodes_base import CalculationNode, NodeState
from .workflow_base import WorkflowNode, WorkflowGraph, WorkflowExecutor

__all__ = [
    "CalculationNode",
    "NodeState",
    "WorkflowNode",
    "WorkflowGraph",
    "WorkflowExecutor",
]