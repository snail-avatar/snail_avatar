# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 206_pubfn_set_step_agent.py
# @Desc    : Public Function: Agent 类型映射设置
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 206: Agent 类型映射设置

用于写入 calculator 和 expert 两种类型的 Agent ID 映射到 ProcessSandbox。
支持两种模式：
1. 单类型设置：指定 agent_type + mapping
2. 批量设置：同时设置 calculator 和 expert 两组映射

使用示例（post_process）：
post_process:
  # 批量设置两组映射
  - function: "set_step_agent"
    args_mapping:
      calculator_mapping: "$result.structured_data.workflow_mapping"
      expert_mapping: "$result.structured_data.expert_mapping"
  
  # 单类型设置
  - function: "set_step_agent"
    args_mapping:
      agent_type: "calculator"
      mapping: "$result.structured_data.workflow_mapping"
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnSetStepAgent(AtomicFunction):
    """Agent 类型映射设置 Public Function

    将 calculator 和 expert 两种类型的 Agent ID 映射写入 ProcessSandbox，
    供后续 Agent 步骤按类型读取。
    """

    name: str = "set_step_agent"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "设置 Agent 类型映射：\n"
                    "  - agent_type: Agent 类型（calculator 或 expert）\n"
                    "  - mapping: {loop_item: agent_id} 字典（单类型设置）\n"
                    "  - calculator_mapping: {loop_item: agent_id} 字典（批量设置）\n"
                    "  - expert_mapping: {loop_item: agent_id} 字典（批量设置）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_type": {
                            "type": "string",
                            "description": "Agent 类型（calculator 或 expert）",
                        },
                        "mapping": {
                            "type": "object",
                            "description": "{loop_item: agent_id} 字典，单类型设置",
                        },
                        "calculator_mapping": {
                            "type": "object",
                            "description": "{loop_item: agent_id} 字典，计算器类型映射",
                        },
                        "expert_mapping": {
                            "type": "object",
                            "description": "{loop_item: agent_id} 字典，专家类型映射",
                        },
                    },
                    "required": [],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "206",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 Agent 类型映射设置

        Args:
            args: 参数字典
                - agent_type: Agent 类型（calculator/expert）
                - mapping: {loop_item: agent_id} 字典
                - calculator_mapping: {loop_item: agent_id} 字典
                - expert_mapping: {loop_item: agent_id} 字典
            context: Agent 实例
        """
        sandbox = cls._get_sandbox(context, args)
        if not sandbox:
            return {"status": "error", "message": "未找到 ProcessSandbox"}

        # 方式1：批量设置两组映射（最常用）
        calculator_mapping = args.get("calculator_mapping")
        expert_mapping = args.get("expert_mapping")
        
        if calculator_mapping or expert_mapping:
            count = 0
            if calculator_mapping and isinstance(calculator_mapping, dict):
                sandbox.set_agent_type_mapping("calculator", calculator_mapping)
                count += 1
            if expert_mapping and isinstance(expert_mapping, dict):
                sandbox.set_agent_type_mapping("expert", expert_mapping)
                count += 1
            return {"status": "success", "message": f"已批量设置 {count} 组映射"}

        # 方式2：单类型设置
        agent_type = args.get("agent_type")
        mapping = args.get("mapping")
        
        if agent_type and mapping and isinstance(mapping, dict):
            sandbox.set_agent_type_mapping(agent_type, mapping)
            return {"status": "success", "message": f"已设置 {agent_type} 的 {len(mapping)} 个映射"}

        return {"status": "error", "message": "参数不足，需要指定 agent_type+mapping 或 calculator_mapping+expert_mapping"}

    # ==================================================================
    # 内部辅助方法
    # ==================================================================

    @staticmethod
    def _get_sandbox(context: Any, args: Dict[str, Any] = None) -> Any:
        """从 Agent 实例获取 ProcessSandbox

        Args:
            context: Agent 实例
            args: 参数字典（用于定位控制器实例）

        Returns:
            ProcessSandbox 实例，未找到返回 None
        """
        if context is None:
            return None

        # 优先从 _controllers 获取
        controllers = getattr(context, '_controllers', {})
        if controllers:
            vkey = ""
            vehicle_suffix = ""
            if args is not None and isinstance(args, dict):
                vkey = args.get('instance_key', '')
                vehicle_suffix = args.get('vehicle_suffix', '')

            if vkey and vkey in controllers:
                controller = controllers[vkey]
                return getattr(controller, '_sandbox', None) if controller else None

            if vehicle_suffix and vehicle_suffix in controllers:
                controller = controllers[vehicle_suffix]
                return getattr(controller, '_sandbox', None) if controller else None

            # 未匹配到具体实例时取第一个
            first_key = next(iter(controllers))
            controller = controllers[first_key]
            return getattr(controller, '_sandbox', None) if controller else None

        # 回退：从 _process_controller 获取
        if hasattr(context, '_process_controller'):
            controller = getattr(context, '_process_controller')
            return getattr(controller, '_sandbox', None) if controller else None

        return None
