# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step1_build_vts_structure.py
# @Desc    : Public Function (a101 step1): 按专业顺序构建 VTS 数据结构
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step1): 按专业顺序构建 VTS 数据结构

读取 VTS 原始数据，按 LLM 确定的专业执行顺序构建结构化字典。
用于 a101 目标定义流程 step1 的 post_process：LLM 确定专业顺序后，
读取 VTS 数据并按该顺序组织，供后续循环步骤使用。

输出结构：{专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: ""}}, ...}

约定默认（YAML 无需显式声明）：
- memory_db/instance_key：由框架自动注入
- categories：缺省时从步骤结果 _step_result.structured_data.categories 读取
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step1BuildVtsStructure(AtomicFunction):
    """按专业顺序构建 VTS 数据结构 Public Function"""

    name: str = "build_vts_structure"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "读取 VTS 数据并按专业顺序构建数据结构。\n"
                    "memory_db/instance_key 自动注入；categories 缺省时从步骤结果 structured_data.categories 读取。\n"
                    "返回 {专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: ""}}, ...}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "专业顺序列表（缺省时自动从步骤结果读取）",
                        },
                    },
                    "required": [],
                },
            },
            "metadata": {
                "type": "data_read",
                "pubfn_index": "a101_step1",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 VTS 数据结构构建

        Args:
            args: 参数字典，memory_db/instance_key 由框架自动注入；
                  categories 可选，缺省时从 _step_result.structured_data.categories 读取
            context: Agent 实例（由 execute() 第 2 参数传入）

        Returns:
            dict: {专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: ""}}, ...}
        """
        # 1. 读取 VTS 原始数据
        vts_raw_data = cls._read_vts_data(args)

        # 2. 获取专业顺序（缺省时按约定从步骤结果 structured_data.categories 读取）
        categories = args.get("categories")
        if categories is None:
            # 按约定路径 result.structured_data.categories 解析
            categories = []
            result = args.get("_step_result")
            if result:
                try:
                    result_dict = json.loads(result) if isinstance(result, str) else result
                    if isinstance(result_dict, dict):
                        structured_data = result_dict.get("structured_data", {})
                        if isinstance(structured_data, dict):
                            cats = structured_data.get("categories", [])
                            if isinstance(cats, list):
                                categories = cats
                except Exception:
                    pass

        # 3. 按专业顺序构建结构
        structured = {}
        for category in categories:
            if category in vts_raw_data:
                structured[category] = vts_raw_data[category]

        return structured

    # ==================================================================
    # 内部方法：从 memorycore 读取 VTS 原始数据
    # ==================================================================

    @classmethod
    def _read_vts_data(cls, args: Dict[str, Any]) -> Dict[str, Any]:
        """从 memorycore 读取 VTS 数据并按专业、二级专业嵌套组织

        Args:
            args: 参数字典，需包含 memory_db, instance_key

        Returns:
            dict: {专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: ""}}, ...}
        """
        db = args.get("memory_db")
        vkey = args.get("instance_key", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import VTS_SHEET_KEY

        sheet_data = get_sheet_data(db, vkey, VTS_SHEET_KEY)
        if not sheet_data or not isinstance(sheet_data, dict):
            return {}

        vts_data = {}
        for category, sub_categories in sheet_data.items():
            if not isinstance(sub_categories, dict):
                continue

            category_data = {}
            for sub_cat, params in sub_categories.items():
                if not isinstance(params, list):
                    continue

                vts_items = []
                for param in params:
                    vts_item = {
                        "name": param.get("名称", ""),
                        "unit": param.get("单位", ""),
                        "param_values": [],
                    }

                    if "参数值" in param and isinstance(param["参数值"], list):
                        for pv in param["参数值"]:
                            if "目标值" in pv.get("名称", ""):
                                vts_item["param_values"].append({
                                    "db_key": pv.get("db_key", ""),
                                    "value": pv.get("值"),
                                })
                    elif "db_key" in param and "值" in param:
                        name = param.get("名称", "")
                        if "目标值" in name:
                            vts_item["param_values"].append({
                                "db_key": param.get("db_key", ""),
                                "value": param.get("值"),
                            })

                    vts_items.append(vts_item)

                if vts_items:
                    category_data[sub_cat] = {
                        "VTS_items": vts_items,
                        "SSTS_parameter": [],
                        "计算公式": "",
                    }

            if category_data:
                vts_data[category] = category_data

        return vts_data
