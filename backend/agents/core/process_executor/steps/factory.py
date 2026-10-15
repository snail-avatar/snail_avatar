# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_factory.py
# @Desc    : Step 工厂 - 从 YAML 配置动态生成步骤类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
StepFactory - 步骤工厂

功能：
- 从 YAML 配置文件动态生成步骤类
- 支持批量加载一个目录下的所有步骤配置
- 提供步骤类的注册和查询功能

使用场景：
- 当 step 完全配置化后，不再需要为每个 step 创建单独的 Python 文件
- 通过 StepFactory 可以直接从 YAML 配置动态生成步骤类

使用示例：
    # 从单个配置文件创建步骤类
    step_class = StepFactory.create_step_from_config(
        config_path="path/to/step.yaml"
    )

    # 从目录批量加载所有步骤
    step_classes = StepFactory.load_all_steps_from_directory(
        directory="path/to/config/steps/"
    )

    # 注册和查询步骤
    StepFactory.register_step(step_class)
    step_class = StepFactory.get_step("DETECT")
"""

from __future__ import annotations

import os
import importlib
from typing import Any, Dict, List, Optional, Type

from .config_driven import (
    ConfigDrivenLLMStep,
    ConfigDrivenAgentStep,
    ConfigDrivenProcessStep,
    get_config_driven_step_class,
)


class StepFactory:
    """步骤工厂 - 从 YAML 配置动态生成步骤类

    特点：
    - 支持从单个 YAML 文件创建步骤类
    - 支持从目录批量加载步骤配置
    - 提供步骤的注册、查询、遍历功能
    - 支持多种 Step 类型（LLM/Agent/Process）
    """

    # 已注册的步骤类缓存
    _registered_steps: Dict[str, Type] = {}

    @classmethod
    def create_step_from_config(cls, config_path: str) -> Optional[Type]:
        """从 YAML 配置文件创建步骤类

        Args:
            config_path: YAML 配置文件路径

        Returns:
            Type or None: 创建的步骤类，失败返回 None
        """
        if not os.path.exists(config_path):
            return None

        try:
            import yaml

            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            if not config:
                return None

            # 获取步骤基本信息
            step_type = config.get('step_type', 'llm')
            step_id = config.get('step_id', '')
            step_name = config.get('step_name', step_id)

            if not step_id:
                return None

            # 获取对应的基类
            base_class = get_config_driven_step_class(step_type)

            # 动态创建步骤类
            config_file_name = os.path.splitext(os.path.basename(config_path))[0]

            # 从配置文件路径推断 agent 目录（config_path 的结构：agent_dir/config/steps/xxx.yaml）
            config_dir = os.path.dirname(config_path)          # .../config/steps
            agent_dir = os.path.dirname(os.path.dirname(config_dir))  # .../agent_dir

            step_class = type(
                step_id + '_Step',
                (base_class,),
                {
                    'step_id': step_id,
                    'step_name': step_name,
                    '_step_config_name': config_file_name,
                    '_agent_dir': agent_dir,
                }
            )

            # 注册到缓存
            cls._registered_steps[step_id] = step_class

            return step_class

        except Exception:
            return None

    @classmethod
    def load_all_steps_from_directory(cls, directory: str) -> List[Type]:
        """从目录批量加载所有步骤配置

        Args:
            directory: YAML 配置文件所在目录

        Returns:
            list: 加载的步骤类列表
        """
        step_classes = []

        if not os.path.isdir(directory):
            return step_classes

        for filename in os.listdir(directory):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                config_path = os.path.join(directory, filename)
                step_class = cls.create_step_from_config(config_path)
                if step_class:
                    step_classes.append(step_class)

        return step_classes

    @classmethod
    def register_step(cls, step_class: Type) -> None:
        """注册步骤类

        Args:
            step_class: 步骤类（必须有 step_id 属性）
        """
        step_id = getattr(step_class, 'step_id', '')
        if step_id:
            cls._registered_steps[step_id] = step_class

    @classmethod
    def get_step(cls, step_id: str) -> Optional[Type]:
        """根据 step_id 获取步骤类

        Args:
            step_id: 步骤标识

        Returns:
            Type or None: 步骤类
        """
        return cls._registered_steps.get(step_id)

    @classmethod
    def get_all_steps(cls) -> Dict[str, Type]:
        """获取所有已注册的步骤类

        Returns:
            dict: step_id 到步骤类的映射
        """
        return dict(cls._registered_steps)

    @classmethod
    def clear_steps(cls) -> None:
        """清除所有已注册的步骤类"""
        cls._registered_steps.clear()

    @classmethod
    def load_steps_from_agent(cls, agent_dir: str) -> List[Type]:
        """从 Agent 目录加载所有步骤

        Args:
            agent_dir: Agent 根目录路径

        Returns:
            list: 加载的步骤类列表
        """
        config_dir = os.path.join(agent_dir, "config", "steps")
        if os.path.isdir(config_dir):
            return cls.load_all_steps_from_directory(config_dir)
        return []

    @classmethod
    def get_step_ids(cls) -> List[str]:
        """获取所有已注册的 step_id 列表

        Returns:
            list: step_id 列表
        """
        return list(cls._registered_steps.keys())

    @classmethod
    def create_step_from_config_dict(cls, config: Dict[str, Any],
                                      config_name: str = "") -> Optional[Type]:
        """从配置字典直接创建步骤类

        Args:
            config: 步骤配置字典
            config_name: 配置名称（用于 _step_config_name）

        Returns:
            Type or None: 创建的步骤类
        """
        step_type = config.get('step_type', 'llm')
        step_id = config.get('step_id', '')
        step_name = config.get('step_name', step_id)

        if not step_id:
            return None

        base_class = get_config_driven_step_class(step_type)

        step_class = type(
            step_id + '_Step',
            (base_class,),
            {
                'step_id': step_id,
                'step_name': step_name,
                '_step_config_name': config_name or step_id.lower(),
                '_step_config': config,  # 直接注入配置
            }
        )

        cls._registered_steps[step_id] = step_class

        return step_class

    @classmethod
    def scan_configs(cls, agent_dir: str, workflow=None) -> Dict[str, Type]:
        """扫描 Agent 目录下的所有步骤配置并注册

        Args:
            agent_dir: Agent 根目录路径
            workflow: ProcessDefinition 对象（可选），用于从 process.yaml 加载步骤配置

        Returns:
            dict: {step_id: StepClass, ...}
        """
        # 先清除旧的注册
        cls.clear_steps()

        # 优先从 config/steps 目录加载（详细配置）
        config_dir = os.path.join(agent_dir, "config", "steps")
        if os.path.isdir(config_dir):
            cls.load_all_steps_from_directory(config_dir)

        # 从 workflow 定义中加载步骤（作为补充，确保所有步骤都有注册）
        if workflow is not None:
            step_configs = workflow.get_all_step_configs()
            for step_config in step_configs:
                step_id = step_config.get("step_id", "")
                if step_id and step_id not in cls._registered_steps:
                    # 使用 process.yaml 中的配置创建步骤类
                    step_type = step_config.get("type", "llm")
                    config_name = step_config.get("config_file", step_id.lower())
                    
                    # 构建完整配置
                    full_config = {
                        "step_type": step_type,
                        "step_id": step_id,
                        "step_name": step_config.get("step_name", step_id),
                        **step_config
                    }
                    
                    cls.create_step_from_config_dict(full_config, config_name)

        return cls.get_all_steps()
