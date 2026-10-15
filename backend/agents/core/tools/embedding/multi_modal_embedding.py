# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : multi_modal_embedding.py
# @Desc    : 多模态嵌入客户端（适配层）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
多模态嵌入客户端（适配层）

封装 EmbeddingDeploy，支持：
- 纯文本向量化
- 图片向量化（本地图片自动转base64）
- 混合模态向量化（文本+图片列表）
- 批量向量化

底层调用由 snail_avatar.backend.llm.deploy.EmbeddingDeploy 统一调度，
支持配置化切换不同 Embedding Provider。
"""

import os
from typing import Dict, List, Optional

import yaml

from snail_avatar.backend.core.work_log import WorkLogger
from snail_avatar.backend.llm.deploy import get_embedding_instance
from snail_avatar.backend.core.path_utils import is_frozen, get_resource_dir


class MultiModalEmbedding:
    """多模态嵌入客户端（适配层），底层调用由 EmbeddingDeploy 统一调度"""

    MODEL_NAME = "qwen3-vl-embedding"

    def __init__(self, api_key: Optional[str] = None, config_path: Optional[str] = None, config: Optional[Dict] = None):
        """
        Args:
            api_key: API Key，不传则从环境变量或 config.ini 读取
            config_path: embedding.yaml 配置文件路径，默认从同级目录加载
            config: 预加载的配置字典，优先级高于 config_path
        """
        self._config = config or self._load_config(config_path)

        if api_key:
            self._config["api_key"] = api_key

        self._deploy = get_embedding_instance(self._config)

    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """加载 embedding 配置文件，兼容开发和打包环境"""
        if config_path is None:
            if is_frozen():
                resource_dir = get_resource_dir()
                config_path = os.path.join(resource_dir, "agents", "core", "embedding", "embedding.yaml")
            else:
                config_path = os.path.join(os.path.dirname(__file__), "embedding.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    @property
    def model_name(self) -> str:
        return self._config.get("model", self.MODEL_NAME)

    @property
    def dimension(self) -> int:
        """向量维度"""
        return self._deploy.dimension

    # ------------------------------------------------------------------
    # 单模态嵌入
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> Optional[List[float]]:
        """纯文本向量化

        Args:
            text: 待向量化的文本

        Returns:
            向量列表，失败返回 None
        """
        result = self._deploy.embed_text(text)
        return result if result else None

    def embed_image(self, image_path: str) -> Optional[List[float]]:
        """图片向量化（直接传递本地文件路径）

        Args:
            image_path: 本地图片路径

        Returns:
            向量列表，失败返回 None
        """
        if not os.path.exists(image_path):
            WorkLogger.error(f"[MultiModalEmbedding] 图片文件不存在: {image_path}")
            return None

        WorkLogger.info(f"[MultiModalEmbedding] 图片路径: {image_path}")
        result = self._deploy.embed_image(image_path)
        return result if result else None

    # ------------------------------------------------------------------
    # 多模态嵌入
    # ------------------------------------------------------------------

    def embed_mixed(self, items: List[Dict[str, str]]) -> Optional[List[float]]:
        """混合模态向量化

        Args:
            items: 模态列表，每项为 {'text': '...'} 或 {'image': 'base64_str'}

        Returns:
            向量列表，失败返回 None
        """
        result = self._deploy.embed_mixed(items)
        return result if result else None

    def embed_document_chunk(self, text: str, image_paths: Optional[List[str]] = None) -> Optional[List[float]]:
        """文档块向量化：文本 + 关联图片一起编码（图片直接传递本地路径）

        Args:
            text: 文档块文本
            image_paths: 关联的图片路径列表

        Returns:
            向量列表，失败返回 None
        """
        items = [{"text": text}]
        if image_paths:
            for path in image_paths:
                if os.path.exists(path):
                    items.append({"image": path})
                    WorkLogger.info(f"[MultiModalEmbedding] 添加图片路径: {path}")
                else:
                    WorkLogger.warn(f"[MultiModalEmbedding] 图片不存在，跳过: {path}")
        result = self._deploy.embed_mixed(items)
        return result if result else None

    # ------------------------------------------------------------------
    # 批量嵌入
    # ------------------------------------------------------------------

    def embed_batch(
        self,
        items_list: List[List[Dict[str, str]]],
        batch_size: int = 4,
    ) -> List[Optional[List[float]]]:
        """批量向量化，控制API调用频率

        Args:
            items_list: 每项是一个模态列表（同 embed_mixed 的参数）
            batch_size: 每批处理数量

        Returns:
            向量列表的列表，与 items_list 一一对应
        """
        import time

        results = []
        for i in range(0, len(items_list), batch_size):
            batch = items_list[i : i + batch_size]
            for items in batch:
                vec = self._deploy.embed_mixed(items)
                results.append(vec if vec else None)
            if i + batch_size < len(items_list):
                time.sleep(0.1)
        return results