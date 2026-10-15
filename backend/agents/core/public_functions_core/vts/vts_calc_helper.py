# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vts_calc_helper.py
# @Desc    : VTS 计算统一入口
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""VTS 计算统一入口（VTS 专属模块）

设计目的：
  - 统一 VTS 计算的动态导入逻辑（避免在每个 function 文件中重复写 importlib）
  - 统一 NaN 检测逻辑（用于判断是否需要触发 VTS 计算）
  - 风格与 ensure_pass_flags_calculated() 保持一致

调用链：
  run_vts_calculation(db)
    → VTSCalculationOrchestrator.run_all(db)
       → 通过 panel 管理器调用 PowerPanel / EcoPanel 的工作流
          → 计算动力性/经济性参数
          → 将计算结果写回 memorycore

  count_vts_nan_params(db)
    → 遍历各车型 VTS sheet，统计"当前值"为 NaN 的数量
    → 用于决策：是否需要触发 VTS 计算
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .data_formatter import VTS_SHEET_KEY, iter_flat_items
_VTS_CALC_ALREADY_TRIGGERED = False


def is_vts_calc_triggered() -> bool:
    """返回 VTS 计算是否已被触发过"""
    return _VTS_CALC_ALREADY_TRIGGERED


def mark_vts_calc_triggered() -> None:
    """标记 VTS 计算已触发（由调用 VTS 计算的 function 设置）"""
    global _VTS_CALC_ALREADY_TRIGGERED
    _VTS_CALC_ALREADY_TRIGGERED = True


# ==========================================================================
# 内部工具：动态获取 VTSCalculationOrchestrator
# ==========================================================================

def _get_vts_orchestrator():
    """动态获取 VTSCalculationOrchestrator（避免循环依赖）

    与 ensure_pass_flags_calculated() 中动态获取 PassFlagCalculator 的方式保持一致。

    Returns:
        VTSCalculationOrchestrator 类或 None
    """
    try:
        import importlib
        mod = importlib.import_module(
            "snail_avatar.backend.agents.core.workflow_base.workflow_tab_base"
        )
        return getattr(mod, "VTSCalculationOrchestrator", None)
    except Exception:
        return None


# ==========================================================================
# 公共工具：VTS 计算
# ==========================================================================

def run_vts_calculation(db) -> Tuple[bool, str, Dict[str, Any]]:
    """执行全车型 VTS 计算（统一入口）

    与 PassFlagCalculator 一起构成 "计算 → 刷新达标标识" 的完整流程：

        run_vts_calculation(db)           ← 计算参数当前值
        ensure_pass_flags_calculated(db)  ← 基于新值刷新达标标识

    实现说明（2026-09-30 重构）：
      - 原 VTSCalculationOrchestrator.run_all() 依赖旧架构 UI 组件，
        在 FastAPI/agent 进程里永远是 None，直接返回空报告。
      - 新实现改为直接循环 workflow_service.run_workflow(panel, suffix)，
        和 FastAPI 端点 /api/vts-ssts/calculate 走同一条路径。
      - workflow_service 内部会自动 build + run workflow 并写回 memorydb。

    Args:
        db: memory_db 实例

    Returns:
        (ok: bool, message: str, report: dict)
        - ok: 是否全部成功（所有 panel × suffix 都无 errors）
        - message: 人类可读的结果消息
        - report: 详细执行结果（per-suffix × per-panel 的 completed/errors/duration）
    """
    if db is None:
        return False, "memory_db 为空", {}

    # 1. 收集所有车型后缀（和 /api/vts-ssts/calculate 保持一致）
    vehsuffix_list = getattr(db, "vehsuffix", []) or []
    suffixes = []
    for v in vehsuffix_list:
        if isinstance(v, dict):
            s = v.get("车型后缀") or v.get("后缀") or v.get("vehicle_suffix")
            if s:
                suffixes.append(s)
    if not suffixes:
        return False, "vehsuffix 里没有车型后缀，无法计算", {}

    # 2. 动态 import workflow_service（避免硬依赖 fastapi_app 层）
    try:
        import importlib
        ws_mod = importlib.import_module(
            "snail_avatar.backend.fastapi_app.services.workflow_service"
        )
        run_workflow = getattr(ws_mod, "run_workflow", None)
    except Exception as e:
        return False, f"workflow_service 导入失败: {e}", {}

    if run_workflow is None:
        return False, "workflow_service.run_workflow 未找到", {}

    _PANELS = ["power", "economy"]  # TODO: 将来加 energy_regen
    report: Dict[str, Any] = {
        "vehicle_count": len(suffixes),
        "panel_count": len(_PANELS),
        "total_runs": 0,
        "success_count": 0,
        "fail_count": 0,
        "total_duration_sec": 0.0,
        "errors": [],
        "details": {},
    }

    for suffix in suffixes:
        report["details"][suffix] = {}
        for panel in _PANELS:
            report["total_runs"] += 1
            try:
                # run_workflow 会内部 build + run + 自动写回 output 到 memory_db
                r = run_workflow(panel, suffix, db)
                completed = r.get("completed", 0)
                errors_cnt = r.get("errors", 0)
                duration = r.get("duration_sec", 0)
                report["details"][suffix][panel] = {
                    "completed": completed,
                    "errors": errors_cnt,
                    "duration_sec": duration,
                }
                if errors_cnt == 0:
                    report["success_count"] += 1
                else:
                    report["fail_count"] += 1
                    report["errors"].append(f"{suffix}/{panel}: {errors_cnt} errors")
                report["total_duration_sec"] += duration
            except Exception as e:
                report["details"][suffix][panel] = {"error": str(e)}
                report["fail_count"] += 1
                report["errors"].append(f"{suffix}/{panel}: {e}")

    # 3. 汇总结果
    ok = report["fail_count"] == 0
    dur = round(report["total_duration_sec"], 3)
    msg = (
        f"VTS 计算完成: {report['vehicle_count']} 车型 × {report['panel_count']} 面板"
        f" = {report['total_runs']} 次, "
        f"成功 {report['success_count']}, 失败 {report['fail_count']}, "
        f"耗时 {dur}s"
    )
    return ok, msg, report


# ==========================================================================
# 公共工具：NaN 检测
# ==========================================================================

def count_vts_nan_params(db) -> Tuple[int, int]:
    """统计 VTS 参数中的 NaN/空值数量

    用于判断是否需要触发 VTS 计算：
      - 如果 nan_count > 0 → 存在未计算的参数，应触发计算
      - 如果 nan_count == 0 → 所有参数当前值已填充，无需计算

    Args:
        db: memory_db 实例

    Returns:
        (total_with_current: int, nan_count: int)
        - total_with_current: 检测到有"当前值"字段的参数总数
        - nan_count: 其中为 NaN/空的数量
    """
    if db is None:
        return 0, 0

    # 动态加载依赖
    try:
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import (
            collect_vehicles,
            get_sheet_data,
        )
        from snail_avatar.backend.agents.core.public_functions_core.common.pass_flag_utils import (
            value_is_empty_or_nan,
        )
    except Exception:
        return 0, 0

    total_with_current = 0
    nan_count = 0
    names, name_to_mc_key = collect_vehicles(db)
    for name in names:
        mc_key = name_to_mc_key[name]
        sheet_data = get_sheet_data(db, mc_key, VTS_SHEET_KEY)
        for item in iter_flat_items(sheet_data):
            if "当前值" in item:
                total_with_current += 1
                if value_is_empty_or_nan(item.get("当前值")):
                    nan_count += 1
    return total_with_current, nan_count