# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 模块初始化文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""
知识库函数模板包
"""

from .base_search_function import BaseSearchFunction
from .function_templates.search_rules_template import SearchRulesFunctionTemplate
from .function_templates.search_cases_template import SearchCasesFunctionTemplate
from .function_templates.search_kg_template import SearchKnowledgeGraphFunctionTemplate
from .function_templates.search_vector_template import SearchVectorFunctionTemplate, SearchImageFunctionTemplate

__all__ = [
    "BaseSearchFunction",
    "SearchRulesFunctionTemplate",
    "SearchCasesFunctionTemplate",
    "SearchKnowledgeGraphFunctionTemplate",
    "SearchVectorFunctionTemplate",
    "SearchImageFunctionTemplate",
]