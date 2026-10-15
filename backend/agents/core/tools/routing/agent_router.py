# @Time    : 2026
# @Author  : 李涛
# @File    : agent_router.py
# @Desc    : 多Agent路由与上下文管理
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
多Agent路由与上下文管理

-配置驱动：从 agents/*/config/*.yaml 读取 agent_id、module_path、路由关键词、上下文压缩参数
-负责Agent注册、发现、上下文传递和调度
-验证多Agent系统的调用逻辑和上下文传递逻辑
"""

import importlib
import os
import glob
import yaml

from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger


class AgentRouter:
    """多Agent路由器

    职责：
    - Agent注册与发现（配置驱动）
    - 上下文传递（父Agent → 子Agent）
    - Agent调度（根据用户消息决定由哪个Agent处理）
    """

    _instance = None
    _agents = {}
    _agent_configs = {}   # 存储从 yaml 加载的完整配置

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_all_agent_configs()  # 实例化时扫描所有配置
        return cls._instance

    # ========== 配置扫描与加载 ==========

    def _load_all_agent_configs(self):
        """扫描 agents/*/config/*.yaml，加载所有子Agent配置

        约定的目录结构：
            snail_avatar/
                agents/
                    00_main_agent/config/main_agent.yaml
                    01_VTS_SSTS_agent/config/vts_ssts_agent.yaml
                    ...
        
        兼容打包环境：同时扫描内置Agent和用户添加的Agent
        """
        from snail_avatar.backend.core.path_utils import is_frozen, get_resource_dir, get_writable_dir
        
        agents_dirs = []
        
        # 1. 扫描内置Agent（开发环境或打包环境的内置目录）
        agents_dir = os.path.join(get_resource_dir(), "agents")
        if os.path.isdir(agents_dir):
            agents_dirs.append(agents_dir)
        
        # 2. 打包环境下，额外扫描EXE目录下的agents文件夹（用户添加的Agent）
        if is_frozen():
            user_agents_dir = os.path.join(get_writable_dir(), "agents")
            if os.path.isdir(user_agents_dir) and user_agents_dir != agents_dir:
                agents_dirs.append(user_agents_dir)
        
        # 开发环境下，也支持在 agents/ 目录添加新 Agent
        if not is_frozen():
            # 从 core/tools/routing/agent_router.py 往上 4 级 → agents/
            dev_agents_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            if os.path.isdir(dev_agents_dir) and dev_agents_dir != agents_dir:
                agents_dirs.append(dev_agents_dir)

        if not agents_dirs:
            return

        # 查找所有 agent 配置文件
        for agents_dir in agents_dirs:
            yaml_pattern = os.path.join(agents_dir, "*", "config", "*.yaml")
            for yaml_path in glob.glob(yaml_pattern):
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)

                    if not config or "agent_id" not in config:
                        continue

                    agent_id = config["agent_id"]
                    agent_dir = os.path.dirname(os.path.dirname(yaml_path))
                    config["_agent_dir"] = agent_dir
                    self._agent_configs[agent_id] = config

                except Exception as e:
                    print(f"加载Agent配置失败 [{yaml_path}]: {e}")

    def get_agent_config(self, agent_id):
        """获取指定Agent的完整配置 dict"""
        return self._agent_configs.get(agent_id, {})

    def get_all_agent_ids(self):
        """获取所有已配置的 agent_id 列表"""
        return list(self._agent_configs.keys())

    def register(self, agent_id, agent_instance):
        """注册Agent实例

        Args:
            agent_id: Agent唯一标识
            agent_instance: Agent实例
        """
        self._agents[agent_id] = agent_instance

    def get_agent(self, agent_id):
        """获取Agent实例

        Args:
            agent_id: Agent唯一标识

        Returns:
            Agent实例，不存在则返回None
        """
        if agent_id not in self._agents:
            self._lazy_load_agent(agent_id)
        return self._agents.get(agent_id)

    def _lazy_load_agent(self, agent_id):
        """懒加载Agent实例（从配置读取 module_path）

        Args:
            agent_id: Agent唯一标识
        """
        config = self._agent_configs.get(agent_id)
        if not config:
            return

        module_path = config.get("module_path")
        if not module_path:
            return

        try:
            module = importlib.import_module(module_path)
            
            if hasattr(module, "GenericExpertAgent"):
                agent_dir = config.get("_agent_dir")
                yaml_filename = f"{agent_id}.yaml"
                agent_class = getattr(module, "GenericExpertAgent")
                self._agents[agent_id] = agent_class(agent_dir=agent_dir, yaml_filename=yaml_filename)
            elif hasattr(module, "GenericWorkflowAgent"):
                agent_dir = config.get("_agent_dir")
                yaml_filename = f"{agent_id}.yaml"
                agent_class = getattr(module, "GenericWorkflowAgent")
                self._agents[agent_id] = agent_class(agent_dir=agent_dir, yaml_filename=yaml_filename)
            else:
                agent_class_name = "".join(word.capitalize() for word in agent_id.split("_"))
                agent_class = getattr(module, agent_class_name, None)
                if agent_class:
                    self._agents[agent_id] = agent_class()
        except Exception as e:
            pass

    def list_agents(self):
        """列出所有已注册的Agent

        Returns:
            list: [{agent_id, agent_name, agent_description}, ...]
        """
        result = []
        for agent_id, agent in self._agents.items():
            result.append({
                "agent_id": agent_id,
                "agent_name": getattr(agent, "AGENT_NAME", agent_id),
                "agent_description": getattr(agent, "AGENT_DESCRIPTION", ""),
            })
        return result

    # ========== 上下文构建 ==========

    def build_context(self, from_agent_id, to_agent_id, user_message):
        """构建传递给目标Agent的上下文（截断长度从配置读取）"""
        from_agent = self.get_agent(from_agent_id)
        to_agent = self.get_agent(to_agent_id)
        from_config = self._agent_configs.get(from_agent_id, {})

        if not from_agent or not to_agent:
            return ""

        from_name = getattr(from_agent, "AGENT_NAME", from_agent_id)
        from_prompt = getattr(from_agent, "_system_prompt", "") or getattr(from_agent, "SYSTEM_PROMPT", "")

        # 从配置读取截断参数
        ctx_cfg = from_config.get("context_config", {})
        prompt_truncate = ctx_cfg.get("source_prompt_truncate", 2000)
        from_prompt_truncated = from_prompt[:prompt_truncate]

        to_name = getattr(to_agent, "AGENT_NAME", to_agent_id)

        # 提取源Agent最近的对话摘要（最近对话完整保留，不截断）
        # 将源 Agent 的 summary_config 和 agent_id 传入摘要器，实现按 Agent 差异化摘要
        recent_summary = self._extract_recent_summary(
            from_agent,
            max_rounds=ctx_cfg.get("recent_summary_max_rounds", 3),
            summary_config=from_config.get("summary_config", {}),
            agent_id=from_agent_id,
        )

        context = f"[来自 {from_name} 的上下文]\n"
        context += f"{from_name} 角色描述：{from_prompt_truncated}...\n"
        if recent_summary:
            context += f"{from_name} 最近对话摘要：{recent_summary}\n"
        context += f"\n[请 {to_name} 基于以上上下文回答用户问题]"

        # 记录上下文构建过程（完整内容，供面板调试查看）
        # full_input: 上下文 + 用户问题的完整拼接（即子 Agent 实际收到的输入）
        full_input = context + "\n\n[用户当前问题]\n" + user_message
        AgentMessageLogger.log(
            "router", "context_build",
            f"已构建上下文：{from_agent_id} → {to_agent_id}，长度 {len(context)} 字符",
            context_full=context,
            full_input=full_input,
        )

        return context

    def _extract_recent_summary(self, agent, max_rounds=3, summary_config=None, agent_id=None):
        """提取Agent最近的对话摘要（LLM摘要 + 最近对话原文）

        使用 ConversationSummarizer 将旧对话压缩为摘要，
        最近 max_rounds 轮（max_rounds*2 条）完整保留原文。
        LLM 失败时自动降级为纯规则截断。

        Args:
            agent: 源 Agent 实例
            max_rounds: 完整保留的最近对话轮数（1轮 = user + assistant）
            summary_config: 可选，源 Agent 的摘要专用配置（来自 YAML 的 summary_config 节）
            agent_id: 可选，源 Agent 的 ID，用于在摘要器中按 Agent 缓存 LLMDeploy 实例
        """
        from snail_avatar.backend.agents.core.tools.LLM_tools import get_summarizer

        history = agent.conversation.get_history()
        if not history:
            return ""

        keep_recent = max_rounds * 2
        summarizer = get_summarizer()
        summary_text, recent_messages = summarizer.summarize_with_recent(
            history,
            keep_recent=keep_recent,
            summary_config=summary_config,
            agent_id=agent_id,
        )

        # 拼接：旧对话摘要 + 最近对话原文（完整保留，不截断）
        parts = []
        if summary_text:
            parts.append(f"[之前对话摘要]\n{summary_text}")
        if recent_messages:
            recent_text = self._format_recent_messages(recent_messages)
            if recent_text:
                parts.append(f"[最近对话]\n{recent_text}")

        return "\n\n".join(parts)

    @staticmethod
    def _format_recent_messages(messages):
        """将最近对话消息格式化为可读文本（完整保留原文，不截断）

        Args:
            messages: 最近对话消息列表

        Returns:
            str: 格式化后的对话文本
        """
        parts = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content")
            if content is None:
                content = ""
            if role == "user":
                parts.append(f"用户: {content}")
            elif role == "assistant":
                parts.append(f"助手: {content}")
            elif role == "tool":
                if content:
                    parts.append(f"工具结果: {content}")
        return "\n".join(parts)

    # ========== 上下文路由决策 ==========

    def dispatch(self, user_message, current_agent_id="main_agent", conversation_history=None):
        """根据用户消息决定由哪个Agent处理（**优先使用 LLM 路由决策**，失败降级为关键词匹配）

        Args:
            user_message: 用户消息文本
            current_agent_id: 当前活跃Agent标识
            conversation_history: 对话历史列表，格式为 [{"role": "user|assistant|system", "content": "..."}]

        Returns:
            dict: {agent_id, context_prefix, reason}
        """
        # 记录用户原始输入
        AgentMessageLogger.log(current_agent_id, "user_input", user_message)

        # ======================================================================
        # 步骤 1：优先调用 LLM 路由工具决策
        # ======================================================================
        try:
            from snail_avatar.backend.agents.core.tools.LLM_tools import get_llm_router

            llm_router_tool = get_llm_router()
            llm_result = llm_router_tool.route(
                user_message,
                current_agent_id,
                agent_configs=self._agent_configs,
                conversation_history=conversation_history,
            )

            # LLM 返回的结果格式（新增字段说明）:
            #   {"agent_id": str, "reason": str, "trust_level": ..., "used_llm": bool,
            #    "llm_input_system_prompt": str, "llm_input_user_message": str,
            #    "llm_raw_output": str, "llm_parsed_output": str, "fallback_reason": str}
            if isinstance(llm_result, dict):
                target_agent_id = str(llm_result.get("agent_id", "")).strip()
                reason = str(llm_result.get("reason", "")).strip() or "LLM路由决策"
                used_llm = bool(llm_result.get("used_llm", False))
                trust_level = str(llm_result.get("trust_level", "medium"))

                if target_agent_id and target_agent_id in self._agent_configs:
                    # 构造 extra：携带 LLM 输入输出和降级信息，供 UI 详细展示
                    extra = {
                        "current_agent": current_agent_id,
                        "target_agent": target_agent_id,
                        "used_llm": used_llm,
                        "trust_level": trust_level,
                    }
                    for k in ("llm_input_system_prompt", "llm_input_user_message",
                              "llm_raw_output", "llm_parsed_output", "fallback_reason"):
                        v = llm_result.get(k)
                        if v not in (None, ""):
                            extra[k] = v

                    method_label = "LLM路由" if used_llm else "关键词匹配"
                    display_reason = (
                        f"[{method_label}] {reason}，转交至 {target_agent_id}"
                        f" (trust_level={trust_level})"
                    )
                    AgentMessageLogger.log(
                        "router", "router_decision",
                        display_reason,
                        **extra,
                    )

                    context_prefix = ""
                    if current_agent_id != target_agent_id:
                        context_prefix = self.build_context(
                            current_agent_id, target_agent_id, user_message
                        )
                    return {
                        "agent_id": target_agent_id,
                        "context_prefix": context_prefix,
                        "reason": f"[{method_label}] {reason}",
                    }
        except Exception as e:
            # LLM 路由工具本身抛异常，不影响主流程，降级为原有关键词匹配
            try:
                AgentMessageLogger.log(
                    "router", "router_fallback",
                    f"LLM 路由工具调用异常，已降级为关键词匹配。"
                    f" 异常类型: {type(e).__name__}",
                    error=str(e),
                )
            except Exception:
                pass

        # ======================================================================
        # 步骤 2：LLM 路由不可用，降级为原有关键词匹配
        # ======================================================================
        for agent_id, config in self._agent_configs.items():
            if agent_id == current_agent_id:
                continue

            keywords = config.get("routing_keywords", [])
            if not keywords:
                continue

            for keyword in keywords:
                if keyword in user_message:
                    AgentMessageLogger.log(
                        "router", "router_decision",
                        f"匹配关键词 [{keyword}]，转交至 {agent_id}",
                        current_agent=current_agent_id,
                        target_agent=agent_id,
                        used_llm=False,
                        trust_level="low",
                        fallback_reason="LLM 路由工具不可用，已降级为关键词匹配",
                    )

                    context_prefix = ""
                    if current_agent_id != agent_id:
                        context_prefix = self.build_context(
                            current_agent_id, agent_id, user_message
                        )
                    return {
                        "agent_id": agent_id,
                        "context_prefix": context_prefix,
                        "reason": f"匹配关键词 [{keyword}]，转交至 {agent_id}",
                    }

        # 默认由当前Agent处理
        AgentMessageLogger.log(
            "router", "router_decision",
            f"无匹配关键词，由 {current_agent_id} 直接处理",
            current_agent=current_agent_id,
            used_llm=False,
            trust_level="low",
            fallback_reason="LLM 路由工具不可用且无匹配关键词",
        )

        return {
            "agent_id": current_agent_id,
            "context_prefix": "",
            "reason": "无匹配关键词，由当前Agent处理",
        }

    # ========== 清空所有Agent对话历史 ==========

    def clear_all_history(self):
        """清空所有Agent的对话历史"""
        for agent in self._agents.values():
            if hasattr(agent, "clear_history"):
                agent.clear_history()


def get_agent_router():
    """获取AgentRouter单例

    Returns:
        AgentRouter: 路由器实例
    """
    return AgentRouter()
