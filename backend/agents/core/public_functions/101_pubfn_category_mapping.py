# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 101_pubfn_category_mapping.py
# @Desc    : Public Function: 构建专业分类映射表
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 101: 构建专业分类映射表

从 memory core 读取 VTS 数据，构建标准化的专业分类映射关系。
作为后续参数名、类别名、db_key 校验的基准。

输出结构：
{
    "category_mapping": {专业名: {二级专业: 标准名}},
    "sub_category_index": {二级专业名: 二级专业名}
}
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnCategoryMapping(AtomicFunction):
    """专业分类映射表构建 Public Function"""

    name: str = "build_category_mapping"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "构建专业分类映射表。\n"
                    "从 memory core 读取 VTS 数据，构建一级专业、二级专业、标准名的映射关系，\n"
                    "作为后续名称校验的基准。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            "metadata": {
                "type": "data_read",
                "pubfn_index": "101",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行映射表构建

        Args:
            args: 参数字典，memory_db/instance_key 由框架自动注入

        Returns:
            dict: {category_mapping, sub_category_index}
        """
        return cls.build_mapping(args)

    # ==================================================================
    # 核心方法：构建映射表
    # ==================================================================

    @classmethod
    def build_mapping(cls, args: Dict[str, Any]) -> Dict[str, Any]:
        """从 memory core 构建专业分类映射表

        从 target_vts 表读取 VTS 数据，提取所有一级专业和二级专业名称，
        构建标准化映射表和全局索引。

        Args:
            args: 需包含 memory_db, instance_key

        Returns:
            dict: {
                "category_mapping": {专业: {二级专业: 标准名}},
                "sub_category_index": {二级专业名: 二级专业名}
            }
        """
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import VTS_SHEET_KEY

        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")

        # 1. 读取 target_vts 数据
        sheet_data = get_sheet_data(db, instance_key, VTS_SHEET_KEY)
        if not sheet_data or not isinstance(sheet_data, dict):
            return {"category_mapping": {}, "sub_category_index": {}}

        # 2. 构建映射表
        category_mapping = {}
        sub_category_index = {}

        for cat1_name, cat1_data in sheet_data.items():
            if not isinstance(cat1_data, dict):
                continue

            category_mapping[cat1_name] = {}
            for cat2_name in cat1_data.keys():
                # 添加到专业映射
                category_mapping[cat1_name][cat2_name] = cat2_name

                # 添加到全局索引
                sub_category_index[cat2_name] = cat2_name

        return {
            "category_mapping": category_mapping,
            "sub_category_index": sub_category_index,
        }
