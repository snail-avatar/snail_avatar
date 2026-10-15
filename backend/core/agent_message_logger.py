# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : agent_message_logger.py
# @Desc    : Agent 消息记录器 - 记录多 Agent 之间的交互过程
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Agent 消息记录器 - 单例模式，供 agent_router / 各 Agent 写入内部交互消息

【设计定位】
    chat_service SSE  → 用户看到的"最终答案"（干净）
    本消息记录器      → 内部过程（像调试器单步跟踪：路由决策、上下文传递、工具调用）

【参考设计】与 core/work_log.py WorkLogger 模式完全一致：
    WorkLogger         → 记录计算节点执行日志
    AgentMessageLogger → 记录 Agent 交互过程

使用方式：
    from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger

    # 记录消息
    AgentMessageLogger.log("main_agent", "user_input", "用户消息内容")
    AgentMessageLogger.log("router", "router_decision", "转交给vts_ssts_agent")

    # UI 面板消费
    queue = AgentMessageLogger.get_queue()

消息类型定义：
    - user_input       用户原始输入
    - router_decision   路由器决策（如"匹配到XX关键词，转交给YY"）
    - context_build    上下文拼接内容
    - agent_receive    目标 Agent 接收到消息
    - tool_call        函数/工具调用（如 get_vehicle_spec()）
    - tool_result      工具返回结果
    - agent_response   Agent 最终回复（与 chat_service 最终返回给前端的一致）
    - system           系统消息（如"模型加载完成"）
    - round_separator  轮次分隔线
    - summary_fallback 摘要降级（LLM 调用失败→纯规则摘要）
"""

from dataclasses import dataclass, field
from datetime import datetime
import queue
import threading


@dataclass
class AgentMessage:
    """单条 Agent 消息的结构化数据"""
    timestamp: datetime                          # 消息产生时间
    agent_id: str                               # 产生消息的 agent id
    message_type: str                           # 消息类型（见上方列表）
    content: str                                # 消息正文
    extra: dict = field(default_factory=dict)   # 附加信息（可选）

    def format_for_display(self) -> str:
        """格式化显示：时间戳 + agent_id + 内容"""
        time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        return f"[{time_str}] [{self.agent_id}] {self.content}"


class AgentMessageLogger:
    """
    Agent 消息记录器（单例模式）

    提供全局消息队列管理，支持跨模块记录。
    - agent_router 在这里记录路由决策和上下文传递
    - 各 Agent 在这里记录接收、调用工具和回复过程
    - 右侧面板 AgentMessagePanel 在这里消费并显示

    设计约束：
    - 队列有最大长度（默认 1000），超出时丢弃最老消息
    - 所有写入/读取操作线程安全（通过 threading.Lock）
    """

    _instance = None
    _queue = queue.Queue(maxsize=1000)          # 最多保留 1000 条，避免内存膨胀
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def log(cls, agent_id: str, message_type: str, content: str, **extra) -> None:
        """
        记录一条消息 - 线程安全

        Args:
            agent_id:    产生消息的 Agent 标识
            message_type: 消息类型（见模块顶部定义）
            content:     消息正文
            **extra:    附加信息字典（可选，存放在 AgentMessage.extra 中）
        """
        msg = AgentMessage(
            timestamp=datetime.now(),
            agent_id=agent_id,
            message_type=message_type,
            content=str(content),
            extra=extra,
        )
        try:
            with cls._lock:
                if cls._queue.full():
                    # 队列已满 → 丢弃最老的一条（保持最近数据）
                    try:
                        cls._queue.get_nowait()
                    except queue.Empty:
                        pass
                cls._queue.put(msg)
        except Exception:
            # 静默失败（日志系统不能影响主流程）
            pass

    @classmethod
    def get_queue(cls) -> queue.Queue:
        """获取消息队列实例（供 UI 面板消费）"""
        return cls._queue

    @classmethod
    def clear(cls) -> None:
        """清空所有消息"""
        with cls._lock:
            cls._queue = queue.Queue(maxsize=1000)

    @classmethod
    def reset(cls) -> None:
        """重置消息系统（别名，与 WorkLogger 接口一致）"""
        cls.clear()
