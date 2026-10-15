# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflows.py
# @Desc    : workflows
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Workflow 计算 API 路由（Phase 2 完整实现）

四个端点：
  GET  /api/workflows                 — 列出所有可用 workflow（扫描 YAML）
  GET  /api/workflows/{id}/nodes      — 列出 workflow 节点拓扑（前端 DAG 渲染）
  POST /api/workflows/run             — 执行 workflow 计算
  GET  /api/workflows/{id}/viz/{node_id} — 节点可视化数据（仅 SSTS 路径有）
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_memory_database
from ..services.workflow_service import (
    WORKFLOW_REGISTRY,
    scan_workflows,
    run_workflow,
    get_workflow_nodes,
    get_sandbox_snapshot,
    get_sandbox_sheet_detail,
)

router = APIRouter()


# =========================================================================
# 请求/响应模型
# =========================================================================

class RunWorkflowRequest(BaseModel):
    panel_or_wfid: str = Field(..., description="panel_type(power/economy/energy_regen) 或 workflow_id")
    vehicle_suffix: str = Field(..., description="车型后缀，如 evLTO / reevLTO")


class RunWorkflowResponse(BaseModel):
    workflow_id: str
    workflow_name: str
    vehicle_suffix: str
    duration_sec: float
    completed: int
    errors: int
    nodes: list


# =========================================================================
# 端点实现
# =========================================================================

@router.get("/workflows", summary="列出所有可用 Workflow")
async def list_workflows():
    """扫描 agents/*/config/workflow_*.yaml，返回所有已注册 workflow"""
    workflows = scan_workflows()
    return {
        "count": len(workflows),
        "workflows": workflows,
        "registered_ids": list(WORKFLOW_REGISTRY.keys()),
    }


@router.get("/workflows/{panel_or_wfid}/nodes", summary="列出 Workflow 节点拓扑")
async def list_nodes(
    panel_or_wfid: str,
    vehicle_suffix: str = Query("", description="车型后缀，可选。传了才能匹配正确的 YAML 布局"),
    memory_db=Depends(get_memory_database),
):
    """
    构建工作流（不执行），返回节点列表含 position / upstream / schema，供前端 DAG 图渲染。
    panel_or_wfid 可以是 panel_type（power/economy/energy_regen）或具体 workflow_id。
    """
    try:
        nodes = get_workflow_nodes(panel_or_wfid, vehicle_suffix, memory_db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"构建工作流失败: {str(e)}")

    # 组装边
    edges = []
    for node in nodes:
        for up in node["upstream"]:
            edges.append({"from": up, "to": node["node_id"]})

    return {
        "workflow_id": panel_or_wfid,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


@router.post("/workflows/run", summary="执行 Workflow 计算", response_model=RunWorkflowResponse)
async def run_workflow_api(
    req: RunWorkflowRequest,
    memory_db=Depends(get_memory_database),
):
    """
    同步执行 workflow 计算（后台 executor 已用 logger 输出进度）。
    返回执行结果 + 每个节点的状态（state/completed/error）。
    """
    # 解析 panel_or_wfid（兼容 panel_type 和具体 workflow_id）
    try:
        from ..services.workflow_service import _resolve_registry
        _resolve_registry(req.panel_or_wfid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # --- vehicle_suffix 校验 ---
    # 如果 memory_db 已加载 Excel，检查 suffix 是否在 vehsuffix 列表中
    vehsuffix_list = getattr(memory_db, "vehsuffix", None)
    if vehsuffix_list and isinstance(vehsuffix_list, list) and len(vehsuffix_list) > 0:
        valid_suffixes = [v.get("车型后缀") for v in vehsuffix_list if isinstance(v, dict)]
        if req.vehicle_suffix not in valid_suffixes:
            raise HTTPException(
                status_code=400,
                detail=f"车型后缀 '{req.vehicle_suffix}' 不在已加载的 Excel 数据中。"
                       f"有效后缀: {valid_suffixes[:10]}" + ("..." if len(valid_suffixes) > 10 else ""),
            )
    elif not vehsuffix_list:
        # 空 vehsuffix 说明 Excel 未加载
        raise HTTPException(
            status_code=400,
            detail="MemoryDatabase 中没有车型数据。请先通过 POST /api/vehicles/load 加载 Excel 文件。",
        )

    # 异步执行以避免阻塞 FastAPI 事件循环（workflow 本身是同步的）
    try:
        result = await asyncio.to_thread(
            run_workflow, req.panel_or_wfid, req.vehicle_suffix, memory_db
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow 执行失败: {str(e)}")

    return result


@router.get("/workflows/{workflow_id}/viz/{node_id}", summary="获取节点可视化数据")
async def get_viz(workflow_id: str, node_id: str):
    """
    返回 viz_dict JSON，前端 ECharts 渲染。

    注意：只有 SSTSWorkflowExecutor（ENERGY_REGEN）的节点有 visualization_results。
    VTS 路径的 workflow 返回 not_available。
    """
    if workflow_id not in WORKFLOW_REGISTRY:
        raise HTTPException(status_code=404, detail=f"未注册的 workflow_id: {workflow_id}")

    reg = WORKFLOW_REGISTRY[workflow_id]
    if not reg["use_ssts_executor"]:
        return {
            "status": "not_available",
            "reason": f"workflow {workflow_id} 使用 WorkflowExecutor（非 SSTS），无 visualization_results",
        }

    # 注意：visualization_results 只在 run_workflow 执行过程中产生
    # 这里返回占位 + 说明 Phase 7 接入真实数据
    return {
        "status": "placeholder",
        "message": "Phase 7 实现：run_workflow 后缓存 visualization_results 到内存，此端点返回缓存值",
        "workflow_id": workflow_id,
        "node_id": node_id,
    }


# =========================================================================
# 沙箱快照（UI 沙箱内存 Tab 用）
# =========================================================================

@router.get("/workflows/{panel_or_wfid}/sandbox", summary="获取 SSTS 沙箱快照")
async def get_sandbox(
    panel_or_wfid: str,
    vehicle_suffix: str = Query("", description="车型后缀（当前用于 UI 侧标识；沙箱会扫描项目根所有后缀）"),
    memory_db=Depends(get_memory_database),
):
    """
    临时创建 SSTSSandbox → 自动索引项目根 → 加载零部件文件 → 返回 snapshot

    返回的 snapshot 结构（shape 由 ssts_sandbox.snapshot() 定义）：
      {
        "is_project_loaded": bool,
        "project_folder": str,
        "loaded_file_count": int,
        "vehicle_suffixes": [...],
        "data": {
          "reevlto": {
            "Motor": {
              "Emotor_F": {
                "_axle": "front",
                "_variants": {
                  "motor_parameter": {
                    "_meta": {...},
                    "sheets": {
                      "eff_map": {"type": "map_2d", "shape": "137×79", ...},
                      "external_characteristin": {"type": "curve_1d", "shape": "81p", ...}
                    }
                  }
                }
              }
            }
          }
        }
      }

    注意：sandbox 是请求级临时创建的，请求结束即销毁。
    """
    try:
        from ..services.workflow_service import _resolve_registry
        _resolve_registry(panel_or_wfid)   # 先校验注册存在
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        data = get_sandbox_snapshot(panel_or_wfid, vehicle_suffix, memory_db)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"沙箱加载失败: {str(e)}")

    return {
        "ok": True,
        "panel_type": panel_or_wfid,
        "vehicle_suffix": vehicle_suffix,
        "sandbox": data,
    }


@router.get("/workflows/{panel_or_wfid}/sandbox/sheet", summary="获取沙箱中单个 sheet 的完整数据")
async def get_sandbox_sheet(
    panel_or_wfid: str,
    vehicle_suffix: str = Query(..., description="车型后缀"),
    component: str = Query(..., description="零部件类型, 如 Motor"),
    instance: str = Query(..., description="实例名, 如 Emotor_R"),
    variant: str = Query(..., description="方案名(文件名去扩展名), 如 motor_parameter_1"),
    sheet_name: str = Query(..., description="Sheet 名, 如 eff_map"),
    memory_db=Depends(get_memory_database),
):
    """
    按需获取某个零部件参数文件里某个 sheet 的完整数据。

    典型场景：前端点击 snapshot 树里的 leaf（sheet）节点 → 右侧面板请求本端点
    渲染完整的 x/y/z 数组数据（ECharts 图表 / 表格 / 纯标量）。

    返回格式见 workflow_service.get_sandbox_sheet_detail。
    """
    try:
        from ..services.workflow_service import _resolve_registry
        _resolve_registry(panel_or_wfid)   # 先校验注册存在
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        data = get_sandbox_sheet_detail(
            panel_or_wfid=panel_or_wfid,
            vehicle_suffix=vehicle_suffix,
            component=component,
            instance=instance,
            variant=variant,
            sheet_name=sheet_name,
            memory_db=memory_db,
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"沙箱 sheet 数据加载失败: {str(e)}")

    # sheet 不存在返回 404 更友好；参数缺失等由 service 返回 ok=False 透传
    if not data.get("ok", True):
        raise HTTPException(status_code=404, detail=data.get("error", "sheet 不存在"))

    return data
