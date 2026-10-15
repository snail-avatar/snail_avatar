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
            entry[field_prefix] = p_item.get("值")
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
                    entry["当前值"] = item.get("值")
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
