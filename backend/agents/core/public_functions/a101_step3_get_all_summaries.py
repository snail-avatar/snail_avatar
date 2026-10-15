# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step3_get_all_summaries.py
# @Desc    : 私有函数：读取所有专业的 step2_7 总结结果
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
私有函数 a101_step3_get_all_summaries

功能：读取所有专业的 step2_7（专业总结）结果，
用于 step3（整车总结）的输入数据。

输入：
  - sandbox: 沙箱实例

输出：
  - 格式化的各专业总结文本
"""

from __future__ import annotations

import json
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class GetAllCategorySummariesFunction(AtomicFunction):
    """读取所有专业总结结果的函数"""

    name: str = "get_all_category_summaries"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "读取所有专业的 step2_7 总结结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                    },
                    "required": ["sandbox"],
                },
            },
            "metadata": {
                "type": "data_extraction",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行读取所有专业总结

        Args:
            args: 参数字典
            context: 上下文对象

        Returns:
            str: 格式化的各专业总结文本
        """
        sandbox = args.get("sandbox")

        if not sandbox:
            return "暂无专业总结数据"

        # 获取所有专业列表
        categories = cls._get_categories(sandbox)

        if not categories:
            return "暂无专业总结数据"

        # 读取各专业的总结结果
        results = []
        for category in categories:
            summary = cls._get_category_summary(sandbox, category)
            results.append({
                "category": category,
                "summary": summary,
            })

        # 格式化输出
        output_parts = []
        output_parts.append("【各专业总结汇总】\n")

        for result in results:
            category = result["category"]
            summary = result["summary"]

            output_parts.append(f"=== 专业「{category}」===")
            if summary:
                output_parts.append(summary)
            else:
                output_parts.append("（暂无总结）")
            output_parts.append("")

        return "\n".join(output_parts)

    @classmethod
    def _get_categories(cls, sandbox) -> list:
        """获取所有专业列表

        Args:
            sandbox: 沙箱实例

        Returns:
            list: 专业名称列表
        """
        try:
            # 尝试从 process_data 获取 VTS 分类数据
            vts_category_data = sandbox.get_process_data("vts_category_data")
            if vts_category_data:
                if isinstance(vts_category_data, dict):
                    return list(vts_category_data.keys())
                elif isinstance(vts_category_data, str):
                    parsed = json.loads(vts_category_data)
                    if isinstance(parsed, dict):
                        return list(parsed.keys())
        except (Exception,):
            pass

        # 尝试从 step_results 获取已执行的专业
        try:
            step_results = getattr(sandbox, 'step_results', {})
            categories = set()
            for key in step_results.keys():
                # 查找包含 SUMMARIZE_CATEGORY 的键
                if 'SUMMARIZE_CATEGORY' in key and '_SUMMARIZE_CATEGORY' in key:
                    category = key.replace('_SUMMARIZE_CATEGORY', '')
                    categories.add(category)
            return sorted(categories)
        except (Exception,):
            pass

        return []

    @classmethod
    def _get_category_summary(cls, sandbox, category: str) -> str:
        """获取指定专业的总结结果

        Args:
            sandbox: 沙箱实例
            category: 专业名称

        Returns:
            str: 总结文本
        """
        full_step_id = f"{category}_SUMMARIZE_CATEGORY"
        step_result = sandbox.get_step_result(full_step_id)

        if not step_result:
            return ""

        # 解析结果
        summary = ""
        if isinstance(step_result, dict):
            content = step_result.get("content", "")
            if isinstance(content, str):
                summary = content
            elif isinstance(content, dict):
                summary = json.dumps(content, ensure_ascii=False, indent=2)
        elif isinstance(step_result, str):
            summary = step_result

        return summary
