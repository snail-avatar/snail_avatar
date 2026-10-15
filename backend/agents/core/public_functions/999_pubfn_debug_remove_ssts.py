# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 999_pubfn_debug_remove_ssts.py
# @Desc    : 临时调试函数 - 删除指定 db_key 的 SSTS 参数，用于验证后续修订逻辑
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
临时调试函数：删除指定 db_key 的 SSTS 参数

用于模拟 LLM 输出缺失参数的场景，验证 step2_4_validate_targets 和
step2_4_revise_if_needed 两个后处理步骤能否正常执行。

调试完成后请删除此文件及 YAML 中对应的配置。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.core.work_log import WorkLogger


class DebugRemoveSsts(AtomicFunction):
    """临时调试：删除指定 db_key 的 SSTS 参数"""

    name: str = "debug_remove_ssts"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "临时调试工具：删除指定 db_key 的 SSTS 参数\n"
                    "用于模拟 LLM 输出缺失参数的场景"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": "待处理的数据（含 vts_targets）",
                        },
                        "target_db_key": {
                            "type": "string",
                            "description": "要删除的 SSTS 参数 db_key",
                        },
                    },
                    "required": ["data", "target_db_key"],
                },
            },
            "metadata": {
                "type": "debug",
                "pubfn_index": "999",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行删除操作"""
        data = args.get("data", {})
        target_db_key = args.get("target_db_key", "")

        if not data or not target_db_key:
            return data

        vts_targets = data.get("vts_targets", [])

        removed_count = 0

        for vts in vts_targets:
            ssts_list = vts.get("SSTS_parameter", [])
            original_len = len(ssts_list)

            # 过滤掉匹配的条目
            ssts_list[:] = [
                s for s in ssts_list
                if s.get("db_key") != target_db_key
            ]

            removed_count += original_len - len(ssts_list)

            # 如果 SSTS_parameter 已清空，删除空列表以触发后续修订逻辑
            if not ssts_list and "SSTS_parameter" in vts:
                del vts["SSTS_parameter"]

        if removed_count > 0:
            WorkLogger.info(
                f"debug_remove_ssts: 删除了 {removed_count} 个 "
                f"db_key={target_db_key} 的 SSTS 参数"
            )
        else:
            WorkLogger.info(
                f"debug_remove_ssts: 未找到 db_key={target_db_key} 的 SSTS 参数"
            )

        return data