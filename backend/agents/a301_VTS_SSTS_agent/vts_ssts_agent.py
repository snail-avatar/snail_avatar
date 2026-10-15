# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vts_ssts_agent.py
# @Desc    : VTS状态分析Agent - 支持 function calling
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS_SSTS_agent - VTS 状态分析 Agent（支持 function calling）

角色定位:
  "VTS 状态分析专家" —— 根据 memorycore 中的 VTS/SSTS 参数数据，回答用户关于
  整车目标值状态、达标情况的问题。数据有效性由查询工具内部自动保证。

能力:
  1. 读取 MemoryCore 中结构化的 VTS/SSTS 参数
  2. 统计达标情况并转义为自然语言摘要
  3. 按车型筛选参数数据

工作流程:
  - 查询类工具会自动检测参数是否已计算（NaN 检测）
  - 如未计算，自动触发 VTS 全车型计算
  - 自动刷新达标标识后返回分析结果
  - 用户无需关心"先计算再查询"的技术细节

继承关系:
  VTSComputeAgent → 获得 VTS 计算注册 + LLM 对话 / 对话历史 / 工具注册 / function calling 能力

对外接口保持不变:
  - send_message(user_input, context_prefix, callback) -> (response_text, usage_info)
  - clear_history()
  - initialize()
  - register_tool()
  - get_registered_tool_names()
"""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from snail_avatar.backend.agents.core.agent_base import VTSComputeAgent
from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger

from .functions import create_default_registry, set_memory_db


# ==========================================================================
# Agent 主类
# ==========================================================================

class VtsSstsAgent(VTSComputeAgent):
    """VTS 状态分析 Agent - 支持 function calling"""

    # VTS 计算自动注册
    is_vts_agent = True
    vts_category = "VTS状态分析"
    vts_priority = 5

    # VTS 分析可能涉及多轮工具调用，轮数较多
    MAX_TOOL_ROUNDS = 8

    # VTS Agent 需要 memory_db（用于读取整车参数）
    NEEDS_MEMORY_DB = True

    def __init__(self):
        # 调用基类初始化
        super().__init__(
            agent_dir=os.path.dirname(__file__),
            yaml_filename="vts_ssts_agent.yaml",
            create_registry_fn=create_default_registry,
            memory_db=None,
            vehicle_suffix="",
        )

    # ------------------------------------------------------------------
    # 主接口：send_message（VTS Agent 有 memory_db 注入逻辑，因此覆写）
    # ------------------------------------------------------------------

    def send_message(self, user_input: str, context_prefix: str = "",
                      callback=None, set_memory_db_fn=None,
                      query_mode: str = "auto",
                      pipeline_config: dict = None) -> Tuple[str, Dict[str, Any], Any]:
        """发送消息并获取 LLM 回复（支持 function calling 循环）"""
        if self.is_processing:
            return "正在处理上一个请求，请等待...", {}, None

        try:
            self.is_processing = True

            # 懒注入 memory_db（VTS 分析需要读取整车参数）
            self._ensure_memory_db(set_memory_db)

            # 记录接收
            AgentMessageLogger.log(
                self._agent_id, "agent_receive",
                f"VTS 分析专家接收消息（{len(user_input)} 字符，"
                f"上下文前缀 {len(context_prefix)} 字符）",
                user_input_full=user_input,
                has_context=bool(context_prefix),
            )

            # function calling 循环
            result = self._run_tool_calling_loop(
                user_input=user_input,
                context_prefix=context_prefix,
                max_tool_rounds=self.MAX_TOOL_ROUNDS,
                return_with_agent_id=False,
            )
            response_text, cumulative_usage = result[0], result[1]
            structured_data = result[2] if len(result) >= 3 else None

            if callback:
                try:
                    callback(response_text, structured_data)
                except Exception:
                    try:
                        callback(response_text)
                    except Exception:
                        pass

            return response_text, cumulative_usage, structured_data

        except Exception as e:
            error_msg = f"处理请求时发生错误: {e}"
            AgentMessageLogger.log(self._agent_id, "system", error_msg)
            return error_msg, {}, None
        finally:
            self.is_processing = False
