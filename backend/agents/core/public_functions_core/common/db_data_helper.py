# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : db_data_helper.py
# @Desc    : 跨 Agent 共享模块：从 memory_db 提取通用数据
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：从 memory_db 提取通用数据

提供以下通用能力：
1. collect_vehicles - 从 memory_db 提取车型列表
2. get_vehicle_name_by_key - 根据 instance_key 查找车型显示名称
3. get_sheet_data - 从 memory_db 读取指定 sheet 的原始数据
4. read_param_by_db_key - 按 db_key 读取单个参数值

这些函数与 VTS/SSTS/经济性等具体领域无关，任何需要访问 memory_db 的 agent 都可以使用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def collect_vehicles(db) -> Tuple[List[str], Dict[str, str]]:
    """从 memory_db 收集可用车型列表

    Args:
        db: MemoryDatabase 实例（应包含 vehsuffix 和 memorycore 属性）

    Returns:
        Tuple[List[str], Dict[str, str]]:
            - 第一个元素：车型显示名称列表（排序后）
            - 第二个元素：显示名称 -> memorycore 键名 的映射
    """
    if db is None:
        return [], {}

    names: List[str] = []
    name_to_mc_key: Dict[str, str] = {}

    suffix_list = getattr(db, "vehsuffix", None) or []
    mc = getattr(db, "memorycore", None) or {}

    if not suffix_list:
        return [], {}

    for veh in suffix_list:
        name = veh.get("车型") or veh.get("车型名称") or None
        if not name:
            continue
        suffix = str(veh.get("车型后缀", "") or "")
        if suffix:
            mc_key_candidate = f"{name}_{suffix}"
        else:
            mc_key_candidate = name

        actual_mc_key = None
        if mc_key_candidate in mc:
            actual_mc_key = mc_key_candidate
        else:
            for k in mc.keys():
                if name in k and (not suffix or suffix in k):
                    actual_mc_key = k
                    break
        if actual_mc_key is None:
            actual_mc_key = name

        names.append(name)
        name_to_mc_key[name] = actual_mc_key

    return names, name_to_mc_key


def get_vehicle_name_by_key(db, instance_key: str) -> str:
    """根据 instance_key 查找车型显示名称

    从 memory_db.vehsuffix 中查找匹配的车型条目，返回其显示名称。
    匹配方式：后缀精确匹配优先，其次是车型名包含在 instance_key 中。

    Args:
        db: MemoryDatabase 实例（应包含 vehsuffix 属性）
        instance_key: 车型键名（如 "增程车型（WLTC）_reevlto"）

    Returns:
        str: 车型显示名称（如 "增程车型（WLTC）"），找不到时返回 instance_key
    """
    if not instance_key:
        return ""

    if db is None:
        return instance_key

    vehsuffix_list = getattr(db, "vehsuffix", None) or []
    if not isinstance(vehsuffix_list, list):
        return instance_key

    # 从 instance_key 中提取后缀部分用于匹配
    # "增程车型（WLTC）_reevlto" → suffix = "reevlto"
    # 使用 rsplit 从后往前分割，避免车型名含下划线时解析错误
    suffix = instance_key.rsplit("_", 1)[-1] if "_" in instance_key else instance_key

    for veh in vehsuffix_list:
        if not isinstance(veh, dict):
            continue
        veh_suffix = str(veh.get("车型后缀", "") or "")
        veh_name = str(veh.get("车型", "") or "")
        # 匹配方式1：后缀精确匹配
        if veh_suffix and veh_suffix == suffix and veh_name:
            return veh_name
        # 匹配方式2：车型名包含在 instance_key 中
        if veh_name and veh_name in instance_key:
            return veh_name

    # 找不到匹配时返回 instance_key 本身作为兜底
    return instance_key


def get_sheet_data(db, mc_key: str, sheet_key: str) -> Dict[str, Any]:
    """从 memorycore 中获取指定车型 + 指定 sheet 的原始数据

    Args:
        db: MemoryDatabase 实例
        mc_key: memorycore 中的车型键（如 "车型A_evLTO"）
        sheet_key: sheet 关键字，如 "target_ssts"、"target_vts"

    Returns:
        Dict: 原始 sheet 数据。如果找不到则返回空字典。
    """
    if db is None:
        return {}
    mc = getattr(db, "memorycore", None) or {}
    veh_data = mc.get(mc_key, {})
    if not veh_data:
        print(f"[DEBUG][get_sheet_data] veh_data empty! mc_key={mc_key!r} available keys={list(mc.keys())}")
        return {}
    # sheet_key 模糊匹配（大小写不敏感）— 因为 Excel sheet 名大小写不规则
    sk_lower = sheet_key.lower()
    for sheet_name, sheet_data in veh_data.items():
        if sk_lower in str(sheet_name).lower():
            if isinstance(sheet_data, dict):
                print(f"[DEBUG][get_sheet_data] matched: sheet_key={sheet_key!r} -> sheet_name={sheet_name!r} dict_keys={list(sheet_data.keys())[:3]}")
                return sheet_data
            if isinstance(sheet_data, list):
                print(f"[DEBUG][get_sheet_data] matched: sheet_key={sheet_key!r} -> sheet_name={sheet_name!r} (list len={len(sheet_data)})")
                return {"<未分类>": {"<未分类>": sheet_data}}
    print(f"[DEBUG][get_sheet_data] NO MATCH: sheet_key={sheet_key!r}, veh_data keys={list(veh_data.keys())}")
    return {}


def read_param_by_db_key(db, db_key: str) -> Any:
    """按 db_key 读取单个参数值

    Args:
        db: MemoryDatabase 实例（应实现 get_ssts_vts_param 方法）
        db_key: 参数的 db_key 标识

    Returns:
        Any: 参数值，未找到时返回 None
    """
    if db is None:
        return None

    if hasattr(db, "get_ssts_vts_param"):
        return db.get_ssts_vts_param(db_key)

    return None