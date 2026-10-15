# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Core 层包初始化文件

此模块包含项目核心组件（非计算引擎框架部分），包括：
- 内存数据库管理
- 配置管理
- 通用工具函数
- 数据解析器

注意：计算引擎基类已移动到 engine/core/
使用方法：
    from snail_avatar.engine import CalculationNode, WorkflowGraph
    from snail_avatar.core import memory_database, config
"""

from .memory import memory_database
from . import config

__all__ = ['memory_database', 'config']
