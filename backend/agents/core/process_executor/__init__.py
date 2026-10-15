# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 流程控制器模块导出
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程执行器模块

包含：
- ProcessController: 流程控制器（多继承组合）
- StepDefinition, StepState, ProcessSandbox: 数据结构
- ProcessStep, ProcessAgentStep, ProcessLLMStep, ProcessProcessStep: 步骤基类
- ConfigDrivenLLMStep, ConfigDrivenAgentStep, ConfigDrivenProcessStep: 配置驱动步骤
- StepFactory: 步骤工厂
- VariableResolver: 变量解析器
- ProcessEngine, ProcessDefinition, ProcessParser: 流程引擎
"""

from .data_structures import StepDefinition, StepState, ProcessDefinition
from .process_sandbox import ProcessSandbox, StepResultData, StepErrorData

# 步骤基类
from .steps.base import ProcessStep
from .steps.agent_step import ProcessAgentStep
from .steps.llm_step import ProcessLLMStep
from .steps.process_step import ProcessProcessStep

# 配置驱动步骤
from .steps.config_driven import (
    ConfigDrivenLLMStep,
    ConfigDrivenAgentStep,
    ConfigDrivenProcessStep,
    get_config_driven_step_class,
    STEP_TYPE_MAP,
)

# 步骤工厂
from .steps.factory import StepFactory

# 变量解析器
from .utils.variable_resolver import VariableResolver
from .utils.context_provider import IContextProvider, YamlContextProvider

# LLM 配置加载器
from .utils.llm_config_loader import (
    load_global_llm_config,
    merge_with_global_llm_config,
)

# 流程引擎
from .engine.process_engine import ProcessEngine
from .engine.parser import ProcessParser

# 流程控制器（ProcessController 组合类定义在 controllers/__init__.py）
from .controllers import (
    ProcessController,
    ProcessControllerBase,
    ProcessControllerLoop,
    ProcessControllerResult,
    ProcessControllerProgress,
    ProcessControllerControl,
)


__all__ = [
    # 数据结构
    "StepDefinition", "StepState", "ProcessDefinition",
    # 流程沙箱
    "ProcessSandbox", "StepResultData", "StepErrorData",
    # 步骤基类
    "ProcessStep", "ProcessAgentStep", "ProcessLLMStep", "ProcessProcessStep",
    # 配置驱动步骤
    "ConfigDrivenLLMStep", "ConfigDrivenAgentStep", "ConfigDrivenProcessStep",
    "get_config_driven_step_class", "STEP_TYPE_MAP",
    # 步骤工厂
    "StepFactory",
    # 变量解析器
    "VariableResolver",
    # 上下文提供者
    "IContextProvider", "YamlContextProvider",
    # LLM 配置
    "load_global_llm_config", "merge_with_global_llm_config",
    # 流程引擎
    "ProcessEngine", "ProcessParser",
    # 流程控制器
    "ProcessController",
    "ProcessControllerBase", "ProcessControllerLoop",
    "ProcessControllerResult",
    "ProcessControllerProgress", "ProcessControllerControl",
]
