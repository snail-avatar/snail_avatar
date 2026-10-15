# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow.py
# @Desc    : workflow
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""Pydantic schemas for Workflow-related API"""
from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict


class RunWorkflowRequest(BaseModel):
    """执行 Workflow 请求"""
    workflow_id: str = Field(..., description="Workflow ID，如 'ev_economy', 'power_rwd'")
    vehicle_suffix: str = Field(..., description="车型后缀")
    reset_first: bool = Field(True, description="执行前是否重置中间变量")


class RunWorkflowResponse(BaseModel):
    """执行 Workflow 响应"""
    status: str  # success / error
    workflow_id: str
    vehicle_suffix: str
    executed_nodes: List[str]
    failed_nodes: List[str] = []
    duration_ms: int = 0
    error: Optional[str] = None


class WorkflowNodeInfo(BaseModel):
    """Workflow 节点信息"""
    node_type_id: str
    name: str
    upstream: List[str]
    inputs_count: int
    outputs_count: int


class WorkflowInfo(BaseModel):
    """Workflow 概要"""
    workflow_id: str
    workflow_category: str
    drive_type: str
    node_count: int
    nodes: List[WorkflowNodeInfo]


class VizDataResponse(BaseModel):
    """节点可视化数据响应"""
    node_id: str
    vehicle_suffix: str
    charts: List[Dict[str, Any]]  # viz_dict 列表
