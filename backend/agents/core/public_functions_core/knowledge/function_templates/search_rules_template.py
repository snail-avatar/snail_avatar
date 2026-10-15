# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : search_rules_template.py
# @Desc    : 规则搜索函数模板
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
规则搜索函数模板

用于创建各领域专家Agent的规则查询函数，子类只需配置：
- name: 函数名
- engine_class: 规则引擎类完整路径
- data_dir: 数据目录相对于子类所在目录的路径
- domain_name: 领域名称（用于描述）
"""

from __future__ import annotations

from typing import Any, Dict

from ..base_search_function import BaseSearchFunction


class SearchRulesFunctionTemplate(BaseSearchFunction):
    """规则搜索函数模板"""

    name = "search_rules"
    engine_class = "snail_avatar.backend.agents.core.knowledge_engines.rule_engine.RuleEngine"
    data_dir = ""
    domain_name = "领域"
    _tool_type = "rules"
    default_top_k = 10  # 工具级条目默认值，可被 FunctionFactory 从 YAML 覆盖

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": f"在{cls.domain_name}规则库中搜索领域规则，包括物理公式、经验公式、设计准则等。"
                               f"适用于查找计算公式、设计参数范围、经验规律等。返回匹配的规则及其详细描述。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": f"搜索查询内容，如'阻力公式'、'设计参数'等{cls.domain_name}相关术语",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": f"返回{cls.domain_name}规则数量，默认{cls.default_top_k}",
                            "default": cls.default_top_k,
                        },
                    },
                    "required": ["query"],
                },
            },
            "metadata": {
                "type": getattr(cls, "_tool_type", "rules"),
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        query = args.get("query", "")
        top_k = args.get("top_k", cls.default_top_k)

        if not query:
            return {"type": "text", "content": "请提供搜索查询内容。"}

        try:
            engine = cls._get_engine_instance()

            # 精确匹配 + 向量语义检索 并行执行，合并去重
            search_method = getattr(engine, cls.search_method)
            precise = search_method(query)                 # 精确匹配（按 score 排序）
            vector = cls._vector_search(query, top_k=top_k)  # 向量语义检索（按相似度排序）

            # 合并去重：精确匹配优先，向量补漏；按 name 去重
            seen = set()
            results = []
            for item in precise:
                key = item.get("name", "")
                if key and key not in seen:
                    seen.add(key)
                    results.append(item)
            for item in vector:
                key = item.get("name", "")
                if key and key not in seen:
                    seen.add(key)
                    results.append(item)

            if not results:
                return {"type": "text", "content": f"未找到与 '{query}' 相关的内容。"}

            return cls._format_results(results[:top_k])

        except Exception as e:
            return {"type": "text", "content": f"查询失败: {str(e)}"}

    @classmethod
    def _format_results(cls, results: list) -> Dict[str, Any]:
        """格式化规则搜索结果"""
        result_rows = []
        content_lines = []

        for rule in results:
            name = rule.get("name", "")
            cat = rule.get("category", "")
            desc = rule.get("description", "")
            formula = rule.get("formula", "")
            source = rule.get("source", "")

            result_rows.append({
                "名称": name,
                "类别": cat,
                "来源": source,
            })

            content_lines.append(f"{name}({cat})")
            content_lines.append(f"描述: {desc}")
            if formula:
                content_lines.append(f"公式: {formula}")
            if source:
                content_lines.append(f"来源: {source}")
            content_lines.append("")

        return {
            "type": "text",
            "content": "\n".join(content_lines),
            "summary": {
                "domain": cls.domain_name,
                "count": len(results),
                "details": result_rows,
            }
        }
