# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : chat.py
# @Desc    : chat
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
聊天 API 路由（Phase 3 实现）

三个端点：
  POST /api/chat                — 同步聊天（非流式）
  GET  /api/chat/stream         — SSE 流式聊天（阶段事件）
  GET  /api/agents/{agent_id}/history  — 读取 Agent 对话历史

SSE 事件格式：
  data: {"type": "routing", "content": "...", "agent_id": "router"}
  data: {"type": "tool_call", "content": "...", "agent_id": "xxx"}
  data: {"type": "tool_result", "content": "...", "agent_id": "xxx"}
  data: {"type": "agent_response", "content": "...", "agent_id": "xxx"}
  data: {"type": "final", "response": "...", "usage": {...}, "agent_id": "...", "structured_data": ...}
  data: {"type": "done"}
"""
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..dependencies import get_main_agent, get_agent_router
from ..services.chat_service import send_chat_message, send_chat_message_stream

router = APIRouter()


# =========================================================================
# 聊天配置 / 模型信息
# =========================================================================

@router.get("/chat/info", summary="获取聊天配置（模型名等）")
async def get_chat_info():
    """返回 main_agent 使用的 LLM 模型名称。

    从 deploy._llm_instances 缓存里取 main_agent 对应的 LLMDeploy 实例的 model_name。
    如果缓存里还没有（服务启动后用户还没发过消息），返回 YAML fallback 值。
    """
    try:
        from snail_avatar.backend.llm.deploy import _llm_instances
        model_name = "qwen3.5-plus"  # fallback（main_agent YAML 里配置的模型名）
        llm = _llm_instances.get("main_agent")
        if llm and hasattr(llm, 'model_name'):
            model_name = llm.model_name
        return {"ok": True, "model_name": model_name}
    except Exception as e:
        return {"ok": False, "model_name": "unknown", "error": str(e)}


# =========================================================================
# 请求模型
# =========================================================================

class ChatRequest(BaseModel):
    message: str = Field("", description="用户消息（纯文字可留空，纯图片发送时空message必须带images）")
    context_prefix: str = Field("", description="上下文前缀（可选）")
    reset_history: bool = Field(False, description="发送前是否清空历史")
    images: List[str] = Field(default_factory=list, description="用户上传的图片base64列表（可选）")


# =========================================================================
# 端点实现
# =========================================================================

@router.post("/chat", summary="发送聊天消息（同步非流式）")
async def chat_sync(
    req: ChatRequest,
    main_agent=Depends(get_main_agent),
):
    """
    同步聊天接口。内部用 asyncio.to_thread 包装 MainAgent.send_message（阻塞调用）。
    返回完整响应 + usage_info + 最终回答的 agent_id。
    """
    if req.reset_history:
        main_agent.clear_history()

    result = await asyncio.to_thread(
        send_chat_message, main_agent, req.message, req.context_prefix, req.images
    )
    return result


@router.post("/chat/stream", summary="发送聊天消息（SSE 事件流）")
async def chat_stream(
    req: ChatRequest,
    main_agent=Depends(get_main_agent),
):
    """
    SSE 流式聊天接口。事件流包括：路由决策 → 工具调用 → 工具结果 → 最终回复 → done。

    使用 POST + JSON body 接收消息（支持图片 base64），返回 SSE 事件流。
    前端使用 fetch() + ReadableStream 消费。
    注意：这是**阶段事件流式**（AgentMessageLogger 队列消费），不是 token 级流式。
    """
    # 校验：消息和图片不能同时为空
    if not req.message.strip() and not req.images:
        return {"error": "消息内容和图片不能同时为空"}

    if req.reset_history:
        main_agent.clear_history()

    async def _event_generator():
        async for event in send_chat_message_stream(main_agent, req.message, req.context_prefix, req.images):
            yield event

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.get("/agents/{agent_id}/history", summary="读取 Agent 对话历史")
async def get_history(
    agent_id: str,
    agent_router=Depends(get_agent_router),
    main_agent=Depends(get_main_agent),
):
    """
    读取指定 Agent 的对话历史。
    特殊 agent_id：main_agent 读取 MainAgent 的历史。
    """
    # 特殊：main_agent 从单例直接取
    if agent_id == "main_agent":
        agent = main_agent
    else:
        agent = agent_router.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    conversation = getattr(agent, "conversation", None)
    if conversation is None:
        return {"agent_id": agent_id, "history": [], "message": "该 Agent 没有 conversation 属性"}

    history = conversation.get_history()
    # 转为 JSON 可序列化格式
    formatted = []
    for msg in history:
        formatted.append({
            "role": getattr(msg, "role", "unknown"),
            "content": getattr(msg, "content", str(msg)),
        })

    return {
        "agent_id": agent_id,
        "message_count": len(formatted),
        "history": formatted,
    }
