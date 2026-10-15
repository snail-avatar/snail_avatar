# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 202_pubfn_format_vts_data.py
# @Desc    : Public Function: 格式化 VTS 数据供 Prompt 使用
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 202: 格式化 VTS 数据供 Prompt 使用

将 VTS 指标列表格式化为可读文本，供 LLM Prompt 使用。
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnFormatVtsData(AtomicFunction):
    """格式化 VTS 数据供 Prompt 使用 Public Function"""

    name: str = "format_vts_data_for_prompt"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "将 VTS 指标列表格式化为可读文本供 LLM Prompt 使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vts_list": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "VTS 指标列表，每项包含 name, unit, sub_category, param_values 等字段",
                        },
                    },
                    "required": [],
                },
            },
            "metadata": {
                "type": "data_format",
                "pubfn_index": "202",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 VTS 数据格式化

        Args:
            args: 参数字典，可选包含 vts_list 和 professional_category
            context: 上下文对象（用于获取 sandbox）

        Returns:
            str: 格式化后的文本
        """
        # 1. 如果直接提供了 vts_list，优先使用
        vts_list = args.get("vts_list")
        
        # 2. 如果没有 vts_list，尝试从 sandbox 获取（新嵌套结构）
        if not vts_list:
            professional_category = args.get("professional_category", "")
            
            if context:
                # 尝试从 context 获取 sandbox
                sandbox = cls._get_sandbox_from_context(context)
                if sandbox:
                    vts_category_data = sandbox.get_process_data("vts_category_data") or {}
                    category_data = vts_category_data.get(professional_category, {})
                    # 将嵌套结构扁平化为列表
                    if isinstance(category_data, dict):
                        vts_list = cls._flatten_nested_structure(category_data)
                    else:
                        vts_list = []
        
        return cls.format_vts_data_for_prompt(vts_list or [])

    @classmethod
    def _get_sandbox_from_context(cls, context: Any) -> Any:
        """从 context 获取 sandbox 实例

        Args:
            context: 上下文对象

        Returns:
            sandbox 实例或 None
        """
        # 尝试直接获取 sandbox 属性
        sandbox = getattr(context, 'sandbox', None)
        if sandbox:
            return sandbox
        
        # 尝试从 process_controller 获取
        controller = getattr(context, '_process_controller', None)
        if controller and hasattr(controller, 'get_sandbox'):
            return controller.get_sandbox()
        
        # 尝试从 _controllers 获取
        controllers = getattr(context, '_controllers', None)
        if controllers:
            first_controller = next(iter(controllers.values()), None)
            if first_controller and hasattr(first_controller, 'get_sandbox'):
                return first_controller.get_sandbox()
        
        # 尝试从 _sandbox 属性获取
        sandbox = getattr(context, '_sandbox', None)
        if sandbox:
            return sandbox
        
        return None

    # ==================================================================
    # 嵌套结构扁平化
    # ==================================================================

    @classmethod
    def _flatten_nested_structure(cls, category_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将新嵌套结构扁平化为 VTS 列表

        新结构：{二级专业: {VTS_items: [...], SSTS_parameter: [...], 计算公式: ""}}
        输出：[{name, unit, sub_category, param_values, SSTS_parameter, 计算公式}, ...]

        Args:
            category_data: 嵌套结构

        Returns:
            List[Dict]: 扁平化后的 VTS 条目列表
        """
        flat_list = []
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue

            vts_items = group_content.get("VTS_items", [])
            ssts_params = group_content.get("SSTS_parameter", [])
            formula = group_content.get("计算公式", "")

            for vts_item in vts_items:
                if not isinstance(vts_item, dict):
                    continue
                entry = {
                    "name": vts_item.get("name", ""),
                    "unit": vts_item.get("unit", ""),
                    "sub_category": sub_cat_name,
                    "param_values": vts_item.get("param_values", []),
                    "SSTS_parameter": ssts_params,
                    "计算公式": formula,
                }
                flat_list.append(entry)

        return flat_list

    # ==================================================================
    # 格式化方法
    # ==================================================================

    @classmethod
    def format_vts_data_for_prompt(cls, vts_list: List[Dict[str, Any]]) -> str:
        """格式化 VTS 数据为可读文本供 LLM 使用

        Args:
            vts_list: VTS 指标列表，每个条目包含 name, unit, sub_category, param_values 等字段

        Returns:
            str: 格式化后的文本
        """
        if not vts_list:
            return "（暂无 VTS 数据，请从上下文信息中提取）"

        lines = []
        for vts_item in vts_list:
            name = vts_item.get("name", "")
            unit = vts_item.get("单位", vts_item.get("unit", ""))
            sub_category = vts_item.get("sub_category", "")
            param_values = vts_item.get("param_values", [])

            param_texts = []
            for param in param_values:
                db_key = param.get("db_key", "")
                value = param.get("值", param.get("value", "NaN"))
                param_texts.append(f"{db_key}={value}")

            line = f"- {name}（单位: {unit}，子分类: {sub_category}）"
            if param_texts:
                line += f"，参数: {', '.join(param_texts)}"
            lines.append(line)

        return "\n".join(lines)
