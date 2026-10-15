# @Time    : 2026
# @Author  : 李涛
# @File    : main_agent.py
# @Desc    : 主Agent - 通用LLM对话 + 子Agent路由（支持 function calling）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
主Agent - 通用LLM对话 + 子Agent路由

角色与职责:
  1. 作为系统的默认对话入口，回答通用技术问题
  2. 通过 AgentRouter 调度子 Agent（关键词匹配 → 转交给对应领域 Agent）
  3. 在自己的对话中调用内部工具函数（例如列出所有子 Agent 信息）

继承关系:
  LLMConversationAgent → 获得 LLM 对话 / 对话历史 / 工具注册 / function calling 能力
  主 Agent 不参与 VTS 计算，因此直接继承基础对话能力

对外接口保持不变:
  - send_message(user_input, context_prefix, callback) -> (response_text, usage_info, responding_agent_id)
  - clear_history()
  - initialize()
  - register_tool()
  - get_registered_tool_names()
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from snail_avatar.backend.agents.core.agent_base import LLMConversationAgent
from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionRegistry
from snail_avatar.backend.agents.core.tools.routing import get_agent_router
from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger


# ==========================================================================
# Agent 主类
# ==========================================================================

class MainAgent(LLMConversationAgent):
    """主Agent - 通用LLM对话 + 子Agent路由 + function calling"""

    # 主 Agent 的工具调用轮数略少（主要职责是路由，不是深度工具调用）
    MAX_TOOL_ROUNDS = 5

    # 主 Agent 不需要 memory_db
    NEEDS_MEMORY_DB = False

    # 主 Agent 保留对话历史，维持与用户的连续对话
    CLEAR_HISTORY_ON_CALL = False

    def __init__(self):
        # 调用基类初始化
        # 使用空的注册表工厂，由基类根据 YAML 配置中的 public_functions 自动注册工具
        super().__init__(
            agent_dir=os.path.dirname(__file__),
            yaml_filename="main_agent.yaml",
            create_registry_fn=lambda: FunctionRegistry(),
            memory_db=None,
            vehicle_suffix="",
        )

    # ------------------------------------------------------------------
    # 主 Agent 专属：AgentRouter 懒加载
    # ------------------------------------------------------------------

    def _extra_init(self) -> None:
        """主 Agent 专属初始化：懒加载 AgentRouter"""
        self._router: Optional[Any] = None

    @property
    def router(self):
        """懒加载 AgentRouter"""
        if self._router is None:
            self._router = get_agent_router()
            self._router.register(self._agent_id, self)
        return self._router

    # ------------------------------------------------------------------
    # 子 Agent 委托（主 Agent 专属）
    # ------------------------------------------------------------------

    def delegate_to_agent(self, agent_id, user_input, context_prefix="") -> Tuple[str, Dict[str, Any], str, Any]:
        """将用户消息转交给子Agent处理

        Args:
            agent_id:       目标Agent标识
            user_input:     用户输入文本
            context_prefix: 上下文前缀

        Returns:
            tuple: (response_text, usage_info, agent_id, structured_data)
        """
        agent = self.router.get_agent(agent_id)
        if not agent:
            return f"未找到Agent: {agent_id}", {}, agent_id, None

        try:
            # 清空历史逻辑已移至各子 Agent 的 send_message 入口处
            # 子 Agent 通过 CLEAR_HISTORY_ON_CALL 属性自行决定是否清空
            result = agent.send_message(user_input, context_prefix=context_prefix)
            if isinstance(result, tuple):
                if len(result) >= 4:
                    return result[0], result[1] or {}, result[2], result[3]
                elif len(result) >= 3:
                    return result[0], result[1] or {}, agent_id, result[2]
                elif len(result) == 2:
                    return result[0], result[1] or {}, agent_id, None
            return str(result), {}, agent_id, None
        except Exception as e:
            return f"子Agent处理失败: {e}", {}, agent_id, None

    # ------------------------------------------------------------------
    # 主接口：send_message（主 Agent 有路由逻辑，因此覆写基类方法）
    # ------------------------------------------------------------------

    def send_message(self, user_input, context_prefix: str = "",
                     callback=None) -> Tuple[str, Dict[str, Any], str]:
        """发送消息并获取 LLM 回复（支持子 Agent 调度 + 主 Agent function calling）

        处理流程:
          1. 先尝试通过 router 的关键词匹配转交给子 Agent
          2. 如果没有匹配关键词，则由主 Agent 在自己的对话中调用自有工具
             并通过 LLM 生成最终回复

        Args:
            user_input:      用户输入文本
            context_prefix: 父Agent传递的上下文前缀（可选，主 Agent 一般为空）
            callback:        流式回调函数（可选，当前实现为非流式，但保留接口兼容）

        Returns:
            tuple: (response_text, usage_info, responding_agent_id)
        """
        if self.is_processing:
            return "正在处理上一个请求，请等待...", {}, self._agent_id

        try:
            self.is_processing = True

            # ===== 第一步：关键词匹配，决定是否转交给子 Agent =====
            # 获取最近3轮对话历史，用于辅助路由决策
            history_for_routing = self.conversation.get_history()[-6:] if self.conversation.get_history() else []
            dispatch_result = self.router.dispatch(user_input, self._agent_id, history_for_routing)
            target_agent_id = dispatch_result["agent_id"]

            if target_agent_id != self._agent_id:
                # 转交给子 Agent 处理
                response_text, usage_info, responding_agent, structured_data = self.delegate_to_agent(
                    target_agent_id, user_input, dispatch_result["context_prefix"]
                )

                # 把子 Agent 的回复记录到主 Agent 对话历史（用于上下文连贯）
                self.conversation.add_user_message(user_input)
                self.conversation.add_assistant_message(f"[由 {responding_agent} 回答] {response_text}")

                AgentMessageLogger.log(
                    self._agent_id, "round_separator",
                    f"===== 本轮对话结束（最终回复由 {responding_agent} 生成）=====",
                )

                if callback:
                    try:
                        callback(response_text, structured_data)
                    except Exception:
                        try:
                            callback(response_text)
                        except Exception:
                            pass
                return response_text, usage_info, responding_agent, structured_data

            # ===== 第二步：主 Agent 自己处理（支持 function calling）=====
            # 调用基类的 function calling 循环
            result = self._run_tool_calling_loop(
                user_input=user_input,
                context_prefix=context_prefix,
                max_tool_rounds=self.MAX_TOOL_ROUNDS,
                return_with_agent_id=True,
            )
            if len(result) >= 4:
                response_text, cumulative_usage, responding_agent, structured_data = result
            else:
                response_text, cumulative_usage, responding_agent = result
                structured_data = None

            AgentMessageLogger.log(
                self._agent_id, "round_separator",
                f"===== 本轮对话结束（最终回复由 {responding_agent} 生成）=====",
            )

            if callback:
                try:
                    callback(response_text, structured_data)
                except Exception:
                    try:
                        callback(response_text)
                    except Exception:
                        pass

            return response_text, cumulative_usage, responding_agent, structured_data

        except Exception as e:
            error_msg = f"处理请求时发生错误: {e}"
            AgentMessageLogger.log(self._agent_id, "system", error_msg)
            return error_msg, {}, self._agent_id
        finally:
            self.is_processing = False
