# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : value_formatter.py
# @Desc    : 跨 Agent 共享模块：值类型检测与格式化工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：值类型检测与格式化工具

提供对计算结果（标量、时间序列、数组、字典等）的通用检测和格式化能力，
用于将计算结果显示为对用户友好的文本。
"""

from __future__ import annotations

from typing import Any, Dict


def detect_value_type(value: Any) -> str:
    """检测值的类型

    Args:
        value: 任意类型的值

    Returns:
        str: 类型描述字符串，如 "int"、"float"、"TimeSeries"、"ndarray" 等
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, (list, tuple)):
        return "list"
    if hasattr(value, "value") and hasattr(value, "time"):
        return "TimeSeries"
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return "ndarray"
    except ImportError:
        pass
    return type(value).__name__


def format_value_for_display(value: Any, max_length: int = 200) -> str:
    """将值格式化为适合显示的字符串

    Args:
        value: 任意类型的值
        max_length: 输出字符串的最大长度（超长时会截断并添加 "..."）

    Returns:
        str: 格式化后的字符串
    """
    if value is None:
        return "None (未计算)"

    if isinstance(value, (int, float)):
        return f"{value:.6g}"

    if isinstance(value, str):
        return value if len(value) <= max_length else value[:max_length] + "..."

    if isinstance(value, dict):
        keys = list(value.keys())[:10]
        preview = {k: value[k] for k in keys if k in value}
        text = str(preview)
        return text if len(text) <= max_length else text[:max_length] + "..."

    if hasattr(value, "value") and hasattr(value, "time"):
        stats = extract_time_series_stats(value)
        return (f"[TimeSeries] 长度={stats.get('length', 0)}, "
                f"均值={stats.get('mean', 'N/A')}, "
                f"范围=[{stats.get('min', 'N/A')}, {stats.get('max', 'N/A')}]")

    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            text = f"[ndarray] shape={value.shape}, dtype={value.dtype}"
            if value.size <= 10:
                text += f", values={value.tolist()}"
            else:
                stats = extract_time_series_stats(value)
                text += (f", min={stats.get('min', 'N/A'):.4g}, "
                         f"max={stats.get('max', 'N/A'):.4g}, "
                         f"mean={stats.get('mean', 'N/A'):.4g}")
            return text
    except (ImportError, Exception):
        pass

    text = str(value)
    return text if len(text) <= max_length else text[:max_length] + "..."


def extract_time_series_stats(value: Any) -> Dict[str, Any]:
    """从时间序列或数组中提取统计信息

    Args:
        value: 可能是 TimeSeries 对象、numpy 数组或普通列表

    Returns:
        Dict: 包含 length、min、max、mean 等统计字段（如果适用）
    """
    stats: Dict[str, Any] = {}

    if hasattr(value, "value") and hasattr(value, "time"):
        try:
            ts_values = value.value
            length = len(ts_values) if hasattr(ts_values, "__len__") else 1
            stats["length"] = length
            try:
                import numpy as np
                if isinstance(ts_values, np.ndarray):
                    stats["min"] = float(np.min(ts_values))
                    stats["max"] = float(np.max(ts_values))
                    stats["mean"] = float(np.mean(ts_values))
                elif isinstance(ts_values, (list, tuple)) and len(ts_values) > 0:
                    stats["min"] = float(min(ts_values))
                    stats["max"] = float(max(ts_values))
                    stats["mean"] = float(sum(ts_values) / len(ts_values))
            except (TypeError, ValueError):
                pass
        except Exception:
            pass
        return stats

    try:
        import numpy as np
        if isinstance(value, np.ndarray) and value.size > 0:
            stats["length"] = value.size
            stats["min"] = float(np.min(value))
            stats["max"] = float(np.max(value))
            stats["mean"] = float(np.mean(value))
        return stats
    except (ImportError, Exception):
        pass

    if isinstance(value, (list, tuple)) and len(value) > 0:
        try:
            stats["length"] = len(value)
            numeric_values = [float(v) for v in value if isinstance(v, (int, float))]
            if numeric_values:
                stats["min"] = min(numeric_values)
                stats["max"] = max(numeric_values)
                stats["mean"] = sum(numeric_values) / len(numeric_values)
        except (TypeError, ValueError):
            pass

    return stats