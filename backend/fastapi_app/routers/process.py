# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : process.py
# @Desc    : process
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
流程编排（Process）API 路由 — Phase 4 实现

7 端点：
  GET  /api/process/vehicles              列出可执行目标值定义的车型
  GET  /api/process/steps                 获取流程步骤拓扑（前端预渲染时间线）
  POST /api/process/run                   启动流程（后台线程，立即返回）
  GET  /api/process/stream/{instance_key} SSE 进度事件流（15s 心跳保活）
  GET  /api/process/{instance_key}/status 状态查询（进度、当前步骤等）
  GET  /api/process/{instance_key}/results 读取所有步骤结果 + 最终总结
  POST /api/process/{instance_key}/stop    停止正在执行的流程

架构：
  ProcessService 维护 instance_key → RunState 映射。
  RunState.queue 是 SSE 的事件源；后台线程 push、SSE endpoint drain。
  同一 instance_key 用 threading.Lock 防并发 run_flow。
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from snail_avatar.backend.fastapi_app.services.process_service import ProcessService

router = APIRouter()


# =========================================================================
# Pydantic 请求体
# =========================================================================

class RunProcessRequest(BaseModel):
    instance_key: str = Field(..., description="车型的 instance_key（如 reevlto、reevlto_reev）")
    mode: str = Field("ALL", description="执行模式：ALL（全部）或 SINGLE（单项）")
    target_category: Optional[str] = Field("", description="单项模式下的目标项名称")


# =========================================================================
# 端点实现
# =========================================================================

@router.get("/process/vehicles", summary="列出可执行目标值定义的车型")
async def process_vehicles():
    """返回所有可执行目标值定义流程的车型列表（含 instance_key）。

    前端用此接口渲染目标值定义页面的车型下拉选择器。
    """
    return ProcessService.list_vehicles()


@router.get("/process/steps", summary="获取流程步骤拓扑")
async def process_steps():
    """返回流程的步骤拓扑结构：
    - outer_steps: 外层步骤（INIT → LOOP → FINAL_SUMMARY 等）
    - inner_steps: 循环内的内层步骤
    - loop_step_ids: 所有循环节点 ID
    - conditional_optional_map: 条件分支映射

    前端可据此预渲染进度条时间线。
    """
    return ProcessService.get_steps()


@router.post("/process/run", summary="启动目标值定义流程（后台线程）")
async def run_process(req: RunProcessRequest):
    """启动流程，立即返回（后台异步执行，耗时 3-10 分钟）。

    返回 ok=true 时，前端应立即连接 SSE endpoint 接收进度事件。
    同一 instance_key 正在执行时返回 ok=false + already_running=true。
    """
    if not req.instance_key.strip():
        raise HTTPException(status_code=400, detail="instance_key 不能为空")

    result = ProcessService.run_process(
        instance_key=req.instance_key.strip(),
        mode=req.mode,
        target_category=req.target_category or "",
    )

    if not result.get("ok"):
        # 业务层拒绝（并发冲突等）→ 409 Conflict
        if result.get("already_running"):
            raise HTTPException(status_code=409, detail=result.get("message", "正在执行中"))
        raise HTTPException(status_code=500, detail=result.get("message", "启动失败"))

    return result


@router.get("/process/stream/{instance_key}", summary="流程进度 SSE 事件流")
async def process_stream(instance_key: str):
    """SSE 推送流程进度事件。

    事件类型：
      connected      —— 连接成功（立即发送）
      step_progress  —— 步骤进度推进（含 step_id / loop_item / progress）
      heartbeat      —— 15s 心跳，防止代理/防火墙断连
      done           —— 流程完成（status=success/stopped/paused/error）
      error          —— 异常终止

    前端 EventSource 连接后，通过 type 字段分发到进度条/步骤卡片。
    """
    stream = ProcessService.stream_events(instance_key)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            "Connection": "keep-alive",
        },
    )


@router.get("/process/{instance_key}/status", summary="查询流程状态")
async def process_status(instance_key: str):
    """返回流程当前状态：
    - is_running: 是否正在执行
    - progress: 整体进度 0-1
    - controller_state: ProcessController 的完整状态快照
    - final_result: 最终结果（执行完成后填充）
    """
    return ProcessService.get_status(instance_key)


@router.get("/process/{instance_key}/results", summary="读取所有步骤结果")
async def process_results(instance_key: str):
    """返回已执行的所有步骤结果：
    - step_results: 完整步骤结果列表（controller._step_results）
    - summary_text: FINAL_SUMMARY 步骤的文本（如果已执行）
    - total_steps: 已完成步骤数
    - final_status: 最终状态
    """
    return ProcessService.get_results(instance_key)


@router.post("/process/{instance_key}/stop", summary="停止流程")
async def stop_process(instance_key: str):
    """停止正在执行的流程。

    底层调用 ProcessEngine.stop() 设置停止标志，
    引擎在下一步开始前检查并提前退出。
    """
    result = ProcessService.stop_process(instance_key)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "停止失败"))
    return result


@router.post("/process/{instance_key}/pause", summary="暂停流程")
async def pause_process(instance_key: str):
    """暂停正在执行的流程。

    引擎在下一步开始前的检查点生效；
    当前步骤不会被中途打断（LLM 调用自然返回后才暂停）。
    """
    result = ProcessService.pause_process(instance_key)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "暂停失败"))
    return result


@router.post("/process/{instance_key}/resume", summary="继续流程")
async def resume_process(instance_key: str):
    """继续已暂停的流程（从暂停点恢复）"""
    result = ProcessService.resume_process(instance_key)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "继续失败"))
    return result


@router.post("/process/{instance_key}/step", summary="单步执行")
async def step_process(instance_key: str):
    """单步执行流程（执行一个步骤后自动暂停，方便 review）

    两种场景：
    - 流程已暂停 → 让主循环走一步 + 自动再 pause（Step-then-pause）
    - 流程未启动/已结束 → 新开线程执行 run_single_step

    流程正在 running（未暂停）时不允许点单步。
    """
    result = ProcessService.step_process(instance_key)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "单步执行失败"))
    return result


@router.post("/process/{instance_key}/repeat", summary="重复本步")
async def repeat_process(instance_key: str):
    """重复执行上一步（从快照恢复后重新跑一个单步）

    前置条件：ProcessController 有 snapshot（至少执行过一步）。
    流程正在运行时不允许重复（快照会被覆盖）。
    """
    result = ProcessService.repeat_process(instance_key)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "重复执行失败"))
    return result


# ==========================================================================
# Sheet 数据查询 + 沙箱数据
# ==========================================================================

@router.get("/process/{instance_key}/sheet", summary="读取指定 sheet 数据")
async def get_process_sheet(instance_key: str, sheet_key: str):
    """读取流程关联的 sheet 数据（产品定义 / VTS / SSTS）

    Args:
        instance_key: 车型 mc_key（如 reevlto_reev）
        sheet_key: 关键字：base_产品定义 / target_vts / target_ssts
    """
    return ProcessService.get_sheet(instance_key, sheet_key)


@router.get("/process/{instance_key}/sandbox", summary="读取流程沙箱数据")
async def get_process_sandbox(instance_key: str):
    """读取流程执行后的沙箱私有数据（ProcessController.sandbox）"""
    return ProcessService.get_sandbox(instance_key)
