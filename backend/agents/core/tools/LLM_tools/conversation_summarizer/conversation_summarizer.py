# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : conversation_summarizer.py
# @Desc    : 对话摘要器 - 使用轻量 LLM 将对话历史压缩为语义摘要
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
对话摘要器 - 使用 qwen3.5-flash 轻量模型将对话历史压缩为语义摘要

重构后（与 deploy.py 保持单一职责一致，支持按 Agent 差异化配置）:
  - API Key 获取：由 APIKeyProvider 负责
  - 环境检查/模型加载：由 LLMEnvironment 负责
  - LLM 调用：由 LLMDeploy 负责，按 agent_id 独立缓存实例
  - 配置优先级：调用方传入的 summary_config > agent YAML > summarizer.yaml 默认 > Python 代码兜底

两个使用场景:
  场景 A（路由传递）: 主 Agent 切换到子 Agent 时，将旧对话摘要 + 最近对话原文
                      拼接为上下文前缀，让子 Agent 理解"之前聊了什么"
  场景 B（上下文裁剪）: ConversationManager._trim() 裁剪旧消息前，先将其压缩
                       为摘要作为"长期记忆"保留，避免关键信息被暴力丢弃

使用方式:
    from snail_avatar.backend.agents.core.tools.LLM_tools import get_summarizer

    summarizer = get_summarizer()

    # 最简调用：使用 summarizer.yaml 中的默认配置
    summary_text = summarizer.summarize(messages)

    # 按 Agent 差异化：传入 agent 的 summary_config 和 agent_id
    # （agent.summary_config 来自 agent 自身 YAML 中 summary_config 节）
    summary_text = summarizer.summarize(
        messages,
        summary_config=agent_config.get("summary_config", {}),
        agent_id=agent.agent_id,
    )

    # 场景 A：摘要旧消息 + 完整保留最近 N 条
    summary_text, recent_messages = summarizer.summarize_with_recent(
        messages, keep_recent=6, summary_config=summary_config, agent_id=agent_id
    )

    # 纯规则摘要（降级时使用）
    summary_text = summarizer.rule_summary(messages, summary_config)
"""

import os
import threading
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# 模块级 LLMDeploy 实例池：按 agent_id 独立缓存，避免不同 Agent 混用同一个实例
# =============================================================================

_llm_pool: Dict[str, Any] = {}
_llm_pool_lock = threading.Lock()


class ConversationSummarizer:
    """对话摘要器 - 使用轻量 LLM 将对话历史压缩为语义摘要

    设计约束:
    - 使用 qwen3.5-flash 轻量模型（在 summarizer.yaml 中可修改，可被 agent 的
      summary_config 覆盖）
    - LLM 调用失败时自动降级为规则截断摘要
    - 通过 LLMDeploy / LLMEnvironment / APIKeyProvider 统一完成环境准备和 API 调用
    - 线程安全（通过 threading.Lock）
    - 支持按 Agent 差异化：调用方传入 summary_config dict 即可覆盖默认参数
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 懒加载：summarizer.yaml 默认配置在首次调用时加载一次
        self._default_config: Optional[Dict[str, Any]] = None
        self._init_default_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def summarize(self,
                  messages: List[Dict[str, Any]],
                  summary_config: Optional[Dict[str, Any]] = None,
                  agent_id: Optional[str] = None,
                  max_output_tokens: Optional[int] = None) -> str:
        """将一组对话消息压缩为摘要文本

        配置优先级（从高到低）:
          1. 本方法的 max_output_tokens 参数（为了兼容老调用而保留，仅覆盖 LLM 输出 token 数）
          2. 传入的 summary_config dict（通常来自调用方 agent 的 YAML summary_config 节）
          3. summarizer.yaml 默认配置
          4. Python 代码兜底常量

        Args:
            messages: 对话消息列表（格式同 ConversationManager.history）
            summary_config: 可选，调用方 agent 的摘要覆盖配置，如:
                {
                    "max_new_tokens": 800,
                    "summary_length_hint": "300字",
                    "user_truncate": 120,
                    "assistant_truncate": 180,
                    "model_name": "qwen3.5-flash",
                    "temperature": 0.3,
                }
            agent_id: 可选，用于标识此摘要属于哪个 agent，LLMDeploy 实例按此 key 缓存
            max_output_tokens: 可选，兼容旧调用方式的快捷参数，等效于 summary_config
                中的 max_new_tokens

        Returns:
            str: 摘要文本（LLM 失败时降级为规则截断摘要）
        """
        if not messages:
            return ""

        # 合并默认配置与调用方覆盖配置
        effective_config = self._merge_config(summary_config)

        # max_output_tokens 参数优先级最高（兼容旧调用）
        if max_output_tokens is not None:
            effective_config["llm_config"]["max_new_tokens"] = max_output_tokens

        try:
            return self._llm_summarize(messages, effective_config, agent_id)
        except Exception as e:
            # LLM 摘要调用抛异常（网络超时、API 错误、配置缺失等）
            # 降级为纯规则摘要，并在流式工作信息窗口中记录警告
            try:
                from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger
                _agent_id = agent_id if agent_id else "conversation_summarizer"
                AgentMessageLogger.log(
                    _agent_id,
                    "summary_fallback",
                    f"LLM 摘要调用失败，已降级为纯规则摘要（{len(messages)} 条消息）。"
                    f" 异常类型: {type(e).__name__}",
                    error=str(e)
                )
            except Exception:
                pass  # 日志系统异常不影响主流程
            # 规则摘要也要使用合并后的截断长度
            return self.rule_summary(messages, summary_config)

    def summarize_with_recent(self,
                              messages: List[Dict[str, Any]],
                              keep_recent: int = 6,
                              summary_config: Optional[Dict[str, Any]] = None,
                              agent_id: Optional[str] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """摘要旧消息 + 完整保留最近 N 条（场景 A：路由传递）

        将消息分为两部分:
          - 旧消息（前 len - keep_recent 条）→ LLM 摘要
          - 最近消息（后 keep_recent 条）→ 完整保留原文

        Args:
            messages: 完整对话消息列表
            keep_recent: 完整保留的最近消息条数
            summary_config: 可选，调用方 agent 的摘要覆盖配置（同 summarize）
            agent_id: 可选，用于标识此摘要属于哪个 agent

        Returns:
            tuple: (旧消息摘要文本, 最近消息列表)
        """
        if not messages:
            return "", []

        if len(messages) <= keep_recent:
            return "", list(messages)

        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        summary_text = self.summarize(
            old_messages,
            summary_config=summary_config,
            agent_id=agent_id,
        )
        return summary_text, recent_messages

    def rule_summary(self,
                     messages: List[Dict[str, Any]],
                     summary_config: Optional[Dict[str, Any]] = None) -> str:
        """纯规则摘要（降级方案，与原 _extract_recent_summary 逻辑一致）

        按 agent 差异化的 user_truncate / assistant_truncate 进行截断。

        Args:
            messages: 对话消息列表
            summary_config: 可选，调用方 agent 的摘要覆盖配置

        Returns:
            str: 规则截断后的摘要文本
        """
        if not messages:
            return ""

        # 合并默认配置与调用方覆盖配置
        effective_config = self._merge_config(summary_config)
        rule_cfg = effective_config["rule_summary_config"]

        user_truncate = rule_cfg.get("user_truncate", 2000)
        assistant_truncate = rule_cfg.get("assistant_truncate", 2000)

        summary_parts = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content")
            if content is None:
                content = ""
            if role == "user":
                summary_parts.append(f"用户: {content[:user_truncate]}")
            elif role == "assistant":
                summary_parts.append(f"助手: {content[:assistant_truncate]}")
            elif role == "tool":
                tool_content = content[:assistant_truncate] if content else ""
                if tool_content:
                    summary_parts.append(f"工具结果: {tool_content}")

        return "\n".join(summary_parts)

    # ------------------------------------------------------------------
    # 内部方法：初始化 / LLM 摘要 / 配置加载 / 实例缓存
    # ------------------------------------------------------------------

    def _ensure_default_config_loaded(self) -> None:
        """懒加载 summarizer.yaml 默认配置（仅首次调用时执行一次）"""
        if self._default_config is not None:
            return

        with self._init_default_lock:
            if self._default_config is not None:
                return
            self._default_config = self._load_config_from_yaml()

    def _load_config_from_yaml(self) -> Dict[str, Any]:
        """从 config/summarizer.yaml 加载默认配置

        Returns:
            dict: 解析后的配置字典；读取失败时返回 _default_config_fallback()
        """
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config",
            "summarizer.yaml",
        )

        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if isinstance(config, dict):
                return config
            # YAML 解析结果非 dict（例如文件为空），返回兜底配置
            return self._default_config_fallback()
        except FileNotFoundError:
            return self._default_config_fallback()
        except Exception:
            return self._default_config_fallback()

    def _merge_config(self, summary_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """将调用方传入的 summary_config 与 summarizer.yaml 默认配置合并

        summary_config 中的键覆盖默认配置中的同名键；不存在的键保留默认值。

        合并后的结构:
        {
            "system_prompt": "...{summary_length_hint}...",  # 含模板，未替换
            "summary_length_hint": "200字",
            "llm_config": {"model_name":..., "max_new_tokens":..., ...},
            "rule_summary_config": {"user_truncate": 100, "assistant_truncate": 150},
        }
        """
        self._ensure_default_config_loaded()

        # 复制默认配置，避免污染原对象
        default = dict(self._default_config or {})

        if not summary_config or not isinstance(summary_config, dict):
            return default

        # 顶层字段 summary_length_hint
        if "summary_length_hint" in summary_config:
            default["summary_length_hint"] = summary_config["summary_length_hint"]

        # llm_config 节：合并覆盖
        default_llm = dict(default.get("llm_config", {}))
        override_llm = summary_config.get("llm_config")
        if isinstance(override_llm, dict):
            default_llm.update(override_llm)
        default["llm_config"] = default_llm

        # rule_summary_config 节：合并覆盖
        default_rule = dict(default.get("rule_summary_config", {}))
        override_rule = summary_config.get("rule_summary_config")
        if isinstance(override_rule, dict):
            default_rule.update(override_rule)
        default["rule_summary_config"] = default_rule

        return default

    def _get_or_create_llm(self,
                           agent_id: str,
                           llm_config: Dict[str, Any],
                           system_prompt: str) -> Any:
        """从模块级 llm_pool 获取或创建 LLMDeploy 实例

        按 (agent_id, frozenset(llm_config key items)) 作为缓存 key，
        确保不同 agent / 不同模型配置得到不同的 LLMDeploy 实例。
        """
        # 生成稳定的 cache key
        llm_items = tuple(sorted(llm_config.items(), key=lambda x: x[0]))
        cache_key = f"{agent_id}||{llm_items}"

        # 先快速判断是否已有
        if cache_key in _llm_pool:
            return _llm_pool[cache_key]

        with _llm_pool_lock:
            # 二次判断，防止并发创建
            if cache_key in _llm_pool:
                return _llm_pool[cache_key]

            from snail_avatar.backend.llm.deploy import LLMDeploy
            llm = LLMDeploy(agent_id, system_prompt, llm_config)
            _llm_pool[cache_key] = llm
            return llm

    def _llm_summarize(self,
                       messages: List[Dict[str, Any]],
                       effective_config: Dict[str, Any],
                       agent_id: Optional[str]) -> str:
        """调用 LLM 生成摘要

        Args:
            messages: 待摘要的消息列表
            effective_config: 合并后的有效配置（含 system_prompt 模板、
                llm_config、rule_summary_config、summary_length_hint）
            agent_id: 可选，用于 LLMDeploy 实例缓存 key

        Returns:
            str: 摘要文本；LLM 调用失败/返回错误时，返回 None 让调用方降级
        """
        # 1. 把 system_prompt 模板中的 {summary_length_hint} 替换为实际值
        system_prompt_template = effective_config.get("system_prompt", "")
        summary_length_hint = effective_config.get("summary_length_hint", "200字")
        # 使用 str.replace 而不是 str.format，避免 prompt 中出现其他 {} 导致 KeyError
        system_prompt = system_prompt_template.replace(
            "{summary_length_hint}", summary_length_hint
        )

        # 2. 获取或创建 LLMDeploy 实例（按 agent_id 独立缓存）
        llm_config = effective_config.get("llm_config", {})
        effective_agent_id = agent_id or "default_summarizer"
        llm = self._get_or_create_llm(effective_agent_id, llm_config, system_prompt)

        # 3. 先调用 rule_summary 生成一个紧凑的输入文本
        #    （避免把超长原始对话直接丢给 LLM，降低 token 消耗）
        user_content = self.rule_summary(messages, effective_config.get("rule_summary_config", {}))
        if not user_content.strip():
            return ""

        # 4. 构造摘要任务的对话历史：单条 user 消息，告知 LLM 需要摘要的内容
        #    system_prompt 由 LLMDeploy 在 init 时注入，此处仅传入 user 消息
        conversation_history = [
            {"role": "user", "content": f"请摘要以下对话：\n\n{user_content}"},
        ]

        # 5. 通过 LLMDeploy 统一调用 LLM
        result = llm.generate_response("", conversation_history, tools=None)

        # 6. LLMDeploy 返回 dict 格式：{"content": str, "usage": dict} 或出错信息
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            # 如果 LLM 返回了有效摘要内容，直接返回；否则降级为规则摘要
            if content and not content.startswith("错误"):
                return content

        # LLM 调用未抛异常但返回内容无效（空字符串或以"错误"开头）
        # 降级为纯规则摘要，并在流式工作信息窗口中记录警告
        try:
            from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger
            _agent_id = agent_id if agent_id else "conversation_summarizer"
            AgentMessageLogger.log(
                _agent_id,
                "summary_fallback",
                f"LLM 摘要返回内容无效，已降级为纯规则摘要（{len(messages)} 条消息）。"
                f" 提示：检查 summarizer.yaml 的 system_prompt / summary_length_hint 是否合理。"
            )
        except Exception:
            pass  # 日志系统异常不影响主流程
        return self.rule_summary(messages, effective_config.get("rule_summary_config", {}))

    @staticmethod
    def _default_config_fallback() -> Dict[str, Any]:
        """返回一套合理的兜底配置（summarizer.yaml 读取失败时使用）

        结构与 summarizer.yaml 保持一致，确保后续合并逻辑无需特殊处理。
        """
        return {
            "agent_id": "conversation_summarizer",
            "agent_name": "对话摘要器",
            "agent_description": "默认配置（YAML 读取失败）",
            # system_prompt 模板：{summary_length_hint} 会在运行时替换
            "system_prompt": (
                "你是一个对话摘要助手。你的任务是将对话历史压缩为简洁的摘要。\n"
                "\n"
                "要求：\n"
                "1. 保留用户的核心意图和关键信息（如车型、参数名、具体数值）\n"
                "2. 保留助手的关键结论和操作（如调用了什么工具、计算了什么结果）\n"
                "3. 忽略寒暄、重复和无关细节\n"
                "4. 用第三人称客观描述，不要添加主观判断\n"
                "5. 摘要长度控制在{summary_length_hint}以内"
            ),
            # 模板变量的默认值
            "summary_length_hint": "200字",
            # LLM 参数
            "llm_config": {
                "model_name": "qwen3.5-flash",  # 【重要】必须是阿里云百炼 API 支持的真实模型名
                "max_new_tokens": 500,
                "temperature": 0.3,
                "top_p": 0.8,
                "presence_penalty": 1.0,
                "context_window": 64000,
            },
            # 规则摘要参数
            "rule_summary_config": {
                "user_truncate": 100,
                "assistant_truncate": 150,
            },
        }


# ----------------------------------------------------------------------
# 模块级工厂函数：对外保持不变（调用方无需修改 import）
# ----------------------------------------------------------------------

_summarizer_instance = None


def get_summarizer() -> ConversationSummarizer:
    """获取摘要器单例

    对外 API 保持不变：调用方（agent_router.py、conversation_manager.py）
    仍可以用 `from snail_avatar.backend.agents.core.tools.LLM_tools import get_summarizer` 正常使用。
    """
    global _summarizer_instance
    if _summarizer_instance is None:
        _summarizer_instance = ConversationSummarizer()
    return _summarizer_instance
