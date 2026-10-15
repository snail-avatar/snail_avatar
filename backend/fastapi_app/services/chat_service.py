# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : chat_service.py
# @Desc    : chat_service
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Chat Service — LLM 聊天 + SSE 事件流封装

设计约束（迁移边界）：
  不能改 snail_avatar 目录下的业务代码。
  因此 SSE 不是 token 级流式（LLMDeploy.generate_streaming_response 没被 function calling 循环调用），
  而是**阶段事件流式**：监听 AgentMessageLogger 的 queue.Queue，把路由决策/工具调用/最终回复
  等中间过程作为结构化 SSE 事件发送给前端。

SSE 事件格式：
  data: {"type": "routing", "content": "...", "agent_id": "..."}
  data: {"type": "tool_call", "content": "...", "agent_id": "..."}
  data: {"type": "tool_result", "content": "...", "agent_id": "..."}
  data: {"type": "agent_response", "content": "...", "agent_id": "..."}
  data: {"type": "final", "response": "...", "usage": {...}, "agent_id": "...", "structured_data": ...}
  data: {"type": "error", "message": "..."}
  data: {"type": "done"}
"""

import asyncio
import base64
import json
import os
import queue
import tempfile
import threading
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from snail_avatar.backend.agents.a000_main_agent.main_agent import MainAgent
from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger


# 不需要采集的噪音消息类型
_SKIP_TYPES = {"round_separator", "system"}

# 映射 AgentMessageLogger.message_type → SSE event type
_TYPE_MAP = {
    "user_input": "user_input",
    "router_decision": "routing",
    "context_build": "context",
    "agent_receive": "agent_receive",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "agent_response": "agent_response",
    "flow_progress": "flow_progress",
}


def _queue_size(q: queue.Queue) -> int:
    """线程安全地取 queue size（近似值）"""
    try:
        return q.qsize()
    except NotImplementedError:
        #某些平台 qsize 不支持，用 get_nowait 计数
        return 0


# =========================================================================
# 图片处理辅助函数
# =========================================================================

# 临时文件清理队列 —— 程序退出时由 GC 清理，这里只保存路径列表方便追踪
_TEMP_IMAGE_PATHS: List[str] = []


def _save_images_to_temp(images_base64: List[str]) -> List[str]:
    """把前端传来的 base64 图片保存到本地临时文件，返回文件路径列表

    Args:
        images_base64: base64 编码的图片字符串列表（不含 data: 前缀）

    Returns:
        临时文件路径列表
    """
    paths = []
    for img_b64 in images_base64:
        try:
            # 去掉可能存在的 data:image/xxx;base64, 前缀
            clean_b64 = img_b64
            if "," in clean_b64:
                clean_b64 = clean_b64.split(",", 1)[1]

            img_bytes = base64.b64decode(clean_b64)
            # 生成唯一临时文件
            fd, path = tempfile.mkstemp(suffix=".png", prefix="chat_img_")
            with os.fdopen(fd, "wb") as f:
                f.write(img_bytes)

            paths.append(path)
            _TEMP_IMAGE_PATHS.append(path)
        except Exception:
            # 单张图片失败不影响整体
            continue
    return paths


def _inject_images_into_message(message: str, image_paths: List[str]) -> str:
    """把用户上传的图片路径注入到 LLM 能理解的提示文本中

    LLM 看到这个提示后，会根据 system_prompt 里的触发条件调用 search_aero_image 工具。
    """
    if not image_paths:
        return message

    paths_str = ", ".join(image_paths)
    if message.strip():
        return f"{message}\n\n[注意：用户已提供图片，请先使用 search_aero_image 工具进行以图搜图，图片路径：{paths_str}]"
    else:
        return f"[注意：用户提供了图片，没有附带文字描述，请使用 search_aero_image 工具进行以图搜图，图片路径：{paths_str}]"


# =========================================================================
# 同步聊天（包装 MainAgent.send_message）
# =========================================================================

def send_chat_message(
    main_agent: MainAgent,
    message: str,
    context_prefix: str = "",
    images: List[str] = None,
) -> Dict[str, Any]:
    """同步发送消息，返回结构化结果"""
    try:
        # 如果用户上传了图片：保存为临时文件 + 注入到消息中让 LLM 触发图片检索工具
        image_paths = _save_images_to_temp(images or [])
        effective_message = _inject_images_into_message(message, image_paths) if image_paths else message

        result = main_agent.send_message(effective_message, context_prefix=context_prefix)
        # send_message 返回 (response_text, usage_info, agent_id) 或 4-tuple
        if isinstance(result, tuple):
            response = result[0] if len(result) > 0 else ""
            usage = result[1] if len(result) > 1 else {}
            agent_id = result[2] if len(result) > 2 else getattr(main_agent, "_agent_id", "unknown")
            structured_data = result[3] if len(result) > 3 else None
        else:
            response = str(result)
            usage = {}
            agent_id = getattr(main_agent, "_agent_id", "unknown")
            structured_data = None

        return {
            "response": response,
            "usage_info": usage,
            "responding_agent_id": agent_id,
            "structured_data": structured_data,
        }
    except Exception as e:
        return {
            "response": f"处理失败: {str(e)}",
            "usage_info": {},
            "responding_agent_id": getattr(main_agent, "_agent_id", "unknown"),
            "structured_data": None,
            "error": str(e),
        }


# =========================================================================
# SSE 事件流（AsyncGenerator）
# =========================================================================

async def send_chat_message_stream(
    main_agent: MainAgent,
    message: str,
    context_prefix: str = "",
    images: List[str] = None,
) -> AsyncGenerator[str, None]:
    """
    异步生成 SSE 事件流

    实现原理：
      1. 记录 AgentMessageLogger queue 当前 size，作为"水位线"
      2. 在后台线程跑 main_agent.send_message()（同步阻塞）
      3. 同时用 asyncio.sleep 轮询 queue，把新增消息转成 SSE 事件
      4. 后台线程结束后发送 final + done 事件

    SSE 格式：每个事件是一行 `data: {json}\\n\\n`
    """
    # 如果用户上传了图片：保存为临时文件 + 注入到消息中让 LLM 触发图片检索工具
    image_paths = _save_images_to_temp(images or [])
    effective_message = _inject_images_into_message(message, image_paths) if image_paths else message

    msg_queue = AgentMessageLogger.get_queue()

    # 记录起始水位线（当前已有的消息数）
    start_size = _queue_size(msg_queue)

    # 关键：把 start_size 数量的旧消息从 queue 里排干丢弃。
    # 原因：AgentMessageLogger 的 queue 是跨对话共享的全局单例，上一次对话结束后
    # queue 里可能残留上一次对话的 agent_response / done 消息。如果不先排干，
    # 本次对话的 SSE 生成器一开始就会 drain 出残留旧事件 → 前端收到残留 done 事件
    # → 立刻调 disconnect() 掐断 SSE 连接 → 后续真正的 final 事件到不了前端。
    for _ in range(start_size):
        try:
            msg_queue.get_nowait()
        except queue.Empty:
            break

    # 用于在线程和 async 之间传递最终结果
    result_holder: Dict[str, Any] = {"result": None, "error": None}

    def _run_in_thread():
        try:
            result = main_agent.send_message(effective_message, context_prefix=context_prefix)
            result_holder["result"] = result
        except Exception as e:
            result_holder["error"] = str(e)

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()

    # 聚合所有 tool_result extra 里的图片 base64（用于 final 事件传给前端）
    collected_images: List[str] = []

    try:
        # 循环：一边等线程完成，一边消费新日志
        while thread.is_alive() or not msg_queue.empty():
            # 尝试从 queue 里取新消息（非阻塞轮询）
            drained = []
            while not msg_queue.empty():
                try:
                    msg = msg_queue.get_nowait()
                    drained.append(msg)
                except queue.Empty:
                    break

            # drained 的消息同时写入 bridge 的 MSG_HISTORY（供 AgentMessagesPage 轮询）
            # 因为 queue.Queue 是破坏性读取，SSE 读了 bridge 就拿不到了，所以同时写一份
            try:
                from ..services.agent_msg_bridge import MSG_HISTORY, _lock as _bridge_lock
                with _bridge_lock:
                    for _m in drained:
                        MSG_HISTORY.append(_m)
            except Exception:
                pass

            for msg in drained:
                msg_type = getattr(msg, "message_type", "")
                if msg_type in _SKIP_TYPES:
                    continue

                sse_type = _TYPE_MAP.get(msg_type, msg_type)
                event = {
                    "type": sse_type,
                    "content": getattr(msg, "content", ""),
                    "agent_id": getattr(msg, "agent_id", ""),
                    "timestamp": getattr(msg, "timestamp", "").strftime("%H:%M:%S") if hasattr(getattr(msg, "timestamp", None), "strftime") else "",
                }
                # extra 信息也带上（可能含 tool_arguments 等）
                extra = getattr(msg, "extra", None)
                if extra:
                    try:
                        event["extra"] = dict(extra)
                    except Exception:
                        pass
                    # 聚合 tool_result 里的图片（给 final 事件用）
                    if msg_type == "tool_result" and isinstance(extra, dict):
                        imgs = extra.get("images", [])
                        if imgs and isinstance(imgs, list):
                            collected_images.extend(imgs)

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 等一下再轮询（避免空转）
            await asyncio.sleep(0.1)

            # 线程已结束且队列也排空了？
            if not thread.is_alive() and len(drained) == 0:
                break

        # 发送 final 事件（包含完整响应）
        if result_holder["error"]:
            yield f"data: {json.dumps({'type': 'error', 'message': result_holder['error']}, ensure_ascii=False)}\n\n"
        else:
            final = result_holder["result"]
            if isinstance(final, tuple):
                response = final[0] if len(final) > 0 else ""
                usage = final[1] if len(final) > 1 else {}
                agent_id = final[2] if len(final) > 2 else ""
                structured_data = final[3] if len(final) > 3 else None
            else:
                response = str(final) if final else ""
                usage = {}
                agent_id = ""
                structured_data = None

            # final 事件带上收集到的图片 base64 列表
            final_payload = {
                "type": "final",
                "response": response,
                "usage": usage,
                "agent_id": agent_id,
                "structured_data": structured_data,
                "images": collected_images,
            }
            yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"

        # done 事件同时写入 AgentMessageLogger，让 bridge MSG_HISTORY 也能收到
        AgentMessageLogger.log("main_agent", "done", "done")
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    except asyncio.CancelledError:
        # 客户端断开连接
        AgentMessageLogger.log("main_agent", "done", "done (client disconnected)")
        yield f"data: {json.dumps({'type': 'error', 'message': '客户端断开'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
    except Exception as e:
        AgentMessageLogger.log("main_agent", "done", f"done (error: {e})")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
