# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
三核架构验证模块

【职责拆分】
1. excel_operator.py - Excel操作类，纯文件IO
2. data_parser.py - 数据解析类，纯格式转换
3. memory_database.py - 内存数据库类，纯数据管理
4. test_ui.py - 最小验证UI程序
"""

from .excel_operator import ExcelOperator
from .data_parser import DataParser
from .memory_database import MemoryDatabase

__all__ = ["ExcelOperator", "DataParser", "MemoryDatabase"]
