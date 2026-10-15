# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : run_doe_analysis.py
# @Desc    : 抽象基类：运行 DOE（Design of Experiments）参数灵敏度分析
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：运行 DOE（Design of Experiments）参数灵敏度分析

所有需要进行多参数组合扫描分析的 agent 都可以继承此类。
子类需要覆盖关键方法：_collect_sensitive_params 和 _run_single_calculation。
"""

from __future__ import annotations

import copy
import json
from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db


class AbstractDOEAnalysisFunction(FunctionBase):
    """运行 DOE 分析的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

    @classmethod
    def _collect_sensitive_params(cls, workflow: Any, node_id: str = "") -> list[dict[str, Any]]:
        """子类可覆盖：从工作流中收集可扫描的参数列表

        默认实现：查找节点中的 ssts_vts_schema 并筛选 direction=input 的参数。
        """
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

            for var_name, schema in ssts_schema.items():
                if schema.get("direction") == "input":
                    current_value = ssts_values.get(var_name, 0)
                    if isinstance(current_value, (int, float)):
                        params.append({
                            "node_id": nid,
                            "var_name": var_name,
                            "current_value": current_value,
                            "min_val": current_value * 0.9,
                            "max_val": current_value * 1.1,
                            "unit": schema.get("unit", ""),
                            "description": schema.get("description", var_name),
                        })

        return params

    @classmethod
    def _collect_output_vars(cls, workflow: Any) -> list[dict[str, Any]]:
        """子类可覆盖：从工作流中收集输出变量列表

        默认实现：查找 vts_outputs 以及 intermediate_outputs 中数值型的输出。
        """
        outputs: list[dict[str, Any]] = []

        nodes_dict = getattr(workflow, "all_nodes", None)
        if nodes_dict is None:
            graph = getattr(workflow, "graph", None)
            if graph is not None:
                nodes_dict = getattr(graph, "nodes", {})

        if not nodes_dict:
            return outputs

        for nid, wf_node in nodes_dict.items():
            node_instance = getattr(wf_node, "node_instance", None)
            if node_instance is None:
                continue

            ssts_schema = getattr(node_instance, "ssts_vts_schema", {})
            for var_name, schema in ssts_schema.items():
                if schema.get("direction") == "output":
                    outputs.append({
                        "node_id": nid,
                        "var_name": var_name,
                        "unit": schema.get("unit", ""),
                    })

            inter_output_schema = getattr(node_instance, "intermediate_output_schema", {})
            for var_name, schema in inter_output_schema.items():
                outputs.append({
                    "node_id": nid,
                    "var_name": var_name,
                    "unit": schema.get("unit", ""),
                })

        return outputs

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
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀，如 'evlto'",
                        },
                        "target_params": {
                            "type": "array",
                            "description": "指定分析的参数及扰动范围（必填）。可根据 semantic_overview 的计算流信息，选择关键输入参数",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "node_id": {
                                        "type": "string",
                                        "description": "节点ID，如 'node_2_ResistanceCalculator'"
                                    },
                                    "var_name": {
                                        "type": "string",
                                        "description": "变量名，如 'mass_curb'"
                                    },
                                    "levels": {
                                        "type": "array",
                                        "description": "参数水平值列表（可选，默认 ±5% 扰动），如 [2100, 2337, 2600]",
                                        "items": {"type": "number"}
                                    }
                                },
                                "required": ["node_id", "var_name"]
                            }
                        },
                        "output_vars": {
                            "type": "array",
                            "description": "关注的输出变量列表（可选）。可根据 semantic_overview 的计算流信息，选择 VTS 指标或关键中间变量。格式：'node_id/var_name'",
                            "items": {"type": "string"}
                        },
                        "max_trials": {
                            "type": "integer",
                            "default": 50,
                            "description": "最大试算次数（硬上限 100）"
                        },
                        "node_id": {
                            "type": "string",
                            "description": "（可选）指定要扫描的节点ID，不指定则扫描所有节点的敏感参数（已废弃，请使用 target_params）",
                        },
                    },
                    "required": ["vehicle_suffix", "target_params"],
                },
            },
        }

    @classmethod
    def _select_doe_method(cls, params_count: int) -> str:
        """根据参数数量自动选择 DOE 方法"""
        if params_count <= 3:
            return "full_factorial"
        elif 4 <= params_count <= 6:
            return "taguchi"
        else:
            return "latin_hypercube"

    @classmethod
    def _generate_param_levels(cls, current_value: float, levels: list = None) -> list[float]:
        """生成参数水平值（默认 ±5% 扰动）"""
        if levels is not None and len(levels) >= 2:
            return sorted(levels)
        
        return [
            current_value * 0.95,
            current_value,
            current_value * 1.05
        ]

    @classmethod
    def _generate_full_factorial(cls, params: list[dict[str, Any]]) -> list[dict[str, float]]:
        """生成全因子试验组合"""
        import itertools
        levels = [p["levels"] for p in params]
        combinations = list(itertools.product(*levels))
        return [dict(zip([p["var_name"] for p in params], combo)) for combo in combinations]

    @classmethod
    def _generate_latin_hypercube(cls, params: list[dict[str, Any]], num_samples: int) -> list[dict[str, float]]:
        """生成 Latin Hypercube 试验组合"""
        import random
        
        samples = []
        for _ in range(num_samples):
            combo = {}
            for p in params:
                levels = p["levels"]
                idx = random.randint(0, len(levels) - 1)
                combo[p["var_name"]] = levels[idx]
            samples.append(combo)
        return samples

    @classmethod
    def _generate_taguchi(cls, params: list[dict[str, Any]]) -> list[dict[str, float]]:
        """生成 Taguchi 正交表试验组合（简化版：L9）"""
        import random
        
        num_params = len(params)
        num_samples = min(9, 3 ** num_params)
        
        samples = []
        for i in range(num_samples):
            combo = {}
            for p in params:
                levels = p["levels"]
                level_idx = i % len(levels)
                combo[p["var_name"]] = levels[level_idx]
            samples.append(combo)
        
        return samples

    @classmethod
    def _analyze_main_effects(cls, results: list[dict[str, Any]], params: list[dict[str, Any]], output_vars: list[str]) -> dict[str, Any]:
        """分析每个参数对输出的主效应"""
        effects = {}
        
        for var_str in output_vars:
            effects[var_str] = {}
            for p in params:
                param_key = f"{p['node_id']}/{p['var_name']}"
                level_values = {}
                
                for trial in results:
                    level = trial["params"].get(p["var_name"])
                    if level not in level_values:
                        level_values[level] = []
                    if var_str in trial and trial[var_str] is not None:
                        level_values[level].append(trial[var_str])
                
                effects[var_str][param_key] = {
                    level: sum(vals) / len(vals) if vals else 0
                    for level, vals in level_values.items()
                }
        
        return effects

    @classmethod
    def _rank_parameter_influence(cls, results: list[dict[str, Any]], params: list[dict[str, Any]], output_vars: list[str]) -> dict[str, list[dict[str, Any]]]:
        """按影响程度排序参数"""
        rankings = {}
        
        for var_str in output_vars:
            influences = []
            values = [trial[var_str] for trial in results if var_str in trial and trial[var_str] is not None]
            
            if not values:
                continue
            
            output_range = max(values) - min(values)
            output_mean = sum(values) / len(values) if len(values) > 0 else 0
            
            for p in params:
                param_key = f"{p['node_id']}/{p['var_name']}"
                param_levels = sorted(set([trial["params"].get(p["var_name"]) for trial in results]))
                
                if len(param_levels) >= 2:
                    param_range = param_levels[-1] - param_levels[0]
                    param_mean = sum(param_levels) / len(param_levels) if len(param_levels) > 0 else 0
                    
                    sensitivity = 0
                    if output_mean != 0 and param_mean != 0:
                        sensitivity = (output_range / output_mean) / (param_range / param_mean)
                    
                    influences.append({
                        "param": param_key,
                        "sensitivity": abs(sensitivity)
                    })
            
            rankings[var_str] = sorted(influences, key=lambda x: x["sensitivity"], reverse=True)
        
        return rankings

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> dict[str, Any]:
        vehicle_suffix = args.get("vehicle_suffix", "")
        target_params = args.get("target_params", [])
        output_vars = args.get("output_vars", [])
        param_ranges = args.get("param_ranges", {})
        max_trials = args.get("max_trials", 50)

        if isinstance(target_params, str):
            try:
                target_params = json.loads(target_params)
            except Exception:
                target_params = []

        if isinstance(output_vars, str):
            try:
                output_vars = json.loads(output_vars)
            except Exception:
                output_vars = []

        if isinstance(param_ranges, str):
            try:
                param_ranges = json.loads(param_ranges)
            except Exception:
                param_ranges = {}

        if not vehicle_suffix:
            return {"type": "text", "content": f"[{cls.tool_title}]\n参数错误：必须提供 vehicle_suffix。"}

        if not target_params:
            return {"type": "text", "content": f"[{cls.tool_title}]\n参数错误：必须提供 target_params。\n提示：请提供要分析的参数列表，格式为 [{{'node_id': '...', 'var_name': '...'}}]"}

        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：未初始化 MemoryDatabase 引用。"}

        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)

        if workflow is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：无法加载工作流实例。\n提示：请确保 Agent 已正确初始化并导入了车型数据。"}

        if not hasattr(workflow, "run_all"):
            return {"type": "text", "content": f"[{cls.tool_title}]\n[警告] 工作流不支持 run_all()，无法执行 DOE 分析。"}

        try:
            processed_params = []
            warnings = []
            for p in target_params:
                node_id = p.get("node_id", "")
                var_name = p.get("var_name", "")
                
                if not node_id or not var_name:
                    continue
                
                nodes_dict = getattr(workflow, "all_nodes", None)
                if nodes_dict is None:
                    graph = getattr(workflow, "graph", None)
                    if graph is not None:
                        nodes_dict = getattr(graph, "nodes", {})
                
                if not nodes_dict or node_id not in nodes_dict:
                    warnings.append(f"未找到节点 {node_id}，跳过")
                    continue
                
                wf_node = nodes_dict[node_id]
                node_instance = getattr(wf_node, "node_instance", None)
                if node_instance is None:
                    continue
                
                current_value = getattr(node_instance, "_ssts_values", {}).get(var_name)
                if current_value is None:
                    warnings.append(f"节点 {node_id} 中未找到参数 {var_name}，跳过")
                    continue
                
                levels = cls._generate_param_levels(current_value, p.get("levels"))
                processed_params.append({
                    "node_id": node_id,
                    "var_name": var_name,
                    "levels": levels,
                    "current_value": current_value
                })

            if not processed_params:
                return {"type": "text", "content": f"[{cls.tool_title}]\n[错误] 未能加载任何有效参数。\n提示：请检查 target_params 中的 node_id 和 var_name 是否正确。"}

            params_count = len(processed_params)
            doe_method = cls._select_doe_method(params_count)

            method_names = {
                "full_factorial": "全因子设计",
                "taguchi": "Taguchi 正交表",
                "latin_hypercube": "Latin Hypercube"
            }

            if doe_method == "full_factorial":
                trials = cls._generate_full_factorial(processed_params)
            elif doe_method == "taguchi":
                trials = cls._generate_taguchi(processed_params)
            else:
                trials = cls._generate_latin_hypercube(processed_params, min(max_trials, 100))

            max_allowed = min(max_trials, 100)
            truncated = False
            if len(trials) > max_allowed:
                trials = trials[:max_allowed]
                truncated = True

            if not output_vars:
                outputs = cls._collect_output_vars(workflow)
                output_vars = [f"{o['node_id']}/{o['var_name']}" for o in outputs[:5]]
            
            temp_db = copy.deepcopy(db)
            original_db = workflow.executor.memory_db
            workflow.executor.memory_db = temp_db
            for node_id, node in workflow.all_nodes.items():
                node.node_instance.memory_db = temp_db
            
            results = []
            try:
                for i, trial in enumerate(trials, 1):
                    for p in processed_params:
                        db_key = f"{p['var_name']}_result_{vehicle_suffix}"
                        temp_db.set_ssts_vts_param(db_key, trial[p["var_name"]])
                    
                    workflow.run_all(reset_first=True)
                    
                    output_result = {"trial": i, "params": trial}
                    for var_str in output_vars[:5]:
                        parts = var_str.split("/")
                        if len(parts) == 2:
                            node_id, var_name = parts
                            display_name = node_id
                            if node_id in workflow.all_nodes:
                                node = workflow.all_nodes[node_id]
                                node_instance = getattr(node, "node_instance", None)
                                if node_instance is not None:
                                    display_name = getattr(node_instance, "node_display_name", node_id)
                            vts_key = f"{var_name}_result_{vehicle_suffix}"
                            value = temp_db.get_ssts_vts_param(vts_key)
                            if value is not None:
                                output_result[var_str] = value
                                output_result[f"{display_name}/{var_name}"] = value
                    
                    results.append(output_result)
            
            finally:
                workflow.executor.memory_db = original_db
                for node_id, node in workflow.all_nodes.items():
                    node.node_instance.memory_db = original_db
                del temp_db
                try:
                    workflow.run_all(reset_first=True)
                except Exception as recover_error:
                    warnings.append(f"恢复工作流状态失败: {recover_error}")

            main_effects = cls._analyze_main_effects(results, processed_params, output_vars[:5])
            rankings = cls._rank_parameter_influence(results, processed_params, output_vars[:5])

            param_columns = ["参数", "当前值", "水平值"]
            param_rows = []
            for p in processed_params:
                param_key = f"{p['node_id']}/{p['var_name']}"
                levels_str = ", ".join([f"{v:.4g}" if isinstance(v, float) else str(v) for v in p["levels"]])
                param_rows.append({
                    "参数": param_key,
                    "当前值": p["current_value"],
                    "水平值": levels_str
                })

            result_columns = ["试算次数"] + [p["var_name"] for p in processed_params] + list(output_vars[:5])
            result_rows = []
            for r in results:
                row = {"试算次数": r["trial"]}
                for p in processed_params:
                    row[p["var_name"]] = r["params"].get(p["var_name"])
                for var in output_vars[:5]:
                    row[var] = r.get(var)
                result_rows.append(row)

            column_labels = {}
            column_formats = {}
            for col in result_columns:
                if col == "试算次数":
                    column_labels[col] = "试算次数"
                    column_formats[col] = ""
                elif "/" in col:
                    parts = col.split("/")
                    node_id, var_name = parts
                    display_name = var_name
                    unit = ""
                    if node_id in workflow.all_nodes:
                        node = workflow.all_nodes[node_id]
                        node_instance = getattr(node, "node_instance", None)
                        if node_instance is not None:
                            schema = getattr(node_instance, "ssts_vts_schema", {})
                            if var_name in schema:
                                display_name = schema[var_name].get("description", var_name)
                                unit = schema[var_name].get("unit", "")
                    column_labels[col] = f"{display_name}({unit})" if unit else display_name
                    column_formats[col] = ".1f"
                else:
                    column_labels[col] = col
                    column_formats[col] = ".2f"

            ranking_rows = []
            for var_str in output_vars[:3]:
                if var_str in rankings and rankings[var_str]:
                    for i, item in enumerate(rankings[var_str], 1):
                        ranking_rows.append({
                            "输出变量": var_str,
                            "排名": i,
                            "参数": item["param"],
                            "敏感度系数": f"{item['sensitivity']:.4g}"
                        })

            summary_text = f"[{cls.tool_title}]\n目标车型: {vehicle_suffix}\n试验方法: {method_names.get(doe_method, doe_method)}（自动选择）\n参数数量: {params_count}\n试算次数: {len(results)}"
            if truncated:
                summary_text += "\n[警告] 试验组合数超过最大限制，已截断为 100 次"
            if warnings:
                summary_text += "\n[警告] " + "; ".join(warnings)
            summary_text += "\n\n如需进一步优化，建议优先调整敏感度系数较高的参数。"

            return {
                "type": "table",
                "title": f"{cls.tool_title} - 车型 {vehicle_suffix}",
                "columns": result_columns,
                "column_labels": column_labels,
                "column_formats": column_formats,
                "rows": result_rows,
                "summary": {
                    "vehicle_suffix": vehicle_suffix,
                    "doe_method": method_names.get(doe_method, doe_method),
                    "params_count": params_count,
                    "trials_count": len(results),
                    "param_table": {"columns": param_columns, "rows": param_rows},
                    "ranking_table": {"columns": ["输出变量", "排名", "参数", "敏感度系数"], "rows": ranking_rows},
                    "warnings": warnings,
                    "text_summary": summary_text
                }
            }

        except Exception as e:
            import traceback
            return {"type": "text", "content": f"[{cls.tool_title}]\n[错误] DOE 分析过程中发生异常: {e}\n[详细] {traceback.format_exc()}"}