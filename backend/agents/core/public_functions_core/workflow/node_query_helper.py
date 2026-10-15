# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_query_helper.py
# @Desc    : 跨 Agent 共享模块：工作流节点信息查询工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
跨 Agent 共享模块：工作流节点信息查询工具

提供对工作流中的节点信息的通用查询能力：
1. get_workflow_node_list - 获取工作流中所有节点的基本信息
2. get_node_inputs_outputs - 获取指定节点的详细输入输出信息
3. get_node_output_value - 读取指定节点的某个输出变量值
4. extract_vts_params_from_workflow - 从工作流中提取所有 VTS 输出参数

适用于所有基于工作流（workflow）引擎的计算型 agent。
"""

from __future__ import annotations

from typing import Any, Dict

from ..common.memory_db import get_memory_db
from ..common.value_formatter import (
    detect_value_type,
    extract_time_series_stats,
    format_value_for_display,
)


def get_workflow_node_list(workflow: Any) -> list[dict[str, Any]]:
    """获取工作流中所有节点的基本信息

    Args:
        workflow: 工作流对象（应具有 all_nodes 或 graph.nodes 属性）

    Returns:
        list[dict]: 每个元素包含:
            - node_id: 节点ID
            - node_display_name: 显示名称
            - node_category: 分类
            - node_description: 描述
            - upstream_nodes: 上游依赖节点ID列表
            - ssts_input_count: SSTS 输入变量数
            - intermediate_input_count: 中间变量输入数
            - intermediate_output_count: 中间变量输出数
            - has_vts_output: 是否输出 VTS 参数
    """
    nodes_info: list[dict[str, Any]] = []

    nodes_dict = getattr(workflow, "all_nodes", None)
    if nodes_dict is None:
        graph = getattr(workflow, "graph", None)
        if graph is not None:
            nodes_dict = getattr(graph, "nodes", {})

    if not nodes_dict:
        return nodes_info

    topology_config = getattr(workflow, "topology_config", {})
    topology_nodes = topology_config.get("nodes", {}) if topology_config else {}

    for node_id, wf_node in sorted(nodes_dict.items()):
        node_instance = getattr(wf_node, "node_instance", None)
        if node_instance is None:
            continue

        upstream = []
        if node_id in topology_nodes:
            node_config = topology_nodes[node_id]
            upstream = node_config.get("upstream", [])

        ssts_schema = getattr(node_instance, "ssts_vts_schema", {})
        ssts_input_count = sum(
            1 for schema in ssts_schema.values()
            if schema.get("direction") == "input"
        )

        inter_inputs = getattr(node_instance, "intermediate_input_values", {})
        inter_input_count = len(inter_inputs)

        inter_output_schema = getattr(node_instance, "intermediate_output_schema", {})
        inter_output_count = len(inter_output_schema)

        has_vts_output = any(
            schema.get("direction") == "output"
            for schema in ssts_schema.values()
        )

        nodes_info.append({
            "node_id": node_id,
            "node_display_name": getattr(node_instance, "node_display_name", node_id),
            "node_category": getattr(node_instance, "node_category", ""),
            "node_description": getattr(node_instance, "node_description", ""),
            "upstream_nodes": upstream,
            "ssts_input_count": ssts_input_count,
            "intermediate_input_count": inter_input_count,
            "intermediate_output_count": inter_output_count,
            "has_vts_output": has_vts_output,
        })

    return nodes_info


def get_node_inputs_outputs(workflow: Any, node_id: str) -> dict[str, Any]:
    """获取指定节点的详细输入输出信息

    Args:
        workflow: 工作流对象
        node_id: 节点ID

    Returns:
        dict: 包含基本信息、SSTS 输入、中间变量输入、中间变量输出、VTS 输出
    """
    result: dict[str, Any] = {
        "node_id": node_id,
        "node_display_name": "",
        "node_category": "",
        "node_description": "",
        "upstream_nodes": [],
        "ssts_inputs": {},
        "intermediate_inputs": {},
        "intermediate_outputs": {},
        "vts_outputs": {},
        "node_found": False,
    }

    nodes_dict = getattr(workflow, "all_nodes", None)
    if nodes_dict is None:
        graph = getattr(workflow, "graph", None)
        if graph is not None:
            nodes_dict = getattr(graph, "nodes", {})

    if not nodes_dict or node_id not in nodes_dict:
        return result

    wf_node = nodes_dict[node_id]
    node_instance = getattr(wf_node, "node_instance", None)
    if node_instance is None:
        return result

    result["node_found"] = True
    result["node_display_name"] = getattr(node_instance, "node_display_name", node_id)
    result["node_category"] = getattr(node_instance, "node_category", "")
    result["node_description"] = getattr(node_instance, "node_description", "")

    topology_config = getattr(workflow, "topology_config", {})
    topology_nodes = topology_config.get("nodes", {}) if topology_config else {}
    if node_id in topology_nodes:
        result["upstream_nodes"] = topology_nodes[node_id].get("upstream", [])

    # SSTS 输入
    ssts_schema = getattr(node_instance, "ssts_vts_schema", {})
    ssts_values = getattr(node_instance, "_ssts_values", {})
    vehicle_suffix = getattr(node_instance, "vehicle_suffix", "")
    
    for var_name, schema in ssts_schema.items():
        if schema.get("direction") == "input":
            current_value = ssts_values.get(var_name, "未设置")
            # 构建完整的 db_key：{var_name}_result_{vehicle_suffix}
            db_key = f"{var_name}_result_{vehicle_suffix}" if vehicle_suffix else ""
            result["ssts_inputs"][var_name] = {
                "unit": schema.get("unit", ""),
                "description": schema.get("description", var_name),
                "current_value": current_value,
                "db_key": db_key,
            }
        elif schema.get("direction") == "output":
            db_key = schema.get(
                "db_key",
                f"{var_name}_result_{getattr(node_instance, 'vehicle_suffix', '')}"
            )
            current_value = "未计算"
            db = get_memory_db()
            if db and hasattr(db, "get_ssts_vts_param"):
                current_value = db.get_ssts_vts_param(db_key)
            result["vts_outputs"][var_name] = {
                "db_key": db_key,
                "unit": schema.get("unit", ""),
                "description": schema.get("description", var_name),
                "current_value": current_value,
            }

    # 中间变量输入
    inter_inputs = getattr(node_instance, "intermediate_input_values", {})
    for var_name, value in inter_inputs.items():
        result["intermediate_inputs"][var_name] = {
            "type": detect_value_type(value),
            "current_value": format_value_for_display(value),
        }

    # 中间变量输出
    inter_output_schema = getattr(node_instance, "intermediate_output_schema", {})
    inter_output_values = getattr(node_instance, "intermediate_output_values", {})
    for var_name, schema in inter_output_schema.items():
        current_value = inter_output_values.get(var_name, "未计算")
        result["intermediate_outputs"][var_name] = {
            "type": schema.get("type", "unknown"),
            "unit": schema.get("unit", ""),
            "description": schema.get("description", var_name),
            "current_value": format_value_for_display(current_value),
        }

    return result


def get_node_output_value(workflow: Any, node_id: str, output_var_name: str) -> dict[str, Any]:
    """读取指定节点的某个输出变量值

    Args:
        workflow: 工作流对象
        node_id: 节点ID
        output_var_name: 输出变量名

    Returns:
        dict: 包含 value、type、unit、stats、found、node_found、var_found 等字段
    """
    result: dict[str, Any] = {
        "value": None,
        "type": "unknown",
        "unit": "",
        "stats": {},
        "found": False,
        "node_found": False,
        "var_found": False,
    }

    nodes_dict = getattr(workflow, "all_nodes", None)
    if nodes_dict is None:
        graph = getattr(workflow, "graph", None)
        if graph is not None:
            nodes_dict = getattr(graph, "nodes", {})

    if not nodes_dict or node_id not in nodes_dict:
        return result

    result["node_found"] = True
    wf_node = nodes_dict[node_id]
    node_instance = getattr(wf_node, "node_instance", None)
    if node_instance is None:
        return result

    # 先从中间变量输出查找
    inter_output_values = getattr(node_instance, "intermediate_output_values", {})
    inter_output_schema = getattr(node_instance, "intermediate_output_schema", {})

    if output_var_name in inter_output_values:
        result["var_found"] = True
        value = inter_output_values[output_var_name]
        schema = inter_output_schema.get(output_var_name, {})
        result["value"] = value
        result["type"] = detect_value_type(value)
        result["unit"] = schema.get("unit", "")
        result["stats"] = extract_time_series_stats(value)
        result["found"] = True
        return result

    # 如果不在中间变量输出，检查是否是 VTS 输出
    ssts_schema = getattr(node_instance, "ssts_vts_schema", {})
    if output_var_name in ssts_schema and ssts_schema[output_var_name].get("direction") == "output":
        result["var_found"] = True
        db_key = ssts_schema[output_var_name].get(
            "db_key",
            f"{output_var_name}_result_{getattr(node_instance, 'vehicle_suffix', '')}"
        )
        result["unit"] = ssts_schema[output_var_name].get("unit", "")

        # 从数据库读取 VTS 输出值
        db = get_memory_db()
        if db and hasattr(db, "get_ssts_vts_param"):
            value = db.get_ssts_vts_param(db_key)
            result["value"] = value
            result["type"] = detect_value_type(value)
            result["stats"] = extract_time_series_stats(value)
            result["found"] = True

    return result


def extract_vts_params_from_workflow(workflow: Any) -> dict[str, dict[str, Any]]:
    """从工作流中提取所有 VTS 输出参数

    Args:
        workflow: 工作流对象

    Returns:
        dict: {var_name: {"node_id", "db_key", "unit", "description", "current_value"}}
    """
    result: dict[str, dict[str, Any]] = {}

    nodes_dict = getattr(workflow, "all_nodes", None)
    if nodes_dict is None:
        graph = getattr(workflow, "graph", None)
        if graph is not None:
            nodes_dict = getattr(graph, "nodes", {})

    if not nodes_dict:
        return result

    for node_id, wf_node in nodes_dict.items():
        node_instance = getattr(wf_node, "node_instance", None)
        if node_instance is None:
            continue

        ssts_schema = getattr(node_instance, "ssts_vts_schema", {})
        for var_name, schema in ssts_schema.items():
            if schema.get("direction") == "output":
                db_key = schema.get(
                    "db_key",
                    f"{var_name}_result_{getattr(node_instance, 'vehicle_suffix', '')}"
                )

                current_value = "未计算"
                db = get_memory_db()
                if db and hasattr(db, "get_ssts_vts_param"):
                    current_value = db.get_ssts_vts_param(db_key)

                result[var_name] = {
                    "node_id": node_id,
                    "db_key": db_key,
                    "unit": schema.get("unit", ""),
                    "description": schema.get("description", var_name),
                    "current_value": current_value,
                }

    return result