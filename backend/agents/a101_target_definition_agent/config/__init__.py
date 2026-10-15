# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 模块初始化文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
a101_target_definition_agent 配置与步骤注册表

纯配置驱动：所有步骤从 config/steps/*.yaml 动态加载（通过 StepFactory）。
无需 Python 实现代码，业务逻辑已抽取为 public functions。
"""

import os
from typing import Dict, Type

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.process_executor import StepFactory

# Agent根目录
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_step_registry() -> Dict[str, Type[FunctionBase]]:
    """获取 step_id → StepClass 的注册表
    
    所有步骤均由配置驱动，从 config/steps/ 目录扫描加载。
    
    Returns:
        dict: {step_id: StepClass, ...}
    """
    return StepFactory.scan_configs(AGENT_DIR)


def get_inner_step_registry() -> Dict[str, Type[FunctionBase]]:
    """获取专业内循环步骤的注册表（不含外层步骤）"""
    all_steps = get_step_registry()
    outer_steps = {"DETECT_CATEGORIES", "FINAL_SUMMARY"}
    return {k: v for k, v in all_steps.items() if k not in outer_steps}


def register_steps(registry) -> None:
    """注册所有 Step 类到 FunctionRegistry"""
    step_registry = get_step_registry()
    for step_class in step_registry.values():
        registry.register(step_class)