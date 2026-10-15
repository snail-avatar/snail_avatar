# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_run_flow.py
# @Desc    : Function：执行目标值定义完整流程（run_flow）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Function：执行目标值定义完整流程

实现方式：复用 ProcessService（Panel 手动执行也用它），保证两条链路完全一致：
  - 同一个 ProcessContext 单例、同一个 ProcessEngine、同一套步骤
  - 进度推送走 RunState.queue（per-instance 独占，无竞争）→ /api/process/stream → Panel 进度组件
  - 防重复执行、中途停止/暂停天然支持

function_run_flow 退化为薄薄的适配层：
  1. 调 ProcessService.run_process() 启动后台线程
  2. 阻塞等待 RunState.done_event（带超时）
  3. 从 ProcessController 提取 FINAL_SUMMARY 文本
  4. 返回给 LLM
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db


def _extract_final_summary(controller, final_summary_step_id: str = "FINAL_SUMMARY") -> Dict[str, Any]:
    """从 controller._step_results 中提取最终总结步骤的结果

    Args:
        controller: ProcessController 实例
        final_summary_step_id: 最终总结步骤的 step_id（默认 "FINAL_SUMMARY" 兜底）

    Returns:
        Dict: {
            "found": bool,
            "content": str,       # LLM 总结文本
            "step_result": Dict, # 完整 step_result 原始数据
        }
    """
    results = controller._step_results if hasattr(controller, '_step_results') else []

    # 从后往前找最终总结步骤（列表可能包含多个循环项结果）
    for record in reversed(results):
        if record.get("step_id") == final_summary_step_id:
            step_result = record.get("step_result", {})
            # FINAL_SUMMARY 是 llm/text 模式，content 在 step_result 中
            # 可能的字段: content / result.content / final_summary
            content = ""
            if isinstance(step_result, dict):
                content = (
                    step_result.get("content", "")
                    or step_result.get("result", {}).get("content", "")
                    or step_result.get("final_summary", "")
                )
            if content:
                return {
                    "found": True,
                    "content": str(content),
                    "step_result": step_result,
                }
            # 没拿到 content，也返回原始 step_result 让 LLM 自行理解
            return {
                "found": True,
                "content": str(step_result) if step_result else "",
                "step_result": step_result,
            }

    return {
        "found": False,
        "content": "",
        "step_result": {},
    }


# LLM function 调用等待流程完成的最大秒数
# 兜底超时（秒）：长流程可能涉及多专业+DOE 分析，最高 1 小时
_WAIT_TIMEOUT_SECONDS = 3600


class RunTargetDefinitionFlowFunction(FunctionBase):
    """执行目标值定义完整流程（复用 ProcessService）"""

    name = "run_target_definition_flow"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "执行指定车型的完整目标值定义流程（专业检测→映射确定→法规校核→初版定义→达标验证→参数优化→最终总结）。"
                               "参数 vehicle_name 必须是 list_target_definition_vehicles 返回的 instance_key 值（括号里的那个），"
                               "不是车型中文名。此工具执行时间较长（几分钟），调用后请等待返回。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vehicle_name": {
                            "type": "string",
                            "description": "车型的 instance_key（memorycore key），如 'reevlto'、'reevlto_reev'。"
                                           "必须与 list_target_definition_vehicles 返回的值一致。"
                        }
                    },
                    "required": ["vehicle_name"],
                },
            },
        }

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        # ---- 1. 参数校验 ----
        instance_key = args.get("vehicle_name", "").strip()
        if not instance_key:
            return {"type": "text", "content": "参数错误：缺少必填字段 vehicle_name（instance_key）。请先调用 list_target_definition_vehicles 获取合法值。"}

        # 检查 memory_db
        memory_db = get_memory_db()
        if memory_db is None:
            return {"type": "text", "content": "当前未加载数据（memory_db 为空），请先导入 Excel 数据文件。"}

        # ---- 2. 启动流程（非阻塞，ProcessService 内部开后台线程跑 run_flow） ----
        # ProcessService.run_process 会自动：
        #   - 防并发（RunState.lock）
        #   - reset 执行状态（ctx.reset_execution_state）
        #   - 注册 callback 到 ProcessController（推进度到 RunState.queue → Panel SSE）
        #   - 开后台线程调 ctx.run_flow()
        #   - 完成后 set done_event + release lock
        try:
            from snail_avatar.backend.fastapi_app.services.process_service import ProcessService
        except Exception as e:
            return {"type": "text", "content": f"导入 ProcessService 失败: {e}"}

        start_result = ProcessService.run_process(instance_key, mode="ALL")
        if not start_result.get("ok"):
            already_running = start_result.get("already_running", False)
            if already_running:
                return {"type": "text", "content": f"车型 {instance_key} 的流程正在执行中，请等待完成后再调用。"}
            return {"type": "text", "content": f"启动流程失败: {start_result.get('message', '未知错误')}"}

        # ---- 3. 阻塞等待完成（带超时） ----
        state = ProcessService._get_or_create_state(instance_key)
        done = state.done_event.wait(timeout=_WAIT_TIMEOUT_SECONDS)

        if not done:
            # 超时不代表一定失败——流程可能还在后台跑
            return {
                "type": "text",
                "content": (
                    f"流程启动后已等待 {_WAIT_TIMEOUT_SECONDS} 秒仍未完成，可能仍在后台执行中。"
                    f"请到 Panel 查看实时进度，或稍后重试。"
                ),
                "summary": {
                    "vehicle_name": instance_key,
                    "instance_key": instance_key,
                    "status": "timeout_still_running",
                },
            }

        # ---- 4. 检查最终状态 ----
        final_result = state.final_result or {}
        status = final_result.get("status", "unknown")

        if status == "error":
            return {"type": "text", "content": f"流程执行出错: {final_result.get('message', '')}"}

        if status == "stopped":
            return {"type": "text", "content": "流程已被用户停止。"}

        if status == "paused":
            return {"type": "text", "content": "流程已暂停，请到 Panel 继续执行或单步调试。"}

        # ---- 5. 提取 FINAL_SUMMARY 文本 ----
        summary_text = ""
        try:
            # ProcessService.get_results 已封装好，内部会从 controller._step_results 提取
            results_data = ProcessService.get_results(instance_key)
            summary_text = results_data.get("summary_text", "")
        except Exception:
            summary_text = ""

        # fallback：直接从 controller 取
        if not summary_text:
            try:
                from snail_avatar.backend.fastapi_app.dependencies import get_process_context
                ctx = get_process_context()
                controller = ctx._get_controller(instance_key)
                extract_result = _extract_final_summary(controller)
                summary_text = extract_result.get("content", "")
            except Exception:
                summary_text = ""

        # ---- 6. 构建返回 ----
        vehicle_label = instance_key
        # 尝试从 memory_db 拿到更友好的车型名称
        try:
            from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import collect_vehicles
            names, name_to_mc_key = collect_vehicles(memory_db)
            for name, mc_key in name_to_mc_key.items():
                if mc_key == instance_key:
                    vehicle_label = name
                    break
        except Exception:
            pass

        if summary_text:
            return {
                "type": "text",
                "content": summary_text,
                "summary": {
                    "vehicle_name": vehicle_label,
                    "instance_key": instance_key,
                    "status": "completed",
                },
            }
        else:
            return {
                "type": "text",
                "content": (
                    f"目标值定义流程已对车型「{vehicle_label}」执行完毕（status={status}），"
                    f"但未获取到最终总结报告。可能流程未完全执行到 FINAL_SUMMARY 步骤，"
                    f"或发生中断。请到 Panel 查看详细步骤结果。"
                ),
                "summary": {
                    "vehicle_name": vehicle_label,
                    "instance_key": instance_key,
                    "status": status or "no_summary_found",
                },
            }


ALL_FUNCTIONS = [
    RunTargetDefinitionFlowFunction,
]
