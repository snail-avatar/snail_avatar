# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : memory_dbs.py
# @Desc    : memory_dbs
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
内存数据库 API — MemoryDatabase / LLMMemory 只读查询 + SSTS/VTS 参数写入

三个端点：
  GET    /api/memory-dbs          — MemoryDatabase 所有数据（sheets/vehsuffix/memorycore/ecocycle/inter_data）
  GET    /api/llm-memory          — LLMMemory（从 memorycore 同步压缩后的 LLM 友好格式）
  PUT    /api/vts-ssts/param      — 写单个 SSTS/VTS 参数（调 db.set_ssts_vts_param）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from ..services.memory_bridge import get_memory_db_data, get_llm_memory_data
from ..dependencies import get_memory_database

router = APIRouter()


class ParamWriteRequest(BaseModel):
    db_key: str
    value: Any


@router.get("/memory-dbs", summary="获取 MemoryDatabase 全量数据")
async def list_memory_dbs():
    try:
        # 返回前先重算一遍达标标识（幂等操作，确保 NaN/空值行不再被误标为不达标）
        # 之前的问题：VtsSstsPage 直接读 memory_db，里面达标标识是旧值（NaN→0），
        # ensure_pass_flags_calculated 只在 a301 agent function 里调，页面刷新永远看不到更新
        try:
            from snail_avatar.backend.agents.core.public_functions_core.vts.pass_flag_calculator import (
                ensure_pass_flags_calculated,
            )
            db = get_memory_database()
            if db is not None:
                ensure_pass_flags_calculated(db)
        except Exception:
            pass  # 重算失败不阻塞正常查询

        data = get_memory_db_data()
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/llm-memory", summary="获取 LLM 压缩记忆")
async def get_llm_memory():
    try:
        data = get_llm_memory_data()
        return data
    except Exception as e:
        return {"ok": False, "error": str(e), "current": {}}


@router.put("/vts-ssts/param", summary="写 SSTS/VTS 参数值")
async def write_param(req: ParamWriteRequest):
    """写入单个参数到 MemoryCore。value 会自动做类型推断（数字/布尔/字符串）。"""
    db = get_memory_database()
    if db is None:
        return {"ok": False, "error": "内存数据库未加载"}

    if not hasattr(db, "set_ssts_vts_param"):
        return {"ok": False, "error": "set_ssts_vts_param 方法不存在"}

    # 类型推断：前端传来的 value 可能是字符串（如编辑框输入），需要转换
    value = req.value
    if isinstance(value, str):
        v = value.strip()
        # 尝试数字
        try:
            if "." in v or "e" in v.lower():
                value = float(v)
            else:
                value = int(v)
        except ValueError:
            # 尝试布尔
            low = v.lower()
            if low in ("true", "1", "yes", "是"):
                value = True
            elif low in ("false", "0", "no", "否"):
                value = False
            else:
                value = v  # 保持字符串

    try:
        written = db.set_ssts_vts_param(req.db_key, value)
        if written:
            return {"ok": True, "db_key": req.db_key, "value": value}
        else:
            return {"ok": False, "error": f"未找到 db_key={req.db_key}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/vts-ssts/calculate", summary="VTS 全量计算（FastAPI 无 flet 依赖版）")
async def vts_calculate():
    """
    VTS 全量计算：遍历所有车型后缀 × 所有计算面板（power + economy）直接执行 workflow。

    原 VTSCalculationOrchestrator.run_all() 依赖旧架构 UI 组件，
    在 FastAPI 进程里永远是 None，直接返回空报告。

    本端点改为直接调 workflow_service.run_workflow()，每条计算结果写回 memory_db。
    """
    import asyncio
    from ..services.workflow_service import run_workflow

    db = get_memory_database()
    if db is None:
        return {"ok": False, "error": "内存数据库未加载"}

    # 1. 收集所有车型后缀
    vehsuffix_list = getattr(db, "vehsuffix", []) or []
    suffixes = []
    for v in vehsuffix_list:
        if isinstance(v, dict):
            s = v.get("车型后缀") or v.get("后缀") or v.get("vehicle_suffix")
            if s:
                suffixes.append(s)
    if not suffixes:
        return {"ok": False, "error": "vehsuffix 里没有车型后缀，无法计算"}

    # 2. 遍历所有车型 × 所有面板执行
    _PANELS = ["power", "economy"]  # TODO: 将来加 energy_regen
    results = {}
    success_count = 0
    fail_count = 0
    total_duration = 0.0
    errors = []

    for suffix in suffixes:
        results[suffix] = {}
        for panel in _PANELS:
            try:
                # run_workflow 会内部 build + run + 自动写回 output 到 memory_db
                r = await asyncio.to_thread(run_workflow, panel, suffix, db)
                completed = r.get("completed", 0)
                errors_cnt = r.get("errors", 0)
                duration = r.get("duration_sec", 0)
                results[suffix][panel] = {
                    "ok": errors_cnt == 0,
                    "completed": completed,
                    "errors": errors_cnt,
                    "duration_sec": duration,
                    "workflow_id": r.get("workflow_id"),
                }
                success_count += 1 if errors_cnt == 0 else 0
                fail_count += 1 if errors_cnt > 0 else 0
                total_duration += duration
            except Exception as e:
                import traceback
                results[suffix][panel] = {"ok": False, "error": str(e)}
                errors.append(f"{suffix}/{panel}: {e}")
                fail_count += 1

    return {
        "ok": True,
        "vehicle_count": len(suffixes),
        "panel_count": len(_PANELS),
        "total_runs": len(suffixes) * len(_PANELS),
        "success_count": success_count,
        "fail_count": fail_count,
        "total_duration_sec": round(total_duration, 3),
        "results": results,
        "errors": errors,
        "message": (
            f"VTS 计算完成: {len(suffixes)} 车型 × {len(_PANELS)} 面板"
            f" = {len(suffixes) * len(_PANELS)} 次, "
            f"成功 {success_count}, 失败 {fail_count}, "
            f"耗时 {round(total_duration, 3)}s"
        ),
    }
