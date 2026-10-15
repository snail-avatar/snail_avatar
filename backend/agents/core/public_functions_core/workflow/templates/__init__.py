# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 模块初始化文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""
工作流function抽象基类模板
"""

from .run_full_calculation import AbstractRunFullCalculationFunction
from .modify_and_recalculate import AbstractModifyAndRecalculateFunction

__all__ = [
    "AbstractRunFullCalculationFunction",
    "AbstractModifyAndRecalculateFunction",
]

# 其他基类待添加...