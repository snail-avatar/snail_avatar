# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_5_parse_result.py
# @Desc    : Public Function (a101 step2_5): SSTS数值合理性校核 - 结果解析
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_5): SSTS数值合理性校核 - 结果解析

为 step2_5 (VALIDATE_TARGETS) 提供结果解析能力：

1. read_status_from_result: 读取Agent格式化后的结果，验证 structured_data.status 字段
   Agent 调用 vts_ssts_agent 返回自然语言 → _format_result 整理为 JSON
   本函数读取该 JSON，确保 status 字段存在并有效，供条件判断节点使用。

数据来源：
- result: Agent格式化后的JSON字符串（通过 $result 注入）

必需参数（YAML 需显式声明）：
- operation: 操作类型
- result: Agent结果JSON字符串
"""

from __future__ import annotations

import json
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_5ParseResult(AtomicFunction):
    """Step2_5 结果解析 Public Function"""

    name: str = "step2_5_parse_result"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_5 专属结果解析工具。提供以下操作：\n"
                    "  - read_status_from_result: 读取Agent输出中的status字段并验证"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "操作类型：read_status_from_result",
                        },
                        "result": {
                            "type": "string",
                            "description": "Agent格式化后的JSON结果字符串",
                        },
                    },
                    "required": ["operation"],
                },
            },
            "metadata": {
                "type": "data_extract",
                "pubfn_index": "a101_step2_5",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行结果解析

        Args:
            args: 参数字典
            context: Agent 实例

        Returns:
            含 result 键的字典，result 为 JSON 字符串
        """
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        try:
            if operation == "read_status_from_result":
                return cls.read_status_from_result(args)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    @classmethod
    def read_status_from_result(cls, args: Dict[str, Any]) -> Dict[str, Any]:
        """读取Agent格式化结果中的status字段，验证并透传

        解析 $result JSON，确保 structured_data.status 字段存在且有效。
        若缺失则填充默认值 "fail"，确保条件判断节点可正常读取。

        Args:
            args: 参数字典（含 result: JSON字符串）

        Returns:
            Dict: {"result": JSON字符串}，其中 structured_data.status 已验证
        """
        result_str = args.get("result", "")

        # 尝试解析 JSON
        try:
            if isinstance(result_str, str):
                data = json.loads(result_str)
            elif isinstance(result_str, dict):
                data = result_str
            else:
                raise ValueError(f"result 类型异常: {type(result_str)}")
        except (json.JSONDecodeError, ValueError) as e:
            # JSON 解析失败，返回兜底结果
            fallback = cls._build_fallback_json(f"结果解析失败: {str(e)}")
            return {"result": fallback}

        if not isinstance(data, dict):
            fallback = cls._build_fallback_json("结果格式异常：非字典类型")
            return {"result": fallback}

        # 确保 structured_data 存在
        structured_data = data.get("structured_data", {})
        if not isinstance(structured_data, dict):
            structured_data = {}

        # 确保 status 字段存在且有效
        status = structured_data.get("status", "")
        if status not in ("pass", "fail"):
            structured_data["status"] = "fail"

        # 确保必要字段存在
        structured_data.setdefault("total", 0)
        structured_data.setdefault("passed", 0)
        structured_data.setdefault("failed", 0)
        structured_data.setdefault("failed_items", [])

        # 更新 data 中的 structured_data
        data["structured_data"] = structured_data

        # 确保 reasoning_logic 存在
        if "reasoning_logic" not in data:
            data["reasoning_logic"] = "Agent未提供推理说明"

        result_json = json.dumps(data, ensure_ascii=False)
        return {"result": result_json}

    @classmethod
    def _build_fallback_json(cls, reason: str) -> str:
        """构建兜底结果JSON

        Args:
            reason: 兜底原因

        Returns:
            str: JSON 字符串
        """
        return json.dumps({
            "structured_data": {
                "status": "fail",
                "total": 0,
                "passed": 0,
                "failed": 0,
                "failed_items": [],
            },
            "reasoning_logic": f"[兜底] {reason}",
        }, ensure_ascii=False)