# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : pass_flag_calculator.py
# @Desc    : VTS 达标标识计算工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS 达标标识计算工具（VTS 专属模块）

提供确保所有车型的 VTS 达标标识已重新计算的能力（幂等操作）。

设计意图：
  - 用户在对话中询问 VTS 参数/达标情况时，查询类 function 应先调用此函数
  - 确保查询结果始终基于最新的"当前值"和"目标值"计算
  - 无需用户知道"达标标识重算"这一技术细节

调用链：
  ensure_pass_flags_calculated(db)
    → PassFlagCalculator().calculate_all(db)
       → 遍历所有车型 × SSTS/VTS sheet × 所有参数
          → 根据"达标判据"对比"当前值"与"目标值"
             → 计算并写回"达标标识"到 memorycore
"""

from __future__ import annotations

from typing import Any, Dict


def ensure_pass_flags_calculated(db) -> Dict[str, Any]:
    """确保所有车型的 VTS 达标标识已重新计算（幂等操作）

    Args:
        db: memory_db 实例

    Returns:
        dict: 统计信息（total/updated/pass_count/fail_count/details）
    """
    if db is None:
        return {"total": 0, "updated": 0, "pass_count": 0, "fail_count": 0, "details": []}

    # 动态导入 PassFlagCalculator（避免循环依赖）
    try:
        import importlib
        calc_mod = importlib.import_module(
            "snail_avatar.backend.agents.core.public_functions_core.vts.vts_ssts_pass_calculater"
        )
        PassFlagCalculator = getattr(calc_mod, "PassFlagCalculator", None)
    except Exception:
        return {"total": 0, "updated": 0, "pass_count": 0, "fail_count": 0, "details": []}

    if PassFlagCalculator is None:
        return {"total": 0, "updated": 0, "pass_count": 0, "fail_count": 0, "details": []}

    calc = PassFlagCalculator()
    result = calc.calculate_all(db)

    # 从 details 中统计达标/不达标数量（保持与 orchestrator 中相同的统计口径）
    pass_count = 0
    fail_count = 0
    for d in result.get("details", []):
        after = d.get("after")
        if after == 1:
            pass_count += 1
        elif after == 0:
            fail_count += 1

    return {
        "total": result.get("total", 0),
        "updated": result.get("updated", 0),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "details": result.get("details", []),
    }