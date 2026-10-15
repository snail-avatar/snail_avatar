# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_list_vts_parameters.py
# @Desc    : Function 3：列出指定车型的 VTS 参数（含当前值/目标值/达标状态）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function 3：列出指定车型的 VTS 参数（含当前值/目标值/达标状态）
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import (
    collect_vehicles,
    get_sheet_data,
)
from snail_avatar.backend.agents.core.public_functions_core.common.pass_flag_utils import (
    is_pass_value,
)
from snail_avatar.backend.agents.core.public_functions_core.vts.pass_flag_calculator import (
    ensure_pass_flags_calculated,
)
from snail_avatar.backend.agents.core.public_functions_core.vts.vts_calc_helper import (
    run_vts_calculation,
)
from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import (
    VTS_SHEET_KEY,
    iter_flat_items,
)


class ListVtsParametersFunction(FunctionBase):
    """列出指定车型的 VTS 参数（含当前值/目标值/达标状态）"""

    name = "list_vts_parameters"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "列出指定车型的所有 VTS（整车目标值）参数，包括参数名称、当前值、目标值、达标标识。"
                               "当用户询问某车型的 VTS 参数、或需要了解整车性能目标与实际情况对比时，使用此工具。"
                               "工具会自动检测 NaN 并在首次调用时触发计算（计算完成后不再检测）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vehicle_name": {
                            "type": "string",
                            "description": "车型名称（可选，留空时默认使用第一个可用车型），如 '增程车型'、'纯电车型'。"
                                           "可先用 list_all_vehicles 工具查询可用车型。"
                        }
                    },
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

        calc_msg_lines: List[str] = []
        calc_msg_lines.append("[提示] 正在执行 VTS 重新计算...")
        ok, msg, _report = run_vts_calculation(db)
        if ok:
            calc_msg_lines.append(f"[完成] {msg}。")
        else:
            calc_msg_lines.append(f"[失败] {msg}（将基于现有数据生成列表）。")

        ensure_pass_flags_calculated(db)

        vehicle_name = args.get("vehicle_name", "").strip()
        if vehicle_name:
            if vehicle_name not in name_to_mc_key:
                pre_msg = "\n".join(calc_msg_lines) + "\n" if calc_msg_lines else ""
                return {"type": "text", "content": pre_msg + f"未找到车型: {vehicle_name}。可用车型: {', '.join(names)}"}
            target_name = vehicle_name
        else:
            target_name = names[0]

        mc_key = name_to_mc_key[target_name]
        sheet_data = get_sheet_data(db, mc_key, VTS_SHEET_KEY)
        flat_items = iter_flat_items(sheet_data)

        if not flat_items:
            return {"type": "text", "content": f"车型 {target_name} 暂无 VTS 参数数据。"}

        columns = ["参数名称", "当前值", "目标值", "达标"]
        column_labels = {
            "参数名称": "参数名称",
            "当前值": "当前值",
            "目标值": "目标值",
            "达标": "达标",
        }
        column_formats = {
            "当前值": ".2f",
            "目标值": ".2f",
        }
        rows = []
        for item in flat_items:
            name = item.get("name", "")
            cur = item.get("当前值")
            target = item.get("目标值")
            pass_flag = item.get("达标标识")
            rows.append({
                "参数名称": name,
                "当前值": cur,
                "目标值": target,
                "达标": "是" if is_pass_value(pass_flag) else "否",
            })

        calc_status = "\n".join(calc_msg_lines)

        return {
            "type": "table",
            "title": f"车型 {target_name} 的 VTS 参数",
            "columns": columns,
            "column_labels": column_labels,
            "column_formats": column_formats,
            "rows": rows,
            "summary": {"count": len(flat_items)},
            # 把计算状态带给 LLM，让它知道计算真实执行情况
            "calc_status": calc_status,
        }


ALL_FUNCTIONS = [
    ListVtsParametersFunction,
]
