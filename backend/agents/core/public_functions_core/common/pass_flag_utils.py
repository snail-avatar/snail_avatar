# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : pass_flag_utils.py
# @Desc    : 跨 Agent 共享模块：达标标识通用工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：达标标识通用工具

提供参数达标状态判断和统计的通用能力。
任何需要判断参数是否达标的 agent 都可以使用。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


def is_pass_value(flag_value: Any) -> bool:
    """判断达标标识是否代表"达标"

    Args:
        flag_value: 达标标识值（可能是 1/0、"是"/"否"、True/False 等）

    Returns:
        bool: True 表示达标，False 表示不达标或无法判断
    """
    return flag_value in (1, "1", True, "true", "True", "是")


def value_is_empty_or_nan(value: Any) -> bool:
    """判断一个"当前值"是否为 NaN 或空/缺失

    典型场景：
      - None → True
      - float('nan') / numpy.nan → True
      - "" / "nan" / "NaN" / "none" → True

    Args:
        value: 任意类型的值

    Returns:
        bool: True 表示值为空或 NaN
    """
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, int):
        return False
    if isinstance(value, str):
        v = value.strip().lower()
        if not v or v in {"nan", "none", "null", "-"}:
            return True
        return False
    return False


def count_pass_flags(items: List[Dict[str, Any]]) -> Tuple[int, int, int, List[Dict[str, Any]]]:
    """统计达标情况

    Args:
        items: 参数列表，每个元素应包含 "达标标识" 字段

    Returns:
        Tuple[int, int, int, List[Dict]]:
            - total: 参数总数
            - pass_count: 达标数量
            - fail_count: 不达标数量
            - fail_items: 不达标参数的完整列表（便于进一步分析）
    """
    total = 0
    pass_count = 0
    fail_count = 0
    fail_items: List[Dict[str, Any]] = []

    for item in items:
        flag = item.get("达标标识")
        if flag is None:
            total += 1
            continue
        total += 1
        if is_pass_value(flag):
            pass_count += 1
        else:
            fail_count += 1
            fail_items.append(item)

    return total, pass_count, fail_count, fail_items