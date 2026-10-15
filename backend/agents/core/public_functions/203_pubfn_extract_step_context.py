# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 203_pubfn_extract_step_context.py
# @Desc    : Public Function: 按专业分类提取 Step 上下文
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 203: 按专业分类提取 Step 上下文

从 step_context 中按专业筛选产品定义、VTS/SSTS映射、法规参考数据。
professional_category 由框架自动注入，无需 YAML 显式声明。

支持 operation 参数返回单一值，便于模板变量直接映射：
  - "all": 返回全部 dict（默认，向后兼容）
  - "get_product_info": 只返回 product_info_json 字符串
  - "get_mappings": 只返回 mappings_json 字符串
  - "get_references": 只返回 references_json 字符串
"""

from __future__ import annotations

import json
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnExtractStepContext(AtomicFunction):
    """按专业分类提取 Step 上下文 Public Function"""

    name: str = "extract_step_context_by_category"

    # 缓存：同一次 step 执行中，多次调用共享一次解析结果
    _cache: Dict[str, Dict[str, str]] = {}

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "从 step_context 中按专业筛选产品定义、VTS/SSTS映射、法规参考数据。\n"
                    "支持 operation 参数返回单一值：\n"
                    "  all / get_product_info / get_mappings / get_references"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "step_context": {
                            "type": "object",
                            "description": "步骤上下文字典 {step_id: content_str}",
                        },
                        "operation": {
                            "type": "string",
                            "description": (
                                "操作类型：all（返回dict） / "
                                "get_product_info / get_mappings / get_references"
                            ),
                        },
                    },
                    "required": ["step_context"],
                },
            },
            "metadata": {
                "type": "data_format",
                "pubfn_index": "203",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 Step 上下文按专业提取

        Args:
            args: 参数字典，需包含 step_context；professional_category 由框架自动注入
            context: 上下文对象（未使用）

        Returns:
            根据 operation 返回 str 或 dict
        """
        step_context = args.get("step_context", {})
        category = args.get("professional_category", "")
        operation = args.get("operation", "all")

        result = cls.extract_step_context_by_category(step_context, category)

        if operation == "get_product_info":
            return result["product_info_json"]
        elif operation == "get_mappings":
            return result["mappings_json"]
        elif operation == "get_references":
            return result["references_json"]

        return result

    # ==================================================================
    # 提取方法
    # ==================================================================

    @classmethod
    def extract_step_context_by_category(
        cls, step_context: Dict[str, Any], category: str
    ) -> Dict[str, str]:
        """按专业分类提取 Step 上下文数据

        从 step_context 中按专业筛选产品定义、VTS/SSTS映射、法规参考数据。

        Args:
            step_context: 步骤上下文字典 {step_id: content_str}
            category: 专业分类

        Returns:
            dict: {product_info_json, mappings_json, references_json}
        """
        product_info_json = "{}"
        mappings_json = "{}"
        references_json = "{}"

        for step_id, content_str in step_context.items():
            parts = step_id.split("_", 1)

            is_current_category = (
                len(parts) >= 2 and parts[0] == category
            ) or (
                len(parts) == 1
            )

            if not is_current_category:
                continue

            try:
                content_data = json.loads(content_str)
                if isinstance(content_data, dict) and "structured_data" in content_data:
                    structured = content_data["structured_data"]

                    if "product_information" in structured:
                        product_info_json = json.dumps(structured, ensure_ascii=False, indent=2)
                    elif "vts_ssts_mapping" in structured:
                        mappings_json = json.dumps(structured, ensure_ascii=False, indent=2)
                    elif "regulations" in structured or "VTS/SSTS_references" in structured:
                        references_json = json.dumps(structured, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "product_info_json": product_info_json,
            "mappings_json": mappings_json,
            "references_json": references_json,
        }
