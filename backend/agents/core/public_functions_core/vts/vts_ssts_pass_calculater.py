# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vts_ssts_pass_calculater.py
# @Desc    : VTS/SSTS - 达标标识计算器（已从 ui/component 迁至 core/public_functions_core/vts）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS/SSTS - 达标标识计算器

功能：
1. 遍历 memorycore 中所有车型的 SSTS/VTS 参数
2. 对每个多值参数，根据"达标判据"对比"当前值"和"目标值"
3. 计算"达标标识"（达标=1，不达标=0），写回 memorycore

纯逻辑层，不依赖任何 UI 控件，可在 agent 路径或 UI 路径中安全调用。

数据结构参考：
    {
        "名称": "整备质量",
        "单位": "kg",
        "达标判据": "<=",
        "参数值": [
            {"名称": "当前值", "db_key": "mass_curb_result_reevlto", "值": 2346},
            {"名称": "目标值", "db_key": "mass_curb_target_reevlto", "值": 2346},
            {"名称": "达标标识", "db_key": "mass_curb_pass_reevlto", "值": 1}
        ]
    }

计算规则：
    运算符       当前值 vs 目标值   达标值
    <=          当前值 <= 目标值      1
    <           当前值 <  目标值      1
    >=          当前值 >= 目标值      1
    >           当前值 >  目标值      1
    ==          当前值 == 目标值      1
    !=          当前值 != 目标值      1
    无判据/值为空/NaN/Inf/未知运算符  0 （默认不达标）
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .vts_ssts_data import VehicleDataCollector  # 同目录，相对路径不变
from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import (
    SSTS_SHEET_KEY,
    VTS_SHEET_KEY,
)

EPSILON = 1e-9

def _close_enough(a: float, b: float) -> bool:
    """判断两个浮点数是否在容差范围内相等"""
    return abs(a - b) <= EPSILON

# 运算符名称到判定函数的映射
# 每个函数接收 (当前值, 目标值)，返回 True 表示达标
# 使用容差比较处理浮点精度问题
OPERATORS = {
    "<=": lambda cur, tgt: cur <= tgt or _close_enough(cur, tgt),
    "<":  lambda cur, tgt: cur < tgt and not _close_enough(cur, tgt),
    ">=": lambda cur, tgt: cur >= tgt or _close_enough(cur, tgt),
    ">":  lambda cur, tgt: cur > tgt and not _close_enough(cur, tgt),
    "==": lambda cur, tgt: _close_enough(cur, tgt),
    "!=": lambda cur, tgt: not _close_enough(cur, tgt),
    "=":  lambda cur, tgt: _close_enough(cur, tgt),
}

# "当前值"、"目标值"、"达标标识" 的名称（兼容多种命名）
CURRENT_VALUE_NAMES = {"当前值", "实际值", "现在值"}
TARGET_VALUE_NAMES = {"目标值", "标准值", "基准值"}
PASS_FLAG_NAMES = {"达标标识", "是否达标", "状态"}


# ======================================================================
# 计算器类
# ======================================================================


class PassFlagCalculator:
    """达标标识计算器 - 遍历参数，根据达标判据计算达标标识

    纯逻辑层，不依赖任何 UI 控件，可被面板或其他地方调用。
    """

    def __init__(self):
        self._data_collector = VehicleDataCollector()

    # ------------------------------------------------------------------
    # 核心计算入口
    # ------------------------------------------------------------------

    def calculate_all(self, db) -> Dict[str, Any]:
        """计算所有车型的所有 SSTS/VTS 参数的达标标识

        Args:
            db: memory_db 实例，需要包含 memorycore 属性

        Returns:
            dict: 汇总信息，包含
                - total: 处理的参数总数
                - updated: 实际更新（值有变化）的参数数
                - skipped: 跳过的参数数（缺少必要字段）
                - details: [{vehicle, sheet, name, criterion, current, target, before, after}, ...]
        """
        if db is None:
            return {"total": 0, "updated": 0, "skipped": 0, "details": []}

        summary = {
            "total": 0,
            "updated": 0,
            "skipped": 0,
            "details": [],
        }

        vehicle_names, name_to_mc_key = self._data_collector.collect_vehicles(db)

        for vehicle_name in vehicle_names:
            mc_key = name_to_mc_key.get(vehicle_name, vehicle_name)

            # 分别处理 SSTS 和 VTS 两个 sheet
            for sheet_key in [SSTS_SHEET_KEY, VTS_SHEET_KEY]:
                sheet_data = self._data_collector.get_sheet_data(db, mc_key, sheet_key)
                if not sheet_data:
                    continue

                # 遍历嵌套结构：cat1 -> cat2 -> items
                self._process_sheet_data(
                    db, vehicle_name, sheet_key, sheet_data, summary
                )

        return summary

    def calculate_for_vehicle_and_sheet(
        self, db, mc_key: str, vehicle_name: str, sheet_key: str
    ) -> Dict[str, Any]:
        """仅计算指定车型 + 指定 sheet 的达标标识

        Returns:
            同 calculate_all 的 summary 结构
        """
        summary = {
            "total": 0,
            "updated": 0,
            "skipped": 0,
            "details": [],
        }
        sheet_data = self._data_collector.get_sheet_data(db, mc_key, sheet_key)
        if sheet_data:
            self._process_sheet_data(db, vehicle_name, sheet_key, sheet_data, summary)
        return summary

    # ------------------------------------------------------------------
    # 数据遍历
    # ------------------------------------------------------------------

    def _process_sheet_data(
        self,
        db,
        vehicle_name: str,
        sheet_key: str,
        sheet_data: Dict[str, Dict[str, List[Dict]]],
        summary: Dict[str, Any],
    ) -> None:
        """遍历嵌套的 sheet 数据，对每个多值参数进行计算"""
        if not isinstance(sheet_data, dict):
            return

        for cat1, cat1_data in sheet_data.items():
            if isinstance(cat1_data, list):
                for item in cat1_data:
                    self._process_item(db, vehicle_name, sheet_key, item, summary)
                continue

            if not isinstance(cat1_data, dict):
                continue

            for cat2, items in cat1_data.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            self._process_item(db, vehicle_name, sheet_key, item, summary)
                elif isinstance(items, dict):
                    for sub_cat, sub_items in items.items():
                        if isinstance(sub_items, list):
                            for si in sub_items:
                                self._process_item(db, vehicle_name, sheet_key, si, summary)

    def _process_item(
        self,
        db,
        vehicle_name: str,
        sheet_key: str,
        item: Any,
        summary: Dict[str, Any],
    ) -> None:
        """处理单个参数项"""
        if not isinstance(item, dict):
            return

        param_values = item.get("参数值")
        if not isinstance(param_values, list) or not param_values:
            # 简单参数（没有"参数值"列表），跳过
            return

        # 提取"达标判据"
        criterion = item.get("达标判据")
        if criterion is None or (isinstance(criterion, float) and math.isnan(criterion)):
            criterion = ""

        # 从参数值列表中提取当前值、目标值、达标标识
        current_val, current_db_key = self._extract_param_value(param_values, CURRENT_VALUE_NAMES)
        target_val, target_db_key = self._extract_param_value(param_values, TARGET_VALUE_NAMES)
        pass_val, pass_db_key = self._extract_param_value(param_values, PASS_FLAG_NAMES)

        # 必要字段校验：必须有当前值、目标值、达标标识的 db_key
        if current_db_key is None or target_db_key is None or pass_db_key is None:
            summary["skipped"] += 1
            return

        summary["total"] += 1

        # 计算新的达标标识
        new_pass_flag = self._evaluate_criterion(criterion, current_val, target_val)

        # 记录旧值用于对比（从参数值列表中取，不从 db 读，避免 IO）
        old_pass_flag = pass_val

        # 如果值有变化，则写回数据库
        is_changed = (
            (old_pass_flag is None and new_pass_flag is not None)
            or (old_pass_flag is not None and not self._numbers_equal(old_pass_flag, new_pass_flag))
        )

        if is_changed:
            written = False
            if hasattr(db, "set_ssts_vts_param"):
                written = db.set_ssts_vts_param(pass_db_key, new_pass_flag)
            else:
                # 兜底：直接更新内存中的 item
                for p in param_values:
                    if isinstance(p, dict) and p.get("db_key") == pass_db_key:
                        p["值"] = new_pass_flag
                        written = True
                        break

            if written:
                # 同步更新内存中的 item（保证后续表格渲染使用最新值）
                for p in param_values:
                    if isinstance(p, dict) and p.get("db_key") == pass_db_key:
                        p["值"] = new_pass_flag
                        break
                summary["updated"] += 1

        # 记录详情（用于调试/显示）
        summary["details"].append({
            "vehicle": vehicle_name,
            "sheet": sheet_key,
            "name": item.get("名称", ""),
            "criterion": str(criterion) if criterion else "",
            "current": current_val,
            "target": target_val,
            "before": old_pass_flag,
            "after": new_pass_flag,
        })

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_param_value(
        param_values: List[Dict], name_set: set
    ) -> Tuple[Optional[Any], Optional[str]]:
        """从参数值列表中按名称提取 值 和 db_key

        Args:
            param_values: 参数值列表，每项格式如 {"名称": "当前值", "db_key": "...", "值": x}
            name_set: 可接受的名称集合（如 {"当前值", "实际值"}）

        Returns:
            (value, db_key) - 未找到时返回 (None, None)
        """
        for p in param_values:
            if not isinstance(p, dict):
                continue
            name = p.get("名称", "")
            if name in name_set:
                val = p.get("值")
                db_key = p.get("db_key")
                return val, db_key
        return None, None

    @staticmethod
    def _evaluate_criterion(
        criterion: Any, current_val: Any, target_val: Any
    ) -> int:
        """根据达标判据对比当前值与目标值

        Args:
            criterion: 运算符字符串，如 "<=", ">", "==" 等
            current_val: 当前值
            target_val: 目标值

        Returns:
            1 表示达标，0 表示不达标
        """
        # 规范化判据：去除空白，转字符串
        if criterion is None:
            op_str = ""
        else:
            op_str = str(criterion).strip()

        # 无判据时，默认不达标
        if not op_str or op_str.lower() in {"nan", "none", "null", "-"}:
            return 0

        # 当前值或目标值为空时，默认不达标
        if current_val is None or target_val is None:
            return 0

        # 尝试将当前值和目标值转换为浮点数进行比较
        try:
            cur_num = float(current_val)
        except (TypeError, ValueError):
            cur_num = None

        try:
            tgt_num = float(target_val)
        except (TypeError, ValueError):
            tgt_num = None

        # 当前值或目标值为 nan/inf 时，默认不达标
        if cur_num is not None and (math.isnan(cur_num) or math.isinf(cur_num)):
            return 0
        if tgt_num is not None and (math.isnan(tgt_num) or math.isinf(tgt_num)):
            return 0

        # 如果两侧都能转成数字，按数字比较
        if cur_num is not None and tgt_num is not None:
            func = OPERATORS.get(op_str)
            if func is not None:
                return 1 if func(cur_num, tgt_num) else 0

        # 无法按数字比较时，回退为字符串等值比较（仅对 == / != 有意义）
        if op_str in {"==", "="}:
            return 1 if str(current_val) == str(target_val) else 0
        if op_str == "!=":
            return 1 if str(current_val) != str(target_val) else 0

        # 未知运算符，默认不达标
        return 0

    @staticmethod
    def _numbers_equal(a: Any, b: Any) -> bool:
        """判断两个值是否相等（主要用于 int/float 比较）"""
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return str(a) == str(b)

    # ------------------------------------------------------------------
    # 单条记录计算（供数据拍平层实时调用）
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_flat_item(item: Dict[str, Any]) -> Optional[int]:
        """对单个拍平后的 item 计算达标标识

        item 结构（由 VehicleDataCollector.flatten_items 产生）：
            {
                "名称": "整备质量",
                "单位": "kg",
                "达标判据": "<=",
                "当前值": 2346,
                "当前值_db_key": "mass_curb_result_reevlto",
                "目标值": 2346,
                "目标值_db_key": "mass_curb_target_reevlto",
                "达标标识": 1,
                "达标标识_db_key": "mass_curb_pass_reevlto",
                ...
            }

        Returns:
            1=达标, 0=不达标；如果缺少必要字段（无当前值/目标值/判据）返回 None
        """
        if not isinstance(item, dict):
            return None

        # 只对多值参数（有当前值/目标值/达标标识）做计算
        current_val = item.get("当前值")
        target_val = item.get("目标值")
        criterion = item.get("达标判据")

        # 缺少必要字段时跳过
        if current_val is None and target_val is None:
            return None

        return PassFlagCalculator._evaluate_criterion(criterion, current_val, target_val)


__all__ = ["PassFlagCalculator", "OPERATORS"]
