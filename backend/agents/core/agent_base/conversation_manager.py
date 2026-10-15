# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : conversation_manager.py
# @Desc    : 统一的对话上下文管理模块
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
统一的对话上下文管理模块

此模块提供 ConversationManager 类，用于集中管理各 Agent 内部的对话历史。

原来三个 Agent（main_agent / vts_ssts_agent / economy_analyse_agent）各自
拥有一份几乎相同的上下文管理代码（~30-35 行/文件），包括：
  - self.conversation_history 列表
  - _trim_conversation_history() 裁剪方法
  - _estimate_tokens() token 估算
  - clear_history() 清空历史

重构后，所有 Agent 共享本模块中的 ConversationManager 类，具体参数
（max_messages / max_tokens）从各自的 YAML 配置文件读取。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class ConversationManager:
    """统一的对话上下文管理器

    职责:
      1. 维护消息列表（user / assistant / tool）
      2. 每次新增消息后自动裁剪历史（按条数 + 按 token 数）
      3. 提供统一的 add / get / clear 接口

    典型用法:
        conv = ConversationManager(max_messages=20, max_tokens=150000)
        conv.add_user_message("分析一下经济性计算结果")
        conv.add_tool_call_message([{...}])          # LLM 请求调用工具
        conv.add_tool_result("tool_id_123", "...结果...")
        conv.add_assistant_message("根据分析...")
        history = conv.get_history()                # 传给 LLM
        conv.clear_history()                         # 清空
    """

    def __init__(self, max_messages: int = 20, max_tokens: int = 150000,
                 summary_config: Optional[Dict[str, Any]] = None):
        """初始化对话上下文管理器

        Args:
            max_messages:   最多保留的消息条数（超过则丢弃最旧的）
            max_tokens:     最多保留的 token 数（超过则从最旧开始成对移除）
            summary_config: 可选，此 Agent 专属的摘要器配置，用于在裁剪对话时
                            差异化控制摘要长度（来自 YAML 的 summary_config 节）
        """
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.summary_config: Optional[Dict[str, Any]] = summary_config
        self.history: List[Dict[str, Any]] = []
        self._summary: str = ""
        self._tool_structured_data: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 消息添加接口
    # ------------------------------------------------------------------

    def add_user_message(self, content: str) -> None:
        """添加一条用户消息"""
        self.history.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: str) -> None:
        """添加一条普通助手回复（非 tool_call）"""
        self.history.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_call_message(self, tool_calls: List[Dict[str, Any]]) -> None:
        """添加一条 assistant 的 tool_call 请求消息

        典型消息格式（与 dashscope/OpenAI 兼容）:
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "...",
                        "type": "function",
                        "function": {"name": "...", "arguments": "{...}"}
                    }
                ]
            }
        """
        self.history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })
        self._trim()

    def add_tool_result(self, tool_call_id: str, content: str, structured_data=None) -> None:
        """添加一条 tool 执行结果消息

        典型消息格式（仅包含 LLM 协议所需字段）:
            {
                "role": "tool",
                "content": "...工具返回的文本或字符串...",
                "tool_call_id": "...",
            }

        structured_data 作为独立元数据，按 tool_call_id 关联存储，不进入 LLM 上下文。
        """
        msg = {
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
        }
        if structured_data:
            self._tool_structured_data[tool_call_id] = structured_data
        self.history.append(msg)
        self._trim()

    # ------------------------------------------------------------------
    # 状态查询接口
    # ------------------------------------------------------------------

    def get_history(self) -> List[Dict[str, Any]]:
        """获取完整历史列表（直接传给 LLM 的 generate_response）

        如果存在长期记忆摘要，会作为第一条 system 消息插入历史头部。
        返回的消息仅包含 LLM 协议所需字段，不含 structured_data。
        """
        if self._summary:
            return [{"role": "system", "content": f"[之前对话的长期记忆]\n{self._summary}"}] + self.history
        return self.history

    def get_structured_data(self, tool_call_id: str) -> Any:
        """根据 tool_call_id 查询对应的结构化数据（供前端 UI 渲染）"""
        return self._tool_structured_data.get(tool_call_id)

    def __len__(self) -> int:
        """返回当前消息条数"""
        return len(self.history)

    def is_empty(self) -> bool:
        """是否为空"""
        return len(self.history) == 0

    # ------------------------------------------------------------------
    # 历史管理
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """清空所有对话历史（同时清空长期记忆摘要和结构化数据）"""
        self.history = []
        self._summary = ""
        self._tool_structured_data = {}

    # ------------------------------------------------------------------
    # 内部工具：裁剪 + token 估算
    # ------------------------------------------------------------------

    def _trim(self) -> None:
        """按条数和 token 数裁剪历史

        策略:
          1. 如果条数超过 max_messages，保留最新的 max_messages 条，
             被裁剪的旧消息通过 LLM 摘要压缩为长期记忆
          2. 如果 token 超过 max_tokens，从最旧开始成对移除（user+assistant），
             被移除的消息同样通过 LLM 摘要压缩
        """
        # Step 1：条数限制
        if len(self.history) > self.max_messages:
            removed = self.history[:len(self.history) - self.max_messages]
            self._update_summary(removed)
            self.history = self.history[-self.max_messages:]
            self._cleanup_structured_data(removed)

        # Step 2：token 限制（从最旧开始成对移除，避免破坏工具调用上下文）
        current_tokens = self._estimate_tokens(self.history)
        removed_for_tokens = []
        while current_tokens > self.max_tokens and len(self.history) > 2:
            removed_for_tokens.extend(self.history[:2])
            self.history = self.history[2:]
            current_tokens = self._estimate_tokens(self.history)
        if removed_for_tokens:
            self._update_summary(removed_for_tokens)
            self._cleanup_structured_data(removed_for_tokens)

    def _cleanup_structured_data(self, removed_messages: List[Dict[str, Any]]) -> None:
        """清理被裁剪消息对应的 structured_data 条目"""
        for msg in removed_messages:
            if msg.get("role") == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                if tool_call_id and tool_call_id in self._tool_structured_data:
                    del self._tool_structured_data[tool_call_id]

    def _update_summary(self, removed_messages: List[Dict[str, Any]]) -> None:
        """将被裁剪的消息压缩为摘要，更新长期记忆

        如果已有摘要，将旧摘要与新裁剪消息合并后重新摘要，
        确保摘要只保留一条，不会无限增长。

        使用此 Agent 专属的 summary_config 来差异化控制摘要长度，
        未配置时降级使用摘要器的默认配置。
        """
        if not removed_messages:
            return

        try:
            from snail_avatar.backend.agents.core.tools.LLM_tools import get_summarizer

            summarizer = get_summarizer()

            # 如果已有摘要，将旧摘要作为上下文一起重新摘要
            if self._summary:
                summary_msg = {"role": "system", "content": f"[之前的摘要] {self._summary}"}
                all_to_summarize = [summary_msg] + removed_messages
            else:
                all_to_summarize = removed_messages

            # 传入此 Agent 专属的 summary_config（可能为 None，此时使用默认配置）
            self._summary = summarizer.summarize(
                all_to_summarize,
                summary_config=self.summary_config,
            )
        except Exception:
            # LLM 摘要失败时，用规则截断保留关键信息
            try:
                from snail_avatar.backend.agents.core.tools.LLM_tools import get_summarizer
                summarizer = get_summarizer()
                new_rule_summary = summarizer.rule_summary(
                    removed_messages,
                    summary_config=self.summary_config,
                )
                if self._summary:
                    self._summary = f"{self._summary}\n{new_rule_summary}"
                else:
                    self._summary = new_rule_summary
                # 限制摘要长度，避免降级时无限增长
                if len(self._summary) > 1000:
                    self._summary = self._summary[-1000:]
            except Exception:
                pass

    @staticmethod
    def _estimate_tokens(messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的 token 数

        算法（中文场景的粗粒度估算）:
          - 英文/数字字符：4 个字符 ≈ 1 token
          - 中文字符：2 个字符 ≈ 1 token
          - tool_calls 字段：JSON 序列化后的长度 // 4

        这是一个估算值，不追求精确，主要用于保护上下文不爆。
        """
        total = 0
        for msg in messages:
            # content 字段（可能为 None，例如纯 tool_call 的 assistant 消息）
            content = msg.get("content", "")
            if content:
                if isinstance(content, dict):
                    content = content.get("content", "")
                if content:
                    english_chars = sum(1 for c in content if ord(c) < 128)
                    chinese_chars = len(content) - english_chars
                    total += english_chars // 4 + chinese_chars // 2

            # tool_calls 字段（多条 tool_call 消息的主要内容）
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                try:
                    total += len(json.dumps(tool_calls, ensure_ascii=False)) // 4
                except Exception:
                    total += 200  # 兜底估算
        return total

    # ------------------------------------------------------------------
    # 便捷方法：从 YAML 配置 dict 创建实例
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ConversationManager":
        """从 YAML 配置创建实例（conversation_config + summary_config）

        Args:
            config: 完整的 Agent 配置 dict（通常是 _load_config() 的结果）

        YAML 配置示例:
            conversation_config:
              max_messages: 20
              max_tokens: 150000
            summary_config:
              summary_length_hint: "300字"
              llm_config:
                max_new_tokens: 800
              rule_summary_config:
                user_truncate: 120
                assistant_truncate: 180

        如果没有配置，则使用类内默认值。
        """
        conv_cfg = config.get("conversation_config", {})
        summary_cfg = config.get("summary_config")
        return cls(
            max_messages=conv_cfg.get("max_messages", 20),
            max_tokens=conv_cfg.get("max_tokens", 150000),
            summary_config=summary_cfg,
        )
