# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : agent_msg_bridge.py
# @Desc    : agent_msg_bridge
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Agent Message Bridge — AgentMessageLogger queue.Queue → FastAPI list

与 work_log_bridge.py 模式完全一致：后台 daemon 线程消费 queue → deque(maxlen=1000)

⚠️ 不修改 snail_avatar 目录下的业务代码，只在 fastapi_app 层做桥接。
"""
import queue
import threading
from collections import deque

from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger, AgentMessage

MAX_MSG = 1000
MSG_HISTORY = deque(maxlen=MAX_MSG)
_lock = threading.Lock()
_consumer_started = False


def _start_consumer():
    global _consumer_started
    with _lock:
        if _consumer_started:
            return
        _consumer_started = True

    def _loop():
        import time
        q = AgentMessageLogger.get_queue()
        while True:
            try:
                while True:
                    msg = q.get_nowait()
                    if isinstance(msg, AgentMessage):
                        MSG_HISTORY.append(msg)
            except queue.Empty:
                pass
            time.sleep(0.3)

    t = threading.Thread(target=_loop, daemon=True, name="AgentMsgConsumer")
    t.start()


def msg_to_dict(msg: AgentMessage) -> dict:
    """AgentMessage dataclass → 可 JSON 序列化的 dict"""
    return {
        "timestamp": msg.timestamp.strftime("%H:%M:%S.%f")[:-3],
        "agent_id": msg.agent_id,
        "message_type": msg.message_type,
        "content": msg.content,
        "extra": msg.extra if isinstance(msg.extra, dict) else {},
    }


def get_all_messages() -> list:
    """返回所有历史消息（list[dict]）"""
    _start_consumer()
    with _lock:
        return [msg_to_dict(m) for m in MSG_HISTORY]


def clear_messages() -> int:
    """清空，返回清空条数"""
    _start_consumer()
    with _lock:
        n = len(MSG_HISTORY)
        MSG_HISTORY.clear()
        AgentMessageLogger.clear()
        return n
