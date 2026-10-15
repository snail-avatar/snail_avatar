# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : semantic_summary.py
# @Desc    : 抽象基类：生成语义摘要
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：生成语义摘要

所有需要将工作流计算结果进行自然语言总结的 agent 都可以继承此类。
子类需要覆盖 _extract_domain_specific_info 等关键方法来填充业务特定信息。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase


class AbstractSemanticSummaryFunction(FunctionBase):
    """生成语义摘要的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

    domain_title: str = "计算"
    output_param_titles: dict[str, str] = {}

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
                            "description": "车型后缀标识（如 'evlto'、'reevlto'），用于指定要分析的车型工作流。"
                        }
                    },
                    "required": ["vehicle_suffix"],
                },
            },
        }

    _NODE_NAME_MAPPING: dict[str, str] = {
        "DriveCycleAnalyzer": "驾驶循环分析",
        "ResistanceCalculator": "阻力计算",
        "MotorWorkpoint": "电机工作点分析",
        "WheelEnergy": "车轮能量",
        "EDUEnergy": "EDU能量",
        "EVEnergyConsumption": "EV能耗",
        "REEVEnergyConsumption": "REEV能耗",
        "TireAdhesionLimit": "附着力极限",
        "GradeAdhesionLimit": "坡道附着力极限",
        "PowerLimitCalculator": "功率限制计算",
        "AccelTopSpeedCalculator": "加速时间与最高车速计算",
        "GradePerformanceCalculator": "爬坡性能计算",
    }

    @classmethod
    def _extract_domain_specific_info(cls, workflow: Any, db: Any,
                                       vehicle_suffix: str) -> list[str]:
        """子类应覆盖：填充业务特定的摘要信息。

        默认实现：从 vts_outputs 中读取所有输出参数的当前值。
        """
        from ..node_query_helper import extract_vts_params_from_workflow

        info_lines: list[str] = []
        vts_params = extract_vts_params_from_workflow(workflow)

        if not vts_params:
            return info_lines

        info_lines.append(f"本次{cls.domain_title}计算的核心指标如下：")
        info_lines.append("")

        for var_name, info in vts_params.items():
            title = cls.output_param_titles.get(var_name, var_name)
            current_value = info.get("current_value", "未计算")
            unit = info.get("unit", "")

            if isinstance(current_value, (int, float)):
                if unit:
                    info_lines.append(f"- {title}: {current_value:.4g} {unit}")
                else:
                    info_lines.append(f"- {title}: {current_value:.4g}")
            else:
                if unit:
                    info_lines.append(f"- {title}: {current_value} {unit}")
                else:
                    info_lines.append(f"- {title}: {current_value}")

        info_lines.append("")
        return info_lines

    @classmethod
    def _get_node_display_name(cls, node_id: str, workflow: Any = None) -> str:
        """从节点实例或节点ID提取显示名称"""
        if workflow is not None:
            all_nodes = getattr(workflow, "all_nodes", {})
            if node_id in all_nodes:
                node = all_nodes[node_id]
                node_instance = getattr(node, "node_instance", None)
                if node_instance is not None:
                    display_name = getattr(node_instance, "node_display_name", None)
                    if display_name:
                        return display_name

        parts = node_id.split('_')
        for part in parts:
            for key in cls._NODE_NAME_MAPPING:
                if key in part:
                    base_name = cls._NODE_NAME_MAPPING[key]
                    return base_name
        return node_id

    @classmethod
    def _is_upstream_of(cls, node_a: str, node_b: str, nodes_dict: dict) -> bool:
        """判断 node_a 是否在 node_b 的上游链中"""
        if node_a == node_b:
            return False

        visited = set()
        queue = [node_b]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            upstream = nodes_dict.get(current, {}).get("upstream", [])
            if node_a in upstream:
                return True

            for up_node in upstream:
                if up_node not in visited:
                    queue.append(up_node)

        return False

    @classmethod
    def _sort_nodes_by_dependency(cls, nodes: list[str], nodes_dict: dict) -> list[str]:
        """根据节点之间的依赖关系排序：上游节点在前"""
        sorted_nodes = []
        for node in nodes:
            inserted = False
            for i, existing_node in enumerate(sorted_nodes):
                if cls._is_upstream_of(node, existing_node, nodes_dict):
                    sorted_nodes.insert(i, node)
                    inserted = True
                    break
                elif cls._is_upstream_of(existing_node, node, nodes_dict):
                    continue
            if not inserted:
                sorted_nodes.append(node)
        return sorted_nodes

    @classmethod
    def _generate_workflow_overview(cls, workflow: Any) -> list[str]:
        """仅从配置文件结构信息生成计算流程概览"""
        lines: list[str] = []

        topology_config = getattr(workflow, "topology_config", {})
        nodes_dict = topology_config.get("nodes", {})
        if not nodes_dict:
            return lines

        lines.append("---")
        lines.append("## 计算流程概览")
        lines.append("")

        all_upstream = set()
        for node_id, config in nodes_dict.items():
            all_upstream.update(config.get("upstream", []))

        terminal_nodes = [
            node_id for node_id in nodes_dict.keys()
            if node_id not in all_upstream
        ]

        if not terminal_nodes:
            return lines

        all_flows_nodes: dict[str, list[str]] = {}

        for terminal in terminal_nodes:
            visited = set()
            path = []

            stack = [(terminal, False)]
            while stack:
                node_id, processed = stack.pop()

                if processed:
                    path.append(node_id)
                    continue

                if node_id in visited:
                    continue

                visited.add(node_id)
                stack.append((node_id, True))

                upstream_nodes = nodes_dict.get(node_id, {}).get("upstream", [])
                if not isinstance(upstream_nodes, list):
                    upstream_nodes = []
                sorted_upstream = cls._sort_nodes_by_dependency(upstream_nodes, nodes_dict)
                if not sorted_upstream:
                    sorted_upstream = upstream_nodes
                for up_node in reversed(sorted_upstream):
                    if up_node not in visited:
                        stack.append((up_node, False))

            all_flows_nodes[terminal] = path

        for terminal, flow_nodes in all_flows_nodes.items():
            flow_name = cls._get_node_display_name(terminal, workflow)
            lines.append(f"### {flow_name}")

            chain = []
            for node_id in flow_nodes:
                display_name = cls._get_node_display_name(node_id, workflow)
                chain.append(f"`{node_id}`({display_name})")

            lines.append(f"- 计算路径：{' → '.join(chain)}")

            reused_nodes: list[str] = []
            for node_id in flow_nodes:
                for other_terminal, other_flow_nodes in all_flows_nodes.items():
                    if other_terminal != terminal and node_id in other_flow_nodes:
                        reused_nodes.append(f"`{node_id}`({cls._get_node_display_name(node_id, workflow)})")
                        break

            if reused_nodes:
                unique_reused = sorted(set(reused_nodes))
                lines.append(f"- 复用节点：{', '.join(unique_reused)}")

            lines.append("")

        return lines

    @classmethod
    def _generate_domain_summary(cls, workflow: Any, db: Any,
                                  vehicle_suffix: str) -> list[str]:
        """生成领域分析摘要（如经济性核心指标）"""
        lines: list[str] = []
        lines.append("---")
        lines.append(f"## {cls.domain_title}分析摘要")
        lines.append("")

        domain_info = cls._extract_domain_specific_info(workflow, db, vehicle_suffix)
        if domain_info:
            lines.extend(domain_info)
        else:
            lines.append(f"未检测到明确的{cls.domain_title}指标。")
            lines.append("")

        return lines

    @classmethod
    def _generate_node_details(cls, workflow: Any, detail_mode: str = "summary") -> list[str]:
        """生成节点分析详情

        Args:
            detail_mode: summary（仅含计算结果摘要）/ logic（不含计算结果摘要）/ full（全部）
        """
        lines: list[str] = []
        lines.append("---")
        lines.append("## 各节点分析详情")
        lines.append("")

        from ..node_query_helper import get_workflow_node_list
        nodes = get_workflow_node_list(workflow)

        if not nodes:
            lines.append("暂无节点信息")
            lines.append("")
            return lines

        for node in nodes:
            node_id = node.get("node_id")
            node_desc = node.get("node_display_name") or node_id
            cat = node.get("node_category")

            node_instance = None
            if hasattr(workflow, 'all_nodes') and node_id in workflow.all_nodes:
                node_instance = workflow.all_nodes[node_id].node_instance

            semantic_summary = ""
            if node_instance:
                if hasattr(node_instance, 'intermediate_output_values'):
                    semantic_summary = node_instance.intermediate_output_values.get('semantic_summary', '')

                if not semantic_summary and hasattr(node_instance, 'semantic_solve'):
                    try:
                        semantic_summary = node_instance.semantic_solve()
                    except Exception:
                        pass

            if cat:
                lines.append(f"**分类**: {cat}")
                lines.append("")

            if semantic_summary:
                if detail_mode == "summary":
                    filtered_lines = []
                    in_summary_section = False
                    for line in semantic_summary.split('\n'):
                        if line == "#### 计算结果摘要":
                            in_summary_section = True
                            filtered_lines.append(line)
                            continue
                        if in_summary_section:
                            if re.match(r'^#### ', line):
                                break
                            filtered_lines.append(line)
                    summary_lines = filtered_lines
                elif detail_mode == "logic":
                    filtered_lines = []
                    in_summary_section = False
                    for line in semantic_summary.split('\n'):
                        if line == "#### 计算结果摘要":
                            in_summary_section = True
                            continue
                        if in_summary_section:
                            if re.match(r'^#### ', line):
                                in_summary_section = False
                                filtered_lines.append(line)
                            continue
                        filtered_lines.append(line)
                    summary_lines = filtered_lines
                else:
                    summary_lines = semantic_summary.split('\n')

                for line in summary_lines:
                    lines.append(line)
            else:
                lines.append("暂无详细分析")
            lines.append("")

        return lines

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> dict[str, Any]:
        vehicle_suffix = args.get("vehicle_suffix", "")

        if not vehicle_suffix:
            return {"type": "text", "content": f"[{cls.tool_title}]\n参数错误：必须提供 vehicle_suffix。"}

        from ...common.memory_db import get_memory_db
        db = get_memory_db()

        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)

        if workflow is None and hasattr(cls, '_context_getter') and cls._context_getter is not None:
            try:
                workflow = cls._context_getter(vehicle_suffix)
            except Exception as e:
                print(f"[AbstractSemanticSummaryFunction] _context_getter 获取工作流失败: {e}")

        if workflow is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：无法加载工作流实例。\n提示：请确保 Agent 已正确初始化并导入了车型数据。"}

        detail_mode = "summary"
        if cls.name and "logic" in cls.name:
            detail_mode = "logic"

        try:
            overview_lines = cls._generate_workflow_overview(workflow)
            domain_summary_lines = cls._generate_domain_summary(workflow, db, vehicle_suffix)
            node_detail_lines = cls._generate_node_details(workflow, detail_mode)

            all_lines = []
            all_lines.append(f"# {cls.tool_title}")
            all_lines.append(f"目标车型: {vehicle_suffix}")
            all_lines.append("")

            if overview_lines:
                all_lines.extend(overview_lines)

            if domain_summary_lines:
                all_lines.extend(domain_summary_lines)

            if node_detail_lines:
                all_lines.extend(node_detail_lines)

            return {
                "type": "text",
                "content": "\n".join(all_lines),
            }

        except Exception as e:
            import traceback
            return {"type": "text", "content": f"[{cls.tool_title}]\n[错误] 生成摘要过程中发生异常: {e}\n详细错误信息:\n{traceback.format_exc()}"}