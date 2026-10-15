# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_list_vts_categories.py
# @Desc    : Function：列出所有可用的 VTS 一级分类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function：列出所有可用的 VTS 一级分类

返回 VTS 数据中所有可用的一级分类（cat1）精准名称，用于 LLM 辅助匹配用户输入的模糊术语。
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import (
    collect_vehicles,
    get_sheet_data,
)
from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import (
    VTS_SHEET_KEY,
    iter_flat_items,
)


class ListVtsCategoriesFunction(FunctionBase):
    """列出所有可用的 VTS 一级分类"""

    name = "list_vts_categories"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "列出当前系统中所有可用的 VTS 一级分类（cat1）精准名称。当用户询问某专业的达标情况但使用模糊术语时（如'能耗'、'加速'、'风阻'），应先调用此工具获取精准分类名称，再进行推理匹配。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": "当前未加载数据（memory_db 为空），请先导入 Excel 数据文件。"}

        names, name_to_mc_key = collect_vehicles(db)
        if not names:
            return {"type": "text", "content": "未找到任何车型数据。请确认 memory_db 中已加载 vehsuffix 和 memorycore。"}

        mc_key = name_to_mc_key[names[0]]
        sheet_data = get_sheet_data(db, mc_key, VTS_SHEET_KEY)
        flat_items = iter_flat_items(sheet_data)

        categories = sorted(set(item.get("cat1", "") for item in flat_items if item.get("cat1")))

        if not categories:
            return {"type": "text", "content": "未找到任何 VTS 一级分类数据。"}

        items = [f"{cat}" for cat in categories]

        return {
            "type": "list",
            "title": "当前可用的 VTS 一级分类",
            "content": items,
            "summary": {"count": len(categories)},
        }


ALL_FUNCTIONS = [
    ListVtsCategoriesFunction,
]