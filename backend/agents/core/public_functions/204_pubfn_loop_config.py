# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 204_pubfn_loop_config.py
# @Desc    : Public Function: 通用循环配置保存
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 204: 通用循环配置保存

将循环项写入 ProcessController。
Agent ID 的设置已迁移到 206_pubfn_set_step_agent.py。

配置示例（框架自动处理）：
loop_config:
  loop_items_source: "structured_data.categories"
  target_loop_id: "CATEGORY_LOOP"

手动调用示例（post_process）：
post_process:
  - function: "set_loop_config"
    args_mapping:
      loop_items: "$result.structured_data.categories"
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnLoopConfig(AtomicFunction):
    """通用循环配置保存 Public Function

    将循环项和 agent 映射写入 ProcessController。
    支持任意字段名，通过参数动态指定。
    """

    name: str = "set_loop_config"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "设置循环配置到 ProcessController：\n"
                    "  - loop_items → 设定循环项列表\n"
                    "参数通过 YAML 配置传入，支持任意字段名。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "loop_items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "循环项列表（如专业分类）",
                        },
                        "target_loop_id": {
                            "type": "string",
                            "description": "目标循环步骤ID（可选，默认第一个循环）",
                        },
                    },
                    "required": [],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "204",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行循环配置保存

        Args:
            args: 参数字典
                - loop_items: 循环项列表
                - target_loop_id: 目标循环ID
            context: Agent 实例
        """
        loop_items = args.get("loop_items")
        target_loop_id = args.get("target_loop_id")

        return cls.set_loop_config(context, loop_items, target_loop_id, args)

    # ==================================================================
    # 内部辅助方法
    # ==================================================================

    @staticmethod
    def _get_controller(context: Any, args: Dict[str, Any] = None) -> Any:
        """从 Agent 实例获取 ProcessController

        支持多种控制器存储方式：
        1. ProcessStepAgent 子类使用 _controllers（多实例隔离）
        2. 其他 Agent 使用 _process_controller

        Args:
            context: Agent 实例
            args: 参数字典（用于获取 instance_key 或 vehicle_suffix 定位实例）

        Returns:
            ProcessController 实例，未找到返回 None
        """
        if context is None:
            return None

        controllers = getattr(context, '_controllers', {})
        if controllers:
            vkey = ""
            vehicle_suffix = ""
            if args is not None and isinstance(args, dict):
                vkey = args.get('instance_key', '')
                vehicle_suffix = args.get('vehicle_suffix', '')

            if vkey and vkey in controllers:
                return controllers[vkey]

            if vehicle_suffix and vehicle_suffix in controllers:
                return controllers[vehicle_suffix]

            # 未匹配到具体实例时取第一个（单实例场景兜底）
            first_key = next(iter(controllers))
            return controllers[first_key]

        if hasattr(context, '_process_controller'):
            return getattr(context, '_process_controller')

        return None

    # ==================================================================
    # 保存方法
    # ==================================================================

    @classmethod
    def set_loop_config(
        cls,
        context: Any,
        loop_items: Optional[List[str]],
        target_loop_id: Optional[str] = None,
        args: Dict[str, Any] = None
    ) -> None:
        """将循环配置保存到 ProcessController

        Args:
            context: Agent 实例，用于获取 ProcessController
            loop_items: 循环项列表（如专业分类）
            target_loop_id: 目标循环步骤ID（可选）
            args: 参数字典（含 instance_key/vehicle_suffix，用于定位控制器实例）
        """
        controller = cls._get_controller(context, args)
        if not controller:
            return

        # 设置循环项
        if loop_items and isinstance(loop_items, list):
            controller.set_loop_items(loop_items, loop_step_id=target_loop_id)