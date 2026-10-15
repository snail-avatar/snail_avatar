# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_discovery.py
# @Desc    : 跨 Agent 共享模块：工作流发现与加载
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：工作流发现与加载

提供对 workflow_*.yaml 的通用发现、解析和匹配能力。
适用于所有基于工作流（workflow）引擎的计算型 agent。

使用方式:
    from snail_avatar.backend.agents.core.public_functions_core.workflow.workflow_discovery import (
        discover_all_workflows_in_dir,
        select_workflow_yaml_for_vehicle,
    )

    # 发现所有工作流
    workflows = discover_all_workflows_in_dir("/path/to/agent/config")

    # 根据车型后缀匹配工作流 YAML
    yaml_path = select_workflow_yaml_for_vehicle(config_dir, "evLTO", "economy")
"""

from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional

import yaml


def discover_all_workflows_in_dir(config_dir: str) -> List[Dict[str, Any]]:
    """扫描指定目录下的 workflow_*.yaml，返回所有工作流的基本信息

    Args:
        config_dir: 配置目录路径，应包含 workflow_*.yaml 文件

    Returns:
        List[Dict]: 每个元素包含:
            - workflow_id: 工作流ID
            - workflow_name: 工作流名称
            - energy_type: 能源类型 (ev / reev)
            - yaml_path: YAML 文件路径
            - description: 描述
            - node_count: 节点数量
            - conditions: 支持的工况列表
    """
    workflows = []
    for yaml_path in glob.glob(os.path.join(config_dir, "workflow_*.yaml")):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            wf_id = config.get("workflow_id", "unknown")
            wf_name = config.get("workflow_name", "未知工作流")
            energy_type = config.get("energy_type", "unknown")
            description = config.get("description", "")

            nodes = config.get("nodes", {})
            node_count = len(nodes)

            condition_names = set()
            for node_id in nodes:
                if "Ltem_m7" in node_id:
                    condition_names.add("低温-7℃")
                elif "Ltem_m20" in node_id:
                    condition_names.add("低温-20℃")
                elif "Htem" in node_id:
                    condition_names.add("高温工况")

            if len(condition_names) == 0:
                condition_names.add("标准工况")

            workflows.append({
                "workflow_id": wf_id,
                "workflow_name": wf_name,
                "energy_type": energy_type,
                "description": description,
                "yaml_path": yaml_path,
                "node_count": node_count,
                "conditions": list(condition_names),
            })
        except Exception as e:
            print(f"[workflow_discovery] 加载工作流配置失败: {yaml_path}, 错误: {e}")

    return workflows


def select_workflow_yaml_for_vehicle(config_dir: str, vehicle_suffix: str, domain: str = "") -> Optional[str]:
    """根据车型后缀和领域自动选择对应的工作流 YAML

    匹配规则（按优先级）：
    1. 扫描目录下所有 workflow_*.yaml，找到文件名包含车型后缀（不区分大小写）
    2. 根据能源类型匹配：车型后缀包含 "reev" → REEV 工作流，否则 → EV 工作流
    3. 如果提供了 domain，会优先匹配文件名中包含 domain 的工作流

    Args:
        config_dir: 配置目录
        vehicle_suffix: 车型后缀（如 "evLTO"、"reevLTO"）
        domain: 领域标识（如 "economy"、"power"），用于匹配文件名

    Returns:
        str | None: 匹配的 YAML 文件路径，未找到返回 None
    """
    all_yamls = sorted(glob.glob(os.path.join(config_dir, "workflow_*.yaml")))
    if not all_yamls:
        print(f"[workflow_discovery] 配置目录 {config_dir} 下未找到 workflow_*.yaml 文件")
        return None

    suffix_lower = vehicle_suffix.lower() if vehicle_suffix else ""
    domain_lower = domain.lower() if domain else ""

    # 规则1: 尝试精确匹配车型后缀
    for yaml_path in all_yamls:
        filename = os.path.basename(yaml_path).lower()
        if suffix_lower and suffix_lower in filename:
            return yaml_path

    # 规则2: 根据能源类型匹配
    is_reev = "reev" in suffix_lower
    for yaml_path in all_yamls:
        filename = os.path.basename(yaml_path).lower()
        if is_reev and "reev" in filename:
            return yaml_path
        if not is_reev and "ev_" in filename and "reev" not in filename:
            return yaml_path

    # 规则3: 匹配 domain
    if domain_lower:
        for yaml_path in all_yamls:
            filename = os.path.basename(yaml_path).lower()
            if domain_lower in filename:
                return yaml_path

    # 无匹配，返回 None（不再静默 fallback 到第一个文件）
    print(f"[workflow_discovery] 未找到匹配车型 '{vehicle_suffix}' 的工作流 YAML")
    return None