# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_5_extract_data.py
# @Desc    : Public Function (a101 step2_5): SSTS数值合理性校核 - 数据提取
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_5): SSTS数值合理性校核 - 数据提取

为 step2_5 (VALIDATE_TARGETS) 提供数据提取能力：

1. extract_vts_params: 从 process_data.vts_category_data 提取当前专业的 VTS 参数列表
   用于构建 Agent 查询，告知 Agent 需要校核哪些 VTS 参数

数据来源：
- process_data: vts_category_data 字段

必需参数（YAML 需显式声明）：
- sandbox: 沙箱实例
- operation: 操作类型
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_5ExtractData(AtomicFunction):
    """Step2_5 数据提取 Public Function"""

    name: str = "step2_5_extract_data"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_5 专属数据提取工具。提供以下操作：\n"
                    "  - extract_vts_params: 从 process_data 提取当前专业的 VTS 参数列表"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "操作类型：extract_vts_params",
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类（如空气动力学、底盘等）",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀（如 'reevlto'）",
                        },
                        "instance_key": {
                            "type": "string",
                            "description": "车型标识键（如 '增程车型（WLTC）_reevlto'）",
                        },
                    },
                    "required": ["operation", "sandbox"],
                },
            },
            "metadata": {
                "type": "data_extract",
                "pubfn_index": "a101_step2_5",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行数据提取

        Args:
            args: 参数字典，必须包含 operation 和 sandbox
            context: Agent 实例

        Returns:
            提取结果文本或结构化数据
        """
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        sandbox = args.get("sandbox") or (getattr(context, "sandbox", None) if context else None)

        try:
            if operation == "extract_vts_params":
                return cls.extract_vts_params(sandbox, args)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    @classmethod
    def extract_vts_params(cls, sandbox: Any, args: Dict[str, Any]) -> str:
        """从 process_data 提取当前专业的 VTS 参数列表（新嵌套结构）

        格式化为可读文本，供 Agent 查询使用。

        Args:
            sandbox: 沙箱实例
            args: 参数字典（含 professional_category, vehicle_suffix）

        Returns:
            str: 格式化的 VTS 参数列表文本
        """
        category = args.get("professional_category", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        if not sandbox:
            return "（暂无 VTS 参数数据）"

        try:
            vts_category_data = sandbox.get_process_data("vts_category_data")
        except Exception:
            vts_category_data = None

        if not vts_category_data or not isinstance(vts_category_data, dict):
            return "（暂无 VTS 参数数据）"

        category_data = vts_category_data.get(category, {})
        if not isinstance(category_data, dict) or len(category_data) == 0:
            return f"（专业「{category}」暂无 VTS 参数数据）"

        lines = [f"【专业「{category}」的 VTS 参数列表】", ""]

        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue

            vts_items = group_content.get("VTS_items", [])
            ssts_params = group_content.get("SSTS_parameter", [])
            formula = group_content.get("计算公式", "")

            lines.append(f"【{sub_cat_name}】")

            for vts_item in vts_items:
                if not isinstance(vts_item, dict):
                    continue

                vts_name = vts_item.get("name", "")
                unit = vts_item.get("unit", "")
                param_values = vts_item.get("param_values", [])

                # VTS 参数基本信息
                line = f"- {vts_name}"
                if unit and str(unit) != "Null":
                    line += f"（单位: {unit}）"
                lines.append(line)

                # VTS 的 db_key
                if param_values and isinstance(param_values, list):
                    db_key = ""
                    for pv in param_values:
                        if isinstance(pv, dict) and pv.get("db_key"):
                            db_key = pv["db_key"]
                            break
                    if db_key:
                        lines.append(f"  db_key: {db_key}")

            # 对应 SSTS 参数（组级别共享）
            if ssts_params and isinstance(ssts_params, list):
                ssts_lines = []
                for p in ssts_params:
                    if isinstance(p, dict):
                        ssts_name = p.get("name", "")
                        ssts_db_key = p.get("db_key", "")
                        ssts_unit = p.get("unit", "")
                        ssts_line = ssts_name
                        if ssts_db_key:
                            ssts_line += f" (db_key: {ssts_db_key})"
                        if ssts_unit and str(ssts_unit) != "Null":
                            ssts_line += f" [{ssts_unit}]"
                        ssts_lines.append(ssts_line)
                if ssts_lines:
                    lines.append(f"  对应SSTS: {', '.join(ssts_lines)}")

            # 计算公式
            if formula:
                lines.append(f"  计算公式: {formula}")

            lines.append("")

        return "\n".join(lines)