# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 结果格式整理器模块入口
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

from .result_formatter import ResultFormatter

_formatter_instance = None


def get_result_formatter() -> ResultFormatter:
    """获取结果格式整理器单例
    
    对外 API：调用方可以用 `from snail_avatar.backend.agents.core.tools.LLM_tools import get_result_formatter` 正常使用。
    """
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = ResultFormatter()
    return _formatter_instance