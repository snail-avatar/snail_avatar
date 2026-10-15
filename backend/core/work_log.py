# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : work_log.py
# @Desc    : 日志基础设施
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
工作流日志基础设施

提供统一的日志队列管理，支持跨模块日志记录。
- agents/base/ 中的计算节点和工作流可以记录日志
- ui/panels/ 中的日志面板消费日志

使用方式：
    from snail_avatar.backend.core.work_log import WorkLogger

    # 添加日志
    WorkLogger.add_log("计算开始", "INFO")

    # 获取队列（供 UI 层使用）
    queue = WorkLogger.get_queue()
"""

import queue
import datetime


class WorkLogger:
    """
    工作日志记录器（单例模式）

    提供全局日志队列管理，支持跨层级日志记录。
    日志级别：INFO, WARN, ERROR
    """
    _instance = None
    _log_queue = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._log_queue = queue.Queue()
        return cls._instance

    @classmethod
    def get_queue(cls) -> queue.Queue:
        """获取日志队列实例"""
        return cls._log_queue

    @classmethod
    def add_log(cls, message: str, level: str = "INFO") -> None:
        """
        添加日志到队列

        Args:
            message: 日志消息
            level: 日志级别 (INFO, WARN, ERROR)
        """
        if cls._log_queue is None:
            cls._log_queue = queue.Queue()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}"
        cls._log_queue.put(formatted_message)

    @classmethod
    def info(cls, message: str) -> None:
        """添加 INFO 级别日志"""
        cls.add_log(message, "INFO")

    @classmethod
    def warn(cls, message: str) -> None:
        """添加 WARN 级别日志"""
        cls.add_log(message, "WARN")

    @classmethod
    def error(cls, message: str) -> None:
        """添加 ERROR 级别日志"""
        cls.add_log(message, "ERROR")

    @classmethod
    def reset(cls) -> None:
        """重置日志系统"""
        if cls._log_queue is not None:
            while not cls._log_queue.empty():
                try:
                    cls._log_queue.get_nowait()
                except queue.Empty:
                    break
