# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_exceptions.py
# @Desc    : 步骤执行异常定义
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
步骤执行异常定义

统一管理步骤执行过程中可能出现的各种异常，支持异常的
分类和传递，便于上层代码进行针对性处理（如重试、跳过等）。
"""


class StepExecutionError(Exception):
    """步骤执行错误基类"""
    pass


class NetworkError(StepExecutionError):
    """网络连接错误（可重试）

    当 LLM 调用或 Agent 调用发生网络连接异常时抛出此异常，
    上层代码可捕获此异常并进行自动重试。
    """

    def __init__(self, message: str, error_type: str = "network"):
        super().__init__(message)
        self.error_type = error_type
        self.is_retryable = True
