# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : llm_config_loader.py
# @Desc    : LLM全局配置加载模块 - 懒加载单例模式
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
LLM全局配置加载模块

提供懒加载单例模式的全局LLM配置加载、合并和查询功能。
所有 LLM 类 step 共享同一份全局配置，可被 step 级配置覆盖。
"""

import os
import threading
from typing import Any, Dict, Optional

_global_llm_config: Optional[Dict[str, Any]] = None
_global_llm_config_lock = threading.Lock()


def load_global_llm_config() -> Dict[str, Any]:
    """加载全局 LLM 配置（从 process_executor/config/LLM_step.yaml）"""
    global _global_llm_config
    if _global_llm_config is not None:
        return _global_llm_config

    with _global_llm_config_lock:
        if _global_llm_config is not None:
            return _global_llm_config

        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config",
                "LLM_step.yaml",
            )
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    _global_llm_config = yaml.safe_load(f) or {}
            else:
                _global_llm_config = {}
        except Exception:
            _global_llm_config = {}

    return _global_llm_config


def merge_with_global_llm_config(step_config: Dict[str, Any]) -> Dict[str, Any]:
    """将步骤配置与全局 LLM 默认配置合并

    步骤配置中的值优先级高于全局默认值。

    Args:
        step_config: 步骤特定配置

    Returns:
        dict: 合并后的配置
    """
    global_config = load_global_llm_config()
    defaults = global_config.get("defaults", {})

    if not defaults:
        return step_config

    merged = dict(step_config)

    # 合并 llm_config
    default_llm = defaults.get("llm_config", {})
    step_llm = merged.get("llm_config", {})
    if default_llm and not step_llm:
        merged["llm_config"] = dict(default_llm)
    elif default_llm and step_llm:
        merged_llm = dict(default_llm)
        merged_llm.update(step_llm)
        merged["llm_config"] = merged_llm

    # 合并 stage1_llm_config
    default_stage1 = defaults.get("stage1_llm_config", {})
    step_stage1 = merged.get("stage1_llm_config", {})
    if default_stage1 and not step_stage1:
        merged["stage1_llm_config"] = dict(default_stage1)
    elif default_stage1 and step_stage1:
        merged_s1 = dict(default_stage1)
        merged_s1.update(step_stage1)
        merged["stage1_llm_config"] = merged_s1

    # 合并 stage1_enabled
    if "stage1_enabled" not in merged and "stage1_enabled" in defaults:
        merged["stage1_enabled"] = defaults["stage1_enabled"]

    # 合并 builtin_functions
    default_functions = defaults.get("builtin_functions", [])
    step_functions = merged.get("builtin_functions", [])
    if step_functions:
        merged["builtin_functions"] = step_functions
    elif default_functions:
        merged["builtin_functions"] = default_functions

    return merged