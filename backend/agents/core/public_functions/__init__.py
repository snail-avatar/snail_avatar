# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : Public Functions 公共函数注册中心
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Functions 公共函数注册中心

提供跨Agent、跨Step共享的公共函数注册与发现机制。
所有public function以 "{三位数字前缀}_pubfn_{名称}.py" 命名，放在此目录下。

命名规范（详见 readme.txt）:
- 0xx_pubfn_xxx.py  Agent资源与基础工具类（如计算器、子Agent列表）
- 1xx_pubfn_xxx.py  数据读取类（如VTS/SSTS数据读取、产品数据读取）
- 2xx_pubfn_xxx.py  数据转换与格式化类（如沙箱数据提取、VTS数据格式化）
- 3xx_pubfn_xxx.py  数据校验与计算类（如SSTS校验、VTS校核计算）

私有函数命名规范:
- a{agent_id}_step{X}_*.py  Step级私有函数（如 a101_step2_5_*.py）
- a{agent_id}_process_*.py  Process级私有函数（如 a101_process_*.py）

使用方式:
    from snail_avatar.backend.agents.core.public_functions import get_public_function
    
    fn = get_public_function("calculator")
    result = fn.execute(args, context)
"""

from __future__ import annotations

import os
import importlib
from typing import Any, Dict, List, Optional, Type

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase


# Public function 注册表（模块级缓存）
_public_function_registry: Optional[Dict[str, Type[FunctionBase]]] = None


def _scan_public_functions() -> Dict[str, Type[FunctionBase]]:
    """扫描并加载所有 public function
    
    自动扫描当前目录下的以下文件：
    1. {三位数字前缀}_pubfn_*.py （公共函数）
    2. a{agent_id}_step{X}_*.py （私有函数，如 a101_step1_*.py）
    3. a{agent_id}_process_*.py （process 级函数，如 a101_process_*.py）
    
    找到其中继承自 FunctionBase 的子类并注册。
    """
    registry: Dict[str, Type[FunctionBase]] = {}
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    for filename in sorted(os.listdir(current_dir)):
        if not filename.endswith('.py'):
            continue
        if filename.startswith('__'):
            continue
        
        # 支持三种命名模式：
        # 1. 公共函数：包含 "pubfn" 字样
        # 2. 私有函数：以 "a" 开头，包含 "step" 字样（如 a101_step1_*.py）
        # 3. process 级函数：以 "a" 开头，包含 "process" 字样（如 a101_process_*.py）
        is_pubfn = 'pubfn' in filename
        is_private_fn = filename.startswith('a') and 'step' in filename
        is_process_fn = filename.startswith('a') and 'process' in filename
        
        if not is_pubfn and not is_private_fn and not is_process_fn:
            continue
        
        module_name = filename[:-3]  # 去掉 .py
        full_module_name = f"snail_avatar.backend.agents.core.public_functions.{module_name}"
        
        try:
            module = importlib.import_module(full_module_name)
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) 
                    and issubclass(attr, FunctionBase) 
                    and attr is not FunctionBase
                    and hasattr(attr, 'name')
                    and attr.name):
                    registry[attr.name] = attr
        except Exception:
            pass
    
    return registry


def _ensure_registry() -> Dict[str, Type[FunctionBase]]:
    """确保注册表已加载（懒加载单例模式）"""
    global _public_function_registry
    if _public_function_registry is None:
        _public_function_registry = _scan_public_functions()
    return _public_function_registry


def get_public_function(name: str) -> Optional[Type[FunctionBase]]:
    """根据名称获取 public function 类
    
    Args:
        name: 函数名称（如 "calculator", "list_all_sub_agents"）
    
    Returns:
        FunctionBase 子类，未找到返回 None
    """
    registry = _ensure_registry()
    return registry.get(name)


def get_all_public_functions() -> Dict[str, Type[FunctionBase]]:
    """获取所有已注册的 public function
    
    Returns:
        dict: {function_name: FunctionClass, ...}
    """
    return _ensure_registry()


def get_public_function_schemas(names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """获取指定 public function 的 function calling schema 列表
    
    Args:
        names: 函数名称列表，None 表示获取全部
    
    Returns:
        list: function schema 列表
    """
    registry = _ensure_registry()
    
    if names is None:
        names = list(registry.keys())
    
    schemas = []
    for name in names:
        fn_cls = registry.get(name)
        if fn_cls and hasattr(fn_cls, 'get_schema'):
            schemas.append(fn_cls.get_schema())
    
    return schemas


def reload_public_functions() -> Dict[str, Type[FunctionBase]]:
    """强制重新扫描加载所有 public function（调试用）"""
    global _public_function_registry
    _public_function_registry = None
    return _ensure_registry()


__all__ = [
    'get_public_function',
    'get_all_public_functions',
    'get_public_function_schemas',
    'reload_public_functions',
]
