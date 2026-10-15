# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_2_format_vts_data.py
# @Desc    : Public Function (a101 step2_2): Step2_2 数据准备 + post_process 权威名称覆盖
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_2): Step2_2 公共函数集合

包含两个公共函数：
1. step2_2_format_vts_data: data_sources 阶段，从 sandbox 格式化 VTS 数据供 Prompt 使用
2. step2_2_apply_authoritative_names: post_process 阶段，用 DB 权威中文名覆盖 LLM 编的 SSTS 参数名

设计原则：
  DB 的 SSTS 分类是按部件（cat1="SSTS", cat2="电驱系统"/"风阻"/...），
  不是按专业（空气动力学/动力性/经济性），所以无法在 LLM 调用前
  按专业过滤出正确的 SSTS 名称表。改为：
  - LLM 正常输出 SSTS_parameter（db_key + 自编中文名）
  - post_process 拿到完整 db_key 后，反查 DB 权威中文名并覆盖 name 字段

必需参数（YAML 需显式声明）：
- professional_category: 当前专业名（函数1）
- mapping + memory_db + instance_key（函数2）
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import iter_flat_items


class A101Step2_2FormatVtsData(AtomicFunction):
    """Step2_2 VTS 数据格式化 Public Function（data_sources 阶段）"""

    name: str = "step2_2_format_vts_data"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_2 专属 VTS 数据格式化工具。\n"
                    "从 sandbox.process_data 读取指定专业的 VTS 数据，\n"
                    "格式化为带参数名和值的可读文本，供 LLM Prompt 使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类（如 空气动力学）",
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                    },
                    "required": ["professional_category"],
                },
            },
            "metadata": {
                "type": "data_format",
                "pubfn_index": "a101_step2_2",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 VTS 数据格式化"""
        professional_category = args.get("professional_category", "")
        sandbox = args.get("sandbox")
        if not sandbox:
            sandbox = cls._get_sandbox_from_context(context)
        return cls.format_vts_data_for_prompt(sandbox, professional_category)

    @classmethod
    def _get_sandbox_from_context(cls, context: Any) -> Any:
        """从 context 获取 sandbox 实例"""
        if context is None:
            return None
        sandbox = getattr(context, 'sandbox', None)
        if sandbox:
            return sandbox
        controllers = getattr(context, '_controllers', None)
        if controllers:
            first_controller = next(iter(controllers.values()), None)
            if first_controller and hasattr(first_controller, 'get_sandbox'):
                return first_controller.get_sandbox()
        sandbox = getattr(context, '_sandbox', None)
        if sandbox:
            return sandbox
        return None

    @classmethod
    def format_vts_data_for_prompt(cls, sandbox: Any, professional_category: str) -> str:
        """格式化 VTS 数据为可读文本供 LLM 使用

        从 sandbox.process_data.vts_category_data 读取指定专业的 VTS 列表，
        按二级专业分组格式化为可读文本。
        """
        if not sandbox:
            return "（暂无 VTS 数据，请从上下文信息中提取）"

        vts_category_data = sandbox.get_process_data("vts_category_data") or {}
        category_data = vts_category_data.get(professional_category, {})

        if not category_data or not isinstance(category_data, dict):
            return "（暂无 VTS 数据，请从上下文信息中提取）"

        lines = []
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            vts_items = group_content.get("VTS_items", [])
            if not vts_items:
                continue
            lines.append(f"【{sub_cat_name}】")
            for vts_item in vts_items:
                if not isinstance(vts_item, dict):
                    continue
                name = vts_item.get("name", "")
                unit = vts_item.get("单位", vts_item.get("unit", ""))
                param_values = vts_item.get("param_values", [])
                param_texts = []
                for param in param_values:
                    if not isinstance(param, dict):
                        continue
                    db_key = param.get("db_key", "")
                    value = param.get("值", param.get("value", "NaN"))
                    param_texts.append(f"{db_key}={value}")
                line = f"- {name}（单位: {unit}）"
                if param_texts:
                    line += f"，参数: {', '.join(param_texts)}"
                lines.append(line)
            lines.append("")

        return "\n".join(lines)


# ==========================================================================

