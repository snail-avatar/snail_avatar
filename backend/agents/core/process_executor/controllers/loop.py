# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : controller_loop.py
# @Desc    : 流程控制器循环管理模块 - 循环项设置、推进、完成
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程控制器循环管理模块

提供 ProcessController 的循环管理扩展功能：
1. 设置循环项（支持多循环，按 loop_step_id 操作）
2. 推进循环项
3. 设置/完成当前循环项
4. 获取所有循环状态
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import ProcessControllerBase
from ..data_structures import StepState


class ProcessControllerLoop(ProcessControllerBase):
    """流程控制器循环管理扩展 - 支持多平行循环"""

    def _find_loop_state_by_id(self, loop_step_id: str, 
                                states: List[StepState] = None) -> Optional[StepState]:
        """按 loop_step_id 查找循环状态

        Args:
            loop_step_id: 循环步骤ID
            states: 要搜索的状态列表（默认 _states）

        Returns:
            Optional[StepState]: 找到的循环状态，未找到返回 None
        """
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
        """获取所有循环状态（支持多平行循环）

        Args:
            states: 要搜索的状态列表（默认 _states）

        Returns:
            List[StepState]: 所有循环状态列表
        """
        if states is None:
            states = self._states

        loop_states = []
        for state in states:
            if state.step_type == "loop":
                loop_states.append(state)
            if state.sub_states:
                loop_states.extend(self._get_all_loop_states(state.sub_states))
        return loop_states

    def set_loop_items(self, loop_items: List[str],
                        loop_step_id: str = None) -> None:
        """设置循环项列表（支持多循环）

        Args:
            loop_items: 循环项列表
            loop_step_id: 循环步骤ID（None 表示设置第一个循环）
        """
        loop_state = self._find_target_loop_state(loop_step_id)
        if loop_state:
            loop_state.loop_items = loop_items[:]
            loop_state.current_loop_item = loop_items[0] if loop_items else ""
            loop_state.completed_loop_items = []
            # ===== 关键：engine 进入循环时，把外层 loop step 标记为 running =====
            if loop_state.status == "pending":
                loop_state.start()

    def advance_loop_item(self, loop_step_id: str = None,
                           loop_item: str = "") -> Dict[str, Any]:
        """推进循环项（完成当前循环项，进入下一个）

        Args:
            loop_step_id: 循环步骤ID（None 表示操作第一个循环）
            loop_item: 当前完成的循环项

        Returns:
            dict: 步骤信息
        """
        loop_state = self._find_target_loop_state(loop_step_id)
        if loop_state and loop_item:
            if loop_item not in loop_state.completed_loop_items:
                loop_state.completed_loop_items.append(loop_item)

            remaining = [item for item in loop_state.loop_items 
                         if item not in loop_state.completed_loop_items]
            loop_state.current_loop_item = remaining[0] if remaining else ""
            for sub in loop_state.sub_states:
                sub.reset()

        return self._build_step_info()

    def advance_outer(self, step_id: str, completed: bool = True, 
                      step_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """推进外层步骤（兼容接口）

        Args:
            step_id: 外层步骤ID
            completed: 是否完成
            step_result: 步骤执行结果（字典格式）

        Returns:
            dict: 步骤信息
        """
        return self.advance(step_id, completed, step_result, step_type="outer")

    def set_current_loop_item(self, loop_item: str,
                                loop_step_id: str = None) -> None:
        """设置当前循环项（同时重置子步骤状态）

        Args:
            loop_item: 循环项名称
            loop_step_id: 循环步骤ID（None 表示操作第一个循环）
        """
        loop_state = self._find_target_loop_state(loop_step_id)
        if loop_state:
            loop_state.current_loop_item = loop_item
            # 重置子步骤状态，以便新一轮循环开始时步骤显示为"待执行"
            for sub in loop_state.sub_states:
                sub.reset()

    def complete_loop_item(self, loop_item: str,
                             loop_step_id: str = None) -> None:
        """完成当前循环项

        Args:
            loop_item: 循环项名称
            loop_step_id: 循环步骤ID（None 表示操作第一个循环）
        """
        loop_state = self._find_target_loop_state(loop_step_id)
        if loop_state:
            if loop_item and loop_item not in loop_state.completed_loop_items:
                loop_state.completed_loop_items.append(loop_item)

            remaining = [item for item in loop_state.loop_items 
                         if item not in loop_state.completed_loop_items]
            loop_state.current_loop_item = remaining[0] if remaining else ""

    def get_all_loop_states_summary(self) -> List[Dict[str, Any]]:
        """获取所有循环的状态摘要

        Returns:
            List[Dict[str, Any]]: 每个循环的状态摘要
        """
        loop_states = self._get_all_loop_states()
        summaries = []
        for loop_state in loop_states:
            summaries.append({
                "loop_step_id": loop_state.step_id,
                "loop_step_name": loop_state.step_name,
                "loop_type": loop_state.metadata.get("loop_type", "parallel"),
                "current_item": loop_state.current_loop_item,
                "completed_items": loop_state.completed_loop_items[:],
                "remaining_items": [
                    item for item in loop_state.loop_items 
                    if item not in loop_state.completed_loop_items
                ],
                "total_items": len(loop_state.loop_items),
                "is_completed": loop_state.is_completed(),
                "status": loop_state.status,
            })
        return summaries

    def _find_target_loop_state(self, loop_step_id: str = None) -> Optional[StepState]:
        """查找目标循环状态

        Args:
            loop_step_id: 循环步骤ID（None 表示第一个循环）

        Returns:
            Optional[StepState]: 循环状态
        """
        if loop_step_id:
            return self._find_loop_state_by_id(loop_step_id)
        
        # 返回第一个循环
        loop_states = self._get_all_loop_states()
        return loop_states[0] if loop_states else None

    def get_loop_progress(self, loop_step_id: str) -> Dict[str, Any]:
        """获取指定循环的进度

        Args:
            loop_step_id: 循环步骤ID

        Returns:
            Dict[str, Any]: 循环进度信息
        """
        loop_state = self._find_loop_state_by_id(loop_step_id)
        if not loop_state:
            return {
                "loop_step_id": loop_step_id,
                "error": "循环未找到",
            }

        total = len(loop_state.loop_items)
        completed = len(loop_state.completed_loop_items)
        progress = completed / total if total > 0 else 0.0

        return {
            "loop_step_id": loop_step_id,
            "loop_step_name": loop_state.step_name,
            "total_items": total,
            "completed_items": completed,
            "current_item": loop_state.current_loop_item,
            "progress": progress,
            "is_completed": loop_state.is_completed(),
            "status": loop_state.status,
        }
