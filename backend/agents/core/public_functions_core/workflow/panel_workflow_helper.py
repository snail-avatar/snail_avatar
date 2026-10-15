# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : panel_workflow_helper.py
# @Desc    : 从 workflow_registry 构建工作流实例（flet 清除后简化版）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：构建工作流实例

直接委托给 agents.core.workflow_base.workflow_registry.build_workflow()，
无 flet / FastAPI 依赖。

使用方式:
    from snail_avatar.backend.agents.core.public_functions_core.workflow.panel_workflow_helper import (
        get_workflow_from_panel,
    )
    workflow = get_workflow_from_panel("eco", "evlto")
"""

from __future__ import annotations

from typing import Any, Optional


def get_workflow_from_panel(
    panel_name: str,
    vehicle_suffix: str = ""
) -> Optional[Any]:
    """从共享层 workflow_registry 构建工作流实例

    Args:
        panel_name: panel_id / category / workflow_id，如 "eco"、"power"、"economy"
        vehicle_suffix: 车型后缀，如 "evlto"、"reevlto"

    Returns:
        工作流实例（具有 run_all、graph、all_nodes 等属性），未找到返回 None
    """
    try:
        from snail_avatar.backend.agents.core.workflow_base.workflow_registry import build_workflow
    except Exception as e:
        print(f"[panel_workflow_helper] workflow_registry.build_workflow 导入失败: {e}")
        return None

    try:
        from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
        db = get_memory_db()
    except Exception:
        db = None
    if db is None:
        print("[panel_workflow_helper] memory_db 为空，无法构建 workflow")
        return None

    wf = build_workflow(panel_name, vehicle_suffix, db)
    if wf is None:
        print(f"[panel_workflow_helper] 构建工作流失败: panel={panel_name}, suffix={vehicle_suffix}")
    return wf
