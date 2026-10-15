# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step3_save_final.py
# @Desc    : 私有函数：保存最终总结为 process 输出
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
私有函数 a101_step3_save_final

功能：将 step3 的最终总结保存为 process 的最终输出。

输入：
  - sandbox: 沙箱实例
  - result: 步骤执行结果（由框架自动注入 $result）

输出：
  - 保存状态信息
"""

from __future__ import annotations

import json
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class SaveFinalSummaryFunction(AtomicFunction):
    """保存最终总结的函数"""

    name: str = "save_final_summary"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "将最终总结保存为 process 输出",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "result": {
                            "type": ["object", "string"],
                            "description": "步骤执行结果",
                        },
                    },
                    "required": ["sandbox"],
                },
            },
            "metadata": {
                "type": "data_storage",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行保存最终总结

        Args:
            args: 参数字典
            context: 上下文对象

        Returns:
            str: 保存状态信息
        """
        sandbox = args.get("sandbox")
        result = args.get("result", "")

        if not sandbox:
            return "保存失败：沙箱实例为空"

        try:
            # 处理结果内容
            final_content = ""
            if isinstance(result, dict):
                content = result.get("content", "")
                if isinstance(content, str):
                    final_content = content
                else:
                    final_content = json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, str):
                final_content = result
            else:
                final_content = str(result)

            # 保存到 process_data
            sandbox.set_process_data("final_summary", final_content)

            # 同时保存一份带时间戳的版本
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            sandbox.set_process_data(f"final_summary_{timestamp}", final_content)

            return f"最终总结保存成功（长度: {len(final_content)} 字符）"

        except Exception as e:
            return f"保存失败：{str(e)}"
