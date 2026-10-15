# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : work_log_bridge.py
# @Desc    : work_log_bridge
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
工作日志 Bridge — 从 WorkLogger queue.Queue 消费日志，存到 FastAPI 层的 list

Flet 原版架构：WorkLogger 单例 + queue.Queue（只能消费一次）
FastAPI 层改造：后台线程定时消费 → 存到 LOG_HISTORY（最多 500 条环形缓冲）

Vue 前端通过 GET /api/work-logs 轮询（0.5s 一次）获取所有历史日志。

⚠️ 不修改 snail_avatar 目录下的业务代码，只在 fastapi_app 层做桥接。
"""
import queue
import threading
from collections import deque

from snail_avatar.backend.core.work_log import WorkLogger

# 环形缓冲区：最多保留 500 条日志
MAX_LOGS = 500
LOG_HISTORY = deque(maxlen=MAX_LOGS)
_lock = threading.Lock()
_consumer_started = False


def _start_consumer():
    """后台线程：每 300ms 从 WorkLogger queue 消费日志"""
    global _consumer_started
    with _lock:
        if _consumer_started:
            return
        _consumer_started = True

    def _loop():
        import time
        from snail_avatar.backend.core.work_log import WorkLogger
        while True:
            try:
                q = WorkLogger.get_queue()
                if q is None:
                    # 懒触发：第一次调用 info() 会自动建 queue
                    WorkLogger.info("[WorkLogBridge] consumer 启动")
                    q = WorkLogger.get_queue()
                    if q is None:
                        time.sleep(0.3)
                        continue
                while True:
                    msg = q.get_nowait()
                    LOG_HISTORY.append(msg)
            except queue.Empty:
                pass
            except Exception:
                pass
            time.sleep(0.3)

    t = threading.Thread(target=_loop, daemon=True, name="WorkLogConsumer")
    t.start()


def get_all_logs() -> list:
    """返回所有历史日志（list[str]）"""
    _start_consumer()
    with _lock:
        return list(LOG_HISTORY)


def clear_logs() -> int:
    """清空所有日志，返回清空条数"""
    _start_consumer()
    with _lock:
        n = len(LOG_HISTORY)
        LOG_HISTORY.clear()
        # 同时清空 WorkLogger 原始队列
        q = WorkLogger.get_queue()
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass
        return n


def parse_log_line(line: str) -> dict:
    """
    解析 Flet 原版日志行格式：[2026-09-29 10:30:45] [INFO] 消息内容

    Returns: {"timestamp": "...", "level": "INFO|WARN|ERROR", "message": "..."}
    """
    import re
    m = re.match(r'^\[([^\]]+)\]\s*\[(\w+)\]\s*(.*)', line)
    if m:
        return {
            "timestamp": m.group(1),
            "level": m.group(2).upper(),
            "message": m.group(3),
        }
    # 格式不匹配就整个当 message
    return {"timestamp": "", "level": "INFO", "message": line}
