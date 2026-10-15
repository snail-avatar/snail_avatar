# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : controller_progress.py
# @Desc    : 流程控制器进度与状态查询模块
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程控制器进度与状态查询模块

提供 ProcessController 的进度计算和状态查询扩展功能：
1. 获取当前状态快照（支持多循环）
2. 获取当前执行路径
3. 判断流程是否完成
4. 计算整体进度（支持多平行循环）
5. 序列化状态树
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..data_structures import StepState
from .result import ProcessControllerResult


class ProcessControllerProgress(ProcessControllerResult):
    """流程控制器进度与状态查询扩展 - 支持多平行循环"""

    def get_state(self) -> Dict[str, Any]:
        """获取当前完整状态（支持多循环结构）
        
        注意：此方法返回的 inner_step 仅用于 UI 显示，
        会过滤掉 step_type == "condition" 的条件节点。
        """
        # 获取所有循环状态
        loop_states = self._get_all_loop_states()
        
        # 第一个循环（兼容旧接口）
        first_loop = loop_states[0] if loop_states else None

        outer_step = ""
        inner_step = ""
        current_outer_idx = 0
        current_inner_idx = 0

        if self._states:
            for idx, state in enumerate(self._states):
                if state.status in ("running", "pending"):
                    outer_step = state.step_id
                    current_outer_idx = idx
                    if state.sub_states:
                        # 查找当前活跃的内层步骤，跳过条件节点
                        for sub_idx, sub_state in enumerate(state.sub_states):
                            # 跳过条件节点（step_type == "condition"）
                            if sub_state.step_type == "condition":
                                continue
                            if sub_state.status in ("running", "pending"):
                                inner_step = sub_state.step_id
                                current_inner_idx = sub_idx
                                break
                    break

        # 获取所有内层步骤ID（从所有循环中收集）
        # 同样过滤掉条件节点
        all_inner_step_ids = []
        for loop_state in loop_states:
            if loop_state.sub_states:
                for sub_state in loop_state.sub_states:
                    if sub_state.step_type != "condition":
                        all_inner_step_ids.append(sub_state.step_id)

        # 构建所有循环的状态信息
        loops_info = []
        for loop_state in loop_states:
            # 获取内层步骤ID（过滤条件节点）
            inner_ids = []
            for sub_state in loop_state.sub_states:
                if sub_state.step_type != "condition":
                    inner_ids.append(sub_state.step_id)
            
            loops_info.append({
                "loop_step_id": loop_state.step_id,
                "loop_step_name": loop_state.step_name,
                "loop_type": loop_state.metadata.get("loop_type", "parallel"),
                "current_loop_item": loop_state.current_loop_item,
                "completed_loop_items": loop_state.completed_loop_items[:],
                "remaining_loop_items": [
                    item for item in loop_state.loop_items
                    if item not in loop_state.completed_loop_items
                ],
                "total_loop_items": len(loop_state.loop_items),
                "is_completed": loop_state.is_completed(),
                "status": loop_state.status,
                "inner_step_ids": inner_ids,
            })

        return {
            "outer_step": outer_step,
            "inner_step": inner_step,
            "inner_step_ids": all_inner_step_ids,
            "current_loop_item": first_loop.current_loop_item if first_loop else "",
            "completed_loop_items": first_loop.completed_loop_items[:] if first_loop else [],
            "remaining_loop_items": [
                item for item in (first_loop.loop_items if first_loop else [])
                if item not in (first_loop.completed_loop_items if first_loop else [])
            ],
            "current_outer_idx": current_outer_idx,
            "current_inner_idx": current_inner_idx,
            # 新的多循环字段
            "loops": loops_info,
            "active_loop_index": self._find_active_loop_index(loop_states),
            "total_loops": len(loop_states),
            "completed_loops": sum(1 for l in loop_states if l.is_completed()),
            # 状态树
            "states_tree": self._serialize_states(self._states),
        }

    def _get_all_loop_states(self) -> List[StepState]:
        """获取所有循环状态"""
        loop_states = []
        self._collect_loop_states(self._states, loop_states)
        return loop_states

    def _collect_loop_states(self, states: List[StepState], 
                               loop_states: List[StepState]) -> None:
        """递归收集所有循环状态"""
        for state in states:
            if state.step_type == "loop":
                loop_states.append(state)
            if state.sub_states:
                self._collect_loop_states(state.sub_states, loop_states)

    def _find_active_loop_index(self, loop_states: List[StepState]) -> int:
        """查找当前活跃循环的索引"""
        for idx, loop_state in enumerate(loop_states):
            if loop_state.status in ("running", "pending") and not loop_state.is_completed():
                return idx
        # 如果所有循环都完成，返回最后一个
        return len(loop_states) - 1 if loop_states else -1

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

    def _serialize_states(self, states: List[StepState]) -> List[Dict[str, Any]]:
        """递归序列化状态树"""
        result = []
        for state in states:
            item = {
                "step_id": state.step_id,
                "step_name": state.step_name,
                "step_type": state.step_type,
                "status": state.status,
                "step_result": state.step_result,
                "loop_items": state.loop_items[:],
                "current_loop_item": state.current_loop_item,
                "completed_loop_items": state.completed_loop_items[:],
                "condition_result": state.condition_result,
            }
            if state.sub_states:
                item["sub_states"] = self._serialize_states(state.sub_states)
            result.append(item)
        return result

    def get_current_path(self) -> List[str]:
        """获取当前执行路径"""
        path = []
        self._build_current_path(self._states, path)
        return path

    def _build_current_path(self, states: List[StepState], path: List[str]) -> bool:
        """递归构建当前执行路径"""
        for state in states:
            if state.status == "running":
                path.append(state.step_id)
                if state.sub_states:
                    self._build_current_path(state.sub_states, path)
                return True
            if state.status == "pending":
                path.append(state.step_id)
                if state.sub_states:
                    self._build_current_path(state.sub_states, path)
                return True
        return False

    def is_complete(self) -> bool:
        """判断流程是否完全结束"""
        return all(state.is_completed() for state in self._states)

    def get_progress(self) -> float:
        """获取整体进度（0.0 - 1.0）"""
        if not self._states:
            return 0.0
        total_steps, completed_steps = self._calculate_progress_recursive(self._states)
        if total_steps == 0:
            return 0.0
        return min(completed_steps / total_steps, 1.0)

    def _calculate_progress_recursive(self, states: List[StepState]) -> Tuple[float, float]:
        """递归计算进度（支持多平行循环）

        对于多平行循环：
        - 每个循环是独立的进度单元
        - 循环内的子步骤进度按循环项完成情况加权
        """
        total = 0.0
        completed = 0.0
        for state in states:
            if state.step_type == "loop" and state.loop_items:
                # 循环步骤：按循环项数量计算
                loop_total = len(state.loop_items)
                loop_completed = len(state.completed_loop_items)
                
                # 计算当前循环项的进度
                if state.is_completed():
                    loop_progress = loop_total
                elif state.is_running():
                    # 正在执行当前循环项，按子步骤进度计算
                    sub_progress = self._calculate_sub_steps_progress(state.sub_states)
                    loop_progress = loop_completed + sub_progress
                else:
                    loop_progress = loop_completed
                
                total += loop_total
                completed += loop_progress
            elif state.sub_states:
                # 有子步骤的非循环节点
                sub_total, sub_completed = self._calculate_progress_recursive(state.sub_states)
                total += sub_total
                completed += sub_completed
            else:
                # 普通叶子节点
                if state.is_completed():
                    total += 1
                    completed += 1
                elif state.is_running():
                    total += 1
                    completed += 0.5
                else:
                    total += 1

        return total, completed

    def _calculate_sub_steps_progress(self, sub_states: List[StepState]) -> float:
        """计算循环内子步骤的进度（0.0 - 1.0）"""
        if not sub_states:
            return 0.0
        
        total = len(sub_states)
        completed = 0.0
        
        for sub_state in sub_states:
            if sub_state.is_completed():
                completed += 1.0
            elif sub_state.is_running():
                completed += 0.5
            elif sub_state.status == "error":
                completed += 0.5
        
        return completed / total if total > 0 else 0.0

    def reset(self) -> None:
        """重置流程状态"""
        self._states = []
        self._step_results = []
        self._current_path = []
        self._paused = False
        self._sandbox.clear()
        if self._steps:
            self._init_states(self._steps, self._states)
