# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : process_engine.py
# @Desc    : 流程引擎 - 动态执行 YAML 定义的流程
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程引擎

职责：
1. 动态执行 YAML 定义的流程
2. 支持多平行循环、动态条件分支
3. 支持单步执行和批量执行两种模式

使用方式：
    from snail_avatar.backend.agents.core.process_executor import ProcessEngine

    engine = ProcessEngine("path/to/process.yaml")
    engine.configure_controller(controller)

    # 批量执行
    result = engine.run_flow(ctx, instance_key, mode)

    # 单步执行
    result = engine.run_single_step(ctx, instance_key, mode)
"""

from __future__ import annotations

import os
import re
import ast
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..data_structures import StepDefinition, ProcessDefinition
from .parser import ProcessParser


class ProcessEngine:
    """流程引擎 - 动态执行 YAML 定义的流程
    
    支持的功能：
    1. 多平行循环：多个循环在流程中顺序执行，互不嵌套
    2. 动态条件分支：支持 yes/no 二分分支，可使用简单 Python 表达式评估条件
    3. 通用循环处理：通过 step_type == "loop" 识别任意循环步骤，无需硬编码 ID
    """

    def __init__(self, yaml_path: str):
        """初始化流程引擎

        Args:
            yaml_path: process.yaml 文件路径
        """
        self.yaml_path = yaml_path
        self.workflow = ProcessParser.parse(yaml_path)
        
        # 暂停/停止控制
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始为"继续"状态
        self._stop_flag = False
        # step-then-pause 标志：resume_step() 后主循环走完当前步立即再暂停
        self._step_then_pause = False
        # step-then-pause 触发后的回调列表（用于 ProcessService 推送 SSE paused 事件）
        self._step_then_pause_callbacks: List = []

    def pause(self) -> None:
        """暂停执行"""
        self._pause_event.clear()

    def resume(self) -> None:
        """继续执行"""
        self._pause_event.set()

    def resume_step(self) -> None:
        """让主循环走一步后自动再暂停（Step-then-pause 模式）

        场景：流程已 paused（主循环在 _pause_event.wait() 阻塞），
        调用此方法后主循环解除阻塞 → 执行当前步 → 立即自动 pause。
        下一轮循环的 wait() 会再次阻塞，等待下一次 resume/resume_step。
        """
        self._step_then_pause = True
        self._pause_event.set()

    def stop(self) -> None:
        """停止执行"""
        self._stop_flag = True
        self._pause_event.set()  # 解除可能的暂停阻塞

    def is_stopped(self) -> bool:
        """检查是否已停止"""
        return self._stop_flag

    @staticmethod
    def _wrap_step_result(result: Any) -> Dict[str, Any]:
        """统一包装步骤结果为字典格式

        处理不同格式的结果：
        - 普通步骤: {"type": "text", "content": "...", "reasoning_logic": "..."} (已是 dict)
        - 总结步骤: 纯文本字符串 → {"type": "text", "content": "..."}
        - 条件步骤: {"type": "text", "content": "条件判断: 通过"} (已是 dict)

        Args:
            result: 步骤执行结果（可能是 dict 或 str）

        Returns:
            统一格式的字典结果
        """
        if result is None:
            return {"type": "text", "content": ""}
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            return {"type": "text", "content": result}
        # 其他类型转为字符串
        return {"type": "text", "content": str(result)}

    def configure_controller(self, controller) -> None:
        """配置 ProcessController 的步骤结构

        Args:
            controller: ProcessController 实例
        """
        step_defs = ProcessParser.to_step_definitions(self.workflow)
        controller.configure(step_defs)

    def get_outer_steps(self) -> List[Tuple[str, str]]:
        """获取外层步骤列表"""
        result = []

        # 获取正确的外层步骤ID列表
        outer_step_ids = self.workflow.get_outer_step_ids()

        # 根据ID从所有步骤中查找详细信息
        for step_id in outer_step_ids:
            step_data = self.workflow.get_step_by_id(step_id)
            if step_data:
                name = step_data.get("step_name", step_id)
                result.append((step_id, name))

        return result

    def get_inner_steps(self) -> List[Tuple[str, str]]:
        """获取内层步骤列表（所有循环内的步骤）"""
        result = []
        inner_step_ids = self.workflow.get_inner_step_ids()

        for step_id in inner_step_ids:
            step_data = self.workflow.get_step_by_id(step_id)
            if step_data:
                name = step_data.get("step_name", step_id)
                result.append((step_id, name))

        return result

    def get_all_loop_ids(self) -> List[str]:
        """获取所有循环步骤的 ID 列表"""
        return self.workflow.get_all_loop_step_ids()

    def get_conditional_optional_map(self) -> Dict[str, str]:
        """获取条件可选步骤映射: step_id -> 依赖的 condition step_id"""
        return self.workflow.conditional_optional_map

    # ==================================================================
    # 流程执行（从 agent 层下沉的通用流程控制逻辑）
    # ==================================================================

    def run_flow(self, ctx, instance_key: str, mode: str = "ALL",
                 target_item: str = "") -> Dict[str, Any]:
        """批量执行完整流程（属性模式）

        Args:
            ctx: 执行上下文（Agent 实例）
            instance_key: 实例标识（如 instance_key）
            mode: "ALL"（全部）或 "SINGLE"（单项）
            target_item: 单项模式下的目标项名称

        Returns:
            dict: 包含状态、步骤结果和汇总信息的字典
        """
        return self._run_attribute_flow(ctx, instance_key, mode, target_item)

    def _run_attribute_flow(self, ctx, instance_key: str, mode: str = "ALL",
                             target_item: str = "") -> Dict[str, Any]:
        """属性模式连续执行：循环调用 run_single_step

        执行模型：
        1. 重置停止标志
        2. 循环调用 run_single_step 执行每一步
        3. 在每步之间检查暂停/停止状态
        4. 直到所有步骤完成或发生错误

        Args:
            ctx: 执行上下文
            instance_key: 实例标识
            mode: 执行模式
            target_item: 目标项

        Returns:
            dict: 执行结果
        """
        self._stop_flag = False
        self._pause_event.set()

        all_results = []
        has_error = False
        error_message = ""
        max_steps = 2000

        for _ in range(max_steps):
            self._pause_event.wait()
            if self._stop_flag:
                print(f"[DEBUG][Engine] main loop break: stop_flag=True")
                break

            result = self._run_attribute_single_step(ctx, instance_key, mode, target_item)
            all_results.append(result)

            # ===== DEBUG =====
            status = result.get("status", "")
            step_id = result.get("step_id", "")
            step_name = result.get("step_name", "")
            loop_item = result.get("loop_item", "")
            print(f"[DEBUG][Engine] single_step done: step={step_id!r} name={step_name!r} loop={loop_item!r} status={status!r}")

            # ===== Step-then-pause =====
            if self._step_then_pause:
                self._pause_event.clear()
                self._step_then_pause = False
                # 触发回调（ProcessService 场景 A 用此推送 SSE paused 事件）
                for cb in self._step_then_pause_callbacks:
                    try:
                        cb()
                    except Exception:
                        pass

            result_status = result.get("status", "")

            if result_status == "complete":
                break
            elif result_status == "error":
                has_error = True
                error_message = result.get("message", "步骤执行出错")
                break
            elif result_status == "paused":
                # 网络错误暂停，保留进度退出，等待用户手动重试
                break

        controller = ctx._get_controller(instance_key)

        # 检查是否因网络错误暂停
        last_result = all_results[-1] if all_results else {}
        if last_result.get("status") == "paused":
            return {
                "status": "paused",
                "message": last_result.get("message", "网络连接失败，可手动重试"),
                "step_id": last_result.get("step_id", ""),
                "results": all_results,
                "summary": controller.get_full_summary(),
            }

        if has_error:
            return {
                "status": "error",
                "message": error_message,
                "results": all_results,
                "summary": controller.get_full_summary(),
            }
        return {
            "status": "success" if not self._stop_flag else "stopped",
            "results": all_results,
            "summary": controller.get_full_summary(),
        }

    # ===== 属性模式辅助方法 =====

    def _get_full_step_id(self, step_id: str, loop_item: str = "") -> str:
        """获取带循环项前缀的完整步骤ID（用于保证跨循环项的唯一性）

        Args:
            step_id: 步骤 ID
            loop_item: 当前循环项名称

        Returns:
            str: 完整步骤 ID（如 "空气动力学_ANALYZE_PRODUCT"）
        """
        if loop_item:
            inner_step_ids = self.workflow.get_inner_step_ids()
            if step_id in inner_step_ids:
                return f"{loop_item}_{step_id}"
        return step_id

    def _get_next_step_id(self, step_id: str) -> str:
        """获取下一步骤 ID（属性模式）"""
        step = self.workflow._step_id_map.get(step_id)
        if not step:
            return ""
        return step.get("next_step", "")

    def _get_previous_step_id(self, step_id: str) -> str:
        """获取上一个步骤 ID（属性模式，线性顺序中的前一个）"""
        # 从有序步骤列表中查找前一个步骤
        ordered_steps = self.workflow._ordered_step_ids
        if step_id in ordered_steps:
            idx = ordered_steps.index(step_id)
            if idx > 0:
                return ordered_steps[idx - 1]
        return ""

    def _get_step_result(self, ctx, instance_key: str, step_id: str) -> Dict[str, Any]:
        """获取指定步骤的执行结果
        
        从 controller._step_results 中查找（返回最后一个匹配）。
        查找时兼容两种 step_id 格式：
        1. 原始 step_id（顶层步骤直接匹配）
        2. 带 loop_item 前缀的 full_step_id（循环内步骤，格式: "{loop_item}_{step_id}"）
        """
        controller = ctx._get_controller(instance_key)
        
        if not hasattr(controller, '_step_results'):
            return {}
        
        all_results = controller._step_results
        
        last_result = {}
        for result in all_results:
            result_step_id = result.get("step_id", "")
            step_result = result.get("step_result", {})
            # 匹配逻辑：精确匹配 或 去除 loop_item_ 前缀后匹配
            if result_step_id == step_id or result_step_id.endswith(f"_{step_id}"):
                last_result = step_result  # 保存最后一个匹配
        
        return last_result

    def _find_next_step_after_loop(self, loop_name: str) -> str:
        """查找循环组执行完成后的下一步骤 ID"""
        # 遍历循环组中的所有步骤，找到 next_step 指向循环外的步骤
        loop_steps = self.workflow.get_loop_steps(loop_name)
        for step in loop_steps:
            next_id = step.get("next_step", "")
            if next_id:
                next_step = self.workflow._step_id_map.get(next_id)
                if next_step:
                    next_level = next_step.get("step_level", "top_level")
                    next_loop = next_step.get("loop_name", "")
                    # 如果下一步是顶层步骤或属于不同循环组
                    if next_level == "top_level" or next_loop != loop_name:
                        return next_id
        return ""

    def _get_item_arg(self, loop_name: str) -> str:
        """获取循环组的 item_arg"""
        loop_config = self.workflow.get_loop_node_config(loop_name)
        if loop_config:
            return loop_config.get("item_arg", "loop_item")
        return "loop_item"

    def _get_loop_items(self, ctx, instance_key: str, loop_config: Dict[str, Any],
                        mode: str, target_item: str) -> List[Any]:
        """获取循环项列表

        Args:
            ctx: 执行上下文
            instance_key: 实例标识
            loop_config: 循环节点配置
            mode: 执行模式
            target_item: 单项模式下的目标项名称

        Returns:
            List: 循环项列表
        """
        source = loop_config.get("source", {})
        source_type = source.get("type", "")
        
        if mode == "SINGLE" and target_item:
            return [target_item]
        
        if source_type == "init_config":
            # 从 init_config 获取（初始检测步骤已执行，结果保存在 controller 中）
            controller = ctx._get_controller(instance_key)
            state = controller.get_state()
            loop_items = (state.get("remaining_loop_items", []) + 
                         state.get("completed_loop_items", []))
            return loop_items
            
        elif source_type == "step_result":
            # 从指定步骤结果获取
            step_id = source.get("step_id", "")
            result_field = source.get("result_field", "items")
            if step_id:
                step_result = ctx._get_step_result(step_id)
                if step_result and result_field in step_result:
                    return step_result[result_field]
            return []
            
        elif source_type == "function":
            # 调用函数获取
            function_name = source.get("function", "")
            args_mapping = source.get("args_mapping", {})
            if function_name:
                result = self._call_function(ctx, function_name, args_mapping, 
                                           instance_key=instance_key)
                if isinstance(result, dict):
                    return result.get("items", result.get("categories", []))
            return []
            
        return []

    def _evaluate_condition_step(self, step_config: Dict[str, Any], 
                                  step_result: Dict[str, Any]) -> bool:
        """评估条件步骤

        支持三种条件评估模式（优先级从高到低）：
        1. evaluate_by + yes_value/no_value: 从结构化结果中读取字段进行 YES/NO 判断
        2. 动态表达式: Python 表达式，如 "score > 80 and status == 'pass'"
        3. 预设条件类型: "all_pass", "any_pass", "all_fail" 等

        Args:
            step_config: 条件步骤配置
            step_result: 被检查步骤的执行结果

        Returns:
            bool: 条件是否满足 (True=YES/pass, False=NO/fail)
        """
        # 提取实际的结果数据（处理嵌套的 content 字段）
        result_data = self._extract_result_data(step_result)
        
        # 模式1: evaluate_by + yes_value/no_value
        evaluate_by = step_config.get("evaluate_by", "")
        if evaluate_by:
            yes_value = step_config.get("yes_value", "pass")
            no_value = step_config.get("no_value", "fail")
            
            # 支持点号分隔的字段路径，如 "structured_data.status"
            field_value = self._get_nested_value(result_data, evaluate_by)
            
            # 判断条件
            if field_value is not None:
                result = str(field_value) == str(yes_value)
                return result
        
        # 模式2: 动态表达式
        condition_expr = step_config.get("condition", "")
        if condition_expr:
            try:
                # 在受限命名空间中评估表达式
                namespace = dict(result_data) if isinstance(result_data, dict) else {}
                result = bool(eval(condition_expr, {"__builtins__": {}}, namespace))
                return result
            except Exception as e:
                return False
        
        # 模式3: 预设条件类型
        check_condition = step_config.get("check_condition", "")
        if check_condition:
            if check_condition == "all_pass":
                # 检查所有项是否都通过
                items = result_data.get("items", []) if isinstance(result_data, dict) else []
                result = all(item.get("status") == "pass" for item in items) if items else False
                return result
            elif check_condition == "any_pass":
                # 检查是否有任何项通过
                items = result_data.get("items", []) if isinstance(result_data, dict) else []
                result = any(item.get("status") == "pass" for item in items) if items else False
                return result
            elif check_condition == "all_fail":
                # 检查所有项是否都不通过
                items = result_data.get("items", []) if isinstance(result_data, dict) else []
                result = all(item.get("status") == "fail" for item in items) if items else False
                return result
        
        # 默认返回 True（条件满足）
        return True

    def _extract_result_data(self, step_result: Dict[str, Any]) -> Dict[str, Any]:
        """从步骤结果中提取实际的结构化数据

        处理不同格式的结果：
        1. 直接的结构化数据: {"structured_data": {...}, "reasoning_logic": "..."}
        2. 嵌套的 content 字段: {"result": {"type": "text", "content": "..."}}
        3. 字符串格式的 JSON

        Args:
            step_result: 步骤执行结果

        Returns:
            Dict: 实际的结构化数据
        """
        import json
        
        # 获取 result 字段
        result = step_result.get("result", {})
        
        # 情况1: result 包含 content 字段（Agent 返回的包装格式）
        if isinstance(result, dict) and "content" in result:
            content = result.get("content", "")
            if isinstance(content, str):
                try:
                    # 尝试解析 JSON 字符串
                    parsed = json.loads(content)
                    return parsed
                except json.JSONDecodeError as e:
                    return {"content": content}
            elif isinstance(content, dict):
                return content
        
        # 情况2: result 本身是字符串
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                return parsed
            except json.JSONDecodeError as e:
                return {"result": result}
        
        # 情况3: result 本身就是字典（直接包含结构化数据）
        if isinstance(result, dict):
            # 检查是否包含 structured_data
            if "structured_data" in result:
                return result
            else:
                return result
        
        # 默认返回空字典
        return {}

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """获取嵌套字典的值（支持点号分隔的路径）

        Args:
            data: 数据字典
            path: 字段路径，如 "structured_data.status"

        Returns:
            Any: 字段值，不存在返回 None
        """
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def run_single_step(self, ctx, instance_key: str, mode: str = "ALL",
                        target_item: str = "") -> Dict[str, Any]:
        """单步执行流程（属性模式）

        基于 next_step 图的单步执行，自动跳过非交互步骤（INIT、condition），
        直到遇到第一个真实步骤。

        Args:
            ctx: 执行上下文（Agent 实例）
            instance_key: 实例标识
            mode: "ALL" 或 "SINGLE"
            target_item: 目标项名称

        Returns:
            dict: 执行结果
        """
        return self._run_attribute_single_step(ctx, instance_key, mode, target_item)

    def _run_attribute_single_step(self, ctx, instance_key: str, mode: str = "ALL",
                                    target_item: str = "") -> Dict[str, Any]:
        """属性模式单步执行：基于 next_step 图的逐步执行

        自动跳过非交互步骤（INIT、condition），直到遇到第一个真实步骤。
        用户点击一次"单步执行" = 自动完成初始化 + 条件判断 + 执行一个真实步骤。

        Args:
            ctx: 执行上下文
            instance_key: 实例标识
            mode: 执行模式
            target_item: 目标项

        Returns:
            dict: 执行结果
        """
        instance_attrs = self._compute_pre_attrs(ctx, instance_key)
        state = ctx._get_execution_state(instance_key)
        controller = ctx._get_controller(instance_key)
        step_registry = ctx._get_step_registry()
        inner_step_registry = ctx._get_inner_step_registry()

        # ===== DEBUG =====
        print(f"[DEBUG][Engine] single_step entry: stage={state.get('stage')!r} current_step_id={state.get('current_step_id')!r}")
        print(f"[DEBUG][Engine] controller._states count={len(controller._states)} step_ids={[s.step_id for s in controller._states]}")
        print(f"[DEBUG][Engine] controller._states statuses={[(s.step_id, s.status) for s in controller._states]}")

        # 步骤1：初始化（首次调用）— 自动跳过
        if state["stage"] == "INIT":
            loop_items = self._execute_init_config(ctx, instance_key)

            # INIT 步骤完成后，获取下一步（INIT 的 next_step）
            next_step_id = self._get_next_step_id("INIT")

            state.update({
                "stage": "STEP",
                "mode": mode,
                "current_step_id": next_step_id,
                "current_loop_name": "",
                "current_loop_items": [],
                "current_loop_item_idx": 0,
                "condition_results": {},
            })

            controller.advance("INIT", completed=True,
                              step_result={"type": "text", "content": "初始化完成"},
                              auto_advance=False)

            if mode == "SINGLE":
                if target_item and loop_items and target_item not in loop_items:
                    return {
                        "status": "error",
                        "message": f"项 '{target_item}' 不存在，可选项: {', '.join(loop_items)}",
                    }
                if loop_items:
                    state["loop_items"] = [target_item] if target_item else []
                else:
                    state["loop_items"] = []

            # INIT 完成后不返回，继续执行第一个真实步骤

        # 步骤2：自动循环执行 — 跳过条件步骤，直到遇到真实步骤
        if state["stage"] == "STEP":
            max_auto_steps = 100  # 防止无限循环
            auto_count = 0

            while auto_count < max_auto_steps:
                auto_count += 1

                current_step_id = state.get("current_step_id", "")
                if not current_step_id:
                    state["stage"] = "COMPLETE"
                    return {"status": "complete", "message": "所有步骤已执行完毕"}

                step_config = self.workflow._step_id_map.get(current_step_id)
                if not step_config:
                    state["stage"] = "COMPLETE"
                    return {"status": "complete", "message": "所有步骤已执行完毕"}

                step_type = step_config.get("type", "step")
                step_level = step_config.get("step_level", "top_level")
                loop_name = step_config.get("loop_name", "")
                step_id = step_config.get("step_id", "")
                step_name = step_config.get("step_name", "")

                # 处理循环进入
                if step_level == "loop_level" and loop_name != state.get("current_loop_name", ""):
                    state["current_loop_name"] = loop_name
                    loop_node_config = self.workflow.get_loop_node_config(loop_name)
                    if loop_node_config:
                        loop_items = self._get_loop_items(
                            ctx, instance_key, loop_node_config, mode, target_item
                        )
                    else:
                        loop_items = []

                    state["current_loop_items"] = loop_items
                    state["current_loop_item_idx"] = 0

                    if not loop_items:
                        # 循环项为空，跳过循环
                        next_id = self._find_next_step_after_loop(loop_name)
                        state["current_loop_name"] = ""
                        if next_id:
                            state["current_step_id"] = next_id
                            continue  # 自动推进，不返回
                        else:
                            state["stage"] = "COMPLETE"
                            return {"status": "complete", "message": "所有步骤已执行完毕"}

                    controller.set_loop_items(loop_items, loop_step_id=loop_name)
                    controller.set_current_loop_item(loop_items[0], loop_step_id=loop_name)

                # 获取当前循环项
                current_loop_name = state.get("current_loop_name", "")
                current_loop_items = state.get("current_loop_items", [])
                current_loop_item_idx = state.get("current_loop_item_idx", 0)
                
                # 顶层步骤的 loop_item 强制为空字符串
                if step_level == "top_level":
                    loop_item = ""
                else:
                    loop_item = current_loop_items[current_loop_item_idx] if current_loop_name and current_loop_item_idx < len(current_loop_items) else ""

                # 获取步骤类
                if current_loop_name:
                    step_class = inner_step_registry.get(step_id)
                else:
                    step_class = step_registry.get(step_id)

                # 条件步骤：自动跳过，不返回
                if step_type == "condition":
                    check_step_id = step_config.get("check_step", "")
                    if not check_step_id:
                        check_step_id = self._get_previous_step_id(step_id)

                    check_step_result = self._get_step_result(ctx, instance_key, check_step_id)
                    condition_result = self._evaluate_condition_step(step_config, {"result": check_step_result})
                    state.setdefault("condition_results", {})[step_id] = condition_result

                    if condition_result:
                        next_id = step_config.get("next_step", "")
                    else:
                        next_id = step_config.get("next_step_on_fail", "")

                    state["current_step_id"] = next_id

                    condition_summary = {
                        "type": "text",
                        "content": f"条件判断: {'通过' if condition_result else '不通过'}"
                    }
                    controller.advance(step_id, completed=True,
                                      step_result=condition_summary,
                                      loop_item=loop_item,
                                      auto_advance=False)

                    # 自动推进到下一步，继续循环
                    continue

                # ===== 以下是真实步骤（step/agent/llm等），需要用户交互 =====

                if step_class is None:
                    all_results = []
                    step_result = {
                        "step_id": step_id,
                        "step_name": step_name,
                        "result": {"type": "text", "content": f"步骤类未找到: {step_id}", "is_error": True},
                        "is_error": True,
                    }
                    controller.advance(step_id, completed=False,
                                      step_result=step_result["result"],
                                      loop_item=loop_item,
                                      auto_advance=False)

                    next_id = self._get_next_step_id(step_id)
                    state["current_step_id"] = next_id

                    return {
                        "status": "success",
                        "step_id": step_id,
                        "step_name": step_name,
                        "result": step_result["result"],
                        "loop_item": loop_item or "",
                        "warning": "步骤类未找到",
                    }

                # 标记当前步骤为运行中
                controller.advance(step_id, completed=False,
                                  step_result={"type": "text", "content": "执行中..."},
                                  loop_item=loop_item,
                                  auto_advance=False)

                # 构建参数
                args = self._build_step_args(ctx, instance_key, instance_attrs, loop_item)
                if current_loop_name and loop_item:
                    item_arg = self._get_item_arg(current_loop_name)
                    args[item_arg] = loop_item

                ctx._save_snapshot(instance_key)

                step_result = ctx._execute_step(step_class, args, context=ctx)
                result = step_result.get("result", {})

                # 检查是否为网络错误导致的失败（同时匹配英文 "network" 和中文 "网络错误"）
                if result.get("is_error") and result.get("error_type") in ("network", "网络错误"):
                    # 标记步骤为失败但不推进状态，支持继续重试
                    controller.advance(step_id, completed=False,
                                      step_result=self._wrap_step_result(result),
                                      loop_item=loop_item,
                                      auto_advance=False)
                    return {
                        "status": "paused",
                        "step_id": step_id,
                        "step_name": step_name,
                        "message": result.get("content", "网络连接失败，可手动重试"),
                        "loop_item": loop_item or "",
                        "retry_count": result.get("retry_count", 0),
                    }

                controller.advance(step_id, completed=True,
                                  step_result=self._wrap_step_result(result),
                                  loop_item=loop_item,
                                  auto_advance=False)

                # 获取下一步并处理循环推进
                next_step_id = self._get_next_step_id(step_id)

                if current_loop_name and next_step_id:
                    next_step_config = self.workflow._step_id_map.get(next_step_id)
                    if next_step_config and isinstance(next_step_config, dict):
                        next_level = next_step_config.get("step_level", "top_level")
                        next_loop_name = next_step_config.get("loop_name", "")

                        if next_level == "top_level" or next_loop_name != current_loop_name:
                            # 即将退出循环
                            if loop_item:
                                controller.complete_loop_item(loop_item, loop_step_id=current_loop_name)

                            current_loop_item_idx += 1
                            state["current_loop_item_idx"] = current_loop_item_idx

                            if current_loop_item_idx >= len(current_loop_items):
                                # 所有循环项完成
                                state["current_loop_name"] = ""
                                state["current_loop_items"] = []
                                state["current_loop_item_idx"] = 0
                                state["current_step_id"] = next_step_id
                            else:
                                # 还有循环项
                                controller.set_current_loop_item(
                                    current_loop_items[current_loop_item_idx],
                                    loop_step_id=current_loop_name
                                )
                                # 重新从循环组的第一步开始
                                loop_steps = self.workflow.get_loop_steps(current_loop_name)
                                if loop_steps:
                                    state["current_step_id"] = loop_steps[0].get("step_id", "")
                                else:
                                    state["current_step_id"] = next_step_id

                            # 真实步骤执行完毕，返回结果
                            return {
                                "status": "success",
                                "step_id": step_id,
                                "step_name": step_name,
                                "result": step_result["result"],
                                "loop_item": loop_item or "",
                                "message": "循环项推进",
                            }

                state["current_step_id"] = next_step_id

                if not state.get("current_step_id"):
                    state["stage"] = "COMPLETE"

                # 真实步骤执行完毕，返回结果
                return {
                    "status": "success",
                    "step_id": step_id,
                    "step_name": step_name,
                    "result": step_result["result"],
                    "loop_item": loop_item or "",
                }

        # 步骤3：流程完成
        if state["stage"] == "COMPLETE":
            return {"status": "complete", "message": "所有步骤已执行完毕"}

        return {"status": "complete", "message": "所有步骤已执行完毕"}

    @staticmethod
    def _build_step_args(ctx, instance_key: str, instance_attrs: Dict[str, str],
                         loop_item: Optional[str]) -> Dict[str, Any]:
        """构建步骤参数（配置驱动，支持多实例属性注入）

        Args:
            ctx: 执行上下文
            instance_key: 实例标识
            instance_attrs: 从实例标识中提取的属性字典
            loop_item: 当前循环项（非循环步骤为 None）

        Returns:
            dict: 步骤参数
        """
        args_config = ctx._args_config
        args = {
            args_config.get("instance_key_arg", "instance_key"): instance_key,
        }
        # 注入所有实例属性
        args.update(instance_attrs)
        if loop_item is not None:
            args[args_config.get("loop_item_arg", "loop_item")] = loop_item
        return args

    def _execute_init_config(self, ctx, instance_key: str) -> List[str]:
        """执行初始化配置，获取循环项列表

        从 process.yaml 的 init_config 配置中读取 public function 调用定义，
        执行后返回循环项列表。配置缺失时返回空列表。

        Args:
            ctx: 执行上下文（Agent 实例）
            instance_key: 实例标识

        Returns:
            List[str]: 循环项列表
        """
        init_config = self.workflow.raw.get("init_config")
        if not init_config:
            return []

        function_name = init_config.get("function", "")
        args_mapping = init_config.get("args_mapping", {})
        result_field = init_config.get("result_field", "items")

        if not function_name:
            return []

        # 解析参数映射
        from snail_avatar.backend.agents.core.public_functions import get_public_function
        from snail_avatar.backend.agents.core.process_executor.utils.variable_resolver import VariableResolver

        resolver = VariableResolver(
            args={"instance_key": instance_key},
            context=ctx,
            data_sources={}
        )

        resolved_args = {}
        for key, value in args_mapping.items():
            if isinstance(value, str) and value.startswith("$"):
                resolved_args[key] = resolver._resolve_value(value)
            else:
                resolved_args[key] = value

        pub_fn_cls = get_public_function(function_name)
        if pub_fn_cls:
            # 用统一变量解析补全缺失的公共变量
            from snail_avatar.backend.agents.core.process_executor.steps.base import ProcessStep
            instance_attrs = self._compute_pre_attrs(ctx, instance_key)
            step_args = {ctx._args_config.get("instance_key_arg", "instance_key"): instance_key}
            step_args.update(instance_attrs)
            resolved_args = ProcessStep._resolve_variables(ctx, step_args, resolved_args)
            
            result = pub_fn_cls.execute(resolved_args, ctx)
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                items = result.get(result_field, [])
                return items if isinstance(items, list) else []
            return []

        return []

    def _compute_pre_attrs(self, ctx, instance_key: str) -> Dict[str, str]:
        """计算预定义属性（配置驱动，通用调度器）

        从 process.yaml 的 args_config.pre_computed_attrs 读取配置，
        调用指定的公共函数获取属性值。不包含业务逻辑，仅做通用调度。

        所有实例属性统一通过此方法获取，支持属性间的依赖引用。

        Args:
            ctx: 执行上下文
            instance_key: 实例标识

        Returns:
            Dict[str, str]: 属性名 → 属性值 的映射
            如: {"vehicle_suffix": "reevlto", "vehicle_display_name": "增程车型（WLTC）"}
        """
        args_config = ctx._args_config
        pre_computed_attrs = args_config.get("pre_computed_attrs", {})
        
        if not pre_computed_attrs:
            return {}
        
        from snail_avatar.backend.agents.core.public_functions import get_public_function
        from snail_avatar.backend.agents.core.process_executor.utils.variable_resolver import VariableResolver
        from snail_avatar.backend.agents.core.process_executor.steps.base import ProcessStep
        
        result_attrs = {}
        
        # 构建基础参数（仅包含 instance_key）
        step_args = {args_config.get("instance_key_arg", "instance_key"): instance_key}
        
        # 依次计算每个预计算属性，支持属性间依赖
        for attr_name, attr_config in pre_computed_attrs.items():
            function_name = attr_config.get("function", "")
            args_mapping = attr_config.get("args_mapping", {})
            
            if not function_name:
                continue
            
            # 构建变量解析器（包含已计算的属性，支持属性间引用）
            resolver = VariableResolver(
                args=step_args,
                context=ctx,
                data_sources={}
            )
            
            # 解析参数映射
            resolved_args = {}
            for key, value in args_mapping.items():
                if isinstance(value, str) and value.startswith("$"):
                    resolved_args[key] = resolver.resolve(value)
                else:
                    resolved_args[key] = value
            
            # 用统一变量解析补全缺失的公共变量
            resolved_args = ProcessStep._resolve_variables(ctx, step_args, resolved_args)
            
            # 调用公共函数
            pub_fn_cls = get_public_function(function_name)
            if pub_fn_cls:
                try:
                    result = pub_fn_cls.execute(resolved_args, ctx)
                    # 处理返回结果
                    attr_value = self._extract_result_value(result)
                    result_attrs[attr_name] = attr_value
                    # 将新计算的属性添加到 step_args，供后续属性引用
                    step_args[attr_name] = attr_value
                except Exception as e:
                    result_attrs[attr_name] = ""
                    step_args[attr_name] = ""
        
        return result_attrs
    
    @staticmethod
    def _extract_result_value(result: Any) -> str:
        """从公共函数执行结果中提取字符串值

        Args:
            result: 公共函数执行结果

        Returns:
            str: 提取的字符串值
        """
        if isinstance(result, str):
            return result
        elif isinstance(result, dict):
            # 如果是 {"type": "text", "content": "..."} 格式，提取 content
            if "content" in result:
                return str(result["content"])
            elif "result" in result:
                return str(result["result"])
            else:
                return str(result)
        else:
            return str(result) if result else ""
