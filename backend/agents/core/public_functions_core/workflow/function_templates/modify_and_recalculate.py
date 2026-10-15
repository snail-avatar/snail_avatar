# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : modify_and_recalculate.py
# @Desc    : 抽象基类：修改目标值并重新计算
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：修改目标值并重新计算

所有需要修改参数值并触发重新计算的 agent 都可以继承此类。
这是一个通用的模板，具体实现需要根据 agent 的业务逻辑来覆盖关键方法。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db


class AbstractModifyAndRecalculateFunction(FunctionBase):
    """修改目标值并重新计算的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

    @classmethod
    def _modify_parameter(cls, workflow: Any, db: Any,
                           node_id: str, var_name: str, new_value: Any) -> bool:
        """子类可覆盖：将新值写入某个节点的输入参数。

        默认行为：尝试调用 workflow 的方法或直接修改节点属性。

        Returns:
            bool: True 表示修改成功，False 表示失败或未找到。
        """
        nodes_dict = getattr(workflow, "all_nodes", None)
        if nodes_dict is None:
            graph = getattr(workflow, "graph", None)
            if graph is not None:
                nodes_dict = getattr(graph, "nodes", {})

        if nodes_dict and node_id in nodes_dict:
            wf_node = nodes_dict[node_id]
            node_instance = getattr(wf_node, "node_instance", None)
            if node_instance is not None:
                ssts_values = getattr(node_instance, "_ssts_values", None)
                if isinstance(ssts_values, dict) and var_name in ssts_values:
                    try:
                        ssts_values[var_name] = new_value

                        vehicle_suffix = getattr(node_instance, "vehicle_suffix", "")
                        if db is not None and vehicle_suffix:
                            db_key = f"{var_name}_result_{vehicle_suffix}"
                            if hasattr(db, "set_ssts_vts_param"):
                                db.set_ssts_vts_param(db_key, new_value)

                        return True
                    except Exception:
                        pass

        return False

    @classmethod
    def _modify_parameter_by_db_key(cls, db: Any, db_key: str, new_value: Any) -> bool:
        """通过 db_key 直接修改 MemoryCore 中的参数

        Args:
            db: 内存数据库引用
            db_key: 完整的数据库键名（如 "cd_wt_result_reevlto"）
            new_value: 新值

        Returns:
            bool: True 表示修改成功，False 表示失败或未找到。
        """
        if db is None or not db_key:
            return False

        try:
            if hasattr(db, "set_ssts_vts_param"):
                success = db.set_ssts_vts_param(db_key, new_value)
                return success
        except Exception:
            pass

        return False

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
                        "db_key": {
                            "type": "string",
                            "description": "参数的数据库唯一标识符（如 'cd_wt_result_reevlto'），优先使用此参数",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "节点ID（当使用 node_id+input_var_name 方式时必填）",
                        },
                        "input_var_name": {
                            "type": "string",
                            "description": "输入变量名（当使用 node_id+input_var_name 方式时必填）",
                        },
                        "new_value": {
                            "type": "string",
                            "description": "新值（字符串表示，数字请直接写数字）",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀，如 'evlto'",
                        },
                    },
                    "required": ["new_value", "vehicle_suffix"],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> dict[str, Any]:
        db_key = args.get("db_key", "").strip()
        node_id = args.get("node_id", "")
        input_var_name = args.get("input_var_name", "")
        new_value_raw = args.get("new_value", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        if new_value_raw == "" or not vehicle_suffix:
            return {"type": "text", "content": f"[{cls.tool_title}]\n参数错误：必须提供 new_value 和 vehicle_suffix。\n\n使用方式：\n  方式1（推荐）：modify_economy_ssts_and_recalculate(db_key='xxx_result_veh', new_value=xxx, vehicle_suffix='veh')\n  方式2（兼容）：modify_economy_ssts_and_recalculate(node_id='xxx', input_var_name='yyy', new_value=xxx, vehicle_suffix='veh')"}

        if not db_key and (not node_id or not input_var_name):
            return {"type": "text", "content": f"[{cls.tool_title}]\n参数错误：必须提供 db_key，或同时提供 node_id 和 input_var_name。\n\n使用方式：\n  方式1（推荐）：modify_economy_ssts_and_recalculate(db_key='xxx_result_veh', new_value=xxx, vehicle_suffix='veh')\n  方式2（兼容）：modify_economy_ssts_and_recalculate(node_id='xxx', input_var_name='yyy', new_value=xxx, vehicle_suffix='veh')"}

        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：未初始化 MemoryDatabase 引用。"}

        new_value: Any = new_value_raw
        try:
            if "." in new_value_raw or "e" in new_value_raw.lower():
                new_value = float(new_value_raw)
            else:
                new_value = int(new_value_raw)
        except (ValueError, TypeError):
            pass

        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)

        try:
            success = False
            
            if db_key:
                success = cls._modify_parameter_by_db_key(db, db_key, new_value)
                if success and workflow is not None:
                    var_name = db_key.replace(f"_result_{vehicle_suffix}", "")
                    cls._update_workflow_node_cache(workflow, var_name, new_value)
            else:
                if workflow is None:
                    return {"type": "text", "content": f"[{cls.tool_title}]\n错误：无法加载工作流实例（使用 node_id+input_var_name 方式需要工作流）。"}
                success = cls._modify_parameter(workflow, db, node_id, input_var_name, new_value)

            if success:
                recalc_success = False
                if workflow is not None and hasattr(workflow, "run_all"):
                    workflow.run_all(reset_first=True)
                    recalc_success = True

                from ..node_query_helper import extract_vts_params_from_workflow
                vts_params = {}
                if workflow is not None:
                    vts_params = extract_vts_params_from_workflow(workflow)

                if vts_params:
                    columns = ["参数名", "当前值", "单位", "db_key"]
                    column_labels = {
                        "参数名": "参数名称",
                        "当前值": "当前值",
                        "单位": "单位",
                        "db_key": "数据库键",
                    }
                    column_formats = {
                        "当前值": ".2f",
                    }

                    rows = []
                    for var_name, info in vts_params.items():
                        rows.append({
                            "参数名": info.get("description", var_name),
                            "当前值": info.get("current_value", "未计算"),
                            "单位": info.get("unit", ""),
                            "db_key": info.get("db_key", ""),
                        })
                    return {
                        "type": "table",
                        "title": f"{cls.tool_title} - 修改结果",
                        "columns": columns,
                        "column_labels": column_labels,
                        "column_formats": column_formats,
                        "rows": rows,
                        "summary": {
                            "vehicle_suffix": vehicle_suffix,
                            "modify_method": "db_key" if db_key else "node_id+input_var_name",
                            "target": db_key if db_key else f"{node_id}/{input_var_name}",
                            "new_value": new_value,
                            "recalculated": recalc_success,
                        }
                    }
                else:
                    return {
                        "type": "text",
                        "content": f"[{cls.tool_title}]\n目标车型: {vehicle_suffix}\n修改方式: {'db_key' if db_key else 'node_id+input_var_name'}\n目标: {db_key if db_key else f'{node_id}/{input_var_name}'}\n新值: {new_value}\n重新计算: {'成功' if recalc_success else '跳过'}\n\n未检测到 VTS 输出参数。\n提示：可使用 get_node_output(node_id, output_var_name, vehicle_suffix) 查看详细输出。"
                    }
            else:
                suggestions = []
                if db_key:
                    suggestions = cls._find_matching_db_keys(db, db_key, vehicle_suffix)
                
                error_msg = f"[{cls.tool_title}]\n目标车型: {vehicle_suffix}\n[警告] 参数修改未成功。"
                if db_key:
                    error_msg += f"\n提示：请检查 db_key 是否正确。可先调用 get_economy_node_info 获取正确的 db_key。"
                    if suggestions:
                        error_msg += f"\n\n可能的正确 db_key：\n" + "\n".join([f"  • {key}" for key in suggestions])
                else:
                    error_msg += f"\n提示：请检查 node_id 和 input_var_name 是否正确，或该变量是否为可修改的输入参数。"
                
                return {"type": "text", "content": error_msg}

        except Exception as e:
            return {"type": "text", "content": f"[{cls.tool_title}]\n[错误] 操作过程中发生异常: {e}"}

    @classmethod
    def _update_workflow_node_cache(cls, workflow: Any, var_name: str, new_value: Any) -> None:
        """更新工作流中所有节点的缓存值"""
        nodes_dict = getattr(workflow, "all_nodes", None)
        if nodes_dict is None:
            graph = getattr(workflow, "graph", None)
            if graph is not None:
                nodes_dict = getattr(graph, "nodes", {})

        if nodes_dict:
            for wf_node in nodes_dict.values():
                node_instance = getattr(wf_node, "node_instance", None)
                if node_instance is not None:
                    ssts_values = getattr(node_instance, "_ssts_values", None)
                    if isinstance(ssts_values, dict) and var_name in ssts_values:
                        ssts_values[var_name] = new_value

    @classmethod
    def _find_matching_db_keys(cls, db: Any, pattern: str, vehicle_suffix: str) -> list[str]:
        """根据模式查找可能的 db_key"""
        matches = []
        if not db or not hasattr(db, 'memorycore'):
            return matches

        try:
            for veh_data in db.memorycore.values():
                for sheet_data in veh_data.values():
                    if isinstance(sheet_data, dict):
                        for cat1_data in sheet_data.values():
                            for cat2_data in cat1_data.values():
                                for item in cat2_data:
                                    if "参数值" in item:
                                        for param_item in item["参数值"]:
                                            item_db_key = param_item.get("db_key", "")
                                            if pattern.lower() in item_db_key.lower():
                                                matches.append(item_db_key)
                    else:
                        for item in sheet_data:
                            item_db_key = item.get("db_key", "")
                            if pattern.lower() in item_db_key.lower():
                                matches.append(item_db_key)
        except Exception:
            pass

        return sorted(set(matches))[:5]