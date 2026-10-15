# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : controller_base.py
# @Desc    : 流程控制器基础模块 - 初始化配置、状态遍历、基础推进、回调通知
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程控制器基础模块

提供 ProcessController 的核心功能：
1. 初始化和配置步骤结构
2. 状态树遍历（按路径、按ID查找）
3. 步骤基础推进（advance）
4. 回调通知机制
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from ..data_structures import StepDefinition, StepState
from ..process_sandbox import ProcessSandbox
from ..utils.context_provider import IContextProvider


class ProcessControllerBase:
    """流程控制器基础类 - 提供初始化、配置、状态遍历和基础推进功能"""

    def __init__(self, steps: List[StepDefinition] = None,
                 context_provider: IContextProvider = None):
        self._steps: List[StepDefinition] = steps or []
        self._states: List[StepState] = []
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._step_results: List[Dict[str, Any]] = []
        self._current_path: List[int] = []
        self._paused: bool = False
        self._sandbox: ProcessSandbox = ProcessSandbox()
        self._context_provider: IContextProvider = context_provider
        # 快照（步骤执行前保存，异常时可恢复）
        self._snapshot: Optional[Dict[str, Any]] = None

        if self._steps:
            self._init_states(self._steps, self._states)

    def _init_states(self, definitions: List[StepDefinition], states: List[StepState]) -> None:
        """递归初始化状态树"""
        for defn in definitions:
            state = StepState(
                step_id=defn.step_id,
                step_name=defn.step_name,
                step_type=defn.step_type,
                loop_items=defn.loop_items[:],
                metadata=defn.metadata.copy(),
            )
            if defn.has_loop() and defn.loop_items:
                state.current_loop_item = defn.loop_items[0]
            if defn.sub_steps:
                self._init_states(defn.sub_steps, state.sub_states)
            states.append(state)

    def configure(self, steps: List[StepDefinition]) -> None:
        """配置多层步骤结构

        Args:
            steps: StepDefinition 列表，支持任意层级嵌套
        """
        self._steps = steps
        self._states = []
        self._step_results = []
        self._current_path = []
        if self._steps:
            self._init_states(self._steps, self._states)

    def _find_state_by_path(self, parts: List[str], states: List[StepState],
                              current_path: List[int]) -> Tuple[Optional[StepState], List[int]]:
        """递归查找状态节点"""
        if not parts:
            return None, current_path

        for idx, state in enumerate(states):
            if state.step_id == parts[0]:
                if len(parts) == 1:
                    return state, current_path + [idx]
                if state.sub_states:
                    return self._find_state_by_path(parts[1:], state.sub_states, current_path + [idx])
            if state.sub_states:
                found, found_path = self._find_state_by_path(parts, state.sub_states, current_path + [idx])
                if found:
                    return found, found_path
        return None, current_path

    def _find_loop_state(self, states: List[StepState]) -> Optional[StepState]:
        """递归查找第一个循环状态"""
        for state in states:
            if state.step_type == "loop":
                return state
            if state.sub_states:
                found = self._find_loop_state(state.sub_states)
                if found:
                    return found
        return None

    def _find_loop_state_by_id(self, loop_step_id: str, 
                                 states: List[StepState] = None) -> Optional[StepState]:
        """按 ID 查找循环状态"""
        if states is None:
            states = self._states

        for state in states:
            if state.step_type == "loop" and state.step_id == loop_step_id:
                return state
            if state.sub_states:
                found = self._find_loop_state_by_id(loop_step_id, state.sub_states)
                if found:
                    return found
        return None

    def _get_all_loop_states(self, states: List[StepState] = None) -> List[StepState]:
        """获取所有循环状态"""
        if states is None:
            states = self._states

        loop_states = []
        for state in states:
            if state.step_type == "loop":
                loop_states.append(state)
            if state.sub_states:
                loop_states.extend(self._get_all_loop_states(state.sub_states))
        return loop_states

    def _get_parent_states(self, path: List[int]) -> List[StepState]:
        """根据路径获取所有父状态"""
        if not path:
            return []

        states = []
        current = self._states
        for idx in path[:-1]:
            if idx < len(current):
                states.append(current[idx])
                current = current[idx].sub_states
        return states

    def advance(self, step_id: str, completed: bool = True,
                   step_result: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """推进步骤

        记录步骤结果并更新状态，不自动推进到下一步（由引擎通过 next_step 控制流程）。

        Args:
            step_id: 步骤ID（支持点号分隔层级，如 "LOOP.ANALYZE"）
            completed: 是否完成（False表示步骤执行失败，不推进到下一步）
            step_result: 步骤执行结果（字典格式）
            **kwargs: 额外参数
                - auto_advance: 是否自动推进到下一步（默认 True，属性模式传 False）

        Returns:
            dict: 包含当前状态、进度、剩余步骤的字典
        """
        auto_advance = kwargs.pop("auto_advance", True)
        parts = step_id.split(".")
        state, path = self._find_state_by_path(parts, self._states, [])

        # 无论 state 是否存在（条件分支步骤不在状态树中），都要记录结果和通知进度
        # 这是 controller._step_results 和 UI 展示的唯一数据来源
        self._record_result(step_id, step_result, path=path, **kwargs)

        if state:
            if completed:
                state.start()
                state.complete(step_result)
                # 属性模式：不自动推进，由引擎控制流程
                if auto_advance:
                    self._advance_to_next(state, path)
            else:
                state.start()

        self.notify_progress()
        return self._build_step_info()

    def _advance_to_next(self, state: StepState, path: List[int]) -> None:
        """推进到下一个步骤（递归处理）"""
        if state.step_type == "loop":
            if state.current_loop_item and state.current_loop_item not in state.completed_loop_items:
                state.completed_loop_items.append(state.current_loop_item)

            remaining = [item for item in state.loop_items 
                         if item not in state.completed_loop_items]
            if remaining:
                state.current_loop_item = remaining[0]
                for sub in state.sub_states:
                    sub.reset()
                state.current_index = 0
                return

            state.status = "completed"
            self._advance_to_next_parent(path)
            return

        if not path:
            return

        if len(path) == 1:
            idx = path[0]
            if idx < len(self._states) - 1:
                next_state = self._states[idx + 1]
                next_state.start()
                if next_state.sub_states:
                    next_state.sub_states[0].start()
            return

        parent_states = self._get_parent_states(path)
        if parent_states:
            parent_state = parent_states[-1]
            idx_in_parent = path[-1]
            if idx_in_parent < len(parent_state.sub_states) - 1:
                next_sub = parent_state.sub_states[idx_in_parent + 1]
                next_sub.start()
                parent_state.current_index = idx_in_parent + 1
                return

            if parent_state.step_type == "loop":
                if parent_state.current_loop_item and parent_state.current_loop_item not in parent_state.completed_loop_items:
                    parent_state.completed_loop_items.append(parent_state.current_loop_item)

                remaining = [item for item in parent_state.loop_items 
                             if item not in parent_state.completed_loop_items]
                if remaining:
                    parent_state.current_loop_item = remaining[0]
                    for sub in parent_state.sub_states:
                        sub.reset()
                    parent_state.sub_states[0].start()
                    parent_state.current_index = 0
                    return

            parent_state.complete()
            self._advance_to_next(parent_state, path[:-1])

    def _advance_to_next_parent(self, path: List[int]) -> None:
        """推进到父层级的下一个步骤"""
        if not path:
            return

        if len(path) == 1:
            idx = path[0]
            if idx < len(self._states) - 1:
                next_state = self._states[idx + 1]
                next_state.start()
                if next_state.sub_states:
                    next_state.sub_states[0].start()
            return

        parent_states = self._get_parent_states(path)
        if parent_states:
            parent_state = parent_states[-1]
            idx_in_parent = path[-1]
            if idx_in_parent < len(parent_state.sub_states) - 1:
                next_sub = parent_state.sub_states[idx_in_parent + 1]
                next_sub.start()
                return

            parent_state.complete()
            self._advance_to_next_parent(path[:-1])

    def add_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """添加进度回调"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def notify_progress(self) -> None:
        """通知所有回调"""
        step_info = self._build_step_info()
        for callback in self._callbacks:
            try:
                callback(step_info)
            except Exception:
                pass

    def _build_step_info(self) -> Dict[str, Any]:
        """构建步骤信息字典（支持多循环）"""
        state = self.get_state()
        loop_state = self._find_loop_state(self._states)

        # 获取当前内层步骤名称
        inner_step_name = ""
        if self._states:
            for s in self._states:
                if s.status in ("running", "pending") and s.sub_states:
                    for sub in s.sub_states:
                        if sub.status in ("running", "pending"):
                            inner_step_name = sub.step_name
                            break
                    break

        # 判断是否是最后一个循环项
        is_last_loop_item = False
        if loop_state and loop_state.loop_items:
            remaining = [item for item in loop_state.loop_items 
                        if item not in loop_state.completed_loop_items]
            is_last_loop_item = len(remaining) <= 1 and loop_state.current_loop_item in remaining

        result = {
            "outer_step": state["outer_step"],
            "inner_step": state["inner_step"],
            "inner_step_name": inner_step_name,
            "inner_step_ids": state.get("inner_step_ids", []),
            "current_loop_item": state["current_loop_item"],
            "completed_loop_items": state["completed_loop_items"],
            "remaining_loop_items": state["remaining_loop_items"],
            "step_results": self._step_results[:],
            "is_last_loop_item": is_last_loop_item,
            "progress": self.get_progress(),
            "is_complete": self.is_complete(),
            "current_path": self.get_current_path(),
            "is_paused": self._paused,
            # 多循环扩展字段
            "loops": state.get("loops", []),
            "total_loops": state.get("total_loops", 1),
            "completed_loops": state.get("completed_loops", 0),
            "active_loop_index": state.get("active_loop_index", 0),
            # 状态树（属性模式：用于基于状态的渲染）
            "states_tree": state.get("states_tree", []),
        }


        return result

    # ==================================================================
    # Agent 类型映射管理 - 委托给 ProcessSandbox
    # ==================================================================

    def set_agent_type_mapping(self, agent_type: str, mapping: Dict[str, str]) -> None:
        """设置指定 agent_type 的映射

        委托给 ProcessSandbox 存储。

        Args:
            agent_type: Agent 类型（"calculator" 或 "expert"）
            mapping: {loop_item: agent_id} 映射
        """
        self._sandbox.set_agent_type_mapping(agent_type, mapping)

    def get_agent_id_by_type(self, agent_type: str, loop_item: str = "") -> str:
        """根据 agent_type 获取 Agent ID

        委托给 ProcessSandbox 查找。

        Args:
            agent_type: Agent 类型（"calculator" 或 "expert"）
            loop_item: 循环项名称

        Returns:
            str: agent ID，未找到返回空字符串
        """
        return self._sandbox.get_agent_id_by_type(agent_type, loop_item)

    def _find_step_def_by_id(self, step_id: str) -> Optional['StepDefinition']:
        """根据 step_id 查找步骤定义（递归搜索）"""
        return self._recursive_find_step_def(self._steps, step_id)

    def _recursive_find_step_def(self, definitions: List['StepDefinition'], step_id: str) -> Optional['StepDefinition']:
        """递归搜索步骤定义"""
        for defn in definitions:
            if defn.step_id == step_id:
                return defn
            if defn.sub_steps:
                found = self._recursive_find_step_def(defn.sub_steps, step_id)
                if found:
                    return found
        return None

    # ==================================================================
    # 快照机制
    # ==================================================================

    def save_snapshot(self) -> None:
        """保存当前控制器状态的快照"""
        import copy
        self._snapshot = {
            "states": copy.deepcopy(self._states),
            "step_results": copy.deepcopy(self._step_results),
            "current_path": copy.deepcopy(self._current_path),
            "sandbox_step_results": copy.deepcopy(self._sandbox._step_results),
            "sandbox_process_data": copy.deepcopy(self._sandbox._process_data),
            "sandbox_agent_type_mappings": copy.deepcopy(self._sandbox._agent_type_mappings),
        }

    def restore_snapshot(self) -> bool:
        """从快照恢复控制器状态

        Returns:
            bool: 是否成功恢复
        """
        if not self._snapshot:
            return False

        self._states = self._snapshot["states"]
        self._step_results = self._snapshot["step_results"]
        self._current_path = self._snapshot["current_path"]
        self._sandbox._step_results = self._snapshot["sandbox_step_results"]
        self._sandbox._process_data = self._snapshot["sandbox_process_data"]
        self._sandbox._agent_type_mappings = self._snapshot["sandbox_agent_type_mappings"]
        self._snapshot = None
        return True

    def has_snapshot(self) -> bool:
        """检查是否存在可恢复的快照"""
        return self._snapshot is not None
