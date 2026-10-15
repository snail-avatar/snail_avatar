# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : work_logs.py
# @Desc    : work_logs
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
工作日志 API

两个端点：
  GET  /api/work-logs      — 获取所有历史日志（前端轮询 0.5s/次）
  POST /api/work-logs/clear — 清空所有日志
"""
from fastapi import APIRouter

from ..services.work_log_bridge import get_all_logs, clear_logs, parse_log_line

router = APIRouter()


@router.get("/work-logs", summary="获取所有历史日志")
async def list_work_logs():
    """返回所有已记录的工作日志"""
    raw_lines = get_all_logs()
    logs = [parse_log_line(line) for line in raw_lines]
    return {"ok": True, "total": len(logs), "logs": logs}


@router.post("/work-logs/clear", summary="清空所有日志")
async def clear_work_logs():
    """清空所有历史日志"""
    n = clear_logs()
    return {"ok": True, "cleared": n}
