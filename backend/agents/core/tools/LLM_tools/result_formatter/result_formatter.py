# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : result_formatter.py
# @Desc    : 结果格式整理器 - 使用轻量 LLM 将步骤执行结果整理为结构化数据+推理逻辑格式
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
结果格式整理器 - 使用轻量 LLM 将步骤执行结果整理为结构化数据+推理逻辑格式

设计约束:
- 使用 qwen3-8b 轻量模型（在 formatter.yaml 中可修改）
- LLM 调用失败时直接抛出异常（不降级为规则解析）
- 通过 LLMDeploy / LLMEnvironment / APIKeyProvider 统一完成环境准备和 API 调用
- 线程安全（通过 threading.Lock）
- 支持按 Agent 差异化配置

使用方式:
    from snail_avatar.backend.agents.core.tools.LLM_tools import get_result_formatter

    formatter = get_result_formatter()
    
    # 最简调用：使用 formatter.yaml 中的默认配置
    formatted_result = formatter.format(raw_result)
    
    # 按步骤差异化：传入步骤的配置
    formatted_result = formatter.format(
        raw_result,
        formatter_config=step_config.get("formatter_config", {}),
        step_id=step.step_id,
    )
"""

import os
import json
import threading
from typing import Any, Dict, Optional


_llm_pool: Dict[str, Any] = {}
_llm_pool_lock = threading.Lock()


class ResultFormatter:
    """结果格式整理器 - 使用轻量 LLM 将步骤执行结果整理为结构化数据+推理逻辑格式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._default_config: Optional[Dict[str, Any]] = None
        self._init_default_lock = threading.Lock()

    def format(self,
               raw_result: str,
               formatter_config: Optional[Dict[str, Any]] = None,
               step_id: Optional[str] = None) -> str:
        """将原始结果整理为结构化数据+推理逻辑格式

        配置优先级（从高到低）:
          1. 传入的 formatter_config dict（通常来自步骤的 YAML formatter_config 节）
          2. formatter.yaml 默认配置
          3. Python 代码兜底常量

        Args:
            raw_result: 原始结果文本
            formatter_config: 可选，步骤的格式化覆盖配置
            step_id: 可选，用于标识此格式化属于哪个步骤

        Returns:
            str: 格式化后的 JSON 字符串（{"structured_data": {}, "reasoning_logic": ""}）
        """
        if not raw_result:
            return json.dumps({"structured_data": {}, "reasoning_logic": ""}, ensure_ascii=False)

        effective_config = self._merge_config(formatter_config)

        return self._llm_format(raw_result, effective_config, step_id)

    def _rule_format(self, raw_result: str) -> str:
        """规则降级方案：尝试从文本中提取 JSON 结构

        利用 LLMDeploy._parse_json_content 的稳健解析能力处理
        markdown 包裹、截断 JSON、前后夹杂文本等场景。
        """
        import re

        try:
            from snail_avatar.backend.llm.deploy import LLMDeploy
            # 使用 deploy 的统一解析能力
            parsed = LLMDeploy._parse_json_content(raw_result)
            if parsed is not None and isinstance(parsed, dict):
                structured_data = parsed.get("structured_data", parsed)
                reasoning_logic = parsed.get("reasoning_logic", "")
                if "structured_data" not in parsed and "reasoning_logic" not in parsed:
                    structured_data = parsed
                    reasoning_logic = ""
                return json.dumps({
                    "structured_data": structured_data,
                    "reasoning_logic": reasoning_logic
                }, ensure_ascii=False)
            elif parsed is not None:
                return json.dumps({
                    "structured_data": {},
                    "reasoning_logic": str(parsed)
                }, ensure_ascii=False)
        except Exception:
            pass

        # 兜底：原始 find("{") + rfind("}") 逻辑
        try:
            start_idx = raw_result.find("{")
            end_idx = raw_result.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = raw_result[start_idx:end_idx]
                data = json.loads(json_str)

                if isinstance(data, dict):
                    structured_data = data.get("structured_data", data)
                    reasoning_logic = data.get("reasoning_logic", "")
                    if "structured_data" not in data and "reasoning_logic" not in data:
                        structured_data = data
                        reasoning_logic = ""
                    return json.dumps({
                        "structured_data": structured_data,
                        "reasoning_logic": reasoning_logic
                    }, ensure_ascii=False)

                return json.dumps({
                    "structured_data": {},
                    "reasoning_logic": str(data)
                }, ensure_ascii=False)
        except Exception:
            pass

        return json.dumps({
            "structured_data": {},
            "reasoning_logic": raw_result
        }, ensure_ascii=False)

    def _ensure_default_config_loaded(self) -> None:
        """懒加载 formatter.yaml 默认配置"""
        if self._default_config is not None:
            return

        with self._init_default_lock:
            if self._default_config is not None:
                return
            self._default_config = self._load_config_from_yaml()

    def _load_config_from_yaml(self) -> Dict[str, Any]:
        """从 config/formatter.yaml 加载默认配置"""
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config",
            "formatter.yaml",
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

    def _merge_config(self, formatter_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """将调用方传入的 formatter_config 与 formatter.yaml 默认配置合并

        支持覆盖的配置项：
        - llm_config: 深合并（子键级别）
        - system_prompt: 完整替换（不合并），用于 per-step 定制化提示词
        """
        self._ensure_default_config_loaded()

        default = dict(self._default_config or {})

        if not formatter_config or not isinstance(formatter_config, dict):
            return default

        # llm_config 深合并
        default_llm = dict(default.get("llm_config", {}))
        override_llm = formatter_config.get("llm_config")
        if isinstance(override_llm, dict):
            default_llm.update(override_llm)
        default["llm_config"] = default_llm

        # system_prompt 完整替换
        override_prompt = formatter_config.get("system_prompt")
        if override_prompt and isinstance(override_prompt, str):
            default["system_prompt"] = override_prompt

        return default

    def _get_or_create_llm(self,
                           step_id: str,
                           llm_config: Dict[str, Any],
                           system_prompt: str) -> Any:
        """从模块级 llm_pool 获取或创建 LLMDeploy 实例"""
        llm_items = tuple(sorted(llm_config.items(), key=lambda x: x[0]))
        cache_key = f"{step_id}||{llm_items}"

        if cache_key in _llm_pool:
            return _llm_pool[cache_key]

        with _llm_pool_lock:
            if cache_key in _llm_pool:
                return _llm_pool[cache_key]

            from snail_avatar.backend.llm.deploy import LLMDeploy
            llm = LLMDeploy(step_id, system_prompt, llm_config)
            _llm_pool[cache_key] = llm
            return llm

    def _llm_format(self,
                    raw_result: str,
                    effective_config: Dict[str, Any],
                    step_id: Optional[str]) -> str:
        """调用 LLM 进行格式整理"""
        system_prompt = effective_config.get("system_prompt", "")

        llm_config = effective_config.get("llm_config", {})
        effective_step_id = step_id or "default_formatter"
        llm = self._get_or_create_llm(effective_step_id, llm_config, system_prompt)

        conversation_history = [
            {"role": "user", "content": f"请将以下结果整理为结构化数据和推理逻辑两部分：\n\n{raw_result}"},
        ]

        result = llm.generate_response("", conversation_history, tools=None)

        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if content:
                if isinstance(content, dict):
                    return json.dumps(content, ensure_ascii=False)
                formatted = self._rule_format(content)
                return formatted

        raise ValueError("LLM 格式整理返回内容无效")

    @staticmethod
    def _default_config_fallback() -> Dict[str, Any]:
        """返回一套合理的兜底配置"""
        return {
            "agent_id": "result_formatter",
            "agent_name": "结果格式整理器",
            "agent_description": "默认配置（YAML 读取失败）",
            "system_prompt": (
                "你是一个结果格式整理专家，负责将原始文本整理为结构化数据和推理逻辑两部分。\n"
                "\n"
                "【任务要求】\n"
                "1. 从原始结果中提取结构化数据（参数、数值、关系等）\n"
                "2. 提取或总结推理逻辑（决策理由、分析过程等）\n"
                "3. 如果无法提取结构化数据，structured_data 字段返回空对象 {}\n"
                "4. 如果没有推理逻辑，reasoning_logic 字段返回空字符串 \"\"\n"
                "\n"
                "【输出格式】\n"
                "请严格按照以下JSON格式输出，不要包含任何额外文字：\n"
                "{\n"
                "  \"structured_data\": {},\n"
                "  \"reasoning_logic\": \"\"\n"
                "}"
            ),
            "llm_config": {
                "model_name": "qwen3-8b",
                "max_new_tokens": 3000,
                "temperature": 0.1,
                "top_p": 0.9,
                "context_window": 128000,
            },
        }