# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_7_get_reasoning_logics.py
# @Desc    : 私有函数：批量读取指定步骤的 reasoning_logic 字段
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
私有函数 a101_step2_7_get_reasoning_logics

功能：批量读取当前专业的指定步骤的 reasoning_logic 字段，
用于 step2_7（专业总结）的输入数据。

输入：
  - sandbox: 沙箱实例
  - professional_category: 当前专业名
  - step_ids: 要读取的步骤ID列表

输出：
  - 格式化的 reasoning_logic 文本，包含每个步骤的步骤名和推理逻辑
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class GetStepReasoningLogicsFunction(AtomicFunction):
    """批量读取步骤 reasoning_logic 字段的函数"""

    name: str = "get_step_reasoning_logics"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "批量读取指定步骤的 reasoning_logic 字段",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "当前专业分类名称",
                        },
                        "step_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要读取的步骤ID列表",
                        },
                    },
                    "required": ["sandbox", "professional_category", "step_ids"],
                },
            },
            "metadata": {
                "type": "data_extraction",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行批量读取步骤 reasoning_logic

        Args:
            args: 参数字典
            context: 上下文对象

        Returns:
            str: 格式化的 reasoning_logic 文本
        """
        sandbox = args.get("sandbox")
        professional_category = args.get("professional_category", "")
        step_ids = args.get("step_ids", [])

        if not sandbox or not professional_category or not step_ids:
            return "暂无推理逻辑数据"

        # 构建完整的步骤ID列表（带专业名前缀）
        full_step_ids = [f"{professional_category}_{step_id}" for step_id in step_ids]

        # 读取步骤结果
        results = []
        for step_id, full_id in zip(step_ids, full_step_ids):
            step_result = sandbox.get_step_result(full_id)
            reasoning_logic = ""

            if step_result:
                # 尝试解析结果
                if isinstance(step_result, dict):
                    reasoning_logic = step_result.get("reasoning_logic", "")
                elif isinstance(step_result, str):
                    try:
                        parsed = json.loads(step_result)
                        reasoning_logic = parsed.get("reasoning_logic", "")
                    except (json.JSONDecodeError, TypeError):
                        reasoning_logic = step_result

            results.append({
                "step_id": step_id,
                "full_step_id": full_id,
                "reasoning_logic": reasoning_logic,
            })

        # 格式化输出
        output_parts = []
        output_parts.append(f"【专业「{professional_category}」的推理过程汇总】\n")

        for result in results:
            step_id = result["step_id"]
            reasoning_logic = result["reasoning_logic"]

            output_parts.append(f"--- 步骤 {step_id} ---")
            if reasoning_logic:
                output_parts.append(reasoning_logic)
            else:
                output_parts.append("（无推理逻辑记录）")
            output_parts.append("")

        return "\n".join(output_parts)
