# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : context_provider.py
# @Desc    : 上下文提供者接口 - IContextProvider
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
上下文提供者 - IContextProvider 接口与 YamlContextProvider 默认实现

为 VariableResolver 和 Step 模板提供业务变量解析扩展点。
框架层（process_executor）仅依赖抽象接口，保持与业务解耦。
业务层（Agent）通过实现此接口注入业务特定的变量解析逻辑。

用途：
- 解析 YAML 配置中的业务变量引用（如 {professional_category}、{product_data}）
- 为 Planner/Scheduler 提供可发现的 Agent 输入接口契约
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class IContextProvider(ABC):
    """上下文提供者接口 - 变量解析的扩展点

    框架层在解析变量时，若遇到未知变量名，会调用此接口。
    业务层实现此接口，将业务变量名映射到实际数据获取逻辑。
    """

    @abstractmethod
    def resolve_context(self, var_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """解析上下文变量

        Args:
            var_name: 变量名 (如 'professional_category', 'product_data')
            args: 当前步骤的输入参数

        Returns:
            变量的值，如果无法解析则返回 None
        """
        pass


class YamlContextProvider(IContextProvider):
    """基于 YAML 配置的上下文提供者（框架默认实现）

    从 process.yaml 的 context_vars 配置中解析业务变量映射，
    将业务语义变量（如 category、product_data）映射到实际数据获取逻辑。

    支持的配置类型：
    - mapping: 直接映射到另一个变量（如 category → loop_item）
    - value: 常量值
    """

    def __init__(self, vocab_config: Dict[str, Any], agent_instance):
        self._config = vocab_config or {}
        self._agent = agent_instance

    def resolve_context(self, var_name: str, args: Dict[str, Any]) -> Optional[Any]:
        if var_name not in self._config:
            return None

        entry = self._config[var_name]

        # mapping 类型：直接映射到另一个变量
        if 'mapping' in entry:
            return self._resolve_mapping(entry, args)

        # const 类型：常量值
        return entry.get('value')

    def _resolve_mapping(self, entry: Dict[str, Any], args: Dict[str, Any]) -> Optional[Any]:
        """解析 mapping 类型：直接映射到另一个变量的值

        优先从 args 中获取，然后从执行状态中获取。
        """
        source = entry.get('mapping', '')
        if not source:
            return None

        # 优先从 args 中获取（args 中通常有 loop_item, instance_key 等）
        if source in args:
            return args[source]

        # 从执行状态中获取
        state = self._get_current_state(args)
        if state and source in state:
            return state[source]

        return None

    def _get_current_state(self, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取 Agent 当前的执行状态

        优先从 args 中的 instance_key/vehicle_suffix 获取对应实例的状态，
        否则回退到第一个可用实例的状态。
        """
        get_state_fn = getattr(self._agent, 'get_execution_state', None)
        if not get_state_fn or not callable(get_state_fn):
            return {}

        controllers = getattr(self._agent, '_controllers', {})
        if not controllers:
            return {}

        # 优先使用 args 中的 instance_key 或 vehicle_suffix
        if args:
            vkey = args.get('instance_key', '')
            vehicle_suffix = args.get('vehicle_suffix', '')
            if vkey and vkey in controllers:
                return get_state_fn(vkey)
            if vehicle_suffix and vehicle_suffix in controllers:
                return get_state_fn(vehicle_suffix)

        # 回退到第一个可用实例
        first_key = next(iter(controllers.keys()))
        return get_state_fn(first_key)
