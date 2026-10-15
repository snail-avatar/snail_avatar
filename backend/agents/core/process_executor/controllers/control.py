# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : controller_control.py
# @Desc    : 流程控制器流程控制模块 - 条件评估、沙箱管理
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程控制器流程控制模块

提供 ProcessController 的流程控制扩展功能：
1. 条件表达式评估
2. 沙箱实例管理
"""

from __future__ import annotations

import ast
from typing import Any, Dict

from ..process_sandbox import ProcessSandbox
from .progress import ProcessControllerProgress


class ProcessControllerControl(ProcessControllerProgress):
    """流程控制器流程控制扩展"""

    def evaluate_condition(self, condition: str, step_result: Dict) -> bool:
        """计算条件表达式（安全方式）

        Args:
            condition: 条件表达式，如 "score > 80"
            step_result: 步骤结果字典

        Returns:
            bool: 条件是否满足
        """
        if not condition:
            return True

        try:
            expr = condition
            for key, value in step_result.items():
                expr = expr.replace(key, repr(value))

            return ast.literal_eval(expr)
        except Exception:
            return True

    def get_sandbox(self) -> ProcessSandbox:
        """获取沙箱实例"""
        return self._sandbox
