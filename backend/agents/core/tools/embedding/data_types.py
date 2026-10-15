# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : data_types.py
# @Desc    : data_types
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""文档块数据结构"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DocumentChunk:
    """文档块数据结构"""
    chunk_id: str = ""
    text: str = ""
    images: List[str] = field(default_factory=list)  # 图片base64列表
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """检索结果"""
    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)