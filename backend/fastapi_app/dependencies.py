# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : dependencies.py
# @Desc    : dependencies
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
全局单例依赖注入

MemoryDatabase 策略：
  **common/memory_db.py::_memory_db_ref 是全局唯一权威存储槽**。
  本模块的 get_memory_database() / set_memory_database() 完全委托过去。

  写入路径：
    A. FastAPI 路由层 /api/files/open → set_memory_database()
    B. open_project_file 工具（agents/） → set_memory_db()
  读取路径：
    所有路径统一走 get_memory_db()

其他单例（AgentRouter / ConfigManager / MainAgent / ProcessContext）保持 lru_cache。
"""
from functools import lru_cache

# ==========================================================================
# MemoryDatabase — 完全委托给 common/memory_db（唯一权威存储槽）
# ==========================================================================

def get_memory_database():
    """获取全局 MemoryDatabase（委托 common/memory_db 唯一权威槽）"""
    from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
    db = get_memory_db()
    if db is None:
        # 首次启动：新建空实例（兜底，避免 None 导致下游 AttributeError）
        from snail_avatar.backend.core.memory.memory_database import MemoryDatabase
        db = MemoryDatabase()
        set_memory_database(db)
    return db


def set_memory_database(new_instance):
    """Excel 加载后调用：写入唯一权威槽（common/memory_db）"""
    from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import set_memory_db
    set_memory_db(new_instance)


# ==========================================================================
# AgentRouter（Agent 路由调度器）
# ==========================================================================
@lru_cache(maxsize=1)
def get_agent_router():
    """获取 AgentRouter 单例（扫描 agents/*/config/*.yaml 发现所有 Agent）"""
    from snail_avatar.backend.agents.core.tools.routing import get_agent_router as _get_router
    return _get_router()


# ==========================================================================
# ConfigManager（配置文件管理器）
# ==========================================================================
@lru_cache(maxsize=1)
def get_config_manager():
    """获取 ConfigManager 单例（读取 config.ini）"""
    from snail_avatar.backend.core.config import ConfigManager
    return ConfigManager()


# ==========================================================================
# MainAgent（主对话入口 + AgentRouter 调度）
# ==========================================================================
@lru_cache(maxsize=1)
def get_main_agent():
    """获取 MainAgent 单例（LLMConversationAgent + AgentRouter + Function Calling）"""
    from snail_avatar.backend.agents.a000_main_agent.main_agent import MainAgent
    return MainAgent()


# ==========================================================================
# AgentMessageLogger 队列（SSE 事件源）
# ==========================================================================
def get_message_logger_queue():
    """获取 AgentMessageLogger 的内部 queue.Queue，用于 SSE 事件采集"""
    from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger
    return AgentMessageLogger.get_queue()


# ==========================================================================
# ProcessContext（目标值定义流程执行器）
# ==========================================================================
@lru_cache(maxsize=1)
def get_process_context():
    """获取 ProcessContext 单例（target_definition_agent）

    agent_dir 固定指向 a101_target_definition_agent 目录，
    ProcessContext 内部会自动加载 config/process.yaml、初始化 ProcessEngine、
    扫描 config/steps/*.yaml 构建步骤注册表。
    """
    import os
    from snail_avatar.backend.agents.core.process_executor.process_context import ProcessContext

    agent_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "agents", "a101_target_definition_agent",
    )
    memory_db = get_memory_database()
    return ProcessContext(agent_dir=agent_dir, memory_db=memory_db)
