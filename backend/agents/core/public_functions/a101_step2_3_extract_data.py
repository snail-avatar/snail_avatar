# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_3_extract_data.py
# @Desc    : Public Function (a101 step2_3): 法规检查步骤数据提取
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_3): 法规检查步骤数据提取

为 step2_3 (CHECK_REGULATIONS_AND_REFERENCES) 提供数据提取能力：

1. extract_vehicle_info: 从 step_results 提取车型背景信息
2. extract_vts_ssts_text: 从 step_results 提取 VTS/SSTS 格式化文本（供模板变量）
3. extract_vts_ssts_mapping: 从 step_results 提取 VTS/SSTS 原始列表（供 pipeline_config）
4. extract_from_process_data: 从 process_data.vts_category_data 提取（支持 json/list 格式）

数据来源：
- step_results: {category}_{step_id} 格式的 key
- process_data: vts_category_data 字段

必需参数（YAML 需显式声明）：
- sandbox: 沙箱实例
- operation: 操作类型
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_3ExtractData(AtomicFunction):
    """Step2_3 数据提取 Public Function"""

    name: str = "step2_3_extract_data"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_3 专属数据提取工具。提供以下操作：\n"
                    "  - extract_vehicle_info: 从 step_results 提取车型背景信息\n"
                    "  - extract_vts_ssts_text: 从 step_results 提取 VTS/SSTS 格式化文本\n"
                    "  - extract_vts_ssts_mapping: 从 step_results 提取 VTS/SSTS 原始列表\n"
                    "  - extract_from_process_data: 从 process_data 提取（需额外 format 参数）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": (
                                "操作类型：\n"
                                "  extract_vehicle_info / extract_vts_ssts_text / "
                                "extract_vts_ssts_mapping / extract_from_process_data"
                            ),
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "format": {
                            "type": "string",
                            "description": "输出格式（仅 extract_from_process_data 使用）：json 或 list",
                        },
                    },
                    "required": ["operation", "sandbox"],
                },
            },
            "metadata": {
                "type": "data_extract",
                "pubfn_index": "a101_step2_3",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行数据提取

        Args:
            args: 参数字典，必须包含 operation 和 sandbox；
                  professional_category/vehicle_suffix 由框架自动注入
            context: Agent 实例（由 execute() 第 2 参数传入）
        """
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        sandbox = args.get("sandbox") or (getattr(context, "sandbox", None) if context else None)

        try:
            if operation == "extract_vehicle_info":
                return cls.extract_vehicle_info_from_sandbox(sandbox, args)

            elif operation == "extract_vts_ssts_text":
                result = cls.extract_vts_ssts_data_from_sandbox(sandbox, args)
                return result[0] if isinstance(result, tuple) else str(result)

            elif operation == "extract_vts_ssts_mapping":
                result = cls.extract_vts_ssts_data_from_sandbox(sandbox, args)
                return result[1] if isinstance(result, tuple) and len(result) > 1 else []

            elif operation == "extract_from_process_data":
                output_format = args.get("format", "json")
                return cls.extract_vts_ssts_from_process_data(sandbox, args, output_format)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    # ==================================================================
    # 从 step_results 提取的方法（a101 专属 key 拼接）
    # ==================================================================

    @classmethod
    def extract_vehicle_info_from_sandbox(cls, sandbox: Any, args: Dict[str, Any]) -> str:
        """从 step_results 提取车型背景信息

        从 ANALYZE_PRODUCT 步骤结果中获取产品定义信息。

        Args:
            sandbox: 沙箱实例
            args: 步骤参数（包含 professional_category, vehicle_suffix）

        Returns:
            str: 车型背景信息文本
        """
        if not sandbox:
            return "（暂无车型背景信息）"

        category = args.get("professional_category", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        try:
            # key 格式为 {category}_{step_id}，如 "空气动力学_ANALYZE_PRODUCT"
            full_step_id = f"{category}_ANALYZE_PRODUCT" if category else "ANALYZE_PRODUCT"
            step_result = sandbox.get_step_result(full_step_id)

            if not step_result:
                step_result = sandbox.get_step_result("ANALYZE_PRODUCT")
        except Exception:
            step_result = None

        if not step_result:
            return f"车型后缀：{vehicle_suffix}（暂无详细产品信息）"

        structured_data = step_result.get("structured_data", {})
        product_info = structured_data.get("product_information", [])

        if not product_info:
            return f"车型后缀：{vehicle_suffix}（暂无产品定义数据）"

        lines = [f"车型后缀：{vehicle_suffix}"]
        lines.append("产品定义信息：")

        for item in product_info:
            name = item.get("名称", item.get("name", ""))
            value = item.get("值", item.get("value", ""))
            unit = item.get("单位", item.get("unit", ""))
            if name and value:
                line = f"- {name}: {value}"
                if unit and unit != "Null":
                    line += f" {unit}"
                lines.append(line)

        return "\n".join(lines)

    @classmethod
    def extract_vts_ssts_data_from_sandbox(
        cls, sandbox: Any, args: Dict[str, Any]
    ) -> Tuple[str, list]:
        """从 step_results 提取 VTS/SSTS 条目（文本 + 原始数据）

        从 DETERMINE_MAPPING 步骤结果中获取 VTS/SSTS 映射数据（sub_category 分组结构）。

        Args:
            sandbox: 沙箱实例
            args: 步骤参数（包含 professional_category）

        Returns:
            tuple: (格式化文本, 原始映射列表)
        """
        if not sandbox:
            return "（暂无 VTS/SSTS 数据）", []

        category = args.get("professional_category", "")

        try:
            # key 格式为 {category}_{step_id}，如 "空气动力学_DETERMINE_MAPPING"
            full_step_id = f"{category}_DETERMINE_MAPPING" if category else "DETERMINE_MAPPING"
            step_result = sandbox.get_step_result(full_step_id)

            if not step_result:
                step_result = sandbox.get_step_result("DETERMINE_MAPPING")
        except Exception:
            step_result = None

        if not step_result:
            return "（暂无 VTS/SSTS 映射数据）", []

        structured_data = step_result.get("structured_data", {})
        sub_categories = structured_data.get("sub_category", [])

        if not sub_categories:
            return "（暂无 VTS/SSTS 映射条目）", []

        # 扁平化 sub_category 分组结构为列表
        flat_mappings = []
        for group in sub_categories:
            if not isinstance(group, dict):
                continue
            for sub_cat_name, group_list in group.items():
                if not isinstance(group_list, list):
                    continue
                for group_content in group_list:
                    if not isinstance(group_content, dict):
                        continue
                    vts_items = group_content.get("VTS_items", [])
                    ssts_params = group_content.get("SSTS_parameter", [])
                    formula = group_content.get("计算公式", "")

                    for vts in vts_items:
                        if not isinstance(vts, dict):
                            continue
                        entry = {
                            "name": vts.get("name", ""),
                            "unit": vts.get("unit", ""),
                            "sub_category": sub_cat_name,
                            "param_values": vts.get("param_values", []),
                            "SSTS_parameter": ssts_params,
                            "计算公式": formula,
                        }
                        flat_mappings.append(entry)

        if not flat_mappings:
            return "（暂无 VTS/SSTS 映射条目）", []

        # 按 sub_category 分组，避免同子分类 VTS 的 SSTS 列表重复打印
        groups: Dict[str, List[dict]] = {}
        for m in flat_mappings:
            groups.setdefault(m.get("sub_category", "未分类"), []).append(m)

        lines = ["以下是当前专业的 VTS 指标列表（按子分类分组）："]
        for sub_cat, items in groups.items():
            lines.append(f"\n【{sub_cat}】")
            vts_parts = []
            for m in items:
                vts_name = m.get("name", "")
                unit = m.get("单位", m.get("unit", ""))
                part = f"{vts_name}"
                if unit and unit != "Null":
                    part += f"({unit})"
                vts_parts.append(part)
            lines.append(f"VTS: {', '.join(vts_parts)}")

            # 同子分类的 VTS 共享同一组 SSTS，取第一个即可
            first = items[0]
            ssts_params = first.get("SSTS_parameter", [])
            if ssts_params:
                ssts_names = [p.get("name", "") for p in ssts_params
                              if isinstance(p, dict) and p.get("name")]
                if ssts_names:
                    lines.append(f"SSTS参数: {', '.join(ssts_names)}")

        return "\n".join(lines), flat_mappings

    # ==================================================================
    # 从 process_data 提取的方法
    # ==================================================================

    @classmethod
    def extract_vts_ssts_from_process_data(
        cls, sandbox: Any, args: Dict[str, Any], output_format: str
    ) -> Any:
        """从 process_data.vts_category_data 提取 VTS/SSTS 数据

        Args:
            sandbox: 沙箱实例
            args: 参数字典（含 professional_category）
            output_format: 输出格式 "json" 或 "list"

        Returns:
            str or list: 根据 format 返回 JSON 字符串或原始列表
        """
        if not sandbox:
            return "[]" if output_format == "json" else []

        category = args.get("professional_category", "")

        try:
            vts_category_data = sandbox.get_process_data("vts_category_data")
        except Exception:
            vts_category_data = None

        if not vts_category_data or not isinstance(vts_category_data, dict):
            return "[]" if output_format == "json" else []

        category_data = vts_category_data.get(category, {})
        if not isinstance(category_data, dict):
            return "[]" if output_format == "json" else []

        # 将嵌套结构扁平化为列表
        flat_list = []
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            vts_items = group_content.get("VTS_items", [])
            ssts_params = group_content.get("SSTS_parameter", [])
            formula = group_content.get("计算公式", "")

            for vts in vts_items:
                if not isinstance(vts, dict):
                    continue
                entry = {
                    "name": vts.get("name", ""),
                    "unit": vts.get("unit", ""),
                    "sub_category": sub_cat_name,
                    "param_values": vts.get("param_values", []),
                    "SSTS_parameter": ssts_params,
                    "计算公式": formula,
                }
                flat_list.append(entry)

        if output_format == "list":
            return flat_list

        return cls._format_as_json(flat_list)

    @classmethod
    def _format_as_json(cls, flat_list: List[Dict]) -> str:
        """将扁平 VTS 列表格式化为精简 JSON

        Args:
            flat_list: 扁平化后的 VTS 条目列表

        Returns:
            str: JSON 格式字符串
        """
        output_list = []
        for item in flat_list:
            if not isinstance(item, dict):
                continue
            entry = {
                "name": item.get("name", ""),
                "unit": item.get("unit", ""),
                "sub_category": item.get("sub_category", ""),
            }

            # VTS 的 db_key
            param_values = item.get("param_values", [])
            if param_values and isinstance(param_values, list):
                entry["db_key"] = param_values[0].get("db_key", "") if isinstance(param_values[0], dict) else ""

            # SSTS 参数列表（精简格式，只保留 name/unit/db_key）
            ssts_params = item.get("SSTS_parameter", [])
            if ssts_params and isinstance(ssts_params, list):
                entry["SSTS_parameter"] = [
                    {
                        "name": p.get("name", ""),
                        "unit": p.get("unit", ""),
                        "db_key": p.get("db_key", ""),
                    }
                    for p in ssts_params
                    if isinstance(p, dict)
                ]

            # 计算公式
            formula = item.get("计算公式", "")
            if formula:
                entry["计算公式"] = formula

            output_list.append(entry)

        return json.dumps(output_list, ensure_ascii=False, indent=2)