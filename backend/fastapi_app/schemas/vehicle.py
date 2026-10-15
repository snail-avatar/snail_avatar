# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vehicle.py
# @Desc    : vehicle
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""Pydantic schemas for Vehicle-related API"""
from pydantic import BaseModel, Field
from typing import Any, Optional, List


class VehicleInfo(BaseModel):
    """车型信息"""
    vehicle_suffix: str = Field(..., description="车型后缀，如 'ev', 'reev'")
    vehicle_name: Optional[str] = Field(None, description="车型名称")
    vehicle_type: Optional[str] = Field(None, description="车型类型（轿车/SUV等）")
    energy_type: Optional[str] = Field(None, description="能源形式（BEV/REEV/PHEV）")


class VehicleListResponse(BaseModel):
    """车型列表响应"""
    vehicles: List[VehicleInfo]
    total: int


class ParamItem(BaseModel):
    """参数条目"""
    db_key: str
    value: Any = None
    param_name: Optional[str] = None
    unit: Optional[str] = None
    status: Optional[str] = None  # pass/fail/not_checked


class ParamTableResponse(BaseModel):
    """参数表响应（VTS 或 SSTS）"""
    vehicle_suffix: str
    param_type: str = Field(..., description="vts 或 ssts")
    categories: List[dict]  # 按分类组织的参数
    total: int


class UpdateParamRequest(BaseModel):
    """更新参数值请求"""
    db_key: str
    value: Any
