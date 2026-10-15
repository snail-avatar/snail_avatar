# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_3_build_pipeline_config.py
# @Desc    : Public Function (a101 step2_3): 构建多 Agent 管道查询配置
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_3): 构建多 Agent 管道查询配置

基于 VTS/SSTS 映射数据和车型信息，构建 step2_3 专属的多 Agent 管道查询配置。
生成 kg_query / vector_query / rules_query / cases_query 四个查询参数，
供法规检查步骤的子 Agent 分别从知识库、向量库、规则库、案例库检索信息。

必需参数（YAML 需显式声明）：
- professional_category: 专业分类
- vehicle_suffix: 车型后缀
- vts_ssts_mapping: VTS/SSTS 映射列表
- vehicle_info_text: 产品定义信息文本
- vts_ssts_text: VTS/SSTS 指标文本
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_3BuildPipelineConfig(AtomicFunction):
    """Step2_3 Pipeline 配置构建 Public Function"""

    name: str = "step2_3_build_pipeline_config"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_3 专属 Pipeline 配置构建工具。\n"
                    "基于 VTS/SSTS 映射数据和车型信息，构建四组查询参数：\n"
                    "kg_query（知识库查询）、vector_query（向量查询）、\n"
                    "rules_query（规则查询）、cases_query（案例查询）。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类（如 空气动力学）",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀（如 reevlto）",
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
                "pubfn_index": "a101_step2_3",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 Pipeline 配置构建

        Args:
            args: 参数字典
            context: 上下文对象

        Returns:
            dict: 包含 kg_query, vector_query, rules_query, cases_query
        """
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
        """构建 Pipeline 查询配置

        基于 VTS/SSTS 映射数据，提取关键词构建四组查询参数，
        供法规检查步骤的子 Agent 分别检索知识库、向量库、规则库和案例库。

        Args:
            category: 专业分类
            vehicle_suffix: 车型后缀
            vts_ssts_mapping: VTS/SSTS 映射列表
            vehicle_info_text: 产品定义信息文本
            vts_ssts_text: VTS/SSTS 指标文本

        Returns:
            dict: {kg_query, vector_query, rules_query, cases_query}
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

        # 知识库查询：VTS 名称 + SSTS 名称
        keyword_parts = vts_list + ssts_list
        kg_query = " ".join(filter(None, keyword_parts))

        # VTS/SSTS 名称行
        vts_names = "、".join(vts_list) if vts_list else "目标值"
        ssts_names = "、".join(ssts_list) if ssts_list else ""
        if ssts_names:
            vts_ssts_line = f"VTS指标：{vts_names}\nSSTS指标：{ssts_names}"
        else:
            vts_ssts_line = f"VTS指标：{vts_names}"

        # 向量库查询：车型信息 + 专业 + VTS/SSTS 名称 + 任务目标
        vector_query = (
            f"{vehicle_info_text}\n"
            f"专业：{category}\n"
            f"{vts_ssts_line}\n"
            f"目标值定义 参考信息"
        )

        # 规则库查询：车型信息 + VTS/SSTS 文本 + 公式规则计算方法
        rules_query = (
            f"{vehicle_info_text}\n"
            f"{vts_ssts_text}\n"
            f"公式 规则 计算方法"
        )

        # 案例库查询：车型后缀 + 专业 + VTS/SSTS 关键词 + 设计案例
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
