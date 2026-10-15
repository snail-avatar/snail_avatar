# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : llm_router.py
# @Desc    : LLM 对话路由决策工具 - 使用轻量 LLM 根据用户问题决定由哪个 Agent 处理
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
LLM 对话路由决策工具

参照 conversation_summarizer 的实现模式：
  - 单例模式：LLMConversationRouter 为单例，通过 get_llm_router() 获取
  - 配置驱动：优先使用 router.yaml 中的默认配置，可被调用方传入的 router_config 覆盖
  - LLM 调用失败时自动降级为关键词匹配（与原 dispatch 逻辑一致）
  - 通过 LLMDeploy 统一完成环境准备和 API 调用
  - 线程安全（通过 threading.Lock）

使用方式（agent_router.py 中）:

    from snail_avatar.backend.agents.core.tools.LLM_tools import get_llm_router

    router_tool = get_llm_router()

    # 最简调用：使用 router.yaml 中的默认配置
    result = router_tool.route(
        user_message,
        current_agent_id,
        agent_configs=self._agent_configs,
    )
    # result: {"agent_id": str, "reason": str, "trust_level": "high|medium|low", "used_llm": bool}

    # 高级调用：传入 router_config 覆盖默认参数
    result = router_tool.route(
        user_message,
        current_agent_id,
        agent_configs=self._agent_configs,
        router_config={"llm_config": {"model_name": "qwen3.5-plus"}},
    )
"""

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional


# =============================================================================
# 模块级 LLMDeploy 实例池：按 agent_id 独立缓存，避免不同 Agent 混用同一个实例
# =============================================================================

_llm_pool: Dict[str, Any] = {}
_llm_pool_lock = threading.Lock()


class LLMConversationRouter:
    """LLM 对话路由决策工具

    设计约束：
    - 使用 qwen3.5-flash 轻量模型（在 router.yaml 中可修改，可被调用方传入的
      router_config 覆盖）
    - LLM 调用失败 / 返回格式异常 / trust_level 过低时，
      自动降级为原有的关键词匹配逻辑
    - 通过 LLMDeploy / LLMEnvironment / APIKeyProvider 统一完成环境准备和 API 调用
    - 线程安全（通过 threading.Lock）
    - 支持按调用方差异化：调用方传入 router_config dict 即可覆盖默认参数
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 懒加载：router.yaml 默认配置在首次调用时加载一次
        self._default_config: Optional[Dict[str, Any]] = None
        self._init_default_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def route(self,
              user_message: str,
              current_agent_id: str,
              agent_configs: Optional[Dict[str, Any]] = None,
              router_config: Optional[Dict[str, Any]] = None,
              conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """调用 LLM 进行路由决策

        配置优先级（从高到低）:
          1. 传入的 router_config dict
          2. router.yaml 默认配置
          3. Python 代码兜底常量

        Args:
            user_message: 用户输入的问题文本
            current_agent_id: 当前活跃的 Agent ID（如 "main_agent"）
            agent_configs: 所有 Agent 的完整配置字典
                （即 AgentRouter._agent_configs），键为 agent_id，值为 YAML 解析后的 dict
            router_config: 可选，调用方传入的覆盖配置，如:
                {
                    "llm_config": {"model_name": "qwen3.5-plus", "max_new_tokens": 400},
                    "rule_router_config": {"min_trust_level": "medium"},
                }

        Returns:
            dict: 决策结果，包含以下关键字段:
                - agent_id, reason, trust_level, used_llm
                - （used_llm=True 时额外包含）
                  llm_input_system_prompt, llm_input_user_message,
                  llm_raw_output, llm_parsed_output
                - （used_llm=False 且发生降级时额外包含）
                  fallback_reason, llm_input_system_prompt, llm_input_user_message, llm_raw_output
        """
        # --- 快速退出：输入异常 / 无 Agent 配置（此时没有 LLM 输入输出可记录） ---
        if not user_message or not isinstance(user_message, str):
            return {
                "agent_id": current_agent_id,
                "reason": "用户消息为空或格式异常，由当前Agent处理",
                "trust_level": "low",
                "used_llm": False,
                "fallback_reason": "user_message 为空或非字符串",
            }

        if not agent_configs:
            return {
                "agent_id": current_agent_id,
                "reason": "无可用Agent配置，由当前Agent处理",
                "trust_level": "low",
                "used_llm": False,
                "fallback_reason": "agent_configs 为空",
            }

        # --- 构造 LLM 输入（无论成功失败都要记录，用于 UI 展示） ---
        effective_config = self._merge_config(router_config)

        # 构造 Agent 清单（与 _llm_route 内部一致，保留一份副本用于输出）
        agent_inventory_lines: List[str] = []
        for _aid, _cfg in agent_configs.items():
            if isinstance(_cfg, dict):
                _kws = _cfg.get("routing_keywords", [])
                _nicks = _cfg.get("agent_nicknames", [])
                _desc = _cfg.get("agent_description") or _cfg.get("agent_name") or _aid
                _parts = [f"- ID: {_aid}"]
                if _nicks:
                    _parts.append(f"昵称: {', '.join(_nicks)}")
                _parts.append(f"关键词: {', '.join(_kws) if _kws else '(无)'}")
                _parts.append(f"描述: {_desc}")
                agent_inventory_lines.append("；".join(_parts))
        agent_inventory_text = "\n".join(agent_inventory_lines)

        # 构造 system prompt
        system_prompt_template = effective_config.get("system_prompt", "")
        llm_input_system_prompt = (
            system_prompt_template
            .replace("{agent_inventory}", agent_inventory_text)
            .replace("{current_agent_id}", current_agent_id)
        )

        # 构造 user message（可能截断）
        user_truncate = 2000
        if len(user_message) > user_truncate:
            llm_input_user_message = user_message[:user_truncate] + "(...已截断)"
        else:
            llm_input_user_message = user_message

        # --- 调用 LLM ---
        llm_raw_output = ""
        llm_parsed_output: Optional[Dict[str, Any]] = None
        fallback_reason = ""

        try:
            llm_result = self._llm_route(
                user_message, current_agent_id, agent_configs, effective_config,
                _input_snapshot=(llm_input_system_prompt, llm_input_user_message),
                conversation_history=conversation_history,
            )

            # 提取 LLM 原始输出和解析结果（由 _llm_route 注入）
            if isinstance(llm_result, dict):
                llm_raw_output = str(llm_result.pop("_llm_raw_output", "")) or llm_raw_output
                llm_parsed_output = llm_result.pop("_llm_parsed_output", None) or llm_parsed_output

            # 【防御性校验】agent_id 合法性
            if (
                isinstance(llm_result, dict)
                and "agent_id" in llm_result
                and str(llm_result["agent_id"]).strip() in agent_configs
            ):
                # LLM 路由成功：注入输入/输出原始信息
                llm_result["llm_input_system_prompt"] = llm_input_system_prompt
                llm_result["llm_input_user_message"] = llm_input_user_message
                llm_result["llm_raw_output"] = llm_raw_output
                if llm_parsed_output is not None:
                    try:
                        llm_result["llm_parsed_output"] = json.dumps(
                            llm_parsed_output, ensure_ascii=False, indent=2
                        )
                    except Exception:
                        llm_result["llm_parsed_output"] = str(llm_parsed_output)
                return llm_result

            # 校验不通过：降级为关键词匹配
            fallback_reason = (
                f"LLM 返回的 agent_id=[{str(llm_result.get('agent_id', '')) if isinstance(llm_result, dict) else ''}]不在配置中"
            )
            fallback_result = self._keyword_route(
                user_message, current_agent_id, agent_configs
            )
            # 降级时仍然携带 LLM 输入输出，便于 UI 展示
            fallback_result["llm_input_system_prompt"] = llm_input_system_prompt
            fallback_result["llm_input_user_message"] = llm_input_user_message
            fallback_result["llm_raw_output"] = llm_raw_output
            fallback_result["fallback_reason"] = fallback_reason
            return fallback_result
        except Exception as e:
            # LLM 路由抛异常（网络超时、API 错误、配置缺失等）
            fallback_reason = f"LLM 路由调用异常: {type(e).__name__}: {str(e)[:200]}"
            fallback_result = self._keyword_route(
                user_message, current_agent_id, agent_configs
            )
            fallback_result["llm_input_system_prompt"] = llm_input_system_prompt
            fallback_result["llm_input_user_message"] = llm_input_user_message
            fallback_result["llm_raw_output"] = llm_raw_output
            fallback_result["fallback_reason"] = fallback_reason
            return fallback_result

    # ------------------------------------------------------------------
    # 内部方法：初始化 / LLM 路由 / 关键词降级 / 配置加载 / 实例缓存
    # ------------------------------------------------------------------

    def _llm_route(self,
                   user_message: str,
                   current_agent_id: str,
                   agent_configs: Dict[str, Any],
                   effective_config: Dict[str, Any],
                   _input_snapshot=None,
                   conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """调用 LLM 进行路由决策（内部方法，附带 LLM 输入输出原始信息）

        说明:
            通过 `_llm_raw_output` / `_llm_parsed_output` 内部字段将 LLM 原始输出
            传递给外层 route()，由外层统一格式化为对外可见字段后返回。

        Returns:
            dict: {"agent_id", "reason", "trust_level", "used_llm", ...}
        """
        # 1. 构造 Agent 清单（供 LLM 参考选择）
        agent_inventory_lines: List[str] = []
        for agent_id, config in agent_configs.items():
            if not isinstance(config, dict):
                continue
            keywords = config.get("routing_keywords", [])
            nicknames = config.get("agent_nicknames", [])
            description = (
                config.get("agent_description")
                or config.get("agent_name")
                or agent_id
            )
            parts = [f"- ID: {agent_id}"]
            if nicknames:
                parts.append(f"昵称: {', '.join(nicknames)}")
            parts.append(f"关键词: {', '.join(keywords) if keywords else '(无)'}")
            parts.append(f"描述: {description}")
            agent_inventory_lines.append("；".join(parts))
        agent_inventory_text = "\n".join(agent_inventory_lines)

        # 2. 把 system_prompt 模板中的 {agent_inventory} 和 {current_agent_id} 替换为实际值
        system_prompt_template = effective_config.get("system_prompt", "")
        system_prompt = (
            system_prompt_template
            .replace("{agent_inventory}", agent_inventory_text)
            .replace("{current_agent_id}", current_agent_id)
        )

        # 3. 获取或创建 LLMDeploy 实例（按 agent_id 独立缓存）
        llm_config = effective_config.get("llm_config", {})
        effective_agent_id = "llm_router"
        llm = self._get_or_create_llm(
            effective_agent_id, llm_config, system_prompt
        )

        # 4. 构造路由决策的 user 消息（用户问题的前若干字符，避免超长）
        user_truncate = 800
        if len(user_message) > user_truncate:
            truncated_msg = user_message[:user_truncate] + "(...已截断)"
        else:
            truncated_msg = user_message

        # 5. 构造对话历史：使用最近3轮历史 + 当前问题
        routing_history = []
        
        # 添加最近3轮对话历史（排除系统消息）
        if conversation_history and isinstance(conversation_history, list):
            # 取最近的历史记录（往返算一轮，所以取6条，即3轮）
            recent_history = conversation_history[-6:]
            for msg in recent_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role and content and role != "system":
                    # 截断过长的历史内容
                    if len(content) > 2000:
                        content = content[:2000] + "(...已截断)"
                    role_cn = "用户" if role == "user" else "助手"
                    routing_history.append({
                        "role": "user",
                        "content": f"【历史】{role_cn}：{content}"
                    })
        
        # 添加当前问题
        routing_history.append({
            "role": "user",
            "content": f"【当前】用户问题：\n\n{truncated_msg}"
        })

        # 6. 通过 LLMDeploy 统一调用 LLM
        result = llm.generate_response("", routing_history, tools=None)

        # 5.1 保存 LLM 原始输出（用于 UI 展示和调试追踪）
        raw_text = ""
        if isinstance(result, dict):
            raw_text = str(result.get("content", "")) if "content" in result else str(result)
        else:
            raw_text = str(result)

        # 6. 解析 LLM 返回的 JSON
        parsed: Optional[Dict[str, Any]] = None
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if content:
                parsed = self._parse_json(content)

        # --- 辅助函数：给返回 dict 注入原始 LLM 信息（内部字段，以下划线开头） ---
        def _attach_raw(res_dict: Dict[str, Any]) -> Dict[str, Any]:
            res_dict["_llm_raw_output"] = raw_text
            if parsed is not None:
                res_dict["_llm_parsed_output"] = parsed
            return res_dict

        if parsed and isinstance(parsed, dict):
            target_agent_id = str(parsed.get("agent_id", "")).strip()
            reason = str(parsed.get("reason", "")).strip() or "LLM路由决策"
            trust_level_raw = str(parsed.get("trust_level", "medium")).lower()
            trust_level = trust_level_raw if trust_level_raw in ("high", "medium", "low") else "medium"

            # 校验：agent_id 必须在 agent_configs 中存在，否则强制返回当前 Agent
            if target_agent_id not in agent_configs:
                return _attach_raw({
                    "agent_id": current_agent_id,
                    "reason": f"LLM 返回的 agent_id=[{target_agent_id}]不在配置中，由当前Agent处理",
                    "trust_level": "low",
                    "used_llm": True,
                })

            # 校验 trust_level：低于配置要求时降级为关键词匹配
            rule_cfg = effective_config.get("rule_router_config", {})
            min_trust = str(rule_cfg.get("min_trust_level", "low")).lower()
            trust_order = {"low": 0, "medium": 1, "high": 2}
            if trust_order.get(trust_level, 0) < trust_order.get(min_trust, 0):
                fallback = self._keyword_route(
                    user_message, current_agent_id, agent_configs
                )
                # 保留 LLM 原始信息到降级结果中
                fallback["_llm_raw_output"] = raw_text
                if parsed is not None:
                    fallback["_llm_parsed_output"] = parsed
                fallback["fallback_reason"] = f"trust_level={trust_level} 低于 min_trust_level={min_trust}"
                return fallback

            return _attach_raw({
                "agent_id": target_agent_id,
                "reason": reason,
                "trust_level": trust_level,
                "used_llm": True,
            })

        # LLM 返回内容无法解析为 JSON，降级为关键词匹配
        try:
            from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger
            AgentMessageLogger.log(
                "llm_router",
                "router_fallback",
                f"LLM 路由返回内容无法解析为 JSON，已降级为关键词匹配。"
                f" 返回内容前 200 字: {str(result)[:200]}",
            )
        except Exception:
            pass

        fallback = self._keyword_route(user_message, current_agent_id, agent_configs)
        fallback["_llm_raw_output"] = raw_text
        if parsed is not None:
            fallback["_llm_parsed_output"] = parsed
        fallback["fallback_reason"] = "LLM 路由返回内容无法解析为 JSON"
        return fallback

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict[str, Any]]:
        """从 LLM 返回文本中提取 JSON 对象

        处理以下常见格式：
          1. 纯 JSON 文本（含/不含换行、空格）
          2. 被 ```json ... ``` 代码块包裹
          3. 被 ``` ... ``` 代码块包裹
          4. 文本中包含 {...} 片段（取最后一个完整匹配）
        """
        if not text:
            return None

        candidate = text.strip()

        # 尝试 1：直接解析
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

        return None

    def _keyword_route(self,
                       user_message: str,
                       current_agent_id: str,
                       agent_configs: Dict[str, Any]) -> Dict[str, Any]:
        """纯关键词匹配（降级方案，与原 dispatch 逻辑一致）

        Returns:
            dict: {"agent_id", "reason", "trust_level", "used_llm": False}
        """
        for agent_id, config in agent_configs.items():
            if agent_id == current_agent_id:
                continue
            if not isinstance(config, dict):
                continue

            keywords = config.get("routing_keywords", [])
            if not keywords:
                continue

            for keyword in keywords:
                if keyword and keyword in user_message:
                    return {
                        "agent_id": agent_id,
                        "reason": f"匹配关键词 [{keyword}]，转交至 {agent_id}",
                        "trust_level": "medium",
                        "used_llm": False,
                    }

        return {
            "agent_id": current_agent_id,
            "reason": "无匹配关键词，由当前Agent处理",
            "trust_level": "low",
            "used_llm": False,
        }

    def _ensure_default_config_loaded(self) -> None:
        """懒加载 router.yaml 默认配置（仅首次调用时执行一次）"""
        if self._default_config is not None:
            return

        with self._init_default_lock:
            if self._default_config is not None:
                return
            self._default_config = self._load_config_from_yaml()

    def _load_config_from_yaml(self) -> Dict[str, Any]:
        """从 config/router.yaml 加载默认配置

        Returns:
            dict: 解析后的配置字典；读取失败时返回 _default_config_fallback()
        """
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config",
            "router.yaml",
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

    def _merge_config(self, router_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """将调用方传入的 router_config 与 router.yaml 默认配置合并

        router_config 中的键覆盖默认配置中的同名键；不存在的键保留默认值。
        """
        self._ensure_default_config_loaded()

        # 复制默认配置，避免污染原对象
        default = dict(self._default_config or {})

        if not router_config or not isinstance(router_config, dict):
            return default

        # 顶层字段 system_prompt（一般不建议覆盖，但支持）
        if "system_prompt" in router_config:
            default["system_prompt"] = router_config["system_prompt"]

        # llm_config 节：合并覆盖
        default_llm = dict(default.get("llm_config", {}))
        override_llm = router_config.get("llm_config")
        if isinstance(override_llm, dict):
            default_llm.update(override_llm)
        default["llm_config"] = default_llm

        # rule_router_config 节：合并覆盖
        default_rule = dict(default.get("rule_router_config", {}))
        override_rule = router_config.get("rule_router_config")
        if isinstance(override_rule, dict):
            default_rule.update(override_rule)
        default["rule_router_config"] = default_rule

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
        """返回一套合理的兜底配置（router.yaml 读取失败时使用）

        结构与 router.yaml 保持一致，确保后续合并逻辑无需特殊处理。
        """
        return {
            "agent_id": "llm_router",
            "agent_name": "LLM路由器",
            "agent_description": "默认配置（YAML 读取失败）",
            "system_prompt": (
                "你是一个多 Agent 路由决策助手。你的任务是根据用户输入，从给定的"
                "Agent 列表中选择最合适的一个来处理用户问题。\n"
                "\n"
                "【当前可用 Agent 列表】\n"
                "{agent_inventory}\n"
                "\n"
                "当前活跃 Agent: {current_agent_id}\n"
                "\n"
                "只输出 JSON 格式：{\"agent_id\": \"目标Agent的ID\","
                " \"reason\": \"简要理由\", \"trust_level\": \"high|medium|low\"}"
            ),
            "llm_config": {
                "model_name": "qwen3.5-flash",
                "max_new_tokens": 300,
                "temperature": 0.2,
                "top_p": 0.9,
                "presence_penalty": 0.0,
                "context_window": 16000,
            },
            "rule_router_config": {
                "enable_keyword_fallback": True,
                "min_trust_level": "low",
            },
        }


# ----------------------------------------------------------------------
# 模块级工厂函数：对外保持不变（调用方无需修改 import）
# ----------------------------------------------------------------------

_router_instance = None


def get_llm_router() -> LLMConversationRouter:
    """获取 LLM 路由工具单例

    对外 API 保持不变：调用方（agent_router.py）仍可以用
    `from snail_avatar.backend.agents.core.tools.LLM_tools import get_llm_router` 正常使用。
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMConversationRouter()
    return _router_instance
