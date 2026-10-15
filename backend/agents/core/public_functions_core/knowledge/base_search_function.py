# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : base_search_function.py
# @Desc    : 基础搜索函数模板
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
基础搜索函数模板

定义通用的搜索函数接口和实现逻辑，子类只需配置以下参数：
- name: 函数名
- engine_class: 引擎类完整路径（如 'snail_avatar.backend.agents.core.knowledge_engines.rule_engine.RuleEngine'）
- data_dir: 数据目录相对于子类所在目录的路径（如 'rules'）
- search_method: 搜索方法名
- search_description: 搜索描述
- query_description: 查询内容描述

两级检索策略：
1. 先执行精确关键词匹配（引擎的 search 方法，已支持多关键词拆分）
2. 如果第1级无结果，降级到向量语义检索（通过 embedding 配置）
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase


class BaseSearchFunction(FunctionBase):
    """基础搜索函数模板"""

    name = "base_search"
    engine_class = ""
    data_dir = ""
    search_method = "search"
    search_description = "搜索领域知识"
    query_description = "搜索查询内容"

    # 向量检索相关配置（子类可覆盖）
    embedding_module = "snail_avatar.backend.agents.core.tools.embedding"
    embedding_config_path = None
    # 向量集合名称前缀，子类应覆盖（如 "aero_kg"、"aero_rules"、"aero_cases"）
    vector_collection_name = ""
    # 向量语义匹配的相似度阈值，低于此值不返回
    vector_similarity_threshold = 0.4

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.search_description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": cls.query_description,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    @classmethod
    def _get_engine_instance(cls):
        """获取引擎实例"""
        if not cls.engine_class:
            raise ValueError("engine_class 未配置")

        module_path, class_name = cls.engine_class.rsplit(".", 1)
        _mod = importlib.import_module(module_path)
        EngineClass = getattr(_mod, class_name)

        if cls.data_dir:
            data_path = os.path.join(os.path.dirname(cls.__module__), cls.data_dir)
            return EngineClass(data_path)
        return EngineClass()

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        query = args.get("query", "")

        if not query:
            return {"type": "text", "content": "请提供搜索查询内容。"}

        try:
            engine = cls._get_engine_instance()
            search_method = getattr(engine, cls.search_method)
            results = search_method(query)

            if not results:
                return {"type": "text", "content": f"未找到与 '{query}' 相关的内容。"}

            return cls._format_results(results)

        except Exception as e:
            return {"type": "text", "content": f"查询失败: {str(e)}"}

    @classmethod
    def _format_results(cls, results: list, max_length: int = 5000) -> Dict[str, Any]:
        """格式化搜索结果（子类重写）

        Args:
            results: 搜索结果列表
            max_length: 返回内容的最大字符数，超过则截断
        """
        content_lines = [f"找到 {len(results)} 条相关内容：\n"]
        for item in results:
            item_str = str(item)
            content_lines.append(item_str)
            content_lines.append("")

        content = "\n".join(content_lines)

        if len(content) > max_length:
            content = content[:max_length] + "\n... (内容已截断，仅显示前 {} 字符)".format(max_length)

        return {"type": "text", "content": content}

    # ------------------------------------------------------------------
    # 向量语义检索（两级检索的降级机制）
    # ------------------------------------------------------------------

    @classmethod
    def _get_vector_persist_dir(cls) -> Optional[str]:
        """从 embedding 配置文件读取向量库持久化目录"""
        config_path = cls.embedding_config_path
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            vs_config = config.get("vector_store", {})
            persist_dir = vs_config.get("persist_dir")
            if persist_dir:
                return os.path.abspath(os.path.join(os.path.dirname(config_path), persist_dir))
        return None

    @classmethod
    def _get_vector_store(cls):
        """获取向量库实例（用于知识图谱/规则/案例的语义检索降级）

        使用独立的 collection，和文档向量库互不干扰。
        """
        if not cls.vector_collection_name:
            return None

        try:
            _mod = importlib.import_module(cls.embedding_module)
            MultiModalEmbedding = _mod.MultiModalEmbedding
            VectorStore = _mod.VectorStore

            persist_dir = cls._get_vector_persist_dir()
            if persist_dir is None:
                return None

            embedding_fn = MultiModalEmbedding()
            vector_store = VectorStore(
                persist_dir=persist_dir,
                embedding_fn=embedding_fn,
            )
            # 切换到本工具专属的 collection
            vector_store._collection_name = cls.vector_collection_name
            vector_store._collection = vector_store._client.get_or_create_collection(
                name=cls.vector_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return vector_store
        except Exception as e:
            print(f"[{cls.name}] 获取向量库失败: {e}")
            return None

    @classmethod
    def _vector_search(cls, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """向量语义检索降级：返回按 id 索引的原始条目

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            匹配的原始条目列表（从引擎数据中按 metadata.id 取回完整数据）
        """
        vector_store = cls._get_vector_store()
        if vector_store is None:
            return []

        # 检查向量集合是否有数据
        stats = vector_store.get_stats()
        if stats.get("total_vectors", 0) == 0:
            return []

        # 向量检索
        results = vector_store.search(query, top_k=top_k)
        if not results:
            return []

        # 按相似度阈值过滤
        filtered = [r for r in results if r.score >= cls.vector_similarity_threshold]
        if not filtered:
            return []

        # 从向量结果中提取 id，再从引擎获取完整原始数据
        engine = cls._get_engine_instance()
        matched_items = []
        for r in filtered:
            item_id = r.metadata.get("item_id", "")
            if not item_id:
                continue
            # 尝试从引擎按 id 获取完整数据
            item = cls._get_item_by_id(engine, item_id)
            if item:
                matched_items.append(item)

        return matched_items

    @classmethod
    def _get_item_by_id(cls, engine, item_id: str) -> Optional[Dict[str, Any]]:
        """从引擎中按 id 获取单个条目（子类可重写）

        默认实现：遍历 get_all() 查找匹配 id 的条目
        """
        all_items = engine.get_all()
        for item in all_items:
            if item.get("id", "") == item_id:
                return item
        return None

    @classmethod
    def build_vector_index(cls) -> Tuple[bool, str]:
        """构建向量索引（供 UI 按钮调用）

        将引擎中的所有条目向量化存入专属 collection。

        Returns:
            (是否成功, 消息)
        """
        if not cls.vector_collection_name:
            return False, "未配置向量集合名称"

        try:
            vector_store = cls._get_vector_store()
            if vector_store is None:
                return False, "向量库初始化失败"

            engine = cls._get_engine_instance()
            all_items = engine.get_all()
            if not all_items:
                return False, "没有可索引的数据"

            # 清空旧索引
            vector_store.clear_all()

            # 构建文档文本和 metadata
            from snail_avatar.backend.agents.core.tools.embedding.data_types import DocumentChunk

            chunks = []
            for item in all_items:
                item_id = item.get("id", "")
                text = cls._build_index_text(item)
                if not text.strip():
                    continue
                chunk = DocumentChunk(
                    text=text,
                    metadata={
                        "item_id": item_id,
                        "name": item.get("name", item.get("title", "")),
                        "type": cls._tool_type,
                    },
                )
                chunks.append(chunk)

            if not chunks:
                return False, "没有有效的索引内容"

            count = vector_store.add_documents(chunks)
            return True, f"成功构建向量索引，共 {count} 条"

        except Exception as e:
            return False, f"构建向量索引失败: {e}"

    @classmethod
    def _build_index_text(cls, item: Dict[str, Any]) -> str:
        """构建条目的向量索引文本（子类可重写）

        默认实现：拼接所有文本字段
        """
        parts = []
        for key in ("name", "title", "type", "category", "description",
                     "formula", "vehicle_type", "key_params", "results", "desc"):
            val = item.get(key, "")
            if val:
                parts.append(str(val))
        return " ".join(parts)

    @classmethod
    def _two_level_search(cls, query: str, top_k: int = 5) -> Tuple[List[Dict[str, Any]], bool]:
        """两级检索：先关键词匹配，无结果时降级到向量语义检索

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            (结果列表, 是否使用了向量检索)
        """
        # 第1级：关键词精确匹配
        engine = cls._get_engine_instance()
        search_method = getattr(engine, cls.search_method)
        results = search_method(query)

        if results:
            return results[:top_k], False

        # 第2级：向量语义检索降级
        vector_results = cls._vector_search(query, top_k=top_k)
        if vector_results:
            return vector_results[:top_k], True

        return [], False