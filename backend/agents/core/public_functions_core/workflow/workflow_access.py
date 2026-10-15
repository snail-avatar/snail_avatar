# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_access.py
# @Desc    : 跨 Agent 共享模块：工作流访问上下文（WorkflowAgentContext）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：工作流访问上下文（WorkflowAgentContext）

提供工作流实例的懒加载、缓存和访问能力。
适用于所有基于工作流（workflow）引擎的计算型 agent。

使用方式:
    from snail_avatar.backend.agents.core.public_functions_core.workflow.workflow_access import (
        WorkflowAgentContext,
        get_default_context,
    )

    # 创建上下文（在 agent 初始化时）
    ctx = WorkflowAgentContext(
        config_dir="/path/to/agent/config",
        memory_db_getter=get_memory_db,
        domain="economy",
    )

    # 获取指定车型的工作流实例
    workflow = ctx.get_workflow_for_vehicle("evLTO")

    # 执行计算
    workflow.run_all(reset_first=True)
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from .workflow_discovery import (
    discover_all_workflows_in_dir,
    select_workflow_yaml_for_vehicle,
)
from ..common.memory_db import get_memory_db


class WorkflowAgentContext:
    """工作流计算型 agent 的共享上下文

    封装了"如何找到工作流 YAML"、"如何构造 workflow 实例"等 agent-specific 逻辑，
    并提供基于车型的懒加载和缓存机制。

    Attributes:
        config_dir: 工作流配置文件所在的目录
        memory_db_getter: 获取 memory_db 的函数
        domain: 领域标识（如 "economy"、"power"），用于匹配工作流
        _workflow_cache: 工作流实例缓存（key: 车型后缀）
    """

    def __init__(
        self,
        config_dir: str,
        memory_db_getter: Optional[Callable[[], Any]] = None,
        domain: str = "",
    ) -> None:
        """初始化 WorkflowAgentContext

        Args:
            config_dir: 配置目录路径
            memory_db_getter: 获取 memory_db 的回调函数，默认使用 public_functions_core 的 get_memory_db
            domain: 领域标识，用于匹配工作流 YAML
        """
        self.config_dir = os.path.normpath(config_dir)
        self.memory_db_getter = memory_db_getter or get_memory_db
        self.domain = domain
        self._workflow_cache: Dict[str, Any] = {}

    def discover_all_workflows(self) -> List[Dict[str, Any]]:
        """发现本 agent 目录下的所有工作流

        Returns:
            List[Dict]: 工作流列表，详见 discover_all_workflows_in_dir 的返回值
        """
        return discover_all_workflows_in_dir(self.config_dir)

    def get_workflow_for_vehicle(self, vehicle_suffix: str = "") -> Any:
        """懒加载并返回指定车型的 workflow 实例

        Args:
            vehicle_suffix: 车型后缀，如 "evLTO"、"reevLTO"

        Returns:
            workflow 实例（具有 run_all、graph、all_nodes 等属性的对象）。
            如果加载失败可能返回 None。
        """
        cache_key = vehicle_suffix or "default"
        if cache_key in self._workflow_cache:
            return self._workflow_cache[cache_key]

        db = self.memory_db_getter()

        yaml_path = select_workflow_yaml_for_vehicle(
            config_dir=self.config_dir,
            vehicle_suffix=vehicle_suffix,
            domain=self.domain,
        )

        if yaml_path is None:
            print(f"[WorkflowAgentContext] 未找到可用的工作流 YAML（目录: {self.config_dir}）")
            return None

        try:
            from snail_avatar.backend.agents.core.workflow_base.workflow_builder import (
                build_workflow_from_yaml_file,
            )

            workflow = build_workflow_from_yaml_file(
                yaml_path=yaml_path,
                vehicle_suffix=vehicle_suffix,
                memory_db=db,
            )

            self._workflow_cache[cache_key] = workflow
            return workflow
        except Exception as e:
            print(f"[WorkflowAgentContext] 加载工作流失败: {e}")
            return None

    def clear_cache(self) -> None:
        """清空工作流缓存（当数据库或车型信息变化时调用）"""
        self._workflow_cache.clear()


def get_default_context(config_dir: str, domain: str = "") -> WorkflowAgentContext:
    """获取默认的 WorkflowAgentContext 实例

    使用 public_functions_core.common.memory_db 的 get_memory_db 函数作为默认的数据库获取器。

    Args:
        config_dir: 配置目录路径
        domain: 领域标识（如 "economy"、"power"）

    Returns:
        WorkflowAgentContext 实例
    """
    return WorkflowAgentContext(
        config_dir=config_dir,
        memory_db_getter=get_memory_db,
        domain=domain,
    )