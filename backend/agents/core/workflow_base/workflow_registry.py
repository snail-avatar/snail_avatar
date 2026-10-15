# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_registry.py
# @Desc    : workflow_registry
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Workflow Registry — 共享层：panel_id → YAML 路径 → workflow 实例

这是 agent 路径和 FastAPI 路径都依赖的共享逻辑，
不包含任何 FastAPI / flet 特有 import。

职责：
  1. WORKFLOW_REGISTRY：panel_id → {agent_dir, nodes_pkg_path, category, yaml_match_fn}
  2. scan_workflows()：扫描 workflow_*.yaml 返回元数据列表
  3. _resolve_registry()：panel_type / workflow_id → registry 条目
  4. _resolve_yaml_path()：memory_db + vehsuffix → 匹配的 YAML 绝对路径
  5. build_workflow()：只构建不执行，返回 Workflow 对象（agent 路径用）
  6. _safe_json()：递归清理不可 JSON 序列化的值

FastAPI 路径的 run_workflow / get_workflow_nodes 留在 fastapi_app/services/，
它们处理 HTTP 响应格式化、写回 memorydb 等 HTTP 层特有逻辑。
"""

import os
import glob
import yaml
import json
from typing import Any, Dict, List, Optional

from snail_avatar.backend.agents.core.workflow_base.workflow_builder import (
    build_workflow_from_yaml_file,
)


def _safe_json(obj: Any) -> Any:
    """递归清理不可 JSON 序列化的值（NaN/Inf/callable/type/object 等）"""
    if isinstance(obj, float):
        if obj != obj or obj in (float('inf'), float('-inf')):
            return str(obj)
        return obj
    if callable(obj) and not isinstance(obj, (str, int, float, bool)):
        return str(obj)
    if isinstance(obj, type):
        return obj.__name__
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, OverflowError, ValueError):
        return str(obj)


# =========================================================================
# 静态注册表：workflow_id → Agent 构建参数
# =========================================================================

# 注意：本文件在 agents/core/workflow_base/ 下，往上 3 层是 agents/
_AGENTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents")
_AGENTS_ROOT = os.path.abspath(_AGENTS_ROOT)

WORKFLOW_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ---- 经济性 ----
    "EV_ECO_CALC": {
        "agent_dir": os.path.join(_AGENTS_ROOT, "a302_economy_agent"),
        "nodes_pkg_path": "snail_avatar.backend.agents.a302_economy_agent.nodes",
        "vehicle_info_field": "能源形式",
        "vehicle_info_default": "ev",
        "yaml_match_fn": lambda config, value: (
            config.get("calculation_type") == "economy"
            and config.get("energy_type") == value
        ),
        "default_yaml": "workflow_ev_ECO.yaml",
        "category": "economy",
        "panel_id": "eco",  # flet UI / agent YAML 用的标识
        "use_ssts_executor": False,
    },
    "REEV_ECO_CALC": {
        "agent_dir": os.path.join(_AGENTS_ROOT, "a302_economy_agent"),
        "nodes_pkg_path": "snail_avatar.backend.agents.a302_economy_agent.nodes",
        "vehicle_info_field": "能源形式",
        "vehicle_info_default": "reev",
        "yaml_match_fn": lambda config, value: (
            config.get("calculation_type") == "economy"
            and config.get("energy_type") == value
        ),
        "default_yaml": "workflow_reev_ECO.yaml",
        "category": "economy",
        "panel_id": "eco",
        "use_ssts_executor": False,
    },
    # ---- 动力性 ----
    "power_rwd": {
        "agent_dir": os.path.join(_AGENTS_ROOT, "a303_power_agent"),
        "nodes_pkg_path": "snail_avatar.backend.agents.a303_power_agent.nodes",
        "vehicle_info_field": "驱动形式",
        "vehicle_info_default": "fwd",
        "yaml_match_fn": lambda config, value: (
            config.get("workflow_category") == "power"
            and config.get("drive_type") == value
        ),
        "default_yaml": "workflow_power_rwd.yaml",
        "category": "power",
        "panel_id": "power",
        "use_ssts_executor": False,
    },
    # ---- 能量回收 ----
    "ENERGY_REGEN": {
        "agent_dir": os.path.join(_AGENTS_ROOT, "a401_energy_regeneration_agent"),
        "nodes_pkg_path": "snail_avatar.backend.agents.a401_energy_regeneration_agent.nodes",
        "vehicle_info_field": "能源形式",
        "vehicle_info_default": "ev",
        "yaml_match_fn": None,
        "default_yaml": "workflow_energy_regen.yaml",
        "category": "energy_regen",
        "panel_id": "energy_regen",
        "use_ssts_executor": True,
    },
}


# =========================================================================
# 动态扫描：实际的 workflow 列表
# =========================================================================

def scan_workflows() -> List[Dict[str, Any]]:
    """扫描所有 workflow_*.yaml，返回含元数据的 workflow 列表"""
    result = []
    for workflow_id, meta in WORKFLOW_REGISTRY.items():
        yaml_pattern = os.path.join(meta["agent_dir"], "config", "workflow_*.yaml")
        for yaml_path in glob.glob(yaml_pattern):
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                wid = config.get("workflow_id", "")
                if wid != workflow_id:
                    continue
                result.append({
                    "workflow_id": wid,
                    "workflow_name": config.get("workflow_name", wid),
                    "category": meta["category"],
                    "energy_type": config.get("energy_type"),
                    "drive_type": config.get("drive_type"),
                    "use_ssts_executor": meta["use_ssts_executor"],
                })
            except Exception:
                continue
    return result


# =========================================================================
# 按 panel_type / workflow_id 解析 registry 条目
# =========================================================================

def _resolve_registry(panel_or_wfid: str) -> Dict[str, Any]:
    """
    接受以下任一标识，返回 registry 条目：
      - workflow_id（精确匹配 registry key，如 "EV_ECO_CALC"）
      - category（HTTP 路由用，如 "economy"）
      - panel_id（flet UI 面板 / agent YAML 用，如 "eco"）
    """
    # 1. 精确匹配 workflow_id key
    if panel_or_wfid in WORKFLOW_REGISTRY:
        return WORKFLOW_REGISTRY[panel_or_wfid]
    # 2. 按 category 匹配（如 "economy"）
    for r in WORKFLOW_REGISTRY.values():
        if r.get("category") == panel_or_wfid:
            return r
    # 3. 按 panel_id 匹配（flet UI / agent YAML 用的标识，如 "eco"）
    for r in WORKFLOW_REGISTRY.values():
        if r.get("panel_id") == panel_or_wfid:
            return r
    available = (
        sorted(set(r.get("category", "") for r in WORKFLOW_REGISTRY.values() if r.get("category")))
        + sorted(set(r.get("panel_id", "") for r in WORKFLOW_REGISTRY.values() if r.get("panel_id")))
    )
    raise ValueError(
        f"未知的 panel_type/workflow_id/panel_id: {panel_or_wfid}。"
        f"可用标识: {sorted(set(available))}；"
        f"可用 workflow_id: {list(WORKFLOW_REGISTRY.keys())}"
    )


# =========================================================================
# YAML 文件自动匹配
# =========================================================================

def _resolve_yaml_path(
    reg: Dict[str, Any],
    memory_db: Any,
    vehicle_suffix: str,
) -> str:
    """
    根据 yaml_match_fn + vehsuffix 自动匹配正确的 workflow YAML 文件路径。

    返回: YAML 文件绝对路径
    """
    config_dir = os.path.join(reg["agent_dir"], "config")

    vehicle_value = reg["vehicle_info_default"]
    if hasattr(memory_db, "vehsuffix"):
        for vehicle in memory_db.vehsuffix:
            if vehicle.get("车型后缀") == vehicle_suffix:
                vehicle_value = vehicle.get(reg["vehicle_info_field"], reg["vehicle_info_default"])
                break
    if isinstance(vehicle_value, str):
        vehicle_value = vehicle_value.lower()

    workflow_configs = []
    for file_path in glob.glob(os.path.join(config_dir, "workflow_*.yaml")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if reg["yaml_match_fn"] is None or reg["yaml_match_fn"](config, vehicle_value):
                workflow_configs.append(file_path)
        except Exception:
            continue

    if not workflow_configs:
        workflow_configs = [os.path.join(config_dir, reg["default_yaml"])]

    return workflow_configs[0]


# =========================================================================
# 只构建不执行（给 agent 路径用）
# =========================================================================

def build_workflow(
    panel_or_wfid: str,
    vehicle_suffix: str,
    memory_db: Any,
) -> Optional[Any]:
    """
    只构建 workflow 实例（不执行 run_all），返回 Workflow 对象。

    用于 agent 路径（WorkflowAgentBase），它们需要 workflow 实例来：
      - 读取 ssts_vts_schema 列出参数
      - 读取 intermediate_output_values 做语义摘要
      - 修改 input_vars 后执行 DOE 试算

    flet 架构下本来是从 UI 面板拿 workflow 实例；
    FastAPI/agent 进程里没有 flet，直接调 build_workflow_from_yaml_file 构建。
    """
    try:
        reg = _resolve_registry(panel_or_wfid)
        yaml_path = _resolve_yaml_path(reg, memory_db, vehicle_suffix)
        wf = build_workflow_from_yaml_file(
            yaml_path=yaml_path,
            vehicle_suffix=vehicle_suffix,
            memory_db=memory_db,
            nodes_pkg_path=reg["nodes_pkg_path"],
        )
        return wf
    except Exception as e:
        print(f"[workflow_registry.build_workflow] 构建失败 panel={panel_or_wfid}, suffix={vehicle_suffix}: {e}")
        return None
