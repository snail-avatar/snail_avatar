# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_function_factory.py
# @Desc    : 工作流工具函数工厂类（配置驱动）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
工作流工具函数工厂类

根据YAML配置动态创建工具函数子类，支持：
- run_full_calculation: 完整计算
- modify_and_recalculate: 修改参数并重新计算
- run_doe_analysis: DOE分析
- semantic_summary: 语义概览
- semantic_logic: 语义逻辑说明
- list_ssts_params: 参数列表
- list_vehicles_and_workflows: 车型和工作流列表

用法：
    tools_config = [
        {
            "type": "run_full_calculation",
            "name": "run_full_economy_calculation",
            "description": "执行完整的经济性计算流程",
            "tool_title": "经济性计算"
        },
        ...
    ]
    registry = WorkflowFunctionFactory.create_registry(tools_config, agent_dir, panel_id, domain_title)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionRegistry
from snail_avatar.backend.agents.core.public_functions_core.workflow.panel_workflow_helper import (
    get_workflow_from_panel,
)

from .function_templates.run_full_calculation import AbstractRunFullCalculationFunction
from .function_templates.modify_and_recalculate import AbstractModifyAndRecalculateFunction
from .function_templates.run_doe_analysis import AbstractDOEAnalysisFunction
from .function_templates.semantic_summary import AbstractSemanticSummaryFunction
from .function_templates.list_ssts_params import AbstractListSSTSParamsFunction
from .function_templates.list_vehicles import AbstractListVehiclesFunction
from .function_templates.list_workflows import AbstractListWorkflowsFunction


class WorkflowFunctionFactory:
    """工作流工具函数工厂类"""

    TOOL_TYPE_MAP = {
        "run_full_calculation": AbstractRunFullCalculationFunction,
        "modify_and_recalculate": AbstractModifyAndRecalculateFunction,
        "run_doe_analysis": AbstractDOEAnalysisFunction,
        "semantic_summary": AbstractSemanticSummaryFunction,
        "semantic_logic": AbstractSemanticSummaryFunction,
        "list_ssts_params": AbstractListSSTSParamsFunction,
        "list_vehicles": AbstractListVehiclesFunction,
        "list_workflows": AbstractListWorkflowsFunction,
    }

    @classmethod
    def create_registry(
        cls,
        tools_config: List[Dict[str, Any]],
        agent_dir: str,
        panel_id: str,
        domain_title: str,
    ) -> FunctionRegistry:
        """根据配置创建工具函数注册中心

        Args:
            tools_config: 工具配置列表
            agent_dir: Agent目录路径
            panel_id: 面板ID（用于获取工作流上下文）
            domain_title: 领域标题（如"经济性"、"动力性"）

        Returns:
            FunctionRegistry: 工具函数注册中心
        """
        registry = FunctionRegistry()

        def _context_getter(vehicle_suffix: str = "") -> Optional[Any]:
            return get_workflow_from_panel(panel_id, vehicle_suffix)

        for tool_cfg in tools_config:
            tool_type = tool_cfg.get("type")
            template_class = cls.TOOL_TYPE_MAP.get(tool_type)
            if template_class is None:
                continue

            attrs: Dict[str, Any] = {
                "name": tool_cfg.get("name", ""),
                "description": tool_cfg.get("description", ""),
                "tool_title": tool_cfg.get("tool_title", ""),
                "domain_title": domain_title,
                "_context_getter": lambda vs, panel_id=panel_id: get_workflow_from_panel(panel_id, vs),
            }

            subclass = type(
                f"{tool_type.capitalize()}Function_{tool_cfg.get('name', 'generic')}",
                (template_class,),
                attrs,
            )

            registry.register(subclass)

        return registry