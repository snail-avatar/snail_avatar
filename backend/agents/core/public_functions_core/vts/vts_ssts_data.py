# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vts_ssts_data.py
# @Desc    : VTS/SSTS 参数 - 数据访问层（已从 ui/component 迁至 core/public_functions_core/vts）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS/SSTS 参数 - 数据访问层

功能：
1. 从 memory_db 收集可用车型列表
2. 从 memorycore 提取指定车型+sheet 的原始数据
3. 将嵌套结构拍平为参数项列表

纯数据访问，不依赖任何 UI 控件，可在 agent 路径或 UI 路径中安全调用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ======================================================================
# 数据收集器
# ======================================================================


class VehicleDataCollector:
    """车型参数数据收集器 - 纯数据访问，不依赖任何 UI 控件
    """

    # ------------------------------------------------------------------
    # 车型收集
    # ------------------------------------------------------------------

    def collect_vehicles(self, db) -> Tuple[List[str], Dict[str, str]]:
        """从 memory_db 收集可用车型列表

        只从 vehsuffix 获取车型显示名，建立显示名 -> memorycore key 的映射。
        memorycore 的 key 格式为 "车型_车型后缀"，与 Excel 列名一致。

        Returns:
            (vehicle_names, vehicle_name_to_mc_key)
            - vehicle_names: 车型显示名列表
            - vehicle_name_to_mc_key: {显示名: memorycore_key} 映射
        """
        names: List[str] = []
        name_to_mc_key: Dict[str, str] = {}

        # 优先用 get_vehsuffix() 方法（同 eco_panel/power_panel）
        if hasattr(db, "get_vehsuffix"):
            suffix_list = db.get_vehsuffix()
        else:
            suffix_list = getattr(db, "vehsuffix", None) or []

        mc = getattr(db, "memorycore", None) or {}

        if suffix_list:
            for veh in suffix_list:
                name = veh.get("车型") or veh.get("车型名称") or None
                if not name:
                    continue

                suffix = veh.get("车型后缀", "") or ""

                # 构造 memorycore key = 车型_车型后缀（与 Excel 列名一致）
                if suffix:
                    mc_key_candidate = f"{name}_{suffix}"
                else:
                    mc_key_candidate = name

                # 确认该 key 在 memorycore 中实际存在
                actual_mc_key = None
                if mc_key_candidate in mc:
                    actual_mc_key = mc_key_candidate
                else:
                    # 退而求其次：在 memorycore.keys() 中匹配包含 name 和 suffix 的 key
                    for k in mc.keys():
                        if name in k and (not suffix or suffix in k):
                            actual_mc_key = k
                            break

                if actual_mc_key is None:
                    # 最后兜底：直接用 name 作为 key
                    actual_mc_key = name

                names.append(name)
                name_to_mc_key[name] = actual_mc_key
        else:
            # 退化方案：vehsuffix 为空时，直接用 memorycore.keys()
            for key in mc.keys():
                names.append(key)
                name_to_mc_key[key] = key

        return names, name_to_mc_key

    # ------------------------------------------------------------------
    # sheet 数据提取
    # ------------------------------------------------------------------

    def get_sheet_data(self, db, mc_key: str,
                        sheet_key: str) -> Dict[str, Dict[str, List[Dict]]]:
        """获取指定车型 + 指定 sheet 的原生数据

        Args:
            db: memory_db 实例
            mc_key: memorycore 中车型对应的 key（由 collect_vehicles 返回的映射值）
            sheet_key: SSTS_SHEET_KEY 或 VTS_SHEET_KEY
        """
        if db is None:
            return {}
        mc = getattr(db, "memorycore", None) or {}
        veh_data = mc.get(mc_key, {})

        for sheet_name, sheet_data in veh_data.items():
            if sheet_key in sheet_name:
                if isinstance(sheet_data, dict):
                    return sheet_data
                if isinstance(sheet_data, list):
                    return {"<未分类>": {"<未分类>": sheet_data}}
        return {}

    # ------------------------------------------------------------------
    # 嵌套结构拍平
    # ------------------------------------------------------------------

    def flatten_items(self, sheet_data: Dict[str, Dict[str, List[Dict]]]) -> List[Dict[str, Any]]:
        """将嵌套结构拍平为参数项列表，每个 item 附带 cat1/cat2

        特殊处理：如果 item 有 "参数值" 列表（通常包含 当前值/目标值/达标标识 三个子项），
        不拆成多行，而是把子项中的值合并到 item 顶层，作为一行输出。
        """
        if not sheet_data:
            return []
        flat: List[Dict[str, Any]] = []
        for cat1, cat1_data in sheet_data.items():
            if isinstance(cat1_data, list):
                for item in cat1_data:
                    self._append_item(flat, item, cat1, "<未分类>")
                continue
            if not isinstance(cat1_data, dict):
                continue
            for cat2, items in cat1_data.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            param_values = item.get("参数值")
                            if isinstance(param_values, list) and param_values:
                                # 多值参数：合并到 item，作为一行
                                self._append_multi_value_item(flat, item, param_values, cat1, cat2)
                            else:
                                # 简单参数：原样输出
                                self._append_item(flat, item, cat1, cat2)
                elif isinstance(items, dict):
                    for sub_cat, sub_items in items.items():
                        if isinstance(sub_items, list):
                            for si in sub_items:
                                self._append_item(flat, si, cat1, f"{cat2}/{sub_cat}")
        return flat

    def _append_multi_value_item(self, flat: List[Dict[str, Any]], item: Dict[str, Any],
                                 param_values: List[Dict[str, Any]], cat1: str, cat2: str) -> None:
        """处理多值参数：将 参数值 列表中的 当前值/目标值/达标标识 合并到 item 顶层

        参数值列表格式示例：
        [
          {"名称": "当前值", "db_key": "xxx_result_reevlto", "值": 2346},
          {"名称": "目标值", "db_key": "xxx_target_reevlto", "值": 2346},
          {"名称": "达标标识", "db_key": "xxx_pass_reevlto", "值": 1}
        ]

        合并后 item 新增字段：
          当前值, 当前值_db_key
          目标值, 目标值_db_key
          达标标识, 达标标识_db_key
        """
        entry = dict(item)
        entry["cat1"] = cat1
        entry["cat2"] = cat2

        # 从 param_values 中提取三个子项的 值 和 db_key
        # 子项的"名称"字段用来识别类型
        name_to_field_prefix = {
            "当前值": "当前值",
            "实际值": "当前值",       # 兼容命名
            "现在值": "当前值",        # 兼容命名
            "目标值": "目标值",
            "标准值": "目标值",       # 兼容命名
            "基准值": "目标值",       # 兼容命名
            "达标标识": "达标标识",
            "是否达标": "达标标识",     # 兼容命名
            "状态": "达标标识",         # 兼容命名
        }

        has_multi = False
        for p_item in param_values:
            if not isinstance(p_item, dict):
                continue
            sub_name = str(p_item.get("名称") or "").strip()
            field_prefix = name_to_field_prefix.get(sub_name)
            if not field_prefix:
                continue
            value_field = field_prefix
            db_key_field = f"{field_prefix}_db_key"
            entry[value_field] = p_item.get("值")
            entry[db_key_field] = p_item.get("db_key")
            has_multi = True

        if has_multi:
            entry["_has_multi_values"] = True

        flat.append(entry)

    def _append_item(self, flat: List[Dict[str, Any]], item: Any,
                    cat1: str, cat2: str) -> None:
        """将单个参数项追加到扁平列表"""
        if not isinstance(item, dict):
            return
        entry = dict(item)
        entry["cat1"] = cat1
        entry["cat2"] = cat2
        flat.append(entry)


__all__ = ["VehicleDataCollector"]
