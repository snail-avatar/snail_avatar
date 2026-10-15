# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : run_full_calculation.py
# @Desc    : 抽象基类：执行完整工作流计算
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
抽象基类：执行完整工作流计算

所有需要触发工作流完整计算的 agent 都可以继承此类。
子类需要设置 name、description、tool_title 等属性。
"""

from __future__ import annotations

from typing import Any, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from ...common.memory_db import get_memory_db


class AbstractRunFullCalculationFunction(FunctionBase):
    """执行完整工作流计算的抽象基类"""

    name: str = ""
    description: str = ""
    tool_title: str = ""

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
                            "description": "车型后缀，如 'evlto'，用于加载匹配的工作流",
                        },
                    },
                    "required": ["vehicle_suffix"],
                },
            },
        }

    @classmethod
    def execute(cls, args: dict[str, Any], context: Any = None) -> dict[str, Any]:
        vehicle_suffix = args.get("vehicle_suffix", "")

        if not vehicle_suffix:
            return {"type": "text", "content": f"[{cls.tool_title}]\n参数错误：必须提供 vehicle_suffix。"}

        db = get_memory_db()
        if db is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：未初始化 MemoryDatabase 引用。"}

        workflow = None
        if context is not None and hasattr(context, "get_workflow_for_vehicle"):
            workflow = context.get_workflow_for_vehicle(vehicle_suffix)
        
        if workflow is None and hasattr(cls, '_context_getter') and cls._context_getter is not None:
            try:
                workflow = cls._context_getter(vehicle_suffix)
            except Exception as e:
                print(f"[AbstractRunFullCalculationFunction] _context_getter 获取工作流失败: {e}")

        if workflow is None:
            return {"type": "text", "content": f"[{cls.tool_title}]\n错误：无法加载工作流实例。\n提示：请确保 Agent 已正确初始化并导入了车型数据。"}

        try:
            calc_success = False
            if hasattr(workflow, "run_all"):
                workflow.run_all(reset_first=True)
                calc_success = True
            else:
                return {"type": "text", "content": f"[{cls.tool_title}]\n[警告] 工作流不支持 run_all() 方法。"}

            from ..node_query_helper import extract_vts_params_from_workflow
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
                    "title": f"{cls.tool_title} - 计算结果",
                    "columns": columns,
                    "column_labels": column_labels,
                    "column_formats": column_formats,
                    "rows": rows,
                    "summary": {
                        "vehicle_suffix": vehicle_suffix,
                        "calc_success": calc_success,
                        "total_params": len(vts_params),
                    }
                }
            else:
                return {"type": "text", "content": f"[{cls.tool_title}]\n目标车型: {vehicle_suffix}\n[成功] 计算完成\n\n未检测到 VTS 输出参数。\n提示：可调用 get_node_info(node_id) 查看中间计算结果，或使用 get_node_output(node_id, output_var_name, vehicle_suffix) 查看任意节点的详细输出值。"}

        except Exception as e:
            import traceback
            return {"type": "text", "content": f"[{cls.tool_title}]\n[错误] 计算过程中发生异常: {e}\n详细错误信息:\n{traceback.format_exc()}"}