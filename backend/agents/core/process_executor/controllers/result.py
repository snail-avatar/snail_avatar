# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : controller_result.py
# @Desc    : 流程控制器结果管理模块 - 结果记录、查询、汇总
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程控制器结果管理模块

提供 ProcessController 的结果管理扩展功能：
1. 步骤结果记录
2. 单步/多步结果查询
3. 结果汇总报告生成
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from .loop import ProcessControllerLoop


class ProcessControllerResult(ProcessControllerLoop):
    """流程控制器结果管理扩展"""

    def record_result(self, step_id: str, step_result: Dict[str, Any], **kwargs) -> None:
        """记录步骤结果

        Args:
            step_id: 步骤ID
            step_result: 步骤执行结果（字典格式）
            **kwargs: 额外参数
        """
        self._record_result(step_id, step_result, **kwargs)

    def _record_result(self, step_id: str, step_result: Dict[str, Any], **kwargs) -> None:
        """内部方法：记录步骤结果

        自动为循环内步骤添加循环项前缀，以保证跨循环项的唯一性。
        例如：step_id='ANALYZE_PRODUCT', loop_item='空气动力学'
              → full_step_id='空气动力学_ANALYZE_PRODUCT'
        """
        # 优先使用 kwargs 中传入的 loop_item
        if "loop_item" in kwargs:
            loop_item = kwargs.pop("loop_item")
        else:
            loop_state = self._find_loop_state(self._states)
            loop_item = loop_state.current_loop_item if loop_state else ""

        # 自动为循环内步骤添加前缀
        full_step_id = step_id
        if loop_item:
            # 检查是否已经有前缀（避免重复添加）
            prefix = f"{loop_item}_"
            if not step_id.startswith(prefix):
                full_step_id = f"{loop_item}_{step_id}"

        result = {
            "step_id": full_step_id,
            "step_result": step_result,
            "timestamp": datetime.datetime.now().isoformat(),
            "loop_item": loop_item,
            **kwargs,
        }

        # 按 full_step_id 覆盖更新，而非 append 追加
        # 原因：ProcessEngine 对同一步骤会调 2 次 advance（"执行中..." + 真实结果），
        # append 会导致列表里同一步骤有 2 条记录，消费方（Panel、导出脚本）需要自己过滤。
        # 覆盖更新后，_step_results 天生干净——每个 step_id 只有最新的一条。
        dedup_key = full_step_id
        replaced = False
        for idx, existing in enumerate(self._step_results):
            if existing.get("step_id", "") == dedup_key:
                self._step_results[idx] = result
                replaced = True
                break
        if not replaced:
            self._step_results.append(result)

    def get_step_results(self) -> List[Dict[str, Any]]:
        """获取所有步骤结果"""
        return self._step_results[:]

    def get_full_summary(self) -> Dict[str, Any]:
        """获取完整流程的汇总报告"""
        return {
            "progress": self.get_progress(),
            "is_complete": self.is_complete(),
            "current_path": self.get_current_path(),
            "states_tree": self._serialize_states(self._states),
            "step_results": self._step_results[:],
            "summary": self._build_summary_text(),
        }

    def _build_summary_text(self) -> str:
        """构建文本摘要"""
        lines = []
        lines.append("流程执行汇总报告")
        lines.append("=" * 40)

        self._build_summary_recursive(self._states, lines, 0)

        if self._step_results:
            lines.append("")
            lines.append("步骤结果记录:")
            for result in self._step_results:
                step_result = result.get('step_result', {})
                summary_text = self._extract_summary_text(step_result)
                lines.append(f"  - {result['step_id']}: {summary_text[:50]}...")

        return "\n".join(lines)

    def _extract_summary_text(self, step_result: Dict[str, Any]) -> str:
        """从步骤结果字典中提取用于显示的文本
        
        处理不同格式的结果：
        - 普通步骤: {"type": "text", "content": "...", "reasoning_logic": "..."}
        - 总结步骤: {"type": "text", "content": "纯文本总结..."}
        - 条件步骤: {"type": "text", "content": "条件判断: 通过"}
        """
        if not step_result:
            return ""
        if isinstance(step_result, str):
            return step_result
        # 优先返回 content 字段
        if "content" in step_result:
            content = step_result["content"]
            if isinstance(content, str):
                return content
            return str(content)
        # 否则返回字典的字符串表示
        return str(step_result)

    def _build_summary_recursive(self, states: List, lines: List[str], indent: int) -> None:
        """递归构建摘要文本"""
        prefix = "  " * indent
        for state in states:
            status_icon = "✓" if state.is_completed() else "○" if state.is_running() else " "
            line = f"{prefix}{status_icon} {state.step_name} ({state.step_id})"
            if state.step_type == "loop":
                line += f" [循环: {len(state.completed_loop_items)}/{len(state.loop_items)}]"
            if state.step_result:
                summary_text = self._extract_summary_text(state.step_result)
                if summary_text:
                    line += f" - {summary_text[:30]}..."
            lines.append(line)
            if state.sub_states:
                self._build_summary_recursive(state.sub_states, lines, indent + 1)