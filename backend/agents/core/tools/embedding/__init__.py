# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 模块初始化文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""
通用嵌入模块

提供多模态嵌入、向量存储等通用功能，供所有专业Agent复用。
"""

def _lazy_import(module_name, class_name):
    import importlib
    mod = importlib.import_module(module_name)
    return getattr(mod, class_name)


def MultiModalEmbedding(*args, **kwargs):
    cls = _lazy_import("snail_avatar.backend.agents.core.tools.embedding.multi_modal_embedding", "MultiModalEmbedding")
    return cls(*args, **kwargs)


def VectorStore(*args, **kwargs):
    cls = _lazy_import("snail_avatar.backend.agents.core.tools.embedding.vector_store", "VectorStore")
    return cls(*args, **kwargs)


def DocumentProcessor(*args, **kwargs):
    cls = _lazy_import("snail_avatar.backend.agents.core.tools.embedding.document_processor", "DocumentProcessor")
    return cls(*args, **kwargs)
