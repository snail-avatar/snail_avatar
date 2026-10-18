# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : llm_conversation_agent.py
# @Desc    : LLM 对话通用能力基类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
LLM 对话通用能力基类

作为所有 Agent 的最基础类，提供核心对话能力：
  1. 从 YAML 配置加载 agent_id / system_prompt / llm_config
  2. LLM 客户端（get_llm_instance）
  3. 对话历史（ConversationManager）
  4. 工具注册中心（FunctionRegistry）
  5. 两轮式工具目录选择（select_tools）
  6. function calling 循环（_run_tool_calling_loop）

适用的 4 类 Agent：
  1. 主Agent（带 AgentRouter 调度）
  2. 裁判Agent（纯 LLM 对话 + 评价工具）
  3. 计算分析型（VTS/Economy/Power，需 memory_db + 工作流）
  4. 专家问答型（带向量库 / 知识图谱 / 规则库）

继承层次：
  LLMConversationAgent（最基础）
    ├── VTSComputeAgent（VTS 计算注册 + 契约接口）
    │     └── WorkflowAgentBase（工作流计算）
    └── SSTSComputeAgent（预留：SSTS 计算/评估）
"""

import os
from typing import Any, Dict, Tuple

import yaml

from snail_avatar.backend.llm.deploy import get_llm_instance, initialize_llm
from snail_avatar.backend.agents.core.agent_base.conversation_manager import ConversationManager
from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger
from snail_avatar.backend.agents.core.public_functions_core.knowledge.function_templates.search_vector_template import (
    consume_pending_images,
)
from snail_avatar.backend.agents.core.public_functions_core.tool_selector import select_tools, get_catalog_prompt_from_config
from snail_avatar.backend.core.path_utils import get_agent_config_path


# =============================================================================
# 模块级辅助函数：统一加载 Agent 的 YAML 配置
# =============================================================================

def _load_agent_config(agent_dir: str, yaml_filename: str) -> Tuple[Dict[str, Any], str, str, str, Dict[str, Any], str]:
    """从 Agent 目录加载 YAML 配置，返回 (config, agent_id, agent_name, system_prompt, llm_config, catalog_prompt)。

    Args:
        agent_dir:     Agent 所在目录（例如 os.path.dirname(__file__)）
        yaml_filename: YAML 文件名（例如 "main_agent.yaml"）

    Returns:
        tuple: (config, agent_id, agent_name, system_prompt, llm_config, catalog_prompt)
    """
    config_path = get_agent_config_path(agent_dir, yaml_filename)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    agent_id = config.get("agent_id", "unknown_agent")
    agent_name = config.get("agent_name", "未命名 Agent")
    system_prompt = config.get("system_prompt", "")
    llm_config = config.get("llm_config", {})
    catalog_prompt = get_catalog_prompt_from_config(config)
    agent_runtime_config = config.get("agent_runtime_config", {})

    return config, agent_id, agent_name, system_prompt, llm_config, catalog_prompt, agent_runtime_config


# =============================================================================
# LLMConversationAgent - LLM 对话通用能力基类
# =============================================================================

class LLMConversationAgent:
    """LLM 对话通用能力基类（所有 Agent 的最基础类）

    统一封装的能力:
      1. 从 YAML 配置加载 agent_id / system_prompt / llm_config
      2. LLM 客户端（get_llm_instance）
      3. 对话历史（ConversationManager）
      4. 工具注册中心（FunctionRegistry）
      5. 两轮式工具目录选择（select_tools）
      6. function calling 循环（_run_tool_calling_loop）

    子类需要做的事:
      - 在 __init__ 中调用 super().__init__()
      - 如需 memory_db（纯对话型 Agent 传入 None 即可）
      - 覆写 send_message() 以支持子类型专属逻辑（如主 Agent 的路由）
      - 覆写 _build_user_input() 以定制上下文拼接方式
      - 覆写 _extra_init() 以添加额外的初始化逻辑
    """

    # -------------------------------------------------------------------------
    # 类属性：子类可覆写
    # -------------------------------------------------------------------------

    # function calling 循环的最大轮数
    MAX_TOOL_ROUNDS = 8

    # 对话中对用户显示的名称（用于日志）
    AGENT_DISPLAY_NAME = "LLM 对话 Agent"

    # 是否需要 memory_db（纯对话型为 False，计算分析型为 True）
    NEEDS_MEMORY_DB = False

    # 是否在每次 send_message 调用前清空对话历史
    # - True: 专家型子 agent，每次查询独立
    # - False: 主 agent / 流程编排型 agent，需要保持对话连续性
    CLEAR_HISTORY_ON_CALL = False

    # -------------------------------------------------------------------------
    # __init__
    # -------------------------------------------------------------------------

    def __init__(
        self,
        agent_dir: str,
        yaml_filename: str,
        create_registry_fn,
        memory_db=None,
        vehicle_suffix: str = "",
        agent_display_name: str | None = None,
    ):
        """初始化 LLM 对话 Agent

        Args:
            agent_dir:           Agent 所在目录（例如 os.path.dirname(__file__)）
            yaml_filename:       YAML 配置文件名（例如 "main_agent.yaml"）
            create_registry_fn: 创建工具注册中心的函数（例如 create_default_registry）
            memory_db:           MemoryCore 数据库实例（纯对话型传入 None）
            vehicle_suffix:      车型后缀标识（仅 VTS 计算型使用）
            agent_display_name:   对话中对用户显示的名称（默认从 YAML 读取）
        """
        # 保存 memory_db 和 vehicle_suffix（供 VTS 计算型子类使用）
        self._memory_db = memory_db
        self._vehicle_suffix = vehicle_suffix
        self._agent_dir = agent_dir

        # 1. 加载配置（agent_runtime_config 包含 max_tool_rounds、needs_memory_db 等运行时参数）
        (
            self._config,
            self._agent_id,
            agent_name,
            self._system_prompt,
            self._llm_config,
            self._catalog_prompt,
            self._agent_runtime_config,
        ) = _load_agent_config(agent_dir, yaml_filename)

        self._agent_name = agent_display_name or agent_name

        # 1b. YAML 运行时配置覆盖类属性默认值
        yaml_max_rounds = self._agent_runtime_config.get("max_tool_rounds", None)
        if yaml_max_rounds is not None:
            self.MAX_TOOL_ROUNDS = int(yaml_max_rounds)

        yaml_needs_memory = self._agent_runtime_config.get("needs_memory_db", None)
        if yaml_needs_memory is not None:
            self.NEEDS_MEMORY_DB = bool(yaml_needs_memory)

        yaml_clear_history = self._agent_runtime_config.get("clear_history_on_call", None)
        if yaml_clear_history is not None:
            self.CLEAR_HISTORY_ON_CALL = bool(yaml_clear_history)

        # ===== 统一注入：全局通用规则（从 global_rules.yaml 加载，所有 agent 共享）=====
        # 规则追加在各 agent YAML 的 system_prompt 之后，追加新规则只需改 global_rules.yaml
        _global_rules_yaml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "global_rules.yaml")
        if os.path.isfile(_global_rules_yaml):
            try:
                with open(_global_rules_yaml, "r", encoding="utf-8") as _f:
                    _rules_data = yaml.safe_load(_f) or {}
                _rules_list = _rules_data.get("rules", [])
                if _rules_list:
                    self._system_prompt = (self._system_prompt or "") + "\n" + "\n".join(_rules_list)
            except Exception:
                pass  # YAML 加载失败不阻断 agent 初始化

        # 2. LLM 客户端
        self.llm = get_llm_instance(self._agent_id, self._system_prompt, self._llm_config)

        # 3. 对话历史
        self.conversation: ConversationManager = ConversationManager.from_config(self._config)

        # 4. 并发保护
        self.is_processing = False

        # 5. 工具注册中心
        self._registry = create_registry_fn()
        self._tools_list = self._registry.get_tools_list()

        # 5b. 根据配置注册 public functions
        self._register_public_functions()

        # 6. memory_db 注入状态（计算分析型使用）
        self._memory_db_injected = False

        # 7. 子类扩展初始化
        self._extra_init()

    # -------------------------------------------------------------------------
    # 子类可覆写：扩展初始化
    # -------------------------------------------------------------------------

    def _extra_init(self) -> None:
        """子类可覆写此方法以添加额外的初始化逻辑

        例如：主 Agent 在此初始化 router
        """
        pass

    # -------------------------------------------------------------------------
    # 子类可覆写：定制上下文拼接
    # -------------------------------------------------------------------------

    def _build_user_input(self, user_input: str, context_prefix: str = "") -> str:
        """构造实际送入对话历史的用户输入

        默认实现：有 context_prefix 时拼接 [用户当前问题]

        Args:
            user_input:      原始用户输入
            context_prefix: 上下文前缀

        Returns:
            str
        """
        if context_prefix:
            return context_prefix + "\n\n[用户当前问题]\n" + user_input
        return user_input

    # -------------------------------------------------------------------------
    # 工具管理
    # -------------------------------------------------------------------------

    def register_tool(self, func_class) -> None:
        """注册一个自定义工具类"""
        self._registry.register(func_class)
        self._tools_list = self._registry.get_tools_list()

    def get_registered_tool_names(self):
        """返回所有已注册工具的名称（调试用）"""
        names = []
        for schema in self._tools_list:
            try:
                names.append(schema["function"]["name"])
            except Exception:
                pass
        return names

    def _register_public_functions(self) -> None:
        """根据 YAML 配置注册 public functions

        从 agent 的 YAML 配置中读取 public_functions 配置项，
        如果 enabled 为 True，则将指定的 public functions 注册到工具中心。

        YAML 配置格式:
            public_functions:
              enabled: true
              functions:
                - "list_all_sub_agents"
                - "calculator"
        """
        pub_fn_config = self._config.get("public_functions", {})
        if not pub_fn_config.get("enabled", False):
            return

        func_names = pub_fn_config.get("functions", [])
        if not func_names:
            return

        try:
            from snail_avatar.backend.agents.core.public_functions import get_public_function

            for func_name in func_names:
                fn_cls = get_public_function(func_name)
                if fn_cls:
                    self._registry.register(fn_cls)
                else:
                    AgentMessageLogger.log(
                        self._agent_id, "warning",
                        f"Public function 未找到: {func_name}",
                    )

            self._tools_list = self._registry.get_tools_list()

        except Exception as e:
            AgentMessageLogger.log(
                self._agent_id, "error",
                f"注册 public functions 失败: {e}",
            )

    # -------------------------------------------------------------------------
    # 初始化 LLM 接口
    # -------------------------------------------------------------------------

    def initialize(self):
        """初始化 LLM 接口"""
        return initialize_llm(self._agent_id, self._system_prompt, self._llm_config)

    # -------------------------------------------------------------------------
    # 历史管理
    # -------------------------------------------------------------------------

    def clear_history(self) -> None:
        """清空对话历史"""
        self.conversation.clear_history()

    # -------------------------------------------------------------------------
    # 子类可覆写：memory_db 懒注入
    # -------------------------------------------------------------------------

    def _ensure_memory_db(self, set_memory_db_fn=None) -> None:
        """确保 memory_db 已注入到 functions 模块

        Args:
            set_memory_db_fn: 注入函数（例如 from .functions import set_memory_db）

        注入策略:
          从唯一权威槽 public_functions_core.common.memory_db.get_memory_db() 读取。
          未找到则静默跳过，工具执行时会自行检测并提示用户。
        """
        if not self.NEEDS_MEMORY_DB:
            return

        if set_memory_db_fn is None:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import set_memory_db
            set_memory_db_fn = set_memory_db

        try:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            db = get_memory_db()
            if db is not None:
                current_db = get_memory_db()

                if current_db is not db:
                    set_memory_db_fn(db)
                    AgentMessageLogger.log(
                        self._agent_id, "system",
                        f"已将 memory_db 注入到 {self._agent_name} functions 模块"
                    )
        except Exception as e:
            AgentMessageLogger.log(
                self._agent_id, "system",
                f"[警告] 注入 memory_db 失败: {e}"
            )

    # -------------------------------------------------------------------------
    # 核心：function calling 循环
    # -------------------------------------------------------------------------

    def _run_tool_calling_loop(
        self,
        user_input: str,
        context_prefix: str = "",
        max_tool_rounds: int | None = None,
        return_with_agent_id: bool = False,
    ) -> tuple[str, dict[str, Any], str] | tuple[str, dict[str, Any]]:
        """执行 function calling 循环并返回最终回复

        Args:
            user_input:            用户输入文本
            context_prefix:        上下文前缀
            max_tool_rounds:       最大工具调用轮数（默认使用类属性 MAX_TOOL_ROUNDS）
            return_with_agent_id: 是否在返回值中包含 agent_id（主 Agent 需要，子 Agent 不需要）

        Returns:
            如果 return_with_agent_id=True:  (response_text, usage_info, agent_id)
            否则:                           (response_text, usage_info)
        """
        actual_input = self._build_user_input(user_input, context_prefix)
        self.conversation.add_user_message(actual_input)

        selected_tools_list, _phase1_usage = select_tools(
            llm_instance=self.llm,
            registry=self._registry,
            user_input=user_input,
            agent_id=self._agent_id,
            all_tools_list=self._tools_list,
            catalog_prompt=self._catalog_prompt,
            conversation_history=self.conversation.get_history(),
        )

        cumulative_usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        max_rounds = max_tool_rounds if max_tool_rounds is not None else self.MAX_TOOL_ROUNDS
        tool_round = 0

        while tool_round < max_rounds:
            tool_round += 1

            tools_schema_text = ""
            if selected_tools_list:
                import json as _json
                schema_parts = []
                for _ts in selected_tools_list:
                    try:
                        schema_parts.append(_json.dumps(_ts, ensure_ascii=False))
                    except Exception:
                        schema_parts.append(str(_ts))
                tools_schema_text = "\n\n".join(schema_parts)

            AgentMessageLogger.log(
                self._agent_id, "llm_call",
                f"第 {tool_round} 轮调用 LLM（对话历史 {len(self.conversation)} 条，"
                f"可用工具 {len(selected_tools_list)} 个）",
                tools_schema=tools_schema_text,
            )

            response = self.llm.generate_response(
                "",
                self.conversation.get_history(),
                selected_tools_list,
            )

            if response is None:
                fallback = "LLM 返回结果异常"
                self.conversation.add_assistant_message(fallback)
                if return_with_agent_id:
                    return fallback, {}, self._agent_id
                return fallback, {}

            usage = response.get("usage") or {}
            _r_in = int(usage.get("input_tokens", 0))
            _r_out = int(usage.get("output_tokens", 0))
            _r_tot = int(usage.get("total_tokens", 0))
            cumulative_usage["input_tokens"] += _r_in
            cumulative_usage["output_tokens"] += _r_out
            cumulative_usage["total_tokens"] += _r_tot
            _r_cum = int(cumulative_usage["total_tokens"])

            AgentMessageLogger.log(
                self._agent_id, "system",
                (
                    f"第 {tool_round} 轮 LLM Token: 输入 {_r_in} | "
                    f"输出 {_r_out} | 总计 {_r_tot} | 累计 {_r_cum}"
                ),
                token_phase="phase2_round",
                round_number=tool_round,
                input_tokens=_r_in,
                output_tokens=_r_out,
                total_tokens=_r_tot,
                cumulative_total=_r_cum,
            )

            if isinstance(response, dict) and "tool_call" in response and response["tool_call"]:
                tool_call = response["tool_call"]
                tool_call_id = tool_call.get("id") or ""
                function_name = tool_call.get("name", "")
                arguments_json = tool_call.get("arguments", "{}")

                AgentMessageLogger.log(
                    self._agent_id, "tool_call",
                    f"LLM 请求调用工具: {function_name}",
                    tool_name=function_name,
                    tool_call_id=tool_call_id,
                    tool_arguments=arguments_json,
                )

                self.conversation.add_tool_call_message([{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": arguments_json,
                    },
                }])

                try:
                    structured_data, tool_result = self._registry.execute(function_name, arguments_json, self)
                except Exception as e:
                    structured_data = None
                    tool_result = f"[工具执行异常] {e}"

                # 消费工具返回的图片快照（图搜图/以文搜图工具会往 _pending_result_images 里塞 base64）
                pending_images = consume_pending_images()

                AgentMessageLogger.log(
                    self._agent_id, "tool_result",
                    f"工具 {function_name} 执行完成",
                    tool_name=function_name,
                    tool_call_id=tool_call_id,
                    tool_arguments=arguments_json,
                    tool_result=str(tool_result),
                    result_length=len(str(tool_result)),
                    images=pending_images,  # 把图片base64列表透传到SSE事件里
                )

                self.conversation.add_tool_result(tool_call_id, tool_result, structured_data)

                continue

            response_text = response.get("content", "")
            if isinstance(response_text, dict):
                response_text = response_text.get("content", "")
            self.conversation.add_assistant_message(response_text)

            AgentMessageLogger.log(
                self._agent_id, "agent_response",
                f"{self._agent_name}回复（{len(response_text)} 字符）",
                response_full=response_text,
                usage=str(cumulative_usage),
            )

            last_structured_data = None
            history = self.conversation.get_history()
            last_tool_id = None
            for msg in reversed(history):
                if msg.get("role") == "tool":
                    last_tool_id = msg.get("tool_call_id")
                    break
            if last_tool_id:
                last_structured_data = self.conversation.get_structured_data(last_tool_id)

            if return_with_agent_id:
                return response_text, cumulative_usage, self._agent_id, last_structured_data
            return response_text, cumulative_usage, last_structured_data

        self.conversation.add_user_message(
            f"工具调用已达到上限（{max_rounds}轮），请基于以上已获取的所有信息，"
            f"综合总结回答用户的问题。如果没有获取到有效信息，请直接说明。"
        )

        AgentMessageLogger.log(
            self._agent_id, "system",
            f"工具调用达到上限，发起强制总结调用（无工具）",
            token_phase="force_summary",
        )

        summary_response = self.llm.generate_response(
            "",
            self.conversation.get_history(),
            None,
        )

        if summary_response is not None and "content" in summary_response:
            response_text = summary_response.get("content", "")
            if isinstance(response_text, dict):
                response_text = response_text.get("content", "")
            usage = summary_response.get("usage") or {}
            _r_in = int(usage.get("input_tokens", 0))
            _r_out = int(usage.get("output_tokens", 0))
            _r_tot = int(usage.get("total_tokens", 0))
            cumulative_usage["input_tokens"] += _r_in
            cumulative_usage["output_tokens"] += _r_out
            cumulative_usage["total_tokens"] += _r_tot

            AgentMessageLogger.log(
                self._agent_id, "agent_response",
                f"{self._agent_name}强制总结回复（{len(response_text)} 字符）",
                response_full=response_text,
                usage=str(cumulative_usage),
            )

            self.conversation.add_assistant_message(response_text)

            if return_with_agent_id:
                return response_text, cumulative_usage, self._agent_id
            return response_text, cumulative_usage

        fallback = "已完成多轮工具调用，但未得到最终文本回复。请换一种方式重新提问。"
        self.conversation.add_assistant_message(fallback)

        if return_with_agent_id:
            return fallback, cumulative_usage, self._agent_id
        return fallback, cumulative_usage

    # -------------------------------------------------------------------------
    # Pipeline 模式：固定顺序全量查询
    # -------------------------------------------------------------------------

    def _get_pipeline_tool_order(self) -> list[str]:
        """获取 pipeline 模式的工具执行顺序

        返回固定的工具调用顺序：知识图谱 → 向量库 → 规则库 → 案例库

        Returns:
            list[str]: 工具名称列表
        """
        # 根据工具类型映射到工具名称
        # 知识图谱工具 (kg)
        kg_tools = []
        vector_tools = []
        rules_tools = []
        cases_tools = []

        for tool in self._tools_list:
            try:
                tool_name = tool.get("function", {}).get("name", "")
                tool_type = tool.get("metadata", {}).get("type", "")
                if tool_type == "kg":
                    kg_tools.append(tool_name)
                elif tool_type == "vector":
                    vector_tools.append(tool_name)
                elif tool_type == "rules":
                    rules_tools.append(tool_name)
                elif tool_type == "cases":
                    cases_tools.append(tool_name)
            except Exception:
                continue

        # 固定顺序：知识图谱 → 向量库 → 规则库 → 案例库
        return kg_tools + vector_tools + rules_tools + cases_tools

    def _run_pipeline_query(
        self,
        user_input: str,
        context_prefix: str = "",
        pipeline_config: dict = None,
    ) -> tuple[str, dict[str, Any], Any]:
        """执行 pipeline 模式：固定顺序全量查询后 LLM 汇总

        执行顺序：知识图谱 → 向量库 → 规则库 → 案例库 → LLM汇总

        与 auto 模式的区别：
        - auto 模式：LLM 自主决策调用哪些工具、调用几次
        - pipeline 模式：按固定顺序执行所有工具，确保信息完整不遗漏

        Args:
            user_input: 用户输入文本
            context_prefix: 上下文前缀
            pipeline_config: 各工具的查询配置（可选）
                - kg_query: 知识图谱查询
                - vector_query: 向量库查询
                - rules_query: 规则库查询
                - cases_query: 案例库查询
                如未提供，则使用 user_input 的前 200 字符作为查询

        Returns:
            tuple: (response_text, usage_info, structured_data)
        """
        import json
        import uuid

        actual_input = self._build_user_input(user_input, context_prefix)
        self.conversation.add_user_message(actual_input)

        AgentMessageLogger.log(
            self._agent_id, "system",
            f"进入 Pipeline 模式，按固定顺序执行全量查询"
        )

        cumulative_usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        # 获取固定的工具执行顺序
        tool_order = self._get_pipeline_tool_order()

        # 收集所有检索结果
        all_results = {}
        tool_call_id = None

        for tool_name in tool_order:
            try:
                # 构建工具参数
                tool_args = self._build_pipeline_tool_args(tool_name, user_input, all_results, pipeline_config)
                tool_args_json = json.dumps(tool_args, ensure_ascii=False)

                # 生成唯一的 tool_call_id
                tool_call_id = str(uuid.uuid4())

                # 先添加 assistant 的 tool_call 请求消息（模拟 function calling 格式）
                self.conversation.add_tool_call_message([{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_args_json,
                    },
                }])

                AgentMessageLogger.log(
                    self._agent_id, "tool_call",
                    f"[Pipeline] 调用工具: {tool_name}",
                    tool_name=tool_name,
                    tool_arguments=tool_args_json,
                )

                # 执行工具
                structured_data, tool_result = self._registry.execute(
                    tool_name,
                    tool_args_json,
                    self
                )

                # 消费工具返回的图片快照
                pipeline_images = consume_pending_images()

                AgentMessageLogger.log(
                    self._agent_id, "tool_result",
                    f"[Pipeline] 工具 {tool_name} 执行完成",
                    tool_name=tool_name,
                    tool_result=str(tool_result)[:500],
                    images=pipeline_images,
                )

                # 添加 tool 执行结果消息到对话历史
                self.conversation.add_tool_result(
                    tool_call_id=tool_call_id,
                    content=str(tool_result),
                    structured_data=structured_data,
                )

                # 保存结果
                all_results[tool_name] = {
                    "structured_data": structured_data,
                    "tool_result": tool_result,
                }

            except Exception as e:
                AgentMessageLogger.log(
                    self._agent_id, "system",
                    f"[Pipeline] 工具 {tool_name} 执行失败: {e}"
                )
                # 添加失败的 tool_call 和 tool 消息，保持对话历史完整性
                if tool_call_id is None:
                    tool_call_id = str(uuid.uuid4())
                self.conversation.add_tool_call_message([{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args if 'tool_args' in dir() else {"query": user_input}, ensure_ascii=False),
                    },
                }])
                self.conversation.add_tool_result(
                    tool_call_id=tool_call_id,
                    content=f"[执行失败] {e}",
                    structured_data=None,
                )
                all_results[tool_name] = {
                    "structured_data": None,
                    "tool_result": f"[执行失败] {e}",
                }

        # 所有工具执行完成，对话历史中已包含完整的 tool_call 和 tool 消息
        # 现在直接调用 LLM，让其基于完整的工具结果进行汇总
        AgentMessageLogger.log(
            self._agent_id, "system",
            f"[Pipeline] 所有工具执行完成（共 {len(all_results)} 个），开始 LLM 汇总"
        )

        # 获取完整的对话历史（包含 user → tool_calls → tool results）
        history = self.conversation.get_history()

        # ★ 追加一条 user 消息作为汇总触发指令
        #   LLM 对话序列中最后一条是 tool_result，需要一条 user 指令告诉它输出最终答案。
        #   summary_instruction 必须由调用方通过 pipeline_config 传入（业务层负责），
        #   基础设施层不提供任何兜底，避免硬编码业务逻辑。
        summary_trigger = (pipeline_config or {}).get("summary_instruction", "")
        history = history + [{"role": "user", "content": summary_trigger}]

        # ★ 调用 LLM 进行汇总（不传 tools，让 LLM 直接基于已有对话历史回答）
        response = self.llm.generate_response("", history, None)

        if response is None:
            fallback = "Pipeline 模式 LLM 汇总失败"
            self.conversation.add_assistant_message(fallback)
            return fallback, cumulative_usage, None

        usage = response.get("usage") or {}
        cumulative_usage["input_tokens"] += int(usage.get("input_tokens", 0))
        cumulative_usage["output_tokens"] += int(usage.get("output_tokens", 0))
        cumulative_usage["total_tokens"] += int(usage.get("total_tokens", 0))

        response_text = response.get("content", "")
        if isinstance(response_text, dict):
            response_text = response_text.get("content", "")

        self.conversation.add_assistant_message(response_text)

        # 提取最后一个 tool 消息中的 structured_data 作为返回值
        last_structured_data = None
        last_tool_id = None
        for msg in reversed(history):
            if msg.get("role") == "tool":
                last_tool_id = msg.get("tool_call_id")
                break
        if last_tool_id:
            last_structured_data = self.conversation.get_structured_data(last_tool_id)

        AgentMessageLogger.log(
            self._agent_id, "agent_response",
            f"[Pipeline] {self._agent_name}汇总回复（{len(response_text)} 字符）",
            response_full=response_text,
            usage=str(cumulative_usage),
        )

        return response_text, cumulative_usage, last_structured_data

    def _build_pipeline_tool_args(
        self,
        tool_name: str,
        user_input: str,
        previous_results: dict,
        pipeline_config: dict = None,
    ) -> dict:
        """构建 pipeline 模式下的工具调用参数

        如果提供了 pipeline_config，则直接使用配置中的查询内容；
        否则使用 user_input 的前 200 字符作为默认查询。

        对于向量库查询，会动态追加知识图谱查询结果，丰富检索上下文。

        Args:
            tool_name: 工具名称
            user_input: 用户原始输入
            previous_results: 之前步骤的结果 {tool_name: {"structured_data": ..., "tool_result": ...}}
            pipeline_config: 各工具的查询配置（可选）

        Returns:
            dict: 工具调用参数 {"query": "查询内容"}
        """
        query = ""
        tool_name_lower = tool_name.lower()
        is_vector_tool = "knowledge" in tool_name_lower or "vector" in tool_name_lower

        if pipeline_config:
            # 根据工具类型从配置中取对应查询
            if "knowledge_graph" in tool_name_lower or "_kg_" in tool_name_lower:
                query = pipeline_config.get("kg_query", "")
            elif is_vector_tool:
                query = pipeline_config.get("vector_query", "")
                # 动态追加知识图谱查询结果
                kg_content = self._extract_kg_results_for_vector(previous_results)
                if kg_content:
                    query = f"{query}\n\n【知识图谱查询结果】\n{kg_content}"
            elif "rules" in tool_name_lower:
                query = pipeline_config.get("rules_query", "")
            elif "cases" in tool_name_lower:
                query = pipeline_config.get("cases_query", "")

        # 兜底：如果配置中没有，则使用 user_input 前 200 字符
        if not query:
            query = user_input[:200]

        return {"query": query}

    @staticmethod
    def _extract_kg_results_for_vector(previous_results: dict, max_length: int = 1000) -> str:
        """从之前的工具结果中提取知识图谱查询结果

        用于在向量库查询时追加 KG 结果，丰富检索上下文。

        Args:
            previous_results: 之前步骤的结果字典
            max_length: 最大提取长度

        Returns:
            str: 格式化的知识图谱结果文本
        """
        kg_parts = []

        for tool_name, result in previous_results.items():
            tool_name_lower = tool_name.lower()
            if "knowledge_graph" in tool_name_lower or "_kg_" in tool_name_lower or "kg" in tool_name_lower:
                tool_result = result.get("tool_result", "")
                if tool_result and isinstance(tool_result, str):
                    # 截取 KG 结果中最相关的部分
                    content = tool_result.strip()
                    if len(content) > max_length:
                        content = content[:max_length] + "..."
                    kg_parts.append(content)

        if not kg_parts:
            return ""

        # 合并所有 KG 工具的结果
        combined = "\n".join(kg_parts)
        if len(combined) > max_length * 2:
            combined = combined[:max_length * 2] + "\n... (KG结果已截断)"

        return combined

    # -------------------------------------------------------------------------
    # 主接口：send_message（子类可覆写以添加专属逻辑）
    # -------------------------------------------------------------------------

    def send_message(
        self,
        user_input: str,
        context_prefix: str = "",
        callback=None,
        set_memory_db_fn=None,
        query_mode: str = "auto",
        pipeline_config: dict = None,
    ) -> tuple[str, dict[str, Any], Any]:
        """发送消息并获取 LLM 回复

        Args:
            user_input:      用户输入文本
            context_prefix:  上下文前缀
            callback:        流式回调函数
            set_memory_db_fn: memory_db 注入函数（计算分析型需要）
            query_mode:      查询模式
                            - "auto": 自动模式（默认），LLM 决策工具调用
                            - "pipeline": Pipeline 模式，固定顺序全量查询
            pipeline_config: Pipeline 模式下各工具的查询配置（可选）
                            - kg_query: 知识图谱查询
                            - vector_query: 向量库查询
                            - rules_query: 规则库查询
                            - cases_query: 案例库查询

        Returns:
            tuple: (response_text, usage_info, structured_data)
        """
        # 如果配置了每次调用前清空历史，则在此处执行
        if self.CLEAR_HISTORY_ON_CALL:
            self.clear_history()

        if self.is_processing:
            return "正在处理上一个请求，请等待...", {}, None

        try:
            self.is_processing = True

            self._ensure_memory_db(set_memory_db_fn)

            # 根据 query_mode 选择执行模式
            if query_mode == "pipeline":
                AgentMessageLogger.log(
                    self._agent_id, "system",
                    f"使用 Pipeline 模式执行查询"
                )
                result = self._run_pipeline_query(
                    user_input=user_input,
                    context_prefix=context_prefix,
                    pipeline_config=pipeline_config,
                )
            else:
                # 默认 auto 模式：使用 function calling 循环
                result = self._run_tool_calling_loop(
                    user_input=user_input,
                    context_prefix=context_prefix,
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
