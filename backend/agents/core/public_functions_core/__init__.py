# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 跨 Agent 共享公共模块：public_functions_core
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享公共模块：public_functions_core

这是一个按功能领域划分的多层级公共工具集合：

  ┌────────────────────────────────────────────┐
  │  common/  - 纯通用工具（与领域无关）         │
  │    - memory_db.py: 数据库依赖注入          │
  │    - db_data_helper.py: 从 memory_db 提取数据│
  │    - pass_flag_utils.py: 达标标识通用函数   │
  │    - value_formatter.py: 值格式化          │
  └────────────────────────────────────────────┘
  ┌────────────────────────────────────────────┐
  │  knowledge/  - 知识库搜索函数模板            │
  │    - base_search_function.py: 通用搜索基类 │
  │    - search_vector_template.py: 向量检索   │
  │    - search_cases_template.py: 案例搜索   │
  │    - search_kg_template.py: 知识图谱搜索  │
  │    - search_rules_template.py: 规则搜索   │
  └────────────────────────────────────────────┘
  ┌────────────────────────────────────────────┐
  │  workflow/  - 工作流相关工具和模板          │
  │    - workflow_discovery.py: YAML 发现      │
  │    - workflow_access.py: 工作流实例上下文  │
  │    - node_query_helper.py: 节点查询        │
  │    - panel_workflow_helper.py: 面板辅助    │
  │    - templates/: 抽象 FunctionBase 模板    │
  └────────────────────────────────────────────┘
  ┌────────────────────────────────────────────┐
  │  vts/  - VTS/SSTS 专属工具                 │
  │    - vts_calc_helper.py: VTS 计算入口      │
  │    - pass_flag_calculator.py: 达标重算     │
  └────────────────────────────────────────────┘

典型用法（纯通用工具）：
    from snail_avatar.backend.agents.core.public_functions_core.common import get_memory_db, set_memory_db

典型用法（工作流模板）：
    from snail_avatar.backend.agents.core.public_functions_core.workflow.templates import AbstractRunFullCalculationFunction

    class RunCalculationFunction(AbstractRunFullCalculationFunction):
        name = "run_calculation"
        description = "执行完整计算"
        tool_title = "完整计算"

典型用法（VTS 专属）：
    from snail_avatar.backend.agents.core.public_functions_core.vts import ensure_pass_flags_calculated, run_vts_calculation
"""

from .common import (
    set_memory_db,
    get_memory_db,
)
from .vts import (
    ensure_pass_flags_calculated,
    run_vts_calculation,
    count_vts_nan_params,
)

__all__ = [
    # common
    "set_memory_db",
    "get_memory_db",
    # vts
    "ensure_pass_flags_calculated",
    "run_vts_calculation",
    "count_vts_nan_params",
]