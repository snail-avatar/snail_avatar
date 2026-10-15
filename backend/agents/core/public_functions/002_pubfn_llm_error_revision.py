# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 002_pubfn_llm_error_revision.py
# @Desc    : Public Function: LLM 错误修订 - 基于LLM的通用错误修订工具包装类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (002): LLM 错误修订

基于 LLMErrorRevision 工具的包装类，提供在 YAML 配置中直接调用的能力。

核心功能：
1. 通过 Step A（修订）和 Step B（验收）的循环机制，自动检测和修复数据错误
2. 完全依赖 LLM 推理能力进行错误检测和修复
3. 双 Prompt 驱动：step_a_prompt 定义"待修订问题"，step_b_prompt 定义"达标标准"
4. 支持业务层私有函数处理修订结果（如 db_key 匹配填充）
5. LLM 配置参数从配置文件读取，无需在调用时传递

使用场景（YAML 配置示例）：
    post_process:
      - function: "llm_error_revision"
        args_mapping:
          data: "$result.structured_data"
          step_a_prompt: "检查并修复SSTS参数遗漏问题"
          step_b_prompt: "验收标准：所有VTS的SSTS_parameter列表不为空"
        output: "revised_data"
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnLlmErrorRevision(AtomicFunction):
    """LLM 错误修订 Public Function

    作为 LLMErrorRevision 工具的包装类，使其能够作为 public function 被 YAML 配置调用。
    """

    name: str = "llm_error_revision"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "LLM 错误修订工具：\n"
                    "  - 通过 Step A（修订）和 Step B（验收）的循环机制，自动修复数据错误\n"
                    "  - 完全依赖 LLM 推理能力进行错误检测和修复\n"
                    "  - 适用于任何需要 LLM 生成 + 修订的场景"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": "待修订的原始数据（任意可序列化类型）",
                        },
                        "step_a_prompt": {
                            "type": "string",
                            "description": "步骤A - 待修订问题描述（告诉LLM要修复什么）",
                        },
                        "step_b_prompt": {
                            "type": "string",
                            "description": "步骤B - 达标标准描述（告诉LLM如何判断合格）",
                        },
                    },
                    "required": ["data", "step_a_prompt", "step_b_prompt"],
                },
            },
            "metadata": {
                "type": "llm_tool",
                "pubfn_index": "002",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 LLM 错误修订原子操作

        解析参数并调用 LLMErrorRevision 工具。

        Args:
            args: 参数字典，必须包含 data、step_a_prompt、step_b_prompt
            context: 可选上下文对象

        Returns:
            dict: 修订结果，包含以下字段:
                - status: "success" | "max_retries_reached" | "error"
                - revised_data: 最终修订后的数据
                - is_valid: 是否通过最终验收
                - attempts: 实际迭代次数
                - remaining_issues: 最终验收发现的问题列表
                - history: 历史迭代记录
        """
        # 参数校验
        data = args.get("data")
        step_a_prompt = args.get("step_a_prompt", "")
        step_b_prompt = args.get("step_b_prompt", "")

        if data is None:
            return cls._error_result("data 参数不能为空")
        if not step_a_prompt:
            return cls._error_result("step_a_prompt 参数不能为空")
        if not step_b_prompt:
            return cls._error_result("step_b_prompt 参数不能为空")

        # 获取 LLMErrorRevision 工具实例
        try:
            from snail_avatar.backend.agents.core.tools.LLM_tools import get_llm_error_revision
            revision_tool = get_llm_error_revision()
        except Exception as e:
            return cls._error_result(f"获取 LLMErrorRevision 工具失败: {str(e)}")

        # 调用修订工具
        try:
            # 从 context 中提取 conversation_history（如果可用）
            conversation_history = None
            if context and hasattr(context, 'conversation_history'):
                conversation_history = context.conversation_history

            result = revision_tool.revise(
                data=data,
                step_a_prompt=step_a_prompt,
                step_b_prompt=step_b_prompt,
                conversation_history=conversation_history,
            )

            # 处理结果：返回 revised_data 供后续步骤使用
            # 同时在 metadata 中保留完整的修订信息
            revised_data = result.get("revised_data")
            
            # 如果修订成功，返回修订后的数据
            # 如果修订失败，返回原始数据并附带错误信息
            if result.get("status") == "error":
                return {
                    "type": "text",
                    "content": f"LLM错误修订失败: {result.get('last_error', '未知错误')}",
                    "original_data": data,
                }
            
            return revised_data

        except Exception as e:
            return cls._error_result(f"LLM错误修订执行异常: {type(e).__name__}: {str(e)[:200]}")

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        """构造错误结果

        Args:
            message: 错误信息

        Returns:
            dict: 错误结果
        """
        return {
            "type": "text",
            "content": f"[llm_error_revision] {message}",
        }
