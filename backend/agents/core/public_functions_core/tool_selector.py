# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : tool_selector.py
# @Desc    : 两轮式工具选择器（方案 3）—— Phase 1 通用实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
两轮式"工具目录 → 工具详情"工具选择器（方案 3）

【设计目标】
将 Phase 1 工具目录选择逻辑从具体 Agent 中抽离出来，供所有需要
function calling 的子 Agent 复用。

【使用方式】
    from snail_avatar.backend.agents.core.public_functions_core.tool_selector import select_tools

    # 在 send_message() 的顶部，Phase 1 工具选择：
    selected_tools_list, phase1_usage = select_tools(
        llm_instance=self.llm,
        registry=self._registry,
        user_input=user_input,
        agent_id=AGENT_ID,
        all_tools_list=self._tools_list,
        catalog_prompt=None,          # 可选：覆盖默认 Prompt（从 YAML 读取）
    )

    # 然后 Phase 2 用 selected_tools_list 调用 LLM function calling 循环

【返回值】
    (selected_tools_list, phase1_usage_info)
    - selected_tools_list:  Phase 2 要传给 LLM 的工具 schema 列表
    - phase1_usage_info:    Phase 1 这一轮 LLM 调用的 token 使用情况（dict）

【内部流程】
    1. 从 registry 获取工具短目录（名称+一句话描述）
    2. 构造 Phase 1 专用临时消息（不污染用户对话历史）
    3. 调用 LLM 做工具选择题（这一轮 tools=[]，不发完整 schema）
    4. 解析 LLM 输出 → 工具名列表
       - "NONE" 或空 → 空列表（不需要工具）
       - 逗号 / 中文逗号 / 顿号 / 空白 / 换行 都能分隔
    5. 只保留"已注册的工具名"，过滤掉 LLM 胡编的名字
    6. 任何异常 → 回退到"发全部工具"（保证功能不中断）
"""

import re as _re
from typing import Any, Dict, List, Optional, Tuple

from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger

# =============================================================================
# 默认 Prompt（可被各 Agent 的 YAML 配置覆盖）
# =============================================================================

DEFAULT_CATALOG_PROMPT = (
    "你是一个工具选择器。你的任务是：根据用户的问题，从下面的工具目录中"
    "选择最可能需要调用的工具。请只返回工具名称，多个工具用英文逗号分隔。"
    "如果不需要任何工具，回答：NONE。不要输出任何其他文字，不要解释。"
    "如果不确定，宁多勿漏，把可能相关的工具都列出来。\n\n"
    "【工具目录】\n{catalog}"
)


# =============================================================================
# 内部辅助：解析 LLM 输出 → 工具名列表
# =============================================================================

def _parse_tool_names(text: str, registry: Any) -> List[str]:
    """
    解析 Phase 1 LLM 的输出文本，返回已注册的工具名列表。

    解析规则（按优先级）：
      1. "NONE"（不区分大小写）→ 返回空列表
      2. 空字符串 → 返回空列表
      3. 用以下分隔符切分：英文逗号 , 中文逗号 ， 顿号 、 空白 换行
      4. 过滤空白项
      5. 只保留 registry.has_function(name) == True 的项

    Args:
        text:     LLM 输出的原始文本
        registry: FunctionRegistry 实例（需要实现 has_function()）

    Returns:
        List[str]: 已注册的工具名列表（可能为空）
    """
    if not text:
        return []

    text = text.strip()
    if not text:
        return []

    # 规则 1："NONE" → 不需要任何工具
    if text.upper() == "NONE":
        return []

    # 规则 3-4：多分隔符切分 + 过滤空白
    raw_names = _re.split(r"[,，、\s]+", text)
    raw_names = [n.strip() for n in raw_names if n.strip()]

    # 规则 5：只保留已注册的工具
    valid_names = [n for n in raw_names if registry.has_function(n)]
    return valid_names


# =============================================================================
# 主函数：select_tools
# =============================================================================

def _format_history_for_phase1(conversation_history: Any, max_chars: int = 4000) -> str:
    """将对话历史格式化为 Phase 1 LLM 可理解的紧凑文本。

    Args:
        conversation_history: 消息列表，每条为 {"role": "user"|"assistant", "content": "..."}
        max_chars: 历史文本的最大字符数（超过则从最早开始截断）

    Returns:
        格式化后的历史文本，如：
        [user]: 你好
        [assistant]: 你好，请问需要什么帮助？
    """
    if not conversation_history:
        return ""

    lines = []
    # 从新到旧排列，保证保留的是最近的
    for msg in reversed(conversation_history):
        role = msg.get("role", "?")
        content = msg.get("content", "") or ""
        if role not in ("user", "assistant"):
            continue
        # 单条消息截断到 500 字符，避免工具返回的长文本撑爆
        content_short = content[:500] if len(content) > 500 else content
        lines.append(f"[{role}]: {content_short}")

    # 反转回正常顺序
    lines.reverse()

    result = "\n".join(lines)

    # 整体截断：从最早开始切掉
    if len(result) > max_chars:
        result = result[-max_chars:]

    return result


def select_tools(
    llm_instance: Any,
    registry: Any,
    user_input: str,
    agent_id: str,
    all_tools_list: List[Dict[str, Any]],
    catalog_prompt: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Phase 1：两轮式工具选择器。

    让 LLM 从简短的工具目录中挑出可能需要的工具，Phase 2 只把
    挑中工具的完整 schema 发给 LLM，从而减少 token 消耗。

    Args:
        llm_instance:        LLM 实例，需实现 generate_response(system_prompt,
                              conversation_history, tools_list) 接口
        registry:            FunctionRegistry 实例，需实现
                              get_tools_catalog() / has_function(name) /
                              get_tools_by_names(names) 接口
        user_input:          用户输入的原始问题
        agent_id:            当前 Agent 的 ID（用于日志记录）
        all_tools_list:      所有工具的完整 schema 列表（作为兜底回退）
        catalog_prompt:      可选，自定义 Phase 1 Prompt（从 YAML 读取时传入）。
                              必须包含 "{catalog}" 占位符用于插入工具目录。
                              为 None 时使用 DEFAULT_CATALOG_PROMPT。
        conversation_history: 可选，完整对话历史（[{role, content}, ...]）。
                              传入后 Phase 1 LLM 能看到上下文，
                              解决延续性指代短句（如"按此修改"）因缺少历史而误判 NONE 的问题。

    Returns:
        tuple: (selected_tools_list, phase1_usage_info)
            - selected_tools_list: Phase 2 传给 LLM 的工具 schema 列表
            - phase1_usage_info:   Phase 1 的 token 使用信息（dict，可能为空）

    【兜底策略】
    Phase 1 任何阶段失败（LLM 调用异常 / 解析失败）：
    自动回退到"发全部工具"，保证 Phase 2 至少能正常工作。
    """
    # 默认：发全部工具（即原有行为，作为初始值和兜底值）
    selected_tools_list = all_tools_list

    # Phase 1 整体 try/except：任何失败自动回退
    try:
        # 确定 Prompt（自定义优先，否则默认）
        prompt_template = catalog_prompt if catalog_prompt else DEFAULT_CATALOG_PROMPT

        # ① 生成工具目录（短版）
        catalog_text = registry.get_tools_catalog()

        # ② 构造 Phase 1 专用临时消息（不污染用户对话历史）
        catalog_system = prompt_template.format(catalog=catalog_text)
        catalog_history = [
            {"role": "system", "content": catalog_system},
        ]

        # ②a 注入对话历史（如果有）——让 Phase 1 能理解上下文指代
        history_text = _format_history_for_phase1(conversation_history) if conversation_history else ""
        if history_text:
            catalog_history.append({"role": "user", "content": f"【历史对话上下文】\n{history_text}"})

        # ②b 当前用户输入
        catalog_history.append({"role": "user", "content": user_input})

        # ③ 调用 LLM（这一轮不发任何工具 schema）
        AgentMessageLogger.log(
            agent_id, "agent_receive",
            f"Phase 1：工具目录选择（目录 {len(catalog_text)} 字符，"
            f"工具总数 {len(all_tools_list)} 个"
            f"{', 含对话历史' if history_text else ''}）",
            tools_catalog=catalog_text,
        )

        catalog_response = llm_instance.generate_response(
            "",
            catalog_history,
            [],  # Phase 1：不发工具 schema
        )

        # ④ Phase 1 token 使用信息
        phase1_usage = catalog_response.get("usage") or {}

        # 记录 Phase 1 token（独立醒目消息，供 agent_message_panel 渲染）
        _p1_in = int(phase1_usage.get("input_tokens", 0))
        _p1_out = int(phase1_usage.get("output_tokens", 0))
        _p1_tot = int(phase1_usage.get("total_tokens", 0))
        AgentMessageLogger.log(
            agent_id, "system",
            f"Phase 1 Token: 输入 {_p1_in} | 输出 {_p1_out} | 总计 {_p1_tot}",
            token_phase="phase1",
            input_tokens=_p1_in,
            output_tokens=_p1_out,
            total_tokens=_p1_tot,
        )

        # 先记录 Phase 1 的输出（方便调试）
        AgentMessageLogger.log(
            agent_id, "tool_call",
            f"Phase 1 选择结果: {catalog_response.get('content', '')}"
        )

        # ⑤ 解析工具名
        tool_names_text = catalog_response.get("content", "").strip()
        valid_names = _parse_tool_names(tool_names_text, registry)

        if not valid_names:
            # "NONE" / 空 / 无有效工具名 → Phase 2 以 0 个工具模式运行
            selected_tools_list = []
            AgentMessageLogger.log(
                agent_id, "tool_call",
                "Phase 1 判断不需要工具，Phase 2 将以 0 个工具模式运行"
            )
        else:
            # 有有效工具名 → 只取这些工具的完整 schema
            selected_tools_list = registry.get_tools_by_names(valid_names)
            AgentMessageLogger.log(
                agent_id, "tool_call",
                f"Phase 2 将使用 {len(valid_names)} 个工具: {', '.join(valid_names)}"
            )

        return selected_tools_list, phase1_usage

    except Exception as e:
        # Phase 1 整体失败 → 回退到"发全部工具"
        AgentMessageLogger.log(
            agent_id, "system",
            f"Phase 1 工具选择失败，回退到全部工具模式: {e}"
        )
        return all_tools_list, {}


# =============================================================================
# 便捷函数：从 YAML 配置读取自定义 Prompt
# =============================================================================

def get_catalog_prompt_from_config(config: Dict[str, Any]) -> str:
    """
    从 Agent 的 YAML 配置字典中读取自定义 Phase 1 Prompt。

    约定的配置字段名: tool_catalog_prompt
    未配置时返回 DEFAULT_CATALOG_PROMPT。

    用法示例:
        config = yaml.safe_load(open("config/my_agent.yaml", "r", encoding="utf-8"))
        my_prompt = get_catalog_prompt_from_config(config)
    """
    return config.get("tool_catalog_prompt", DEFAULT_CATALOG_PROMPT)