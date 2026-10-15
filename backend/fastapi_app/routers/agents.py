# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : agents.py
# @Desc    : agents
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Agent 管理 API 路由（仅保留 /agents/{agent_id}/config 调试端点）

注意：/api/agents 和 /api/agents/{agent_id}/context 已在 agent_messages.py 中实现，
此处不再重复注册，避免路由冲突导致 FastAPI 先注册的占位路由生效。
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/agents/{agent_id}/config", summary="读取 Agent 配置（调试用）")
async def get_agent_config(agent_id: str):
    """Phase 2 实现。"""
    return {"status": "not_implemented", "message": "Phase 2 实现", "agent_id": agent_id}
