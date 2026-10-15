# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 201_pubfn_pipeline_config_builder.py
# @Desc    : Public Function: Pipeline 配置构建工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 201: Pipeline 配置构建工具

基于原始数据构建多 Agent 管道查询配置。
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnPipelineConfigBuilder(AtomicFunction):
    """Pipeline 配置构建 Public Function"""

    name: str = "pipeline_config_builder"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "基于原始数据构建多 Agent 管道查询配置（kg_query, vector_query, rules_query, cases_query）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀",
                        },
                        "vts_ssts_mapping": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "VTS/SSTS 映射列表",
                        },
                        "vehicle_info_text": {
                            "type": "string",
                            "description": "产品定义信息文本",
                        },
                        "vts_ssts_text": {
                            "type": "string",
                            "description": "VTS/SSTS 指标文本",
                        },
                    },
                    "required": ["professional_category", "vts_ssts_mapping"],
                },
            },
            "metadata": {
                "type": "config_build",
                "pubfn_index": "201",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 Pipeline 配置构建操作"""
        category = args.get("professional_category", "")
        vehicle_suffix = args.get("vehicle_suffix", "")
        vts_ssts_mapping = args.get("vts_ssts_mapping", [])
        vehicle_info_text = args.get("vehicle_info_text", "")
        vts_ssts_text = args.get("vts_ssts_text", "")

        return cls.build_pipeline_config(
            category, vehicle_suffix, vts_ssts_mapping,
            vehicle_info_text, vts_ssts_text,
        )

    @classmethod
    def build_pipeline_config(
        cls,
        category: str,
        vehicle_suffix: str,
        vts_ssts_mapping: List[Dict[str, Any]],
        vehicle_info_text: str = "",
        vts_ssts_text: str = "",
    ) -> Dict[str, str]:
        """基于原始数据构建 Pipeline 查询配置

        Args:
            category: 专业分类
            vehicle_suffix: 车型后缀
            vts_ssts_mapping: VTS/SSTS 映射列表
            vehicle_info_text: 产品定义信息文本
            vts_ssts_text: VTS/SSTS 指标文本

        Returns:
            dict: 包含各工具的查询参数 {kg_query, vector_query, rules_query, cases_query}
        """
        vts_list = []
        ssts_list = []

        # 容错处理：确保 vts_ssts_mapping 是列表
        if not isinstance(vts_ssts_mapping, list):
            vts_ssts_mapping = []

        for mapping in vts_ssts_mapping:
            if not isinstance(mapping, dict):
                continue
            vts_name = mapping.get("name", "")
            if vts_name:
                vts_list.append(vts_name)
            ssts_params = mapping.get("SSTS_parameter", [])
            for p in ssts_params:
                ssts_name = p.get("name", "")
                if ssts_name and ssts_name not in ssts_list:
                    ssts_list.append(ssts_name)

        keyword_parts = vts_list + ssts_list
        kg_query = " ".join(filter(None, keyword_parts))

        vts_names = "、".join(vts_list) if vts_list else "目标值"
        ssts_names = "、".join(ssts_list) if ssts_list else ""
        if ssts_names:
            vts_ssts_line = f"VTS指标：{vts_names}\nSSTS指标：{ssts_names}"
        else:
            vts_ssts_line = f"VTS指标：{vts_names}"

        vector_query = (
            f"{vehicle_info_text}\n"
            f"专业：{category}\n"
            f"{vts_ssts_line}\n"
            f"目标值定义 参考信息"
        )

        rules_query = (
            f"{vehicle_info_text}\n"
            f"{vts_ssts_text}\n"
            f"公式 规则 计算方法"
        )

        case_parts = [vehicle_suffix, category] + vts_list + ssts_list
        case_keywords = " ".join(filter(None, case_parts))
        case_query = (
            f"{vehicle_info_text}\n"
            f"{case_keywords} 设计案例"
        )

        return {
            "kg_query": kg_query,
            "vector_query": vector_query,
            "rules_query": rules_query,
            "cases_query": case_query,
        }