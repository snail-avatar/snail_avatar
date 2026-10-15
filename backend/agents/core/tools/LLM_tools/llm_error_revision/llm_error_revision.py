# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : llm_error_revision.py
# @Desc    : LLM 错误修订工具 - 基于LLM的通用错误修订工具，通过Step A/Step B循环确保数据完整性
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
LLM 错误修订工具

通过 Step A（修订）和 Step B（验收）的循环机制，自动检测和修复数据错误。

核心设计：
  - 完全依赖 LLM 推理能力进行错误检测和修复
  - 双 Prompt 驱动：Step A 定义"待修订问题"，Step B 定义"达标标准"
  - 循环修订：最多迭代 max_retries 次，直到满足 Step B 要求
  - 输出约定：LLM 输出结构化 JSON，便于业务层处理
  - 业务解耦：修订结果由业务层的私有函数处理（如 db_key 匹配填充）

使用方式：
    from snail_avatar.backend.agents.core.tools.LLM_tools import get_llm_error_revision

    revision_tool = get_llm_error_revision()

    result = revision_tool.revise(
        data=initial_data,
        step_a_prompt="检查并修复SSTS参数遗漏问题",
        step_b_prompt="验收标准：所有VTS的SSTS_parameter列表不为空",
    )

    # result 结构:
    # {
    #     "status": "success" | "max_retries_reached" | "error",
    #     "revised_data": {...},           # 最终修订后的数据
    #     "is_valid": true/false,          # 是否通过验收
    #     "attempts": 2,                   # 迭代次数
    #     "remaining_issues": [...],       # 剩余未解决的问题
    #     "history": [...]                 # 历史迭代记录（调试用）
    # }
"""

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional


# =============================================================================
# 模块级 LLMDeploy 实例池：按 agent_id 独立缓存
# =============================================================================

_llm_pool: Dict[str, Any] = {}
_llm_pool_lock = threading.Lock()


class LLMErrorRevision:
    """LLM 错误修订工具

    设计约束：
    - 使用 qwen3.5-flash 轻量模型（在 llm_error_revision.yaml 中可修改）
    - 通过 Step A（修订）和 Step B（验收）的循环机制实现闭环修复
    - LLM 调用失败时自动降级，返回最后一次结果
    - 通过 LLMDeploy 统一完成环境准备和 API 调用
    - 线程安全（通过 threading.Lock）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._default_config: Optional[Dict[str, Any]] = None
        self._init_default_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def revise(self,
               data: Any,
               step_a_prompt: str,
               step_b_prompt: str,
               revision_config: Optional[Dict[str, Any]] = None,
               conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """执行 LLM 错误修订循环

        Args:
            data: 待修订的原始数据（任意可序列化类型）
            step_a_prompt: 步骤A - 待修订问题描述（告诉LLM要修复什么）
            step_b_prompt: 步骤B - 达标标准描述（告诉LLM如何判断合格）
            revision_config: 可选，覆盖默认配置的修订参数
                {
                    "max_retries": 3,
                    "llm_config": {"model_name": "qwen3.5-plus"},
                }
            conversation_history: 可选，历史对话记录

        Returns:
            dict: 修订结果，包含以下字段:
                - status: "success" | "max_retries_reached" | "error"
                - revised_data: 最终修订后的数据
                - is_valid: 是否通过最终验收
                - attempts: 实际迭代次数
                - remaining_issues: 最终验收发现的问题列表
                - history: 历史迭代记录（包含每次的修订和验收结果）
                - last_error: 最后一次错误信息（仅在 status="error" 时）
        """
        # 参数校验
        if not step_a_prompt or not isinstance(step_a_prompt, str):
            return self._error_result("step_a_prompt 不能为空")
        if not step_b_prompt or not isinstance(step_b_prompt, str):
            return self._error_result("step_b_prompt 不能为空")

        # 加载配置
        effective_config = self._merge_config(revision_config)
        max_retries = effective_config.get("revision_config", {}).get("max_retries", 3)

        # 初始化循环变量
        current_data = data
        history: List[Dict[str, Any]] = []
        remaining_issues: List[Dict[str, Any]] = []
        is_valid = False
        last_error = None

        import time as _time

        # 修订循环
        for attempt in range(max_retries):
            iteration_log: Dict[str, Any] = {
                "attempt": attempt + 1,
                "step_a_result": None,
                "step_b_result": None,
                "success": False,
            }

            try:
                # Step A: 修订数据
                _ta = _time.time()
                revised_data, step_a_log = self._step_a_revise(
                    current_data, step_a_prompt, remaining_issues, effective_config,
                    conversation_history
                )
                _ta_end = _time.time()
                iteration_log["step_a_result"] = step_a_log

                # 检查 Step A 是否成功
                if not step_a_log.get("success", False):
                    last_error = step_a_log.get("error", "Step A 执行失败")
                    history.append(iteration_log)
                    continue

                # 更新当前数据
                current_data = revised_data

                # Step B: 验收检查
                _tb = _time.time()
                validation_result, step_b_log = self._step_b_validate(
                    current_data, step_b_prompt, effective_config,
                    conversation_history
                )
                _tb_end = _time.time()
                iteration_log["step_b_result"] = step_b_log

                # 检查 Step B 是否成功
                if not step_b_log.get("success", False):
                    last_error = step_b_log.get("error", "Step B 执行失败")
                    history.append(iteration_log)
                    continue

                # 解析验收结果
                is_valid = validation_result.get("is_valid", False)
                remaining_issues = validation_result.get("remaining_issues", [])

                iteration_log["success"] = True
                iteration_log["is_valid"] = is_valid
                iteration_log["remaining_issues"] = remaining_issues

                # 验收通过，提前退出
                if is_valid:
                    history.append(iteration_log)
                    return {
                        "status": "success",
                        "revised_data": current_data,
                        "is_valid": True,
                        "attempts": attempt + 1,
                        "remaining_issues": [],
                        "history": history,
                    }

            except Exception as e:
                last_error = f"迭代 {attempt + 1} 异常: {type(e).__name__}: {str(e)[:200]}"
                iteration_log["error"] = last_error

            history.append(iteration_log)

        # 达到最大重试次数
        return {
            "status": "max_retries_reached",
            "revised_data": current_data,
            "is_valid": is_valid,
            "attempts": max_retries,
            "remaining_issues": remaining_issues,
            "history": history,
            "last_error": last_error,
        }

    # ------------------------------------------------------------------
    # Step A: 修订数据
    # ------------------------------------------------------------------

    def _step_a_revise(self,
                       current_data: Any,
                       step_a_prompt: str,
                       remaining_issues: List[Dict[str, Any]],
                       effective_config: Dict[str, Any],
                       conversation_history: Optional[List[Dict[str, str]]] = None) -> tuple:
        """Step A: 调用 LLM 修订数据

        Args:
            current_data: 当前待修订数据
            step_a_prompt: 修订问题描述
            remaining_issues: 上一轮验收发现的问题
            effective_config: 生效的配置
            conversation_history: 历史对话

        Returns:
            tuple: (revised_data, step_a_log)
                revised_data: 修订后的数据（解析失败时为原始数据）
                step_a_log: 执行日志
        """
        step_a_log: Dict[str, Any] = {
            "success": False,
            "raw_output": "",
            "parsed_output": None,
            "error": None,
        }

        try:
            # 构造 Step A 的系统提示词
            step_a_system_prompt = effective_config.get("step_a_system_prompt", "")

            # 构造 user message
            user_message = self._build_step_a_user_message(
                current_data, step_a_prompt, remaining_issues
            )

            # 获取或创建 LLMDeploy 实例
            llm_config = effective_config.get("llm_config", {})
            llm = self._get_or_create_llm("llm_error_revision_step_a", llm_config, step_a_system_prompt)

            # 调用 LLM
            llm_input = self._build_llm_input(user_message, conversation_history)
            result = llm.generate_response("", llm_input, tools=None)

            # 提取 LLM 原始输出
            raw_content = self._extract_raw_text(result)
            step_a_log["raw_output"] = str(raw_content)

            # 如果已经是 dict（output_format=json 场景），直接使用
            if isinstance(raw_content, dict):
                parsed = raw_content
            else:
                # 解析 JSON
                parsed = self._parse_json(raw_content)

            if parsed is not None:
                step_a_log["parsed_output"] = parsed
                step_a_log["success"] = True
                return parsed, step_a_log

            # 解析失败
            parse_handling = effective_config.get("revision_config", {}).get("parse_error_handling", "retry")
            if parse_handling == "retry":
                step_a_log["error"] = f"Step A JSON 解析失败: {str(raw_content)[:200]}"
                return current_data, step_a_log
            else:
                step_a_log["error"] = f"Step A JSON 解析失败（已放弃）: {str(raw_content)[:200]}"
                return current_data, step_a_log

        except Exception as e:
            step_a_log["error"] = f"Step A 异常: {type(e).__name__}: {str(e)[:200]}"
            return current_data, step_a_log

    # ------------------------------------------------------------------
    # Step B: 验收检查
    # ------------------------------------------------------------------

    def _step_b_validate(self,
                         revised_data: Any,
                         step_b_prompt: str,
                         effective_config: Dict[str, Any],
                         conversation_history: Optional[List[Dict[str, str]]] = None) -> tuple:
        """Step B: 调用 LLM 验收检查

        Args:
            revised_data: 修订后的数据
            step_b_prompt: 达标标准描述
            effective_config: 生效的配置
            conversation_history: 历史对话

        Returns:
            tuple: (validation_result, step_b_log)
                validation_result: 验收结果字典
                step_b_log: 执行日志
        """
        step_b_log: Dict[str, Any] = {
            "success": False,
            "raw_output": "",
            "parsed_output": None,
            "error": None,
        }

        default_result = {
            "is_valid": False,
            "remaining_issues": [{"type": "validation_error", "description": "验收执行失败"}],
            "score": 0,
        }

        try:
            # 构造 Step B 的系统提示词
            step_b_system_prompt = effective_config.get("step_b_system_prompt", "")

            # 构造 user message
            user_message = self._build_step_b_user_message(revised_data, step_b_prompt)

            # 获取或创建 LLMDeploy 实例
            llm_config = effective_config.get("llm_config", {})
            llm = self._get_or_create_llm("llm_error_revision_step_b", llm_config, step_b_system_prompt)

            # 调用 LLM
            llm_input = self._build_llm_input(user_message, conversation_history)
            result = llm.generate_response("", llm_input, tools=None)

            # 提取 LLM 原始输出
            raw_content = self._extract_raw_text(result)
            step_b_log["raw_output"] = str(raw_content)

            # 如果已经是 dict（output_format=json 场景），直接使用
            if isinstance(raw_content, dict):
                parsed = raw_content
            else:
                # 解析 JSON
                parsed = self._parse_json(raw_content)

            if parsed is not None and isinstance(parsed, dict):
                # 确保必要字段存在
                if "is_valid" in parsed:
                    # 标准化输出
                    validation_result = {
                        "is_valid": bool(parsed.get("is_valid", False)),
                        "remaining_issues": parsed.get("remaining_issues", []),
                        "score": parsed.get("score", 0),
                    }
                    step_b_log["parsed_output"] = validation_result
                    step_b_log["success"] = True
                    return validation_result, step_b_log

            # 解析失败或格式不正确
            step_b_log["error"] = f"Step B 输出格式错误: {str(raw_content)[:200]}"
            return default_result, step_b_log

        except Exception as e:
            step_b_log["error"] = f"Step B 异常: {type(e).__name__}: {str(e)[:200]}"
            return default_result, step_b_log

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _build_step_a_user_message(self,
                                   current_data: Any,
                                   step_a_prompt: str,
                                   remaining_issues: List[Dict[str, Any]]) -> str:
        """构造 Step A 的 user message

        Args:
            current_data: 当前数据
            step_a_prompt: 修订问题描述
            remaining_issues: 上一轮问题列表

        Returns:
            str: 构造好的 user message
        """
        # 序列化当前数据
        try:
            data_json = json.dumps(current_data, ensure_ascii=False, indent=2)
        except Exception:
            data_json = str(current_data)

        # 序列化剩余问题
        issues_text = ""
        if remaining_issues:
            try:
                issues_text = json.dumps(remaining_issues, ensure_ascii=False, indent=2)
            except Exception:
                issues_text = str(remaining_issues)

        # 构造消息
        parts = [
            f"【修复目标】",
            step_a_prompt,
            "",
            f"【当前数据】",
            data_json,
        ]

        if issues_text:
            parts.extend([
                "",
                f"【上次验收发现的问题】",
                issues_text,
                "",
                "请重点关注以上问题，并修复数据。如果没有需要修复的问题，直接返回原数据。",
            ])
        else:
            parts.extend([
                "",
                "请检查数据是否存在需要修复的问题，并进行修复。",
                "如果数据已经符合要求，直接返回原数据。",
            ])

        parts.extend([
            "",
            "【输出要求】",
            "- 直接返回修复后的 JSON 数据",
            "- 不要包含任何额外的说明文字",
        ])

        return "\n".join(parts)

    def _build_step_b_user_message(self,
                                   revised_data: Any,
                                   step_b_prompt: str) -> str:
        """构造 Step B 的 user message

        Args:
            revised_data: 修订后的数据
            step_b_prompt: 达标标准描述

        Returns:
            str: 构造好的 user message
        """
        # 序列化修订后的数据
        try:
            data_json = json.dumps(revised_data, ensure_ascii=False, indent=2)
        except Exception:
            data_json = str(revised_data)

        # 构造消息
        parts = [
            f"【验收标准】",
            step_b_prompt,
            "",
            f"【待检查数据】",
            data_json,
            "",
            "请严格按照验收标准检查数据，并返回验收结果。",
        ]

        return "\n".join(parts)

    def _build_llm_input(self,
                         user_message: str,
                         conversation_history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        """构造 LLM 输入消息列表

        Args:
            user_message: 当前用户消息
            conversation_history: 历史对话

        Returns:
            list: LLM 输入消息列表
        """
        messages: List[Dict[str, str]] = []

        # 添加历史对话（排除 system 消息）
        if conversation_history and isinstance(conversation_history, list):
            for msg in conversation_history[-6:]:  # 最近3轮
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role and content and role != "system":
                    if len(content) > 2000:
                        content = content[:2000] + "(...已截断)"
                    messages.append({"role": role, "content": content})

        # 添加当前消息
        messages.append({"role": "user", "content": user_message})

        return messages

    @staticmethod
    def _extract_raw_text(result: Any) -> Any:
        """从 LLM 返回结果中提取原始文本或结构化内容

        当 output_format=json 时，content 可能已经是 dict，
        此时直接返回 dict 而非 str，避免 Python repr 格式导致的解析失败。

        Args:
            result: LLM 返回结果

        Returns:
            Any: 原始内容（str 或 dict）
        """
        if isinstance(result, dict):
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    return content
                return str(content)
            else:
                return str(result)
        else:
            return str(result)

    @staticmethod
    def _parse_json(text: str) -> Optional[Any]:
        """从 LLM 返回文本中提取 JSON 对象

        处理以下常见格式：
          1. 纯 JSON 文本（含/不含换行、空格）
          2. 被 ```json ... ``` 代码块包裹
          3. 被 ``` ... ``` 代码块包裹
          4. 文本中包含 {...} 片段（取最后一个完整匹配）
          5. Python 字典格式（单引号，如 {'key': 'value'}）
          6. 被引号包裹的内容（如 "{'key': 'value'}"）

        Args:
            text: 待解析的文本

        Returns:
            Any: 解析后的 JSON 对象，失败时返回 None
        """
        if not text:
            return None

        candidate = text.strip()

        # 预处理：移除可能的外层引号包裹
        # LLM 有时会返回被额外引号包裹的内容
        # 例如: "{'key': 'value'}" 或 '"{"key": "value"}"'
        if len(candidate) >= 2:
            # 检查是否被双引号包裹
            if candidate[0] == '"' and candidate[-1] == '"':
                inner = candidate[1:-1].strip()
                # 只有当内部内容以 { 或 [ 开头时才进行替换
                if inner and inner[0] in ('{', '['):
                    candidate = inner
            # 检查是否被单引号包裹
            elif candidate[0] == "'" and candidate[-1] == "'":
                inner = candidate[1:-1].strip()
                if inner and inner[0] in ('{', '['):
                    candidate = inner

        # 尝试 1：直接解析标准 JSON
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # 尝试 2：移除 ```json / ``` 包裹
        def _strip_code_block(s: str) -> str:
            pattern = r"```(?:json)?\s*([\s\S]+?)\s*```"
            m = re.search(pattern, s)
            if m:
                return m.group(1).strip()
            return s

        candidate = _strip_code_block(candidate)
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # 尝试 3：从文本中提取最后一个 {...} 片段
        brace_matches = re.findall(r"\{[^{}]*\}", candidate)
        for frag in reversed(brace_matches):
            try:
                return json.loads(frag)
            except Exception:
                continue

        # 尝试 4：查找 [...] 数组片段
        bracket_matches = re.findall(r"\[[^\[\]]*\]", candidate)
        for frag in reversed(bracket_matches):
            try:
                return json.loads(frag)
            except Exception:
                continue

        # 尝试 5：尝试解析 Python 字典格式（单引号）
        # LLM 经常返回 Python 格式的字典，需要转换为标准 JSON
        try:
            import ast
            # 先尝试使用 ast.literal_eval 解析 Python 字典
            try:
                # 尝试直接用 ast.literal_eval 解析（如果是有效的 Python 字面量）
                result = ast.literal_eval(candidate)
                if isinstance(result, (dict, list)):
                    return result
            except Exception:
                pass
            
            # 尝试手动转换单引号为双引号
            # 这是一个简化的转换，对于 LLM 的简单输出通常有效
            converted = candidate.replace("'", '"')
            try:
                return json.loads(converted)
            except Exception:
                pass
                
        except Exception:
            pass

        return None

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        """构造错误结果

        Args:
            message: 错误信息

        Returns:
            dict: 错误结果
        """
        return {
            "status": "error",
            "revised_data": None,
            "is_valid": False,
            "attempts": 0,
            "remaining_issues": [],
            "history": [],
            "last_error": message,
        }

    # ------------------------------------------------------------------
    # 配置加载与合并
    # ------------------------------------------------------------------

    def _ensure_default_config_loaded(self) -> None:
        """懒加载 llm_error_revision.yaml 默认配置"""
        if self._default_config is not None:
            return

        with self._init_default_lock:
            if self._default_config is not None:
                return
            self._default_config = self._load_config_from_yaml()

    def _load_config_from_yaml(self) -> Dict[str, Any]:
        """从 config/llm_error_revision.yaml 加载默认配置

        Returns:
            dict: 解析后的配置字典；读取失败时返回兜底配置
        """
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config",
            "llm_error_revision.yaml",
        )

        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if isinstance(config, dict):
                return config
            return self._default_config_fallback()
        except FileNotFoundError:
            return self._default_config_fallback()
        except Exception:
            return self._default_config_fallback()

    def _merge_config(self, revision_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """将调用方传入的 revision_config 与默认配置合并

        Args:
            revision_config: 调用方传入的覆盖配置

        Returns:
            dict: 合并后的生效配置
        """
        self._ensure_default_config_loaded()

        # 复制默认配置
        default = dict(self._default_config or {})

        if not revision_config or not isinstance(revision_config, dict):
            return default

        # 合并 llm_config
        default_llm = dict(default.get("llm_config", {}))
        override_llm = revision_config.get("llm_config")
        if isinstance(override_llm, dict):
            default_llm.update(override_llm)
        default["llm_config"] = default_llm

        # 合并 revision_config
        default_rev = dict(default.get("revision_config", {}))
        override_rev = revision_config.get("revision_config")
        if isinstance(override_rev, dict):
            default_rev.update(override_rev)
        default["revision_config"] = default_rev

        return default

    def _get_or_create_llm(self,
                           agent_id: str,
                           llm_config: Dict[str, Any],
                           system_prompt: str) -> Any:
        """从模块级 llm_pool 获取或创建 LLMDeploy 实例

        Args:
            agent_id: Agent 标识
            llm_config: LLM 配置
            system_prompt: 系统提示词

        Returns:
            LLMDeploy 实例
        """
        # 生成稳定的 cache key
        llm_items = tuple(sorted(llm_config.items(), key=lambda x: x[0]))
        cache_key = f"{agent_id}||{llm_items}"

        if cache_key in _llm_pool:
            return _llm_pool[cache_key]

        with _llm_pool_lock:
            if cache_key in _llm_pool:
                return _llm_pool[cache_key]

            from snail_avatar.backend.llm.deploy import LLMDeploy
            llm = LLMDeploy(agent_id, system_prompt, llm_config)
            _llm_pool[cache_key] = llm
            return llm

    @staticmethod
    def _default_config_fallback() -> Dict[str, Any]:
        """返回兜底配置（YAML 读取失败时使用）

        Returns:
            dict: 兜底配置
        """
        return {
            "agent_id": "llm_error_revision",
            "agent_name": "LLM错误修订器",
            "agent_description": "默认配置（YAML 读取失败）",
            "step_a_system_prompt": (
                "你是一个数据修复专家。请根据提供的问题描述修复数据。"
                "只修复指出的问题，不要修改正确的部分。"
                "直接返回修复后的 JSON 数据，不要包含额外文字。"
            ),
            "step_b_system_prompt": (
                "你是一个数据质量检查员。请根据验收标准检查数据是否合格。"
                "输出 JSON 格式：{\"is_valid\": true/false, \"remaining_issues\": [...], \"score\": 0-100}"
            ),
            "llm_config": {
                "model_name": "qwen3.5-flash",
                "max_new_tokens": 1000,
                "temperature": 0.2,
                "top_p": 0.9,
                "presence_penalty": 0.0,
                "context_window": 16000,
            },
            "revision_config": {
                "max_retries": 3,
                "first_pass_optimization": True,
                "parse_error_handling": "retry",
            },
        }


# ----------------------------------------------------------------------
# 模块级工厂函数：对外保持简洁 API
# ----------------------------------------------------------------------

_revision_instance = None


def get_llm_error_revision() -> LLMErrorRevision:
    """获取 LLM 错误修订工具单例

    Returns:
        LLMErrorRevision 实例
    """
    global _revision_instance
    if _revision_instance is None:
        _revision_instance = LLMErrorRevision()
    return _revision_instance
