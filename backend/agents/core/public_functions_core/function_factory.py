# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_factory.py
# @Desc    : 基于配置动态创建Function子类的工厂
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
FunctionFactory - 基于配置动态创建Function子类的工厂

根据YAML配置中的tools段落，动态创建各类型的Function子类并注册到FunctionRegistry。

支持的工具类型：
    - vector: 向量检索
    - image: 图片检索（以图搜图）
    - text_to_image: 以文搜图
    - rules: 规则查询
    - cases: 案例查询
    - kg: 知识图谱查询
"""

import os

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionRegistry
from snail_avatar.backend.agents.core.public_functions_core.knowledge.function_templates.search_vector_template import (
    SearchVectorFunctionTemplate, SearchImageFunctionTemplate, SearchTextToImageFunctionTemplate,
)
from snail_avatar.backend.agents.core.public_functions_core.knowledge.function_templates.search_rules_template import (
    SearchRulesFunctionTemplate,
)
from snail_avatar.backend.agents.core.public_functions_core.knowledge.function_templates.search_cases_template import (
    SearchCasesFunctionTemplate,
)
from snail_avatar.backend.agents.core.public_functions_core.knowledge.function_templates.search_kg_template import (
    SearchKnowledgeGraphFunctionTemplate,
)


class FunctionFactory:
    """基于配置动态创建Function子类的工厂"""

    TOOL_TYPE_MAP = {
        "vector": SearchVectorFunctionTemplate,
        "image": SearchImageFunctionTemplate,
        "text_to_image": SearchTextToImageFunctionTemplate,
        "rules": SearchRulesFunctionTemplate,
        "cases": SearchCasesFunctionTemplate,
        "kg": SearchKnowledgeGraphFunctionTemplate,
    }

    @classmethod
    def create_registry(cls, tools_config: list, agent_dir: str) -> FunctionRegistry:
        """根据配置创建工具注册中心"""
        registry = FunctionRegistry()

        for tool_cfg in tools_config:
            tool_type = tool_cfg.get("type")
            template_class = cls.TOOL_TYPE_MAP.get(tool_type)

            if template_class is None:
                continue

            attrs = {
                "name": tool_cfg.get("name"),
                "domain_name": tool_cfg.get("domain_name"),
                "_tool_type": tool_type,  # 注入工具类型，用于 get_schema() 添加 metadata
                "default_top_k": tool_cfg.get("default_top_k", 10),  # 工具级条目默认值
            }

            embedding_config = tool_cfg.get("embedding_config")
            if embedding_config:
                attrs["embedding_module"] = "snail_avatar.backend.agents.core.tools.embedding"
                attrs["embedding_config_path"] = os.path.join(agent_dir, embedding_config)

            # 为知识图谱/规则库/案例库注入向量集合名称（用于语义检索降级）
            # 集合名格式：{domain_name简写}_{tool_type}，确保各领域各库独立
            if tool_type in ("kg", "rules", "cases"):
                domain_key = tool_cfg.get("domain_key", tool_cfg.get("name", ""))
                attrs["vector_collection_name"] = f"{domain_key}_{tool_type}"

            data_path = tool_cfg.get("data_path", "")
            if data_path:
                attrs["data_dir"] = os.path.join(agent_dir, data_path)

            subclass = type(
                f"{tool_type.capitalize()}Function_{tool_cfg['name']}",
                (template_class,),
                attrs,
            )

            registry.register(subclass)

        return registry