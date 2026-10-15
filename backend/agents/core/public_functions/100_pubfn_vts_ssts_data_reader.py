# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 100_pubfn_vts_ssts_data_reader.py
# @Desc    : Public Function: VTS/SSTS 数据读取与结构化
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 100: VTS/SSTS 数据读取

提供 VTS/SSTS 数据的读取功能，包括：
- 获取 VTS 首层分类列表
- 获取指定专业的 VTS 参数列表（含当前值/目标值/达标标识）
- 获取指定专业的 SSTS 参数列表（含当前值/目标值）
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnVtsSstsDataReader(AtomicFunction):
    """VTS/SSTS 数据读取与结构化 Public Function"""

    name: str = "vts_ssts_data_reader"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "VTS/SSTS 数据读取工具。提供以下操作：\n"
                    "  - get_vts_categories: 获取 VTS 首层分类列表\n"
                    "  - get_vts_params: 获取 VTS 参数列表（含当前值/目标值/达标标识）\n"
                    "  - get_ssts_params: 获取 SSTS 参数列表（含当前值/目标值）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": (
                                "操作类型，可选值：\n"
                                "  get_vts_categories / get_vts_params / get_ssts_params"
                            ),
                        },
                        "category": {
                            "type": "string",
                            "description": "专业分类（用于 get_vts_params / get_ssts_params，可选，为空时返回所有专业）",
                        },
                    },
                    "required": ["operation"],
                },
            },
            "metadata": {
                "type": "data_read",
                "pubfn_index": "100",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 VTS/SSTS 数据读取原子操作"""
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        try:
            if operation == "get_vts_categories":
                return cls.get_vts_categories(args)

            elif operation == "get_vts_params":
                return cls.get_vts_params(args)

            elif operation == "get_ssts_params":
                return cls.get_ssts_params(args)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    # ==================================================================
    # VTS 数据读取方法（原 vts_data_reader）
    # ==================================================================

    @classmethod
    def get_vts_categories(cls, args: Dict[str, Any]) -> List[str]:
        """获取专业分类列表

        从 VTS 首层数据中提取所有专业分类名称。

        Args:
            args: 参数字典，需包含 memory_db, instance_key

        Returns:
            List[str]: 排序后的专业分类列表
        """
        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data

        sheet_data = get_sheet_data(db, instance_key, "target_vts")

        categories = []
        if sheet_data and isinstance(sheet_data, dict):
            for cat1 in sheet_data.keys():
                categories.append(cat1)

        categories.sort()
        return categories

    # ==================================================================
    # VTS/SSTS 参数列表读取方法（原 vts_ssts_params_reader）
    # ==================================================================

    @classmethod
    def get_vts_params(cls, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取 VTS 参数列表

        Args:
            args: 参数字典，需包含 memory_db, instance_key，可选包含 professional_category

        Returns:
            List[Dict]: VTS 参数列表，每项包含 name, unit, current, target, pass_flag
        """
        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        category = args.get("professional_category", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import VTS_SHEET_KEY

        params = []
        sheet_data = get_sheet_data(db, instance_key, VTS_SHEET_KEY)
        if sheet_data and isinstance(sheet_data, dict):
            for cat1, cat2_dict in sheet_data.items():
                if category and cat1 != category:
                    continue

                if isinstance(cat2_dict, dict):
                    for cat2, param_list in cat2_dict.items():
                        if isinstance(param_list, list):
                            for param in param_list:
                                if isinstance(param, dict):
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
                                    params.append({
                                        "name": param.get("名称", ""),
                                        "unit": param.get("单位", ""),
                                        "current": current_value,
                                        "target": target_value,
                                        "pass_flag": pass_flag,
                                    })
        return params

    @classmethod
    def get_ssts_params(cls, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取 SSTS 参数列表

        Args:
            args: 参数字典，需包含 memory_db, instance_key，可选包含 professional_category

        Returns:
            List[Dict]: SSTS 参数列表，每项包含 name, unit, current, target
        """
        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        category = args.get("professional_category", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import SSTS_SHEET_KEY

        params = []
        sheet_data = get_sheet_data(db, instance_key, SSTS_SHEET_KEY)
        if sheet_data and isinstance(sheet_data, dict):
            for cat1, cat2_dict in sheet_data.items():
                if category and cat1 != category:
                    continue

                if isinstance(cat2_dict, dict):
                    for cat2, param_list in cat2_dict.items():
                        if isinstance(param_list, list):
                            for param in param_list:
                                if isinstance(param, dict):
                                    param_values = param.get("参数值", [])
                                    current_value = None
                                    target_value = None
                                    if isinstance(param_values, list):
                                        for pv in param_values:
                                            if isinstance(pv, dict):
                                                if pv.get("名称") == "当前值":
                                                    current_value = pv.get("值")
                                                elif pv.get("名称") == "目标值":
                                                    target_value = pv.get("值")
                                    params.append({
                                        "name": param.get("名称", ""),
                                        "unit": param.get("单位", ""),
                                        "current": current_value,
                                        "target": target_value,
                                    })
        return params