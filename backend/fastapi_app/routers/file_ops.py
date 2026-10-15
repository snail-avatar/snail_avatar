# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : file_ops.py
# @Desc    : file_ops
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
文件操作 API — 打开/保存 Excel

三个端点：
  POST /api/files/open     — 上传 Excel → 保存到 uploads/ → 重建 MemoryDatabase → load_from_excel
  POST /api/files/save     — memory_db.save_memorycore_to_excel() → 返回输出路径
  GET  /api/files/status   — 返回当前加载的 Excel 状态（file_path, sheet_names, 是否已加载）

⚠️ 不修改 snail_avatar 目录下的业务代码，只在 fastapi_app 层做桥接。
"""
import os
import shutil
import threading
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException

from ..dependencies import get_memory_database, set_memory_database
from snail_avatar.backend.core.path_utils import get_writable_dir

router = APIRouter()

# uploads 目录（放在 snail_avatar/uploads/ 下，兼容打包环境）
_UPLOAD_DIR = os.path.join(get_writable_dir(), "uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _reset_memory_database(file_path: str):
    """
    重建全局 MemoryDatabase 单例（替换掉旧实例）
    所有依赖 get_memory_database() 的路由都会自动拿到新实例
    """
    from snail_avatar.backend.core.memory.memory_database import MemoryDatabase

    def core_log_cb(msg):
        from snail_avatar.backend.core.work_log import WorkLogger
        WorkLogger.info(msg)

    # 创建新实例 + 加载 Excel
    new_db = MemoryDatabase(file_path=file_path, log_callback=core_log_cb)
    new_db.load_from_excel()

    # 替换全局单例
    set_memory_database(new_db)

    return new_db


@router.post("/files/open", summary="打开并加载 Excel 文件")
async def open_excel(file: UploadFile = File(...)):
    """
    前端 <input type="file" accept=".xlsx,.xls"> 上传 → 后端保存到 uploads/ → 加载
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，仅支持 .xlsx / .xls")

    # 保存到 uploads/
    safe_name = f"{file.filename}"
    save_path = os.path.join(_UPLOAD_DIR, safe_name)

    # 避免覆盖同名（加时间戳后缀）
    if os.path.exists(save_path):
        import time
        ts = int(time.time())
        base, e = os.path.splitext(safe_name)
        save_path = os.path.join(_UPLOAD_DIR, f"{base}_{ts}{e}")

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {e}")

    # 加载到 MemoryDatabase
    try:
        db = _reset_memory_database(save_path)
        sheet_names = db.sheet_names()
        # 记录一下 WorkLogger（让工作日志页面也能看到）
        from snail_avatar.backend.core.work_log import WorkLogger
        WorkLogger.info(f"=== 已打开 Excel: {safe_name} ===")
        WorkLogger.info(f"共 {len(sheet_names)} 个 Sheet: {', '.join(sheet_names)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"加载 Excel 失败: {e}")

    return {
        "ok": True,
        "file_name": safe_name,
        "file_path": save_path,
        "sheet_count": len(sheet_names),
        "sheet_names": sheet_names,
    }


@router.post("/files/save", summary="保存 memorycore 回 Excel")
async def save_excel():
    db = get_memory_database()

    # 还没加载过
    if not db.file_path:
        return {"ok": False, "error": "尚未加载 Excel 文件，无法保存"}

    # 预计算 output_path（save_memorycore_to_excel 默认 原文件名_更新.xlsx）
    dir_name = os.path.dirname(db.file_path)
    base_name = os.path.basename(db.file_path)
    name_parts = os.path.splitext(base_name)
    output_path = os.path.join(dir_name, f"{name_parts[0]}_更新{name_parts[1]}")

    try:
        success = db.save_memorycore_to_excel()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": f"保存失败: {e}"}

    if success:
        from snail_avatar.backend.core.work_log import WorkLogger
        WorkLogger.info(f"✅ 保存成功: {output_path}")

    return {
        "ok": bool(success),
        "file_path": output_path,
    }


@router.get("/files/status", summary="查询当前 Excel 加载状态")
async def files_status():
    try:
        db = get_memory_database()
        file_path = getattr(db, "file_path", None) or ""
        loaded = bool(file_path) and os.path.exists(file_path)

        sheet_count = 0
        if loaded:
            try:
                sheet_count = len(db.sheet_names())
            except Exception:
                pass

        file_name = os.path.basename(file_path) if file_path else ""

        return {
            "ok": True,
            "loaded": loaded,
            "file_path": file_path,
            "file_name": file_name,
            "sheet_count": sheet_count,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "loaded": False}
