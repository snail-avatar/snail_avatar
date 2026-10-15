# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : memory_bridge.py
# @Desc    : memory_bridge
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Memory Database Bridge — MemoryDatabase / LLMMemory → FastAPI 只读 API

⚠️ 不修改 snail_avatar 目录下的业务代码，只在 fastapi_app 层做桥接。
"""
import json
import traceback
from typing import Any


def _safe_json(obj: Any, _depth: int = 0) -> Any:
    """把任意对象转成可 JSON 序列化的 dict/list/str/number"""
    if _depth > 10:
        return f"<max_depth: {type(obj).__name__}>"
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        # 处理 float NaN/Inf（JSON 不支持）
        if isinstance(obj, float) and (obj != obj or obj in (float('inf'), float('-inf'))):
            return str(obj)
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_json(x, _depth + 1) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_json(v, _depth + 1) for k, v in obj.items()}
    # numpy / pandas
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return _safe_json(obj.tolist(), _depth + 1)
    except ImportError:
        pass
    # 有 to_serializable() 方法
    if hasattr(obj, 'to_serializable'):
        try:
            return _safe_json(obj.to_serializable(), _depth + 1)
        except Exception:
            pass
    # 有 model_dump() / dict()（pydantic）
    for attr in ('model_dump', 'dict'):
        if hasattr(obj, attr):
            try:
                return _safe_json(getattr(obj, attr)(), _depth + 1)
            except Exception:
                pass
    # 最后兜底：转 str
    return str(obj)


def get_memory_db_data() -> dict:
    """读取 MemoryDatabase 所有数据（返回可 JSON 序列化的 dict）

    每个字段独立 try-except，某个字段序列化崩了不影响其他字段。
    """
    from ..dependencies import get_memory_database
    md = get_memory_database()

    data = {}

    # 1. Excel 过渡数据
    try:
        sheets = md.get_all_sheets() if hasattr(md, 'get_all_sheets') else {}
        data["sheets"] = _safe_json(sheets) if sheets else {}
    except Exception as e:
        data["sheets"] = {"_error": str(e)}

    # 2a. VehSuffix
    try:
        vs = getattr(md, 'vehsuffix', None)
        if vs is None and hasattr(md, 'get_vehsuffix'):
            vs = md.get_vehsuffix()
        data["vehsuffix"] = _safe_json(vs) if vs else []
    except Exception as e:
        data["vehsuffix"] = {"_error": str(e)}

    # 2b. MemoryCore
    try:
        mc = getattr(md, 'memorycore', None)
        data["memorycore"] = _safe_json(mc) if mc else {}
    except Exception as e:
        data["memorycore"] = {"_error": str(e), "_tb": traceback.format_exc()}

    # 2c. EcoCycle
    try:
        eco = getattr(md, 'ecocycle', None)
        data["ecocycle"] = _safe_json(eco) if eco else []
    except Exception as e:
        data["ecocycle"] = {"_error": str(e)}

    # 2d. InterData
    try:
        inter = getattr(md, 'inter_data', None)
        data["inter_data"] = _safe_json(inter) if inter else {}
    except Exception as e:
        data["inter_data"] = {"_error": str(e)}

    return data


def get_llm_memory_data() -> dict:
    """同步 LLMMemory 并返回 current（压缩后的 LLM 友好格式）"""
    from ..dependencies import get_memory_database
    from snail_avatar.backend.core.memory.llm_memory import LLMMemory

    md = get_memory_database()
    llm = LLMMemory()

    try:
        mc = getattr(md, 'memorycore', None) or {}
        llm.sync_from_memorycore(mc)
    except Exception as e:
        return {"ok": False, "error": f"sync 失败: {e}", "tb": traceback.format_exc(), "current": {}}

    return {
        "ok": True,
        "current": _safe_json(llm.current) if llm.current else {},
    }
