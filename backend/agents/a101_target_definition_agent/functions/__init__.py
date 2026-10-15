# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : TargetDefinitionAgent - function calling 工具集合
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
TargetDefinitionAgent - function calling 工具集合

自动扫描本目录下所有 function_*.py 文件，并将其中的 ALL_FUNCTIONS 注册到
FunctionRegistry。新增 function 时只需在本目录新建 function_xxx.py 并定义
ALL_FUNCTIONS = [XxxFunction]，无需修改本文件。

使用示例:
    from snail_avatar.backend.agents.a101_target_definition_agent.functions import (
        create_default_registry,
        discover_functions,
    )

    registry = create_default_registry()
    tools = registry.get_tools_list()      # 传给 LLM
    result = registry.execute("run_target_definition_flow", {"vehicle_name": "reevlto"})
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import List, Type

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase, FunctionRegistry


__all__ = [
    "FunctionBase",
    "FunctionRegistry",
    "create_default_registry",
    "discover_functions",
]


# ==========================================================================
# 自动扫描：收集所有 function_*.py 中的 Function 类
# ==========================================================================

def discover_functions() -> List[Type[FunctionBase]]:
    """自动扫描当前包内的 function_*.py 模块，收集其中 ALL_FUNCTIONS 声明的类

    说明:
      - 只扫描文件名以 "function_" 开头的 .py 文件
      - 被扫描的模块必须在顶层定义 ALL_FUNCTIONS = [Cls1, Cls2, ...]
      - 以 _ 开头的 helper 模块不会被扫描
    """
    collected: List[Type[FunctionBase]] = []

    package_name = __name__

    for module_info in pkgutil.iter_modules(__path__):
        mod_name = module_info.name
        if not mod_name.startswith("function_"):
            continue
        full_name = f"{package_name}.{mod_name}"
        try:
            mod = importlib.import_module(full_name)
        except Exception as e:
            print(f"[target_definition/functions/__init__] 导入 {full_name} 失败: {e}")
            continue

        funcs = getattr(mod, "ALL_FUNCTIONS", None)
        if not isinstance(funcs, (list, tuple)):
            print(f"[target_definition/functions/__init__] {mod_name} 未定义 ALL_FUNCTIONS，已跳过")
            continue

        for cls in funcs:
            if isinstance(cls, type) and issubclass(cls, FunctionBase):
                collected.append(cls)
            else:
                print(f"[target_definition/functions/__init__] {mod_name} 中存在非 FunctionBase 子类: {cls}")

    return collected


def create_default_registry() -> FunctionRegistry:
    """创建并返回包含所有默认工具的 FunctionRegistry"""
    registry = FunctionRegistry()
    for func_cls in discover_functions():
        registry.register(func_cls)
    return registry
