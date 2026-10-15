# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : agent_messages.py
# @Desc    : agent_messages
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Agent 消息 & 上下文 API

四个端点：
  GET  /api/agent-messages          — 获取所有历史 AgentMessage（Tab1 轮询）
  POST /api/agent-messages/clear    — 清空
  GET  /api/agents                  — 列出所有已实例化 Agent
  GET  /api/agents/{agent_id}/context — 获取 Agent 上下文（system_prompt + summary + history）
"""
from fastapi import APIRouter, HTTPException

from ..dependencies import get_agent_router
from ..services.agent_msg_bridge import get_all_messages, clear_messages, MSG_HISTORY

router = APIRouter()


@router.get("/agent-messages", summary="获取 Agent 交互消息流")
async def list_agent_messages():
    return {"ok": True, "total": len(MSG_HISTORY), "messages": get_all_messages()}


@router.post("/agent-messages/clear", summary="清空 Agent 消息")
async def clear_agent_messages():
    n = clear_messages()
    return {"ok": True, "cleared": n}


@router.get("/agents", summary="列出所有已实例化 Agent")
async def list_agents():
    try:
        router = get_agent_router()
        agent_ids = router.get_all_agent_ids()
        agents = []
        for aid in agent_ids:
            agent = router.get_agent(aid)
            if agent is not None:
                name = getattr(agent, "AGENT_NAME", aid)
                agents.append({"agent_id": aid, "agent_name": name})
        return {"ok": True, "agents": agents}
    except Exception as e:
        return {"ok": False, "agents": [], "error": str(e)}


@router.get("/agents/{agent_id}/context", summary="获取 Agent 上下文")
async def get_agent_context(agent_id: str):
    try:
        router = get_agent_router()
        agent = router.get_agent(agent_id)
        if agent is None:
            return {"ok": False, "error": f"Agent [{agent_id}] 尚未实例化"}

        agent_name = getattr(agent, "AGENT_NAME", agent_id)

        # 1. system_prompt
        system_prompt = getattr(agent, "_system_prompt", "") or ""

        # 2. summary
        conversation = getattr(agent, "conversation", None)
        summary = ""
        history = []
        if conversation is not None:
            summary = getattr(conversation, "_summary", "") or ""
            history = getattr(conversation, "history", []) or []

        # 3. history — 转可序列化 list
        try:
            history_serializable = [dict(msg) for msg in history] if history else []
        except Exception:
            history_serializable = []

        return {
            "ok": True,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "system_prompt": system_prompt,
            "summary": summary,
            "history": history_serializable,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
