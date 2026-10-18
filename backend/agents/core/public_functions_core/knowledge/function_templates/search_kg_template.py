# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : search_kg_template.py
# @Desc    : 知识图谱搜索函数模板
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
知识图谱搜索函数模板

用于创建各领域专家Agent的知识图谱查询函数，子类只需配置：
- name: 函数名
- engine_class: 知识图谱引擎类（默认使用 core 基类）
- data_dir: 数据目录路径（存放 entities.json 和 relations.json）
- domain_name: 领域名称（用于描述）
"""

from __future__ import annotations

from typing import Any, Dict

from ..base_search_function import BaseSearchFunction


class SearchKnowledgeGraphFunctionTemplate(BaseSearchFunction):
    """知识图谱搜索函数模板"""

    name = "search_knowledge_graph"
    engine_class = "snail_avatar.backend.agents.core.knowledge_engines.knowledge_graph_engine.KnowledgeGraphEngine"
    data_dir = None
    domain_name = "领域"
    search_method = "search_nodes"
    _tool_type = "kg"
    default_top_k = 10  # 工具级条目默认值，可被 FunctionFactory 从 YAML 覆盖

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": f"在{cls.domain_name}知识图谱中搜索概念实体及其关联关系。"
                               f"适用于查找专业术语定义、部件间关系、物理现象与参数的关系等。"
                               f"返回匹配的实体节点及其关联关系和描述。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": f"搜索查询内容，如专业术语、概念名称等{cls.domain_name}相关词汇",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": f"返回{cls.domain_name}节点数量，默认{cls.default_top_k}",
                            "default": cls.default_top_k,
                        },
                    },
                    "required": ["query"],
                },
            },
            "metadata": {
                "type": getattr(cls, "_tool_type", "kg"),
            },
        }

    @classmethod
    def _get_item_by_id(cls, engine, item_id: str):
        """从知识图谱引擎中按 id 获取节点"""
        return engine.get_node(item_id)

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        query = args.get("query", "")
        top_k = args.get("top_k", cls.default_top_k)

        if not query:
            return {"type": "text", "content": "请提供搜索查询内容。"}

        try:
            engine = cls._get_engine_instance()

            # 精确匹配 + 向量语义检索 并行执行，合并去重
            precise = engine.search_nodes(query)                  # 精确匹配（按 score 排序）
            vector = cls._vector_search(query, top_k=top_k)       # 向量语义检索（按相似度排序）

            # 合并去重：精确匹配优先，向量补漏；按 id 去重
            seen = set()
            nodes = []
            for item in precise:
                key = item.get("id", "")
                if key and key not in seen:
                    seen.add(key)
                    nodes.append(item)
            for item in vector:
                key = item.get("id", "")
                if key and key not in seen:
                    seen.add(key)
                    nodes.append(item)

            if not nodes:
                return {"type": "text", "content": f"未找到与 '{query}' 相关的知识图谱节点。"}

            return cls._format_results(nodes[:top_k], engine)

        except Exception as e:
            return {"type": "text", "content": f"知识图谱查询失败: {str(e)}"}

    @classmethod
    def _format_results(cls, nodes: list, engine) -> Dict[str, Any]:
        """格式化知识图谱搜索结果"""
        result_rows = []
        content_lines = []

        for node in nodes:
            node_id = node.get("id", "")
            name = node.get("name", node_id)
            ntype = node.get("type", "")
            desc = node.get("desc", "")

            result_rows.append({
                "名称": name,
                "类型": ntype,
            })

            content_lines.append(f"{name}({ntype})")
            if desc:
                content_lines.append(f"描述: {desc}")

            related = engine.query_related(node_id, depth=1)
            relations = related.get("relations", [])
            if relations:
                content_lines.append("关联:")
                for rel in relations[:10]:
                    content_lines.append(f"  {rel.get('from_name', '')} --[{rel.get('relation', '')}]--> {rel.get('to_name', '')}")
            content_lines.append("")

        return {
            "type": "text",
            "content": "\n".join(content_lines),
            "summary": {
                "domain": cls.domain_name,
                "count": len(nodes),
                "details": result_rows,
            }
        }