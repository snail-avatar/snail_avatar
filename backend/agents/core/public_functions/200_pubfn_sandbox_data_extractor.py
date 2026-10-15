# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 200_pubfn_sandbox_data_extractor.py
# @Desc    : Public Function: 沙箱数据提取工具（已弃用）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 200: 沙箱数据提取工具（已弃用）

原 step2_3 专属的数据提取功能已迁移至：
- a101_step2_3_extract_data.py: 车型信息和 VTS/SSTS 数据提取

此文件保留为占位符，避免潜在的导入错误。
如需使用沙箱数据提取，请使用对应的 step 私有函数。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnSandboxDataExtractor(AtomicFunction):
    """沙箱数据提取 Public Function（已弃用）"""

    name: str = "sandbox_data_extractor"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "沙箱数据提取工具（已弃用，请使用对应的 step 私有函数）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "操作类型（已弃用）",
                        },
                    },
                    "required": ["operation"],
                },
            },
            "metadata": {
                "type": "data_extract",
                "pubfn_index": "200",
                "deprecated": True,
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行沙箱数据提取操作（已弃用）

        所有功能已迁移至 step2_3_extract_data 私有函数。
        """
        return {
            "type": "text",
            "content": (
                "sandbox_data_extractor 已弃用。"
                "请使用 step2_3_extract_data 私有函数替代。"
            ),
        }
