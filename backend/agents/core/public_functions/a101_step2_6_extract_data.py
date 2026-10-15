# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_6_extract_data.py
# @Desc    : Public Function (a101 step2_6): 优化SSTS - 数据提取
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_6): 优化SSTS - 数据提取

为 step2_6 (OPTIMIZE_SSTS) 提供数据提取能力，返回 JSON 格式的原始数据：

1. format_vts_ssts_list: 从 process_data.vts_category_data 提取当前专业的完整 VTS+SSTS 清单
   返回 JSON 字符串，包含 VTS 参数信息、SSTS 参数列表和计算公式

2. extract_validate_result: 从 step_results 提取上一步 VALIDATE_TARGETS 的校核结果
   返回 JSON 字符串，包含 structured_data 和 reasoning_logic

数据来源：
- process_data: vts_category_data 字段
- step_results: {专业名}_VALIDATE_TARGETS 条目

必需参数（YAML 需显式声明）：
- sandbox: 沙箱实例
- operation: 操作类型
"""

from __future__ import annotations

import json
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_6ExtractData(AtomicFunction):
    """Step2_6 数据提取 Public Function"""

    name: str = "step2_6_extract_data"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_6 专属数据提取工具。提供以下操作：\n"
                    "  - format_vts_ssts_list: 提取当前专业的 VTS+SSTS 参数清单（JSON格式）\n"
                    "  - extract_validate_result: 提取上一步校核结果（JSON格式）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "操作类型：format_vts_ssts_list / extract_validate_result",
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类（如空气动力学、底盘等）",
                        },
                    },
                    "required": ["operation", "sandbox"],
                },
            },
            "metadata": {
                "type": "data_extract",
                "pubfn_index": "a101_step2_6",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行数据提取

        Args:
            args: 参数字典，必须包含 operation 和 sandbox
            context: Agent 实例

        Returns:
            str: JSON 格式的提取结果
        """
        operation = args.get("operation", "")
        if not operation:
            return json.dumps({"error": "必须提供 operation 参数"}, ensure_ascii=False)

        sandbox = args.get("sandbox") or cls._get_sandbox_from_context(context)
        category = args.get("professional_category", "")

        try:
            if operation == "format_vts_ssts_list":
                return cls.format_vts_ssts_list(sandbox, category)

            elif operation == "extract_validate_result":
                return cls.extract_validate_result(sandbox, category)

            else:
                return json.dumps({"error": f"未知的操作类型 '{operation}'"}, ensure_ascii=False)

        except Exception as e:
            return json.dumps({"error": f"执行失败: {str(e)}"}, ensure_ascii=False)

    @classmethod
    def _get_sandbox_from_context(cls, context: Any) -> Any:
        """从 context 获取 sandbox 实例"""
        if context is None:
            return None

        sandbox = getattr(context, 'sandbox', None)
        if sandbox:
            return sandbox

        controllers = getattr(context, '_controllers', None)
        if controllers:
            first_controller = next(iter(controllers.values()), None)
            if first_controller and hasattr(first_controller, 'get_sandbox'):
                return first_controller.get_sandbox()

        sandbox = getattr(context, '_sandbox', None)
        if sandbox:
            return sandbox

        return None

    # ==================================================================
    # 操作1：提取 VTS+SSTS 参数清单（JSON格式）
    # ==================================================================

    @classmethod
    def format_vts_ssts_list(cls, sandbox: Any, category: str) -> str:
        """从 process_data 提取当前专业的 VTS+SSTS 参数清单（新嵌套结构）

        从 sandbox.process_data.vts_category_data 读取指定专业的 VTS 列表，
        返回 JSON 字符串，按二级专业分组展示 VTS 基本信息、SSTS_parameter 和计算公式。

        Args:
            sandbox: 沙箱实例
            category: 专业分类名

        Returns:
            str: JSON 格式的 VTS+SSTS 清单
        """
        if not sandbox:
            return json.dumps([], ensure_ascii=False)

        vts_category_data = sandbox.get_process_data("vts_category_data") or {}
        category_data = vts_category_data.get(category, {})

        if not category_data or not isinstance(category_data, dict):
            return json.dumps([], ensure_ascii=False)

        # 精简输出：按二级专业分组
        result = []
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            entry = {
                "sub_category": sub_cat_name,
                "VTS_items": group_content.get("VTS_items", []),
                "SSTS_parameter": group_content.get("SSTS_parameter", []),
                "计算公式": group_content.get("计算公式", ""),
            }
            result.append(entry)

        return json.dumps(result, ensure_ascii=False, indent=2)

    # ==================================================================
    # 操作2：提取上一步校核结果（JSON格式）
    # ==================================================================

    @classmethod
    def extract_validate_result(cls, sandbox: Any, category: str) -> str:
        """从 step_results 提取上一步 VALIDATE_TARGETS 的校核结果

        读取 key 为 {category}_VALIDATE_TARGETS 的步骤结果，
        返回 JSON 字符串，包含 structured_data 和 reasoning_logic。

        Args:
            sandbox: 沙箱实例
            category: 专业分类名

        Returns:
            str: JSON 格式的校核结果
        """
        if not sandbox:
            return json.dumps({}, ensure_ascii=False)

        # 构建 key: {专业名}_VALIDATE_TARGETS
        step_key = f"{category}_VALIDATE_TARGETS"
        result_data = sandbox.get_step_result(step_key)

        if not result_data or not isinstance(result_data, dict):
            return json.dumps({}, ensure_ascii=False)

        # 提取关键字段
        structured_data = result_data.get("structured_data", {})
        reasoning_logic = result_data.get("reasoning_logic", "")

        output = {
            "structured_data": structured_data,
            "reasoning_logic": reasoning_logic,
        }

        return json.dumps(output, ensure_ascii=False, indent=2)