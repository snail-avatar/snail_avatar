# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 模块初始化文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""
工具集模块

统一导出所有核心工具：
- routing: Agent路由调度器
- embedding: 向量化工具
- LLM_tools: LLM辅助工具
"""

from .routing import AgentRouter, get_agent_router
from .embedding import MultiModalEmbedding, VectorStore, DocumentProcessor
from .LLM_tools import get_summarizer, get_llm_router
