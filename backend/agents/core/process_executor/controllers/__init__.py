# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : __init__.py
# @Desc    : 流程控制器模块导出
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程控制器模块

通过 Mixin 模式组合基础功能：
- ProcessControllerBase:    初始化、状态遍历、基础推进、回调通知
- ProcessControllerLoop:    循环管理（多平行循环）
- ProcessControllerResult:  结果记录、查询、汇总
- ProcessControllerProgress: 进度计算、状态查询
- ProcessControllerControl:  条件评估、跳转、暂停、重试

ProcessController 为最终组合类，提供完整的流程控制功能。
"""

from .base import ProcessControllerBase
from .loop import ProcessControllerLoop
from .result import ProcessControllerResult
from .progress import ProcessControllerProgress
from .control import ProcessControllerControl


class ProcessController(ProcessControllerControl):
    """通用多层嵌套流程控制器

    由多个 Mixin 模块组合而成，提供完整的流程控制功能：
    - ProcessControllerBase: 初始化、状态遍历、基础推进
    - ProcessControllerLoop: 循环管理
    - ProcessControllerResult: 结果管理
    - ProcessControllerProgress: 进度查询
    - ProcessControllerControl: 流程控制（条件、跳转、重试等）
    """
    pass


__all__ = [
    "ProcessController",
    "ProcessControllerBase",
    "ProcessControllerLoop",
    "ProcessControllerResult",
    "ProcessControllerProgress",
    "ProcessControllerControl",
]
