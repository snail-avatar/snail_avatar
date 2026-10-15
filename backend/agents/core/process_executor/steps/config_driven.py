# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_config_driven.py
# @Desc    : 配置驱动的 Step 基类 - ConfigDrivenLLMStep, ConfigDrivenAgentStep, ConfigDrivenProcessStep
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
配置驱动的 Step 基类

功能：
- 从 YAML 配置文件动态加载 step 定义
- 支持 schema、prompt_template、llm_config、data_sources、post_process 等配置
- 通过配置自动生成对应的 Step 类

三种配置驱动的 Step 类型：
1. ConfigDrivenLLMStep:    LLM 推理型步骤（调用 ProcessLLMStep）
2. ConfigDrivenAgentStep:   Agent 调用型步骤（调用 ProcessAgentStep）
3. ConfigDrivenProcessStep: 直接执行型步骤（调用 ProcessProcessStep）
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Type

from .llm_step import ProcessLLMStep
from .agent_step import ProcessAgentStep
from .process_step import ProcessProcessStep
from ..utils.variable_resolver import VariableResolver


class ConfigDrivenLLMStep(ProcessLLMStep):
    """配置驱动的 LLM 推理型步骤

    从 YAML 配置文件加载所有配置，
    自动设置 step_id, step_name, schema, prompt_template 等属性。

    使用方式：
        class MyLLMStep(ConfigDrivenLLMStep):
            _step_config_name = "my_step_config"  # 对应 config/steps/ 下的 yaml 文件名

    或通过 StepFactory 动态创建。
    """

    @classmethod
    def _build_prompt(cls, step_config: Dict[str, Any],
                       args: Dict[str, Any],
                       context: Any = None,
                       data_sources: Dict[str, Any] = None) -> str:
        """使用配置中的 prompt_template 构建 prompt

        Args:
            step_config: 步骤配置
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 数据源结果

        Returns:
            str: 构建后的 prompt
        """
        template = step_config.get('prompt_template', '')

        if not template:
            return args.get('query', '')

        # 构建模板变量映射
        template_vars = dict(args)

        # 添加数据源结果
        if data_sources:
            for key, value in data_sources.items():
                if isinstance(value, str):
                    template_vars[key] = value
                elif isinstance(value, list):
                    template_vars[key] = '\n'.join(str(v) for v in value)
                else:
                    template_vars[key] = str(value)

        # 使用 VariableResolver 处理模板中的 $xxx 变量引用（如 $args.xxx, $memory_db 等）
        resolver = VariableResolver(
            args=args,
            context=context,
            data_sources=data_sources or {}
        )

        # 先解析模板中的 $xxx 变量引用
        resolved_template = resolver._resolve_string(template)

        # 使用统一的变量解析补全缺失的业务变量
        template_vars = cls._resolve_variables(context, args, template_vars)

        # 使用解析后的模板填充 {xxx} 变量
        try:
            return resolved_template.format(**template_vars)
        except (KeyError, ValueError):
            # 降级处理：返回解析后的模板
            return resolved_template

    @classmethod
    def _get_config(cls) -> Dict[str, Any]:
        """获取步骤配置"""
        if not cls._step_config:
            cls._step_config = cls._load_step_config()
        return cls._step_config

    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行配置驱动的 LLM 步骤"""
        config = cls._get_config()

        # 更新类属性为配置值
        cls.step_id = config.get('step_id', cls.step_id)
        cls.step_name = config.get('step_name', cls.step_name)
        cls.prompt_template = config.get('prompt_template', '')
        cls.system_prompt = config.get('system_prompt', '')
        cls.llm_config = config.get('llm_config', {})
        cls.stage1_enabled = config.get('stage1_enabled', False)

        # 调用父类方法
        return super()._execute_step(args, context)


class ConfigDrivenAgentStep(ProcessAgentStep):
    """配置驱动的 Agent 调用型步骤

    从 YAML 配置文件加载 agent_id, prompt_template 等配置。

    使用方式：
        class MyAgentStep(ConfigDrivenAgentStep):
            _step_config_name = "my_step_config"
    """

    @classmethod
    def _build_query(cls, args: Dict[str, Any], context: Any = None) -> str:
        """从配置构建查询内容

        Args:
            args: LLM 传入的参数（已包含 data_sources 结果和 task_prompt 等）
            context: Agent 实例

        Returns:
            str: 查询内容
        """
        config = cls._get_config()
        # 同时支持 query_template 和 prompt_template
        template = config.get('query_template', '') or config.get('prompt_template', cls.prompt_template)

        if not template:
            return args.get('query', '')

        # 直接使用 Python 的 str.format() 来填充模板变量
        try:
            result = template.format(**args)
            return result
        except KeyError as e:
            # 如果有缺失的变量，返回原始模板
            return template

    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行配置驱动的 Agent 步骤"""
        config = cls._get_config()

        # 更新类属性
        cls.step_id = config.get('step_id', cls.step_id)
        cls.step_name = config.get('step_name', cls.step_name)
        
        # 从 YAML step config 读取 agent_type 和 agent_id
        cls.agent_type = config.get('agent_type', cls.agent_type)
        cls.agent_id = config.get('agent_id', '')
        
        cls.prompt_template = config.get('prompt_template', '')
        cls.formatter_config = config.get('formatter_config', {})

        return super()._execute_step(args, context)

    @classmethod
    def _get_config(cls) -> Dict[str, Any]:
        """获取步骤配置"""
        if not cls._step_config:
            cls._step_config = cls._load_step_config()
        return cls._step_config


class ConfigDrivenProcessStep(ProcessProcessStep):
    """配置驱动的直接执行型步骤

    从 YAML 配置文件加载 execution_pipeline 等配置。

    使用方式：
        class MyProcessStep(ConfigDrivenProcessStep):
            _step_config_name = "my_step_config"
    """


    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行配置驱动的 Process 步骤"""
        config = cls._get_config()

        # 更新类属性
        cls.step_id = config.get('step_id', cls.step_id)
        cls.step_name = config.get('step_name', cls.step_name)
        cls.execution_pipeline = config.get('execution_pipeline', cls.execution_pipeline)

        return super()._execute_step(args, context)

    @classmethod
    def _get_config(cls) -> Dict[str, Any]:
        """获取步骤配置"""
        if not cls._step_config:
            cls._step_config = cls._load_step_config()
        return cls._step_config


# Step 类型映射
STEP_TYPE_MAP: Dict[str, Type] = {
    'llm': ConfigDrivenLLMStep,
    'agent': ConfigDrivenAgentStep,
    'process': ConfigDrivenProcessStep,
}


def get_config_driven_step_class(step_type: str) -> Type:
    """根据 step 类型获取对应的配置驱动类

    Args:
        step_type: 步骤类型（llm/agent/process）

    Returns:
        Type: 对应的配置驱动步骤类
    """
    return STEP_TYPE_MAP.get(step_type, ConfigDrivenLLMStep)
