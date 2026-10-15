# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : main.py
# @Desc    : main
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Snail Avatar FastAPI 后端

入口模块，负责：
1. sys.path 配置（确保 snail_avatar 包可被正确 import）
2. FastAPI app 创建
3. 单例初始化（lifespan 事件）
4. 路由注册

启动方式:
  uvicorn fastapi_app.main:app --reload --host 0.0.0.0 --port 8000

访问:
  Swagger UI: http://localhost:8000/docs
  ReDoc:      http://localhost:8000/redoc
"""

import sys
from pathlib import Path

# ==========================================================================
# sys.path 配置
# ==========================================================================
# 关键原则：只保留 d:\AI_model 一个路径，绝对禁止同时注册 d:\AI_model\snail_avatar
# 原因：snail_avatar 包内的模块大量使用相对 import（from .calc_nodes_base import），
#       如果两条路径同时存在，同一个 Python 文件会被 importlib 当成两个独立模块加载，
#       导致 issubclass(A, B) 返回 False（A 继承自 calc_nodes_base.CalculationNode，
#       B 继承自 snail_avatar.calc_nodes_base.CalculationNode，虽然源码相同但是不同对象）。
#
# 正确的 import 方式：
#   - from snail_avatar.backend.core.memory import MemoryDatabase  ✅
#   - from snail_avatar.backend.fastapi_app.main import app         ✅
#   - import fastapi_app                                    ❌（不再直接可用）
# ==========================================================================
_PROJECT_ROOT = Path(__file__).parent.parent  # d:\AI_model\snail_avatar
_PARENT_DIR = _PROJECT_ROOT.parent  # d:\AI_model

# 只加入 d:\AI_model，snail_avatar 作为子包被发现
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

# 清理可能残留的 snail_avatar 路径（避免双重加载）
if str(_PROJECT_ROOT) in sys.path:
    sys.path.remove(str(_PROJECT_ROOT))

# ==========================================================================
# FastAPI app 创建
# ==========================================================================
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器

    启动时：
      - 初始化全局单例（MemoryDatabase, AgentRouter 等）
      - 再次注册 access_log filter（覆盖 uvicorn 晚初始化的 logger）
    关闭时：清理资源
    """
    print("[FastAPI] ⏳ 启动中...")

    # 再次确保 access_log filter 注册（uvicorn.access logger 可能在 import 之后才创建）
    _install_access_log_filter()

    # 将单例注入 app.state，便于后续通过 request.app.state 访问
    from snail_avatar.backend.fastapi_app.dependencies import (
        get_memory_database,
        get_agent_router,
    )

    app.state.memory_db = get_memory_database()
    app.state.agent_router = get_agent_router()

    print("[FastAPI] ✅ 启动完成，单例已初始化")
    yield

    print("[FastAPI] 👋 关闭中...")
    # TODO: 如有需要，在此清理资源


app = FastAPI(
    title="Snail Avatar API",
    description="新能源汽车性能开发助手后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

# ==========================================================================
# CORS 中间件（允许 Vue 前端跨域访问）
# ==========================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（局域网其他设备通过 IP 访问）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================================
# Health Check（根路由，确认服务可用）
# ==========================================================================
@app.get("/api/health", tags=["系统"])
async def health_check():
    """健康检查端点"""
    import sys as _sys
    return {
        "status": "ok",
        "service": "snail-avatar-api",
        "python_version": _sys.version,
        "sys_path_root": str(_PARENT_DIR),
    }


# ==========================================================================
# 注册路由
# ==========================================================================
# Phase 1: 先注册占位路由（返回 501 Not Implemented）
# Phase 2+: 逐步实现各路由的实际业务逻辑
from snail_avatar.backend.fastapi_app.routers import chat, agents, vehicles, workflows, process, knowledge, work_logs, agent_messages, memory_dbs, file_ops, expert_panels

app.include_router(chat.router,        prefix="/api", tags=["聊天"])
app.include_router(agents.router,      prefix="/api", tags=["Agent"])
app.include_router(vehicles.router,    prefix="/api", tags=["车辆数据"])
app.include_router(workflows.router,   prefix="/api", tags=["Workflow"])
app.include_router(process.router,     prefix="/api", tags=["流程编排"])
app.include_router(knowledge.router,   prefix="/api", tags=["知识检索"])
app.include_router(work_logs.router,   prefix="/api", tags=["工作日志"])
app.include_router(agent_messages.router, prefix="/api", tags=["Agent消息"])
app.include_router(memory_dbs.router,    prefix="/api", tags=["内存数据库"])
app.include_router(file_ops.router,      prefix="/api", tags=["文件操作"])
app.include_router(expert_panels.router,  tags=["专家面板"])


# ==========================================================================
# 开发入口（python -m fastapi_app.main）
# ==========================================================================
# ==========================================================================
# uvicorn access_log 过滤器 — 静默高频轮询接口，避免控制台刷屏
#
# 策略：直接在 uvicorn.run() 调用时传 access_log=False + 用
#       log_config 完全接管日志格式和过滤
#       （filter 加在 logger 上有时候 handler 绑死了 logger 不生效）
# ==========================================================================
import logging as _logging

# 需要静默的高频轮询 URL 前缀
#   /api/work-logs  — 前端 chatpanel 每 0.5s 轮询
#   /api/files/status — 前端每 5s 轮询
IGNORED_ACCESS_PATHS = frozenset({"/api/files/status", "/api/work-logs"})

class _AccessLogFilter(_logging.Filter):
    """拦截匹配 IGNORED_ACCESS_PATHS 的 access log 记录"""
    def filter(self, record: _logging.LogRecord) -> bool:
        msg = record.getMessage()
        for prefix in IGNORED_ACCESS_PATHS:
            if f'"{prefix}' in msg:
                return False
        return True

def _install_access_log_filter():
    """彻底静默 uvicorn.access 的 INFO 日志（高频轮询刷屏源头）

    两个手段：
    1. 把 uvicorn.access logger level 设为 WARNING（INFO 级别的 access log 直接丢弃）
    2. 给 handler 也加 filter（双重保险，保留非轮询的 ERROR 级别日志）
    """
    target_names = ("uvicorn.access",)
    for logger_name in target_names:
        logger = _logging.getLogger(logger_name)
        # 暴力手段：uvicorn.access 只输出 WARNING 及以上级别
        logger.setLevel(_logging.WARNING)
        # 给所有现有 handler 加 filter（万一 handler 自己有更细的级别配置）
        filt = _AccessLogFilter()
        for h in logger.handlers:
            h.addFilter(filt)
        # 也给 logger 本身加 filter（覆盖未来新增 handler）
        logger.addFilter(filt)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "fastapi_app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
