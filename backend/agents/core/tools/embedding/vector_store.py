# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vector_store.py
# @Desc    : 本地向量存储（基于 Chroma）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
本地向量存储

基于 Chroma 实现，支持：
- 文档块的增删查
- 语义检索（文本查询）
- 以图搜图（图片查询）
- 向量库统计信息
"""

import os
import uuid
import json
from typing import Any, Dict, List, Optional

import chromadb
import yaml
from chromadb.config import Settings

from .data_types import DocumentChunk, SearchResult
from snail_avatar.backend.core.work_log import WorkLogger
from snail_avatar.backend.core.path_utils import is_frozen, get_writable_dir, get_resource_dir


class VectorStore:
    """本地向量存储，基于 Chroma"""

    COLLECTION_NAME = "aero_knowledge"

    def __init__(self, persist_dir: Optional[str] = None, embedding_fn=None, config_path: Optional[str] = None):
        """
        Args:
            persist_dir: 向量库持久化目录，默认从配置文件读取
            embedding_fn: 嵌入函数实例（MultiModalEmbedding），用于将查询文本/图片转为向量
            config_path: embedding.yaml 配置文件路径，用于读取 persist_dir 和 collection_name
        """
        if persist_dir is None:
            persist_dir = self._load_persist_dir(config_path)
        self._persist_dir = os.path.abspath(persist_dir)
        self._embedding_fn = embedding_fn

        os.makedirs(self._persist_dir, exist_ok=True)

        collection_name = self._load_collection_name(config_path)
        self._collection_name = collection_name

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _load_persist_dir(self, config_path: Optional[str] = None) -> str:
        """从配置文件读取向量库路径，兼容开发和打包环境"""
        if is_frozen():
            writable_dir = get_writable_dir()
            return os.path.join(writable_dir, "data", "vector_db")
        
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "embedding.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            vs_config = config.get("vector_store", {})
            persist_dir = vs_config.get("persist_dir")
            if persist_dir:
                return os.path.join(os.path.dirname(config_path), persist_dir)
        return os.path.join(os.path.dirname(__file__), "..", "data", "vector_db")

    def _load_collection_name(self, config_path: Optional[str] = None) -> str:
        """从配置文件读取 collection_name"""
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "embedding.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            vs_config = config.get("vector_store", {})
            collection_name = vs_config.get("collection_name")
            if collection_name:
                return collection_name
        return self.COLLECTION_NAME

    # ------------------------------------------------------------------
    # 添加文档
    # ------------------------------------------------------------------

    def add_documents(self, chunks: List[DocumentChunk]) -> int:
        """批量添加文档块到向量库

        Args:
            chunks: 文档块列表

        Returns:
            成功添加的数量
        """
        if not chunks or self._embedding_fn is None:
            return 0

        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for chunk in chunks:
            text = chunk.text.strip() or f"[文档: {chunk.metadata.get('source', 'unknown')}]"

            if chunk.images:
                items = [{"text": text}]
                for img in chunk.images:
                    items.append({"image": img})
                vec = self._embedding_fn.embed_mixed(items)
            else:
                vec = self._embedding_fn.embed_text(text)

            if vec is None:
                continue

            chunk_id = chunk.chunk_id or str(uuid.uuid4())
            ids.append(chunk_id)
            embeddings.append(vec)
            documents.append(chunk.text)

            clean_meta = self._clean_metadata(chunk.metadata)
            if chunk.images:
                clean_meta["images"] = json.dumps(chunk.images)
            metadatas.append(clean_meta)

        if not ids:
            return 0

        try:
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            return len(ids)
        except Exception as e:
            WorkLogger.error(f"[VectorStore] 添加文档失败: {e}")
            return 0

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """语义检索：文本查询

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        if self._embedding_fn is None:
            return []

        query_vec = self._embedding_fn.embed_text(query)
        if query_vec is None:
            return []

        return self._search_by_vector(query_vec, top_k)

    def search_by_image(self, image_path: str, top_k: int = 10) -> List[SearchResult]:
        """以图搜图

        Args:
            image_path: 查询图片路径
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        if self._embedding_fn is None:
            return []

        query_vec = self._embedding_fn.embed_image(image_path)
        if query_vec is None:
            return []

        return self._search_by_vector(query_vec, top_k)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_by_source(self, source: str) -> int:
        """按来源删除向量

        Args:
            source: 来源文件名

        Returns:
            删除的数量
        """
        try:
            # 查找所有匹配 source 的文档
            results = self._collection.get(
                where={"source": source},
            )
            if results["ids"]:
                self._collection.delete(ids=results["ids"])
                return len(results["ids"])
            return 0
        except Exception as e:
            WorkLogger.error(f"[VectorStore] 删除失败: {e}")
            return 0

    def delete_by_ids(self, ids: List[str]) -> int:
        """按ID列表删除"""
        try:
            self._collection.delete(ids=ids)
            return len(ids)
        except Exception as e:
            WorkLogger.error(f"[VectorStore] 删除失败: {e}")
            return 0

    def clear_all(self) -> None:
        """清空向量库"""
        try:
            self._client.delete_collection(self._collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            WorkLogger.error(f"[VectorStore] 清空失败: {e}")

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        try:
            count = self._collection.count()
            return {
                "total_vectors": count,
                "collection_name": self._collection_name,
                "persist_dir": self._persist_dir,
            }
        except Exception:
            return {"total_vectors": 0, "collection_name": self._collection_name}

    def list_sources(self) -> List[str]:
        """列出所有已入库的来源文件"""
        try:
            results = self._collection.get()
            sources = set()
            for meta in results.get("metadatas", []):
                src = meta.get("source", "")
                if src:
                    sources.add(src)
            return sorted(sources)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _search_by_vector(self, query_vec: List[float], top_k: int) -> List[SearchResult]:
        """按向量检索"""
        try:
            results = self._collection.query(
                query_embeddings=[query_vec],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            search_results = []
            ids = results.get("ids", [[]])[0]
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for i in range(len(ids)):
                meta = metas[i] if i < len(metas) else {}
                images = []
                if "images" in meta:
                    try:
                        images = json.loads(meta["images"])
                    except Exception:
                        images = []
                search_results.append(SearchResult(
                    chunk_id=ids[i],
                    text=docs[i] if i < len(docs) else "",
                    score=1.0 - distances[i] if i < len(distances) else 0.0,
                    metadata=meta,
                    images=images,
                ))

            return search_results
        except Exception as e:
            WorkLogger.error(f"[VectorStore] 检索失败: {e}")
            return []

    @staticmethod
    def _clean_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
        """清理元数据，确保所有值都是 Chroma 支持的类型（str/int/float/bool）"""
        clean = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                clean[k] = v
            elif v is None:
                clean[k] = ""
            else:
                clean[k] = str(v)
        return clean