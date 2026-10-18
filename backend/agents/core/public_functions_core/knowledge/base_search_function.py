# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : base_search_function.py
# @Desc    : 规则/案例/知识图谱检索模板的公共基类（向量降级链路）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
规则/案例/知识图谱检索模板的公共基类

提供向量语义检索降级能力，用于精确关键词匹配（引擎 search 方法）miss 时的语义兜底。
子类（SearchRulesFunctionTemplate / SearchCasesFunctionTemplate / SearchKnowledgeGraphFunctionTemplate）
重写 execute / get_schema / _format_results，在此基类之上组合精确匹配 + 向量降级。
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict, List, Optional

import yaml

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase


class BaseSearchFunction(FunctionBase):
    """规则/案例/知识图谱检索模板的公共基类"""

    name = "base_search"
    engine_class = ""
    data_dir = ""
    search_method = "search"

    # 向量检索相关配置（子类/FunctionFactory 注入）
    embedding_module = "snail_avatar.backend.agents.core.tools.embedding"
    embedding_config_path = None
    vector_collection_name = ""
    vector_similarity_threshold = 0.4

    # 引擎构造参数名映射：各引擎 __init__ 签名不同
    # RuleEngine(rules_path=...) / CaseEngine(cases_path=...) / KnowledgeGraphEngine(data_dir=...)
    _engine_kwarg_map = {
        "rules": "rules_path",
        "cases": "cases_path",
        "kg": "data_dir",
    }

    @classmethod
    def _get_engine_instance(cls):
        """获取引擎实例

        根据 _tool_type 选择正确的构造参数名，
        各引擎 __init__ 签名不同（rules_path / cases_path / data_dir）。
        """
        if not cls.engine_class:
            raise ValueError("engine_class 未配置")

        module_path, class_name = cls.engine_class.rsplit(".", 1)
        _mod = importlib.import_module(module_path)
        EngineClass = getattr(_mod, class_name)

        if cls.data_dir:
            kwarg = cls._engine_kwarg_map.get(getattr(cls, "_tool_type", ""), "data_dir")
            return EngineClass(**{kwarg: cls.data_dir})
        return EngineClass()

    # ------------------------------------------------------------------
    # 向量语义检索（精确匹配 miss 时的降级路径）
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
        """获取向量库实例"""
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
        """向量语义检索：返回引擎中的原始条目（按 metadata.item_id 回查）

        Chroma 向量库中存的是条目的文本化表示（name/category/description/formula 拼接），
        检索后需按 item_id 从引擎中取回完整原始数据。

        metadata.item_id 由 expert_panels.py 的 UI 面板入库端点统一写入，
        不再保留 item_id/id 双字段兼容。
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

        # 从向量结果中按 item_id 回查引擎取完整原始数据
        engine = cls._get_engine_instance()
        matched_items = []
        for r in filtered:
            item_id = r.metadata.get("item_id", "")
            if not item_id:
                continue
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
