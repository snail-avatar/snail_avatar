# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : search_vector_template.py
# @Desc    : 向量检索函数模板
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
向量检索函数模板

用于创建各领域专家Agent的向量检索和以图搜图函数，子类只需配置：
- name: 函数名
- embedding_module: 嵌入模块路径
- domain_name: 领域名称（用于描述）
- persist_dir: 向量库持久化目录（可通过配置动态获取）
"""

import os
import uuid
import yaml
from typing import Any, Dict, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase

_pending_result_images: list[str] = []


def consume_pending_images() -> list[str]:
    """获取并清空待显示的图片列表"""
    global _pending_result_images
    images = _pending_result_images.copy()
    _pending_result_images = []
    return images


class SearchVectorFunctionTemplate(FunctionBase):
    """向量检索函数模板"""

    name = "search_knowledge"
    embedding_module = ""
    domain_name = "领域"
    persist_dir = None
    embedding_config_path = None
    _tool_type = "vector"
    default_top_k = 10  # 工具级条目默认值，可被 FunctionFactory 从 YAML 覆盖

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": f"在{cls.domain_name}专业知识库中搜索与查询相关的文档内容。"
                               f"适用于查找理论知识、经验数据、设计规范等。"
                               f"返回最相关的文档片段及其来源。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": f"搜索查询文本，应使用自然语言描述需要查找的内容，如'{cls.domain_name}相关知识'",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": f"返回{cls.domain_name}结果数量，默认{cls.default_top_k}",
                            "default": cls.default_top_k,
                        },
                    },
                    "required": ["query"],
                },
            },
            "metadata": {
                "type": getattr(cls, "_tool_type", "vector"),
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        query = args.get("query", "")
        top_k = args.get("top_k", cls.default_top_k)

        if not query:
            return {"type": "text", "content": "请提供搜索查询文本。"}

        try:
            import importlib as _il
            _mod = _il.import_module(cls.embedding_module)
            MultiModalEmbedding = _mod.MultiModalEmbedding
            VectorStore = _mod.VectorStore

            if cls.persist_dir is None:
                if cls.embedding_config_path and os.path.exists(cls.embedding_config_path):
                    config_path = cls.embedding_config_path
                else:
                    config_path = os.path.join(os.path.dirname(_mod.__file__), "embedding.yaml")
                
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                    vs_config = config.get("vector_store", {})
                    persist_dir = vs_config.get("persist_dir")
                    if persist_dir:
                        persist_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), persist_dir))
                    else:
                        persist_dir = os.path.join(os.path.dirname(config_path), "..", "data", "vector_db")
                else:
                    persist_dir = os.path.join(os.path.dirname(_mod.__file__), "..", "data", "vector_db")
            else:
                persist_dir = cls.persist_dir

            embedding_fn = MultiModalEmbedding()
            vector_store = VectorStore(persist_dir=persist_dir, embedding_fn=embedding_fn)

            results = vector_store.search(query, top_k=top_k)

            if not results:
                return {"type": "text", "content": f"未找到相关知识。{cls.domain_name}向量库可能为空，请先通过建库管理标签页导入文档。"}

            return cls._format_results(results)

        except Exception as e:
            return {"type": "text", "content": f"向量检索失败: {str(e)}"}

    @classmethod
    def _format_results(cls, results: list) -> Dict[str, Any]:
        """格式化向量检索结果"""
        MAX_CONTENT_LENGTH = 10000

        result_rows = []
        content_lines = []

        for i, r in enumerate(results, 1):
            source = r.metadata.get("source", "未知来源")
            page = r.metadata.get("page", "")
            page_info = f" 第{page}页" if page else ""

            result_rows.append({
                "序号": i,
                "来源": f"{source}{page_info}",
                "相关度": f"{r.score:.2f}",
            })

            content_lines.append(f"[相关度:{r.score:.2f}] 来源:{source}{page_info}")
            content_lines.append(r.text)
            content_lines.append("")

        content = "\n".join(content_lines)
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "\n... (内容已截断)"

        return {
            "type": "text",
            "content": content,
            "summary": {
                "domain": cls.domain_name,
                "query": cls.name,
                "count": len(results),
                "details": result_rows,
            }
        }


class SearchImageFunctionTemplate(FunctionBase):
    """以图搜图函数模板"""

    name = "search_image"
    embedding_module = ""
    domain_name = "领域"
    persist_dir = None
    embedding_config_path = None
    _tool_type = "image"
    default_top_k = 10  # 工具级条目默认值，可被 FunctionFactory 从 YAML 覆盖

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": f"在{cls.domain_name}专业知识库中搜索与图片相似的内容。"
                               f"适用于查找相似的曲线图、仿真云图、原理图等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "查询图片的本地路径",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": f"返回{cls.domain_name}图片数量，默认{cls.default_top_k}",
                            "default": cls.default_top_k,
                        },
                    },
                    "required": ["image_path"],
                },
            },
            "metadata": {
                "type": getattr(cls, "_tool_type", "image"),
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        image_path = args.get("image_path", "")
        top_k = args.get("top_k", cls.default_top_k)

        if not image_path:
            return {"type": "text", "content": "请提供图片路径。"}

        try:
            import importlib as _il
            _mod = _il.import_module(cls.embedding_module)
            MultiModalEmbedding = _mod.MultiModalEmbedding
            VectorStore = _mod.VectorStore

            if cls.persist_dir is None:
                if cls.embedding_config_path and os.path.exists(cls.embedding_config_path):
                    config_path = cls.embedding_config_path
                else:
                    config_path = os.path.join(os.path.dirname(_mod.__file__), "embedding.yaml")
                
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                    vs_config = config.get("vector_store", {})
                    persist_dir = vs_config.get("persist_dir")
                    if persist_dir:
                        persist_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), persist_dir))
                    else:
                        persist_dir = os.path.join(os.path.dirname(config_path), "..", "data", "vector_db")
                else:
                    persist_dir = os.path.join(os.path.dirname(_mod.__file__), "..", "data", "vector_db")
            else:
                persist_dir = cls.persist_dir

            embedding_fn = MultiModalEmbedding()
            vector_store = VectorStore(persist_dir=persist_dir, embedding_fn=embedding_fn)

            results = vector_store.search_by_image(image_path, top_k=top_k)

            if not results:
                return {"type": "text", "content": f"未找到相似图片。{cls.domain_name}向量库可能为空，请先通过建库管理标签页导入文档。"}

            return cls._format_results(results)

        except Exception as e:
            return {"type": "text", "content": f"图片检索失败: {str(e)}"}

    @classmethod
    def _format_results(cls, results: list) -> Dict[str, Any]:
        """格式化图片检索结果"""
        result_rows = []
        content_lines = [f"在专业知识库中找到 {len(results)} 张相似图片：\n"]

        for i, r in enumerate(results, 1):
            source = r.metadata.get("source", "未知来源")
            page = r.metadata.get("page", "")
            page_info = f" 第{page}页" if page else ""
            image_count = len(r.images) if r.images else 0

            result_rows.append({
                "序号": i,
                "来源": f"{source}{page_info}",
                "相似度": f"{r.score:.2f}",
                "图片数": image_count,
            })

            content_lines.append(f"--- 结果 {i} (相似度: {r.score:.2f}) ---")
            content_lines.append(f"来源: {source}{page_info}")

            if r.images:
                for j, img_b64 in enumerate(r.images, 1):
                    img_key = str(uuid.uuid4())
                    _pending_result_images.append(img_b64)
                    content_lines.append(f"[IMAGE:{img_key}]")

            content_lines.append(f"描述: {r.text[:200]}")
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


class SearchTextToImageFunctionTemplate(FunctionBase):
    """以文搜图函数模板：用文字描述搜索知识库中的相关图片"""

    name = "search_image_by_text"
    embedding_module = ""
    domain_name = "领域"
    persist_dir = None
    embedding_config_path = None
    _tool_type = "text_to_image"
    default_top_k = 10

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": f"根据文字描述在{cls.domain_name}专业知识库中搜索相关图片。"
                               f"适用于查找某种特定类型的图片（如'压力云图'、'阻力系数曲线图'、'边界层示意图'等）。"
                               f"返回匹配到的图片及其描述。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "图片内容的文字描述，应尽量具体，如'车身表面压力分布云图'、'风洞试验阻力曲线图'",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": f"返回{cls.domain_name}相关图片数量，默认{cls.default_top_k}",
                            "default": cls.default_top_k,
                        },
                    },
                    "required": ["query"],
                },
            },
            "metadata": {
                "type": getattr(cls, "_tool_type", "text_to_image"),
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        query = args.get("query", "")
        top_k = args.get("top_k", cls.default_top_k)

        if not query:
            return {"type": "text", "content": "请提供图片描述文字。"}

        try:
            import importlib as _il
            _mod = _il.import_module(cls.embedding_module)
            MultiModalEmbedding = _mod.MultiModalEmbedding
            VectorStore = _mod.VectorStore

            if cls.persist_dir is None:
                if cls.embedding_config_path and os.path.exists(cls.embedding_config_path):
                    config_path = cls.embedding_config_path
                else:
                    config_path = os.path.join(os.path.dirname(_mod.__file__), "embedding.yaml")

                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                    vs_config = config.get("vector_store", {})
                    persist_dir = vs_config.get("persist_dir")
                    if persist_dir:
                        persist_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), persist_dir))
                    else:
                        persist_dir = os.path.join(os.path.dirname(config_path), "..", "data", "vector_db")
                else:
                    persist_dir = os.path.join(os.path.dirname(_mod.__file__), "..", "data", "vector_db")
            else:
                persist_dir = cls.persist_dir

            embedding_fn = MultiModalEmbedding()
            vector_store = VectorStore(persist_dir=persist_dir, embedding_fn=embedding_fn)

            # 使用文本向量化搜索（多模态向量空间中，文本向量和图片向量可直接匹配）
            results = vector_store.search(query, top_k=top_k)

            if not results:
                return {"type": "text", "content": f"未找到与描述相关的图片。{cls.domain_name}向量库可能为空，请先通过建库管理标签页导入文档。"}

            return cls._format_results(results)

        except Exception as e:
            return {"type": "text", "content": f"以文搜图检索失败: {str(e)}"}

    @classmethod
    def _format_results(cls, results: list) -> Dict[str, Any]:
        """格式化以文搜图结果 — 只保留含图片的 chunk"""
        # 过滤掉不含图片的 SearchResult
        image_results = [r for r in results if r.images]

        if not image_results:
            # 没有匹配到带图的 chunk，但有纯文本结果
            text_count = len(results) - len(image_results)
            return {
                "type": "text",
                "content": f"未找到与描述直接相关的图片。"
                           f"有 {text_count} 条纯文本相关结果（不含图片），可换个描述再试。",
                "summary": {
                    "domain": cls.domain_name,
                    "count": 0,
                    "details": [],
                }
            }

        result_rows = []
        content_lines = [f"在专业知识库中找到与描述相关的图片（共 {len(image_results)} 条）：\n"]

        for i, r in enumerate(image_results, 1):
            source = r.metadata.get("source", "未知来源")
            page = r.metadata.get("page", "")
            page_info = f" 第{page}页" if page else ""
            image_count = len(r.images) if r.images else 0

            result_rows.append({
                "序号": i,
                "来源": f"{source}{page_info}",
                "相关度": f"{r.score:.2f}",
                "图片数": image_count,
            })

            content_lines.append(f"--- 结果 {i} (相关度: {r.score:.2f}) ---")
            content_lines.append(f"来源: {source}{page_info}")

            if r.images:
                for j, img_b64 in enumerate(r.images, 1):
                    img_key = str(uuid.uuid4())
                    _pending_result_images.append(img_b64)
                    content_lines.append(f"[IMAGE:{img_key}]")

            content_lines.append(f"描述: {r.text[:200]}")
            content_lines.append("")

        return {
            "type": "text",
            "content": "\n".join(content_lines),
            "summary": {
                "domain": cls.domain_name,
                "count": len(image_results),
                "details": result_rows,
            }
        }