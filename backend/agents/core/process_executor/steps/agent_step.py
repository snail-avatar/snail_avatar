# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_agent.py
# @Desc    : Agent调用型步骤基类 - ProcessAgentStep
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
ProcessAgentStep - Agent调用型步骤基类

特点：
- 通过 agent.send_message(query) 调用子 agent 获取推理结果
- 使用 result_formatter 将结果整理为结构化数据+推理逻辑格式
- 支持配置驱动（通过 YAML 配置文件声明 agent_id、formatter_config）
- 不具备声明 public function 的能力（区别于 LLM 步骤）

使用场景：
- 需要调用专家 agent（如法规查询、优化方案分析）
- 需要调用工作流 agent（如映射关系分析、校核计算）
- 需要子 agent 进行多轮推理的复杂任务
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import ProcessStep


class ProcessAgentStep(ProcessStep):
    """Agent调用型步骤基类

    工作模式：
    1. 从配置获取 agent_type（calculator/expert/fix）
    2. 根据 agent_type 获取 agent_id：
       - calculator/expert: 从 sandbox._agent_type_mappings 按类型查找
       - fix: 直接使用 YAML 配置中的 agent_id
    3. 构建 query（查询内容，可使用 prompt_template 模板）
    4. 调用子 agent.send_message(query) 获取结果
    5. 使用 result_formatter 格式化结果为 {structured_data, reasoning_logic}
    6. 返回标准化结果

    子类实现：
        step_id: str                    步骤标识
        step_name: str                  步骤名称
        agent_type: str                 Agent 类型（calculator/expert/fix）
        agent_id: str                   子 agent 标识（fix 类型必填）
        prompt_template: str            查询模板（可选）
        formatter_config: dict          格式化配置（可选）

    配置驱动：
        YAML 文件中声明 agent_type、agent_id、prompt_template、formatter_config
        运行时自动加载并合并
    """

    # 子类必须指定
    agent_type: str = ""  # "calculator" | "expert" | "fix"
    agent_id: str = ""
    prompt_template: str = ""
    formatter_config: Dict[str, Any] = {}

    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行 Agent 调用型步骤

        Args:
            args: LLM 传入的参数（包含 instance_key, vehicle_suffix 等，具体参数名由 args_config 配置）
            context: Agent 实例

        Returns:
            str: 格式化后的 JSON 字符串
        """
        debug_messages = []
        
        # 1. 加载步骤配置
        step_config = cls._step_config or {}
        
        # 2. 根据 agent_type 获取 agent_id
        cls.agent_type = step_config.get('agent_type', cls.agent_type)
        if cls.agent_type == 'fix':
            # fix 类型：直接使用 YAML 配置中的 agent_id
            cls.agent_id = step_config.get('agent_id', '')
        elif cls.agent_type in ('calculator', 'expert'):
            # calculator/expert 类型：从 sandbox 按类型查找
            sandbox_agent_id = cls._get_agent_id_from_sandbox(args, context)
            if sandbox_agent_id:
                cls.agent_id = sandbox_agent_id
        else:
            # 未指定类型，尝试从 sandbox 查找（兼容旧逻辑）
            sandbox_agent_id = cls._get_agent_id_from_sandbox(args, context)
            if sandbox_agent_id:
                cls.agent_id = sandbox_agent_id
            else:
                cls.agent_id = step_config.get('agent_id', '')
        
        # 3. 执行数据源加载（如果配置了 data_sources）
        data_sources_result = cls._execute_data_sources(step_config, args, context)
        
        # 3. 构建模板变量（合并 args + data_sources + 配置中的静态变量）
        template_vars = dict(args) if args else {}
        
        # 添加 data_sources 结果
        if data_sources_result:
            for key, value in data_sources_result.items():
                template_vars[key] = value
        
        # 添加配置中的静态变量（如 task_prompt）
        task_prompt = step_config.get('task_prompt', '')
        if task_prompt:
            template_vars['task_prompt'] = task_prompt

        # 4. 构建查询内容
        query = cls._build_query(template_vars, context)
        
        # 添加 user 消息到 debug
        debug_messages.append({
            "role": "user",
            "content": query
        })

        if not cls.agent_id:
            error_result = json.dumps({
                "structured_data": {},
                "reasoning_logic": "错误：未配置 agent_id"
            }, ensure_ascii=False)
            debug_messages.append({
                "role": "assistant",
                "content": error_result
            })
            return {
                "type": "text",
                "content": error_result,
                "debug_info": {
                    "messages": debug_messages,
                    "step_id": cls.step_id,
                    "step_name": cls.step_name,
                }
            }

        # 调用子 agent
        # 从配置获取 query_mode（默认 auto）
        query_mode = step_config.get('query_mode', 'auto')
        # 从数据源结果获取 pipeline_config（如果有）
        pipeline_config = data_sources_result.get('pipeline_config') if data_sources_result else None
        raw_result = cls._call_sub_agent(
            cls.agent_id, query, args, context,
            query_mode=query_mode,
            pipeline_config=pipeline_config
        )

        if raw_result is None:
            error_result = json.dumps({
                "structured_data": {},
                "reasoning_logic": f"错误：调用子 agent '{cls.agent_id}' 失败"
            }, ensure_ascii=False)
            debug_messages.append({
                "role": "assistant",
                "content": error_result
            })
            return {
                "type": "text",
                "content": error_result,
                "debug_info": {
                    "messages": debug_messages,
                    "step_id": cls.step_id,
                    "step_name": cls.step_name,
                }
            }

        # 添加 agent 原始响应到 debug
        debug_messages.append({
            "role": "assistant",
            "content": str(raw_result)
        })

        # 格式化结果
        formatted_result = cls._format_result(raw_result, args, context)
        
        # 添加格式化结果到 debug
        debug_messages.append({
            "role": "assistant",
            "content": f"格式化结果: {formatted_result}"
        })

        # 在执行 post_process 之前，先将结果保存到 sandbox
        # 这样 post_process 中的函数（如 save_to_process_data）才能读取到步骤结果
        temp_result_dict = {
            "type": "text",
            "content": formatted_result,
        }
        cls._save_to_sandbox(cls.step_id, temp_result_dict, context, args)

        # 5. 执行 post_process（后处理钩子）
        step_config = cls._step_config or {}
        post_process_result = cls._execute_post_process(
            step_config, formatted_result, args, context, data_sources_result
        )
        final_result = post_process_result or formatted_result

        return {
            "type": "text",
            "content": final_result,
            "debug_info": {
                "messages": debug_messages,
                "step_id": cls.step_id,
                "step_name": cls.step_name,
                "agent_id": cls.agent_id,
            }
        }

    @classmethod
    def _get_agent_id_from_sandbox(cls, args: Dict[str, Any], context: Any = None) -> str:
        """从 ProcessSandbox 按 agent_type 获取当前步骤的 agent_id

        查找顺序：
        1. 从 sandbox._agent_type_mappings 按 agent_type + loop_item 查找
        2. 按 agent_type + __default__ 查找
        3. 按 agent_type 获取任意值

        Args:
            args: LLM 传入的参数（用于获取 loop_item）
            context: Agent 实例（用于获取 sandbox）

        Returns:
            str: agent_id，未找到返回空字符串
        """
        # 获取 sandbox
        sandbox = cls._get_sandbox(context, args)
        if not sandbox:
            return ""

        # 获取当前 loop_item（如 "动力性"、"经济性"）
        loop_item = ""
        if args:
            # 尝试从常用字段获取 loop_item
            loop_item = args.get("professional_category", "") or args.get("loop_item", "")

        # 从 sandbox 按 agent_type 查找 agent_id
        return sandbox.get_agent_id_by_type(cls.agent_type, loop_item)

    @classmethod
    def _build_query(cls, args: Dict[str, Any], context: Any = None) -> str:
        """构建查询内容

        优先使用 YAML 配置中的 prompt_template，
        若无配置则使用子类的 prompt_template 属性，
        最终回退到 args 中的 query 字段。
        若模板变量缺失，尝试通过 context_provider 解析业务变量。

        Args:
            args: LLM 传入的参数
            context: Agent 实例

        Returns:
            str: 构建后的查询内容
        """
        # 从配置加载 prompt_template
        step_config = getattr(cls, '_step_config', {}) or {}
        config_template = step_config.get('prompt_template', '')

        template = config_template or cls.prompt_template

        if template:
            # 使用模板渲染
            template_vars = dict(args)

            # 使用统一的变量解析补全缺失的业务变量
            template_vars = cls._resolve_variables(context, args, template_vars)

            try:
                formatted_query = template.format(**template_vars)
                return formatted_query
            except KeyError:
                # 如果模板变量不存在，使用原始模板
                return template

        # 回退：使用 args 中的 query 字段
        return args.get('query', '')

    @classmethod
    def _call_sub_agent(cls, agent_id: str, query: str,
                        args: Dict[str, Any], context: Any = None,
                        query_mode: str = "auto",
                        pipeline_config: Dict[str, Any] = None) -> Optional[str]:
        """调用子 agent

        Args:
            agent_id: 子 agent 标识
            query: 查询内容
            args: LLM 传入的参数
            context: Agent 实例（包含 _agent_map 等）
            query_mode: 查询模式（"auto" 或 "pipeline"）
            pipeline_config: Pipeline 模式下的查询配置

        Returns:
            str or None: 子 agent 的响应文本
        """
        # 方法1: 尝试从 context 获取子 agent（如果有的话）
        target_agent = None
        if context is not None:
            agent_map = getattr(context, '_agent_map', {})
            
            if agent_map:
                target_agent = agent_map.get(agent_id)
                if target_agent is None:
                    for name, agent in agent_map.items():
                        if name == agent_id or (hasattr(agent, 'agent_id') and agent.agent_id == agent_id):
                            target_agent = agent
                            break

        # 方法2: 通过 AgentRouter 获取子 agent（主要方式）
        if target_agent is None:
            try:
                from snail_avatar.backend.agents.core.tools.routing.agent_router import get_agent_router
                router = get_agent_router()
                target_agent = router.get_agent(agent_id)
            except Exception as e:
                pass

        if target_agent is None:
            return None

        # 提前导入 NetworkError，确保在 try/except 块中可用
        from .step_exceptions import NetworkError

        try:
            # 调用子 agent（传递 query_mode 和 pipeline_config）
            result = target_agent.send_message(
                query,
                query_mode=query_mode,
                pipeline_config=pipeline_config
            )
            
            # 处理不同类型的返回值
            if isinstance(result, tuple):
                # tuple 结构: (response_text, usage_info, structured_data)
                if len(result) > 0:
                    content = result[0]
                    # 检查 structured_data 中的网络错误标记
                    if len(result) > 2 and result[2] is not None:
                        structured_data = result[2]
                        if isinstance(structured_data, dict) and structured_data.get("error_type") == "network":
                            raise NetworkError(structured_data.get("content", "网络连接失败"))
                    # 检查 content 本身是否为网络错误
                    if isinstance(content, dict) and content.get("error_type") == "network":
                        raise NetworkError(content.get("content", "网络连接失败"))
                    if isinstance(content, str):
                        # 尝试从字符串中提取 JSON
                        json_str = cls._extract_json_from_text(content)
                        return json_str
                    elif isinstance(content, dict):
                        return json.dumps(content, ensure_ascii=False)
                    return str(content)
                return None
            elif isinstance(result, dict):
                # 检查是否为网络错误的结构化返回
                if result.get("error_type") == "network":
                    raise NetworkError(result.get("content", "网络连接失败"))
                content = result.get('content', str(result))
                if isinstance(content, str):
                    json_str = cls._extract_json_from_text(content)
                    return json_str
                return str(content)
            elif isinstance(result, str):
                json_str = cls._extract_json_from_text(result)
                return json_str
            return str(result)
        except NetworkError:
            # 网络错误直接上抛，由上层统一处理重试
            raise
        except Exception as e:
            return None

    @classmethod
    def _extract_json_from_text(cls, text: str) -> str:
        """从文本中提取 JSON 字符串

        Args:
            text: 可能包含 JSON 的文本

        Returns:
            str: 提取的 JSON 字符串
        """
        import json
        
        if not text:
            return ""
        
        # 尝试直接解析
        try:
            json.loads(text)
            return text
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 尝试从文本中提取 JSON
        try:
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = text[start_idx:end_idx]
                json.loads(json_str)  # 验证是否为有效 JSON
                return json_str
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 如果无法提取 JSON，返回原始文本
        return text

    @classmethod
    def _format_result(cls, raw_result: str, args: Dict[str, Any],
                        context: Any = None) -> str:
        """使用 result_formatter 格式化结果

        Args:
            raw_result: 原始结果文本
            args: LLM 传入的参数
            context: Agent 实例

        Returns:
            str: 格式化后的 JSON 字符串
        """
        # 获取 formatter_config
        step_config = getattr(cls, '_step_config', {}) or {}
        config_formatter = step_config.get('formatter_config', {})

        formatter_config = config_formatter or cls.formatter_config

        try:
            from snail_avatar.backend.agents.core.tools.LLM_tools import get_result_formatter
            formatter = get_result_formatter()

            formatted = formatter.format(
                raw_result,
                formatter_config=formatter_config,
                step_id=cls.step_id,
            )
            return formatted
        except Exception as e:
            # 格式化失败时的降级处理
            return json.dumps({
                "structured_data": {},
                "reasoning_logic": f"格式化失败: {str(e)}\n原始结果: {raw_result}"
            }, ensure_ascii=False)

    @classmethod
    def _save_to_process_data(cls, step_id: str, sandbox, context, args) -> None:
        """Agent 步骤不需要自动写入 process_data，由 post_process 中的公共函数处理"""
        pass
