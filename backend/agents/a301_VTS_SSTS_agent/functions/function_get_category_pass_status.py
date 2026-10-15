# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_get_category_pass_status.py
# @Desc    : Function：按专业分类统计 VTS 达标情况
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function：按专业分类统计 VTS 达标情况

根据指定的专业分类（cat1），精确统计该专业下所有 VTS 参数的达标情况。
避免 LLM 靠猜测判断参数归属导致的分类错误。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import (
    collect_vehicles,
    get_sheet_data,
)
from snail_avatar.backend.agents.core.public_functions_core.common.pass_flag_utils import (
    count_pass_flags,
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


class GetCategoryPassStatusFunction(FunctionBase):
    """按专业分类统计 VTS 达标率"""

    name = "get_category_pass_status"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "按专业分类（如经济性、动力性、空气动力学）统计特定专业的 VTS 达标率。"
                               "适用于用户询问某专业的达标情况，如'经济性相关的VTS指标达标情况如何？'。"
                               "工具会自动检测计算状态并在需要时触发计算。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vehicle_name": {
                            "type": "string",
                            "description": "车型名称（可选，留空时默认使用第一个可用车型）。如果不确定精确名称，可以先调用 list_all_vehicles 获取可用车型列表。示例：'增程车型（WLTC）'、'纯电车型（WLTC）'。"
                        },
                        "category": {
                            "type": "string",
                            "description": "专业分类名称（必填）。如果不确定精确名称，可以先调用 list_vts_categories 获取可用专业分类列表。用户可能使用同义词，如'能耗'指'经济性'，'加速'指'动力性'，'风阻'指'空气动力学'。"
                        }
                    },
                    "required": ["category"],
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
            return {"type": "text", "content": "未找到任何车型数据。"}

        calc_msg_lines: List[str] = []
        calc_msg_lines.append("[提示] 正在执行 VTS 重新计算...")
        ok, msg, _report = run_vts_calculation(db)
        if ok:
            calc_msg_lines.append(f"[完成] {msg}。")
        else:
            calc_msg_lines.append(f"[失败] {msg}（将基于现有数据生成摘要）。")

        ensure_pass_flags_calculated(db)

        vehicle_name = args.get("vehicle_name", "").strip()
        category = args.get("category", "").strip()

        if not category:
            return {"type": "text", "content": "错误：必须提供专业分类参数 category。"}

        if vehicle_name:
            if vehicle_name not in name_to_mc_key:
                pre_msg = "\n".join(calc_msg_lines) + "\n" if calc_msg_lines else ""
                return {"type": "text", "content": pre_msg + f"未找到车型: {vehicle_name}。可用车型: {', '.join(names)}"}
            target_names: List[str] = [vehicle_name]
        else:
            target_names = list(names)

        columns = ["车型", "参数名称", "当前值", "目标值", "状态"]
        column_labels = {
            "车型": "车型",
            "参数名称": "参数名称",
            "当前值": "当前值",
            "目标值": "目标值",
            "状态": "状态",
        }
        column_formats = {
            "当前值": ".2f",
            "目标值": ".2f",
        }
        rows = []
        summary_rows = []

        for name in target_names:
            mc_key = name_to_mc_key[name]
            sheet_data = get_sheet_data(db, mc_key, VTS_SHEET_KEY)
            flat_items = iter_flat_items(sheet_data)

            category_items = [item for item in flat_items if item.get("cat1") == category]

            if not category_items:
                summary_rows.append({
                    "车型": name,
                    "专业分类": category,
                    "总参数": 0,
                    "达标": 0,
                    "不达标": 0,
                    "达标率": "0.0%",
                })
                continue

            total, pass_count, fail_count, fail_items = count_pass_flags(category_items)

            rate = pass_count / total * 100 if total > 0 else 0
            summary_rows.append({
                "车型": name,
                "专业分类": category,
                "总参数": total,
                "达标": pass_count,
                "不达标": fail_count,
                "达标率": f"{rate:.1f}%",
            })

            for item in fail_items:
                pname = item.get("name", "")
                cur = item.get("当前值")
                target = item.get("目标值")
                if isinstance(cur, float) and math.isnan(cur):
                    cur = None
                if isinstance(target, float) and math.isnan(target):
                    target = None
                rows.append({
                    "车型": name,
                    "参数名称": pname,
                    "当前值": cur,
                    "目标值": target,
                    "状态": "不达标",
                })

        calc_status = "\n".join(calc_msg_lines)

        if rows:
            return {
                "type": "table",
                "title": f"{category}专业 VTS 达标情况",
                "columns": columns,
                "column_labels": column_labels,
                "column_formats": column_formats,
                "rows": rows,
                "summary": {
                    "total_vehicles": len(target_names),
                    "total_fail_items": len(rows),
                    "vehicle_summary": summary_rows,
                },
                # 把计算状态带给 LLM，让它知道计算真实执行情况
                "calc_status": calc_status,
            }
        else:
            return {
                "type": "table",
                "title": f"{category}专业 VTS 达标情况",
                "columns": ["车型", "专业分类", "总参数", "达标", "不达标", "达标率"],
                "rows": summary_rows,
                "calc_status": calc_status,
            }


ALL_FUNCTIONS = [
    GetCategoryPassStatusFunction,
]