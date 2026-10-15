# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 模块初始化文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""
通用工具模块（common）

提供与具体领域无关的纯通用工具：
- memory_db: 数据库依赖注入
- value_formatter: 值类型检测与格式化
- db_data_helper: 数据库数据提取
- pass_flag_utils: 达标标识通用工具
"""

from .memory_db import set_memory_db, get_memory_db
from .value_formatter import (
    detect_value_type,
    format_value_for_display,
    extract_time_series_stats,
)
from .db_data_helper import (
    collect_vehicles,
    get_sheet_data,
    read_param_by_db_key,
)
from .pass_flag_utils import (
    is_pass_value,
    value_is_empty_or_nan,
    count_pass_flags,
)

__all__ = [
    # memory_db
    "set_memory_db",
    "get_memory_db",
    # value_formatter
    "detect_value_type",
    "format_value_for_display",
    "extract_time_series_stats",
    # db_data_helper
    "collect_vehicles",
    "get_sheet_data",
    "read_param_by_db_key",
    # pass_flag_utils
    "is_pass_value",
    "value_is_empty_or_nan",
    "count_pass_flags",
]