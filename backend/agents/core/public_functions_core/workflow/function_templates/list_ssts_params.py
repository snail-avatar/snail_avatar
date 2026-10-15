# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : list_ssts_params.py
# @Desc    : 抽象基类：列出 SSTS 参数
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：列出 SSTS 参数

所有需要查询 SSTS 参数列表的计算型 agent 都可以继承此类。
支持按节点筛选、按 db_key 查询单个参数值。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db


class AbstractListSSTSParamsFunction(FunctionBase):
    """列出 SSTS 参数的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

    @classmethod
    def _collect_params_from_workflow(cls, workflow: Any, node_id: str = "") -> list[dict[str, Any]]:
        """从工作流中收集参数信息"""
        params: list[dict[str, Any]] = []

        nodes_dict = getattr(workflow, "all_nodes", None)
        if nodes_dict is None:
            graph = getattr(workflow, "graph", None)
            if graph is not None:
                nodes_dict = getattr(graph, "nodes", {})

        if not nodes_dict:
            return params

        target_nodes = list(nodes_dict.items())
        if node_id and node_id in nodes_dict:
            target_nodes = [(node_id, nodes_dict[node_id])]

        for nid, wf_node in target_nodes:
            node_instance = getattr(wf_node, "node_instance", None)
            if node_instance is None:
                continue

            ssts_schema = getattr(node_instance, "ssts_vts_schema", {})
            ssts_values = getattr(node_instance, "_ssts_values", {})
            vehicle_suffix = getattr(node_instance, "vehicle_suffix", "")

            for var_name, schema in ssts_schema.items():
                direction = schema.get("direction", "")
                current_value = ssts_values.get(var_name, "未设置")
                unit = schema.get("unit", "")
                description = schema.get("description", var_name)
                db_key = f"{var_name}_result_{vehicle_suffix}" if vehicle_suffix else var_name

                params.append({
                    "node_id": nid,
                    "var_name": var_name,
                    "direction": direction,
                    "current_value": current_value,
                    "unit": unit,
                    "description": description,
                    "db_key": db_key,
                })

        return params

    @classmethod
    def _get_param_by_db_key(cls, db: Any, db_key: str) -> Optional[dict[str, Any]]:
        """通过 db_key 查询单个参数值"""
        if db is None or not db_key:
            return None

        try:
            value = db.get_ssts_vts_param(db_key)
            if value is not None:
                return {
                    "db_key": db_key,
                    "value": value,
                    "found": True,
                }
        except Exception:
            pass

        return None

    @classmethod
    def get_schema(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "节点ID（可选，指定则只返回该节点的参数）",
                        },
                        "db_key": {
                            "type": "string",
                            "description": "数据库键名（可选，指定则只查询该参数的值）",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀，如 'evlto'",
                        },
                    },
                    "required": [],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> dict[str, Any]:
        node_id = args.get("node_id", "")
        db_key = args.get("db_key", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：未初始化 MemoryDatabase 引用。"}

        if db_key:
            param_info = cls._get_param_by_db_key(db, db_key)
            if param_info:
                return {
                    "type": "table",
                    "title": f"{cls.tool_title} - 参数查询结果",
                    "columns": ["db_key", "值"],
                    "rows": [{"db_key": param_info["db_key"], "值": param_info["value"]}],
                }
            else:
                return {"type": "text", "content": f"[{cls.tool_title}]\n未找到 db_key: {db_key}\n提示：可调用 list_*_ssts_params() 不带参数获取所有参数列表。"}

        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)

        if workflow is None and vehicle_suffix:
            return {"type": "text", "content": f"[{cls.tool_title}]\n警告：无法加载工作流实例，将从 MemoryCore 直接查询。"}

        params = []
        if workflow is not None:
            params = cls._collect_params_from_workflow(workflow, node_id)

        if not params:
            return {"type": "text", "content": f"[{cls.tool_title}]\n未找到参数信息。\n提示：请确保工作流已初始化并导入了车型数据。"}

        columns = ["节点ID", "参数名", "方向", "描述", "当前值", "单位", "db_key"]
        rows = []
        for p in params:
            rows.append({
                "节点ID": p["node_id"],
                "参数名": p["var_name"],
                "方向": p["direction"],
                "描述": p["description"],
                "当前值": p["current_value"],
                "单位": p["unit"],
                "db_key": p["db_key"],
            })

        return {
            "type": "table",
            "title": f"{cls.tool_title}",
            "columns": columns,
            "rows": rows,
            "summary": {
                "total_params": len(params),
                "vehicle_suffix": vehicle_suffix,
                "node_id": node_id,
            },
        }