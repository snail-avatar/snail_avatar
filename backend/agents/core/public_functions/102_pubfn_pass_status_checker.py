# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 102_pubfn_pass_status_checker.py
# @Desc    : Public Function: VTS 达标情况检查
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 102: VTS 达标情况检查

检查指定专业的 VTS 达标情况，返回总数/达标数/不达标数及不达标项明细。
memory_db/instance_key/professional_category 由框架自动注入，无需 YAML 显式声明。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnPassStatusChecker(AtomicFunction):
    """VTS 达标情况检查 Public Function"""

    name: str = "get_pass_status"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "检查 VTS 达标情况，返回总数/达标数/不达标数及不达标项明细。\n"
                    "memory_db/instance_key/professional_category 自动注入。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类（可选，为空时检查所有专业）",
                        },
                    },
                    "required": [],
                },
            },
            "metadata": {
                "type": "data_read",
                "pubfn_index": "102",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 VTS 达标情况检查

        Args:
            args: 参数字典，memory_db/instance_key/professional_category 由框架自动注入
            context: 上下文对象（未使用）

        Returns:
            Dict: {total, passed, failed, failed_items}
        """
        return cls.get_pass_status(args)

    # ==================================================================
    # 检查方法
    # ==================================================================

    @classmethod
    def get_pass_status(cls, args: Dict[str, Any]) -> Dict[str, Any]:
        """检查 VTS 达标情况

        Args:
            args: 参数字典，需包含 memory_db, instance_key，可选包含 professional_category

        Returns:
            Dict: {total, passed, failed, failed_items}
        """
        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        category = args.get("professional_category", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
        from snail_avatar.backend.agents.core.public_functions_core.common.pass_flag_utils import is_pass_value

        sheet_data = get_sheet_data(db, instance_key, "target_vts")

        total = 0
        passed = 0
        failed = 0
        failed_items = []

        if sheet_data and isinstance(sheet_data, dict):
            for cat1, cat2_dict in sheet_data.items():
                if category and cat1 != category:
                    continue

                if isinstance(cat2_dict, dict):
                    for cat2, param_list in cat2_dict.items():
                        if isinstance(param_list, list):
                            for param in param_list:
                                if isinstance(param, dict):
                                    total += 1
                                    param_values = param.get("参数值", [])
                                    current_value = None
                                    target_value = None
                                    pass_flag = None
                                    if isinstance(param_values, list):
                                        for pv in param_values:
                                            if isinstance(pv, dict):
                                                if pv.get("名称") == "当前值":
                                                    current_value = pv.get("值")
                                                elif pv.get("名称") == "目标值":
                                                    target_value = pv.get("值")
                                                elif pv.get("名称") == "达标标识":
                                                    pass_flag = pv.get("值")

                                    if pass_flag is not None:
                                        if is_pass_value(pass_flag):
                                            passed += 1
                                        else:
                                            failed += 1
                                            failed_items.append({
                                                "name": param.get("名称", ""),
                                                "current": current_value,
                                                "target": target_value,
                                            })

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "failed_items": failed_items,
        }
