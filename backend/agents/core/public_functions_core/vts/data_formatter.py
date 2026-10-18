# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : data_formatter.py
# @Desc    : VTS/SSTS 数据格式化辅助
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS/SSTS 数据格式化辅助

保留 VTS/SSTS 数据结构特有的拍平与字段映射逻辑。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


SSTS_SHEET_KEY = "target_ssts"
VTS_SHEET_KEY = "target_vts"
PRODUCT_DEF_SHEET_KEY = "base_产品定义"

_NAME_TO_FIELD_PREFIX = {
    "当前值": "当前值",
    "实际值": "当前值",
    "现在值": "当前值",
    "目标值": "目标值",
    "标准值": "目标值",
    "基准值": "目标值",
    "达标标识": "达标标识",
    "是否达标": "达标标识",
    "状态": "达标标识",
}

# 需要 clean 浮点尾巴的字段（达标标识是 0/1，不需要）
_CLEAN_FLOAT_FIELDS = {"当前值", "目标值"}


def _clean_float(value: Any) -> Any:
    """clean float 值：先消 IEEE754 精度尾巴，再 round 到 3 位小数

    两步处理：
      1. round(10)  —— 消除 0.35000000000000003 这类 IEEE754 表示噪声
      2. round(3)   —— 统一到 3 位小数，前端 formatDisplayValue 会去末尾 0
                       （如 1096.6669 → 1096.667，0.32 → 0.32，7.5 → 7.5）

    对非 float 值原样返回；对 NaN/Inf 也原样保留（由下游处理）。
    """
    if isinstance(value, float) and not math.isnan(value) and not math.isinf(value):
        return round(round(value, 10), 3)
    return value


def iter_flat_items(sheet_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将 VTS/SSTS 嵌套的 sheet 数据拍平为简单参数列表

    返回列表每项字段:
        name, cat1, cat2,
        当前值, 当前值_db_key,
        目标值, 目标值_db_key,
        达标标识, 达标标识_db_key
    """
    flat: List[Dict[str, Any]] = []
    if not sheet_data:
        return flat

    def _extract_multi_values(entry: Dict[str, Any], param_values: List[Dict[str, Any]]) -> None:
        """处理多值参数"""
        if not param_values:
            return
        for p_item in param_values:
            if not isinstance(p_item, dict):
                continue
            sub_name = str(p_item.get("名称") or "").strip()
            field_prefix = _NAME_TO_FIELD_PREFIX.get(sub_name)
            if not field_prefix:
                continue
            raw_val = p_item.get("值")
            # 对"当前值"和"目标值" clean 浮点尾巴（达标标识是 0/1，不需要）
            entry[field_prefix] = _clean_float(raw_val) if field_prefix in _CLEAN_FLOAT_FIELDS else raw_val
            entry[f"{field_prefix}_db_key"] = p_item.get("db_key")

    def _walk(data: Any, cat1: str, cat2: str) -> None:
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                entry: Dict[str, Any] = {
                    "name": item.get("名称", ""),
                    "单位": item.get("单位", ""),
                    "cat1": cat1,
                    "cat2": cat2,
                }
                param_values = item.get("参数值")
                if isinstance(param_values, list) and param_values:
                    _extract_multi_values(entry, param_values)
                else:
                    entry["当前值"] = _clean_float(item.get("值"))
                    entry["当前值_db_key"] = item.get("db_key")
                flat.append(entry)
        elif isinstance(data, dict):
            for k, v in data.items():
                if cat1 is None or cat1 == "":
                    _walk(v, k, cat2)
                else:
                    _walk(v, cat1, k)

    _walk(sheet_data, "", "")
    return flat
