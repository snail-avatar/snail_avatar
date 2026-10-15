# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 205_pubfn_save_data_to_process.py
# @Desc    : Public Function: 通用数据保存到 process_data
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 205: 通用数据保存到 process_data

将任意数据写入沙箱的 process_data 字段，供后续步骤使用。

使用示例：
post_process:
  - function: "build_vts_structure"
    output: "vts_structure"
  
  - function: "save_data_to_process"
    args_mapping:
      key: "vts_structure"
      data: "$post.vts_structure"
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnSaveDataToProcess(AtomicFunction):
    """通用数据保存到 process_data Public Function

    将数据写入沙箱的 process_data 字段。
    支持 context 自动注入，无需显式声明。
    """

    name: str = "save_data_to_process"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "将数据保存到 process_data：\n"
                    "  - key: 数据的键名\n"
                    "  - data: 数据内容\n"
                    "sandbox/context 由框架自动注入。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "数据的键名（将存储在 process_data[key]）",
                        },
                        "data": {
                            "type": "object",
                            "description": "要保存的数据内容",
                        },
                    },
                    "required": ["key", "data"],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "205",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行数据保存

        Args:
            args: 参数字典
                - key: 数据的键名
                - data: 数据内容
            context: Agent 实例
        """
        key = args.get("key")
        data = args.get("data")

        if not key:
            return None

        return cls.save_to_process(context, key, data, args)

    # ==================================================================
    # 内部辅助方法
    # ==================================================================

    @staticmethod
    def _get_sandbox(context: Any, args: Dict[str, Any] = None) -> Any:
        """从 Agent 实例获取沙箱实例

        Args:
            context: Agent 实例
            args: 参数字典

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

        # 最终回退：从 context 直接获取 sandbox
        return getattr(context, '_sandbox', None)

    # ==================================================================
    # 保存方法
    # ==================================================================

    @classmethod
    def save_to_process(
        cls,
        context: Any,
        key: str,
        data: Any,
        args: Dict[str, Any] = None
    ) -> None:
        """将数据保存到 process_data

        Args:
            context: Agent 实例，用于获取沙箱
            key: 数据的键名
            data: 数据内容
            args: 参数字典（用于定位控制器实例）
        """
        sandbox = cls._get_sandbox(context, args)
        if not sandbox:
            return

        sandbox.set_process_data(key, data)