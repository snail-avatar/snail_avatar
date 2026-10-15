# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_get_param_by_db_key.py
# @Desc    : Function 2：按 db_key 读取单个参数值
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function 2：按 db_key 读取单个参数值
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db


class GetParamByDbKeyFunction(FunctionBase):
    """按 db_key 读取单个参数值"""

    name = "get_parameter_value"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "从 memorycore 中按 db_key 读取单个参数的当前值。db_key 是参数的唯一标识，如"
                               "mass_curb_result_reevlto 表示整备质量（增程车型的当前值）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "db_key": {
                            "type": "string",
                            "description": "参数的 db_key，如 mass_curb_result_reevlto、e_dc_result_reevlto 等。"
                        }
                    },
                    "required": ["db_key"],
                },
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        db_key = args.get("db_key", "")
        if not db_key:
            return {"type": "text", "content": "参数错误: 缺少必填字段 db_key"}

        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": "当前未加载数据（memory_db 为空），请先导入 Excel 数据文件。"}

        # 优先使用 memory_db 已提供的 get_ssts_vts_param 方法
        if hasattr(db, "get_ssts_vts_param"):
            value = db.get_ssts_vts_param(db_key)
        else:
            value = None

        if value is None:
            # 兜底：自行遍历 memorycore
            mc = getattr(db, "memorycore", None) or {}
            found = None
            param_name = ""
            for veh_data in mc.values():
                if not isinstance(veh_data, dict):
                    continue
                for sheet_data in veh_data.values():
                    if isinstance(sheet_data, dict):
                        for cat1_data in sheet_data.values():
                            if isinstance(cat1_data, dict):
                                for cat2_data in cat1_data.values():
                                    if isinstance(cat2_data, list):
                                        for item in cat2_data:
                                            if isinstance(item, dict):
                                                if item.get("db_key") == db_key:
                                                    found = item.get("值")
                                                    param_name = item.get("name", "")
                                                    break
            value = found

        if value is None:
            return {"type": "text", "content": f"未找到参数: db_key={db_key}"}
        
        name = param_name if param_name else db_key
        return {
            "type": "single_value",
            "name": name,
            "content": value,
        }


ALL_FUNCTIONS = [
    GetParamByDbKeyFunction,
]
