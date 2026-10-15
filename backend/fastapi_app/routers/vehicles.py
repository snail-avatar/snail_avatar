# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vehicles.py
# @Desc    : vehicles
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
车辆数据 API 路由

实现:
  - GET  /api/vehicles                 列出所有车型
  - GET  /api/vehicles/{suffix}/vts    VTS 参数表
  - GET  /api/vehicles/{suffix}/ssts   SSTS 参数表
  - PUT  /api/vehicles/{suffix}/params 更新参数值
  - POST /api/vehicles/load            加载 Excel 文件
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Dict, List

from ..dependencies import get_memory_database
from snail_avatar.backend.core.memory.memory_database import MemoryDatabase

router = APIRouter()


# ==========================================================================
# 辅助函数：从 memorycore 提取指定车型 + 类型(VTS/SSTS)的参数
# ==========================================================================
def _extract_params_from_memorycore(
    db: MemoryDatabase,
    vehicle_suffix: str,
    param_type: str,
) -> List[Dict[str, Any]]:
    """从 MemoryDatabase.memorycore 提取指定车型的参数列表

    Args:
        db: MemoryDatabase 实例
        vehicle_suffix: 车型后缀，如 'ev'
        param_type: 'vts' 或 'ssts'

    Returns:
        参数条目列表 [{db_key, value, param_name, unit}, ...]
    """
    results = []
    memorycore = db.memorycore

    # memorycore 结构: {vehicle: {sheet_name: {db_key: value_or_dict}}}
    # 我们需要遍历所有 sheet，找到 db_key 中包含 param_type 的条目
    if vehicle_suffix not in memorycore:
        return results

    vehicle_data = memorycore[vehicle_suffix]
    if not isinstance(vehicle_data, dict):
        return results

    for sheet_name, params in vehicle_data.items():
        if not isinstance(params, dict):
            continue
        for db_key, value in params.items():
            # 过滤：db_key 包含 _vts_ 或 _ssts_ 或 _target_
            key_lower = db_key.lower()
            if param_type == "vts" and ("_vts_" in key_lower or "_target_" in key_lower):
                results.append({
                    "db_key": db_key,
                    "value": value if not isinstance(value, dict) else value.get("值", value),
                    "param_name": db_key.split("_")[0] if "_" in db_key else db_key,
                    "sheet": sheet_name,
                })
            elif param_type == "ssts" and "_ssts_" in key_lower:
                results.append({
                    "db_key": db_key,
                    "value": value if not isinstance(value, dict) else value.get("值", value),
                    "param_name": db_key.split("_")[0] if "_" in db_key else db_key,
                    "sheet": sheet_name,
                })
    return results


# ==========================================================================
# GET /api/vehicles - 列出所有车型
# ==========================================================================
@router.get("/vehicles", summary="列出所有车型")
async def list_vehicles(
    db: MemoryDatabase = Depends(get_memory_database),
):
    """从 MemoryDatabase.memorycore 中提取所有已加载的车型"""
    vehicles = []

    # memorycore 的顶层 key 就是 vehicle_suffix
    if db.memorycore:
        for suffix in db.memorycore.keys():
            # 构造车型信息
            vehicles.append({
                "vehicle_suffix": suffix,
                "vehicle_name": suffix.upper(),
            })

    # 补充 get_vehsuffix() 返回的额外信息
    vehsuffix_list = db.get_vehsuffix()
    if vehsuffix_list and isinstance(vehsuffix_list, list):
        for v in vehsuffix_list:
            if isinstance(v, dict) and "veh_suffix" in v:
                suffix = v["veh_suffix"]
                # 合并信息
                existing = next((x for x in vehicles if x["vehicle_suffix"] == suffix), None)
                if existing:
                    existing.update({
                        "vehicle_name": v.get("veh_name", existing.get("vehicle_name")),
                        "energy_type": v.get("energy_type"),
                    })
                else:
                    vehicles.append({
                        "vehicle_suffix": suffix,
                        "vehicle_name": v.get("veh_name", suffix.upper()),
                        "energy_type": v.get("energy_type"),
                    })

    return {
        "vehicles": vehicles,
        "total": len(vehicles),
    }


# ==========================================================================
# GET /api/vehicles/{suffix}/vts - VTS 参数表
# ==========================================================================
@router.get("/vehicles/{suffix}/vts", summary="读取 VTS 参数表")
async def get_vts(
    suffix: str,
    db: MemoryDatabase = Depends(get_memory_database),
):
    """读取指定车型的所有 VTS 参数"""
    params = _extract_params_from_memorycore(db, suffix, "vts")

    if not params:
        # 数据为空时返回空表（Excel 未导入）
        return {
            "vehicle_suffix": suffix,
            "param_type": "vts",
            "categories": [],
            "total": 0,
            "note": "数据为空，请先通过 POST /api/vehicles/load 导入 Excel 文件",
        }

    # 按 sheet 分组为 categories
    categories: Dict[str, List[Dict]] = {}
    for p in params:
        sheet = p.pop("sheet", "未分类")
        if sheet not in categories:
            categories[sheet] = []
        categories[sheet].append(p)

    return {
        "vehicle_suffix": suffix,
        "param_type": "vts",
        "categories": [{"name": k, "params": v} for k, v in categories.items()],
        "total": len(params),
    }


# ==========================================================================
# GET /api/vehicles/{suffix}/ssts - SSTS 参数表
# ==========================================================================
@router.get("/vehicles/{suffix}/ssts", summary="读取 SSTS 参数表")
async def get_ssts(
    suffix: str,
    db: MemoryDatabase = Depends(get_memory_database),
):
    """读取指定车型的所有 SSTS 参数"""
    params = _extract_params_from_memorycore(db, suffix, "ssts")

    if not params:
        return {
            "vehicle_suffix": suffix,
            "param_type": "ssts",
            "categories": [],
            "total": 0,
            "note": "数据为空，请先导入 Excel",
        }

    categories: Dict[str, List[Dict]] = {}
    for p in params:
        sheet = p.pop("sheet", "未分类")
        if sheet not in categories:
            categories[sheet] = []
        categories[sheet].append(p)

    return {
        "vehicle_suffix": suffix,
        "param_type": "ssts",
        "categories": [{"name": k, "params": v} for k, v in categories.items()],
        "total": len(params),
    }


# ==========================================================================
# PUT /api/vehicles/{suffix}/params - 更新参数值
# ==========================================================================
@router.put("/vehicles/{suffix}/params", summary="更新参数值")
async def update_params(
    suffix: str,
    body: Dict[str, Any],
    db: MemoryDatabase = Depends(get_memory_database),
):
    """更新指定 db_key 的参数值

    Request Body: {"db_key": "mile_ev_result_ev", "value": 15.2}
    """
    db_key = body.get("db_key")
    value = body.get("value")

    if not db_key:
        raise HTTPException(status_code=400, detail="db_key 不能为空")

    success = db.set_ssts_vts_param(db_key, value)
    if not success:
        raise HTTPException(status_code=404, detail=f"未找到 db_key: {db_key}")

    return {"status": "success", "db_key": db_key, "value": value}


# ==========================================================================
# POST /api/vehicles/load - 加载 Excel 文件
# ==========================================================================
@router.post("/vehicles/load", summary="加载 Excel 文件")
async def load_excel(
    file: UploadFile = File(...),
    db: MemoryDatabase = Depends(get_memory_database),
):
    """上传 Excel 文件并加载到 MemoryDatabase

    注意：MemoryDatabase 非线程安全，加载完成后需刷新前端页面
    """
    import tempfile
    import os

    # 保存到临时文件
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 调用 load_from_excel
        db.load_from_excel(tmp_path)

        # 清理临时文件
        os.unlink(tmp_path)

        # 返回加载结果摘要
        vehsuffix = db.get_vehsuffix()
        return {
            "status": "success",
            "filename": file.filename,
            "vehicles_count": len(vehsuffix) if vehsuffix else 0,
            "sheets_count": len(db.data) if db.data else 0,
            "memorycore_entries": sum(
                len(sheet_data)
                for v_data in db.memorycore.values()
                if isinstance(v_data, dict)
                for sheet_data in v_data.values()
                if isinstance(sheet_data, dict)
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载 Excel 失败: {str(e)}")
