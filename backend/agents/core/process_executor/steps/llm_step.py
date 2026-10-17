# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_llm.py
# @Desc    : LLM推理型步骤基类 - ProcessLLMStep
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
ProcessLLMStep - LLM推理型步骤基类

特点：
- 两阶段 LLM 调用模式：阶段1（函数调用）→ 阶段2（JSON格式化）
- 支持配置驱动（通过 YAML 配置文件声明 prompt_template、llm_config、data_sources 等）
- 可调用 public_functions 作为函数
- 支持上下文变量解析

工作流程：
1. 加载步骤配置（YAML）
2. 执行 data_sources（数据源加载）
3. 构建 prompt（使用模板+变量解析）
4. 阶段1：调用 LLM 进行函数调用（可选）
5. 阶段2：调用 LLM 进行 JSON 格式化输出
6. 执行 post_process（后处理钩子）
7. 返回结果

使用场景：
- 需要 LLM 推理的复杂任务
- 需要多轮函数调用的任务
- 需要结构化输出的任务
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import ProcessStep


class ProcessLLMStep(ProcessStep):
    """LLM推理型步骤基类

    两阶段调用模式：
    - 阶段1（stage1）：函数调用阶段，LLM 可调用 public_functions 函数
    - 阶段2（stage2）：JSON格式化阶段，LLM 输出结构化结果

    子类实现：
        step_id: str                    步骤标识
        step_name: str                  步骤名称
        prompt_template: str            Prompt 模板
        system_prompt: str              系统提示词
        llm_config: dict                LLM 配置

    配置驱动（YAML）：
        schema:             Function Calling Schema
        prompt_template:    上下文格式化模板
        system_prompt:      系统提示词
        llm_config:         LLM 参数配置
        stage1_enabled:     是否启用阶段1（默认 false）
        data_sources:       数据源声明
        post_process:       后处理声明
    """

    # 子类配置
    prompt_template: str = ""
    system_prompt: str = ""
    llm_config: Dict[str, Any] = {}
    stage1_enabled: bool = False

    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行 LLM 推理型步骤

        Args:
            args: LLM 传入的参数（包含 instance_key, vehicle_suffix 等，具体参数名由 args_config 配置）
            context: Agent 实例

        Returns:
            str: JSON 格式的执行结果
        """
        import time as _time
        _t0 = _time.time()

        # 1. 加载步骤配置
        step_config = cls._get_effective_config(context)

        # 2. 执行数据源加载
        _t_ds = _time.time()
        data_sources_result = cls._execute_data_sources(step_config, args, context)

        # 3. 构建 prompt
        prompt = cls._build_prompt(step_config, args, context, data_sources_result)

        # 4. 获取 LLM 配置
        effective_llm_config = step_config.get('llm_config', cls.llm_config)
        effective_system_prompt = step_config.get('system_prompt', cls.system_prompt)

        stage1_system_prompt = step_config.get('stage1_system_prompt', '')


        # 初始化 debug messages 列表
        debug_messages = []
        
        # 添加 system prompt（阶段2使用的系统提示词）
        debug_messages.append({
            "role": "system",
            "content": effective_system_prompt
        })

        # 5. 阶段1：工具调用（可选）
        stage1_enabled = step_config.get('stage1_enabled', cls.stage1_enabled)
        stage1_result = None

        if stage1_enabled:
            stage1_system = stage1_system_prompt or effective_system_prompt
            
            _t_s1 = _time.time()
            # 阶段1必须成功，否则抛出异常
            stage1_result, stage1_messages = cls._execute_stage1(prompt, stage1_system,
                                                effective_llm_config, step_config,
                                                args, context, data_sources_result)
            if stage1_messages:
                debug_messages.extend(stage1_messages)
            
            # 验证阶段1结果
            if stage1_result is None:
                raise RuntimeError("Stage 1 返回 None，无法执行 Stage 2。阶段1必须成功返回推理结果。")

        # 6. 阶段2：JSON格式化（可选）
        stage2_enabled = step_config.get('stage2_enabled', True)
        stage2_input = stage1_result if stage1_enabled else prompt
        stage2_result = None
        stage2_messages = []

        if stage2_enabled:
            _t_s2 = _time.time()
            # Stage 2 根据 stage1 是否执行，采用不同的提示语
            stage2_result, stage2_messages = cls._execute_stage2(
                stage2_input, effective_system_prompt,
                effective_llm_config, step_config,
                args, context, data_sources_result,
                stage1_executed=stage1_enabled  # 传递 stage1 是否执行的标志
            )
            if stage2_messages:
                debug_messages.extend(stage2_messages)
        else:
            # 跳过 stage2，直接使用 stage1 结果或原始输入
            stage2_result = stage2_input

        # 7. 执行后处理
        _t_pp = _time.time()
        post_process_result = cls._execute_post_process(step_config, stage2_result or "", args,
                                                        context, data_sources_result)

        final_result = post_process_result or stage2_result
        
        # 构建包含 debug_info 的最终结果
        result_dict = {
            "type": "text",
            "content": final_result,
            "debug_info": {
                "messages": debug_messages,
                "step_id": cls.step_id,
                "step_name": cls.step_name,
                "stage1_enabled": stage1_enabled,
                "stage2_enabled": stage2_enabled,
            }
        }
        
        return result_dict

    @classmethod
    def _get_effective_config(cls, context: Any = None) -> Dict[str, Any]:
        """获取有效的步骤配置

        优先使用已加载的 _step_config，
        若无则调用 _load_step_config 加载。

        Args:
            context: Agent 实例

        Returns:
            dict: 合并后的步骤配置
        """
        config = getattr(cls, '_step_config', {})
        if config:
            return config

        # 触发配置加载
        cls._load_step_config(context)
        return getattr(cls, '_step_config', {}) or {}

    @classmethod
    def _build_prompt(cls, step_config: Dict[str, Any],
                       args: Dict[str, Any],
                       context: Any = None,
                       data_sources: Dict[str, Any] = None) -> str:
        """构建 prompt

        使用 prompt_template 模板，从 args 和 data_sources 中填充变量。
        若模板变量缺失，尝试通过 context_provider 解析业务变量。

        Args:
            step_config: 步骤配置
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 数据源结果

        Returns:
            str: 构建后的 prompt
        """
        template = step_config.get('prompt_template', cls.prompt_template)

        if not template:
            # 回退：使用 args 中的 query 字段
            return args.get('query', '')

        # 构建模板变量映射
        template_vars = dict(args)

        # 添加数据源结果
        if data_sources:
            for key, value in data_sources.items():
                if isinstance(value, str):
                    template_vars[key] = value
                elif isinstance(value, list):
                    template_vars[key] = '\n'.join(str(v) for v in value)
                else:
                    template_vars[key] = str(value)

        # 使用统一的变量解析补全缺失的业务变量
        template_vars = cls._resolve_variables(context, args, template_vars)

        # 尝试渲染模板
        try:
            return template.format(**template_vars)
        except (KeyError, ValueError):
            # 模板变量缺失时的降级处理
            return template

    @classmethod
    def _extract_tool_call(cls, result: dict, depth: int = 0) -> Optional[Dict[str, Any]]:
        """从 LLM 返回中递归提取 tool_call，支持任意嵌套深度。
        
        支持的格式：
        1. {"tool_call": {...}} - 单数格式
        2. {"tool_calls": [{...}]} - 复数数组格式（新增支持）
        3. {"content": '{"tool_call": {...}}'} - 嵌套在 content 中的 JSON 格式
        4. {"content": "{'tool_call': {...}}"} - 嵌套在 content 中的 Python dict 格式
        5. 多层嵌套：content 中的 JSON 包含 content，再包含 tool_call
        
        Args:
            result: LLM 返回的字典
            depth: 当前递归深度（防止无限循环）
            
        Returns:
            dict: tool_call 对象，如果未找到则返回 None
        """
        if depth > 10:  # 防止无限递归
            return None
        
        # 检查直接的 tool_call（单数格式）
        if result.get('tool_call'):
            return result['tool_call']
        
        # 新增：检查 tool_calls（复数数组格式）
        tool_calls = result.get('tool_calls')
        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            return tool_calls[0]  # 取第一个工具调用
        
        # 检查 content 中的嵌套结构
        content = result.get('content', '')
        if content and isinstance(content, str):
            parsed_dict = None
            
            # 尝试 JSON 解析（双引号）
            try:
                parsed_dict = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass
            
            # 如果 JSON 解析失败，尝试 Python dict 解析（单引号）
            if parsed_dict is None:
                try:
                    import ast
                    parsed_dict = ast.literal_eval(content)
                except (ValueError, SyntaxError):
                    pass
            
            # 如果解析成功且是 dict，递归检查
            if isinstance(parsed_dict, dict):
                return cls._extract_tool_call(parsed_dict, depth + 1)
        
        return None

    @classmethod
    def _execute_stage1(cls, prompt: str, system_prompt: str,
                         llm_config: Dict[str, Any],
                         step_config: Dict[str, Any],
                         args: Dict[str, Any],
                         context: Any = None,
                         data_sources: Dict[str, Any] = None) -> tuple:
        """执行阶段1：函数调用（多轮对话模式）

        LLM 可以调用 public_functions 函数来获取信息。
        支持多轮工具调用循环，直到 LLM 返回最终文本结果。

        Args:
            prompt: 构建后的 prompt
            system_prompt: 系统提示词
            llm_config: LLM 配置
            step_config: 步骤配置
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 数据源结果

        Returns:
            tuple: (str, list) 阶段1的结果文本 和 debug messages
        """
        debug_messages = []
        
        # 提前导入 NetworkError，确保在 try/except 块中可用
        from .step_exceptions import NetworkError
        
        try:
            from snail_avatar.backend.llm.deploy import LLMDeploy

            # 获取函数列表
            functions = cls._get_step_functions(context)

            # 调整 LLM 配置（阶段1使用 text 输出格式）
            stage1_config = dict(llm_config)
            stage1_config['output_format'] = 'text'

            # 创建 LLM 实例
            llm = LLMDeploy(cls.step_id, system_prompt, stage1_config)

            # 构建对话历史
            conversation_history = []
            conversation_history.append({"role": "user", "content": prompt})

            # 多轮工具调用循环（最多8轮，给LLM足够的推理空间）
            max_iterations = 8
            final_result = None

            for iteration in range(max_iterations):
                # 调用 LLM（支持函数调用）
                result = llm.generate_response("", conversation_history, tools=functions)

                # 检查是否为网络错误（结构化检测，同时匹配英文 "network" 和中文 "网络错误"）
                if isinstance(result, dict) and result.get("error_type") in ("network", "网络错误"):
                    raise NetworkError(result.get("content", "网络连接失败"))

                # 添加到 debug（仅第一轮添加 user message）
                if iteration == 0:
                    debug_messages.append({
                        "role": "user",
                        "content": prompt
                    })

                # 提取 tool_call（支持直接和嵌套两种格式）
                tool_call = cls._extract_tool_call(result)
                
                if tool_call:
                    tool_name = tool_call.get('name', '?')
                    
                    # 添加 assistant 消息到对话历史和 debug
                    conversation_history.append({
                        "role": "assistant",
                        "content": str(result)
                    })
                    debug_messages.append({
                        "role": "assistant",
                        "content": str(result)
                    })

                    # 执行函数调用
                    function_results = cls._execute_function_calls([tool_call], args, context)

                    # 将函数结果添加到对话历史
                    function_results_text = f"函数 {tool_call.get('name', '?')} 执行结果: {function_results[0]}"
                    conversation_history.append({
                        "role": "tool",
                        "content": function_results_text
                    })

                    # 添加到 debug
                    debug_messages.append({
                        "role": "tool",
                        "content": function_results[0]
                    })
                    
                    continue  # 继续下一轮迭代

                # 无工具调用：提取最终文本结果
                # 先检查是否为错误响应
                if isinstance(result, dict) and 'error' in result:
                    error_info = result.get('error', {})
                    error_msg = error_info.get('message', str(error_info)) if isinstance(error_info, dict) else str(error_info)
                    debug_messages.append({
                        "role": "assistant",
                        "content": f"LLM 返回错误: {error_msg}"
                    })
                    raise RuntimeError(f"Stage 1 LLM 返回错误: {error_msg}")
                
                # 新增：二次检查 tool_calls 格式（防止 _extract_tool_call 漏判）
                # 场景：_extract_tool_call 因某些边界情况未识别，但 result 中实际包含 tool_calls
                if isinstance(result, dict):
                    tool_calls_fallback = result.get('tool_calls')
                    if tool_calls_fallback and isinstance(tool_calls_fallback, list) and len(tool_calls_fallback) > 0:
                        tool_call_fb = tool_calls_fallback[0]
                        if tool_call_fb:
                            # 有 tool_calls 但 _extract_tool_call 未识别，尝试直接处理
                            debug_messages.append({
                                "role": "assistant",
                                "content": str(result)
                            })
                            function_results = cls._execute_function_calls([tool_call_fb], args, context)
                            function_results_text = f"函数 {tool_call_fb.get('name', '?')} 执行结果: {function_results[0]}"
                            conversation_history.append({
                                "role": "tool",
                                "content": function_results_text
                            })
                            debug_messages.append({
                                "role": "tool",
                                "content": function_results[0]
                            })
                            continue  # 继续下一轮迭代

                # 提取 content 作为最终结果
                if isinstance(result, dict):
                    content = result.get('content', str(result))
                    final_result = str(content)
                else:
                    final_result = str(result)
                
                # 检查结果是否为有效的推理内容（非错误信息、非空、非tool_call格式）
                if not final_result or 'error' in final_result.lower() or 'tool_call' in final_result.lower():
                    debug_messages.append({
                        "role": "assistant",
                        "content": final_result
                    })
                    raise RuntimeError(
                        f"Stage 1 返回结果异常: {final_result[:200]}。"
                        f"可能原因：LLM 未能完成推理循环，返回了工具调用格式而非最终文本。"
                    )
                
                debug_messages.append({
                    "role": "assistant",
                    "content": final_result
                })
                break

            # 如果达到最大迭代次数仍无结果，完善 fallback 处理
            if final_result is None:
                # 检查最后一次 LLM 响应是否为 tool_call 格式
                if isinstance(result, dict):
                    last_tool_call = cls._extract_tool_call(result)
                    if last_tool_call:
                        # LLM 在迭代上限内仍在请求工具调用，未能完成推理
                        debug_messages.append({
                            "role": "assistant",
                            "content": str(result)
                        })
                        raise RuntimeError(
                            f"Stage 1 达到最大迭代次数({max_iterations})，"
                            f"LLM 仍在请求工具调用: {last_tool_call.get('name', '?')}。"
                            f"可能需要增加迭代上限或优化 prompt 以减少工具调用次数。"
                        )
                    else:
                        # 非 tool_call 格式，提取内容作为 fallback
                        final_result = result.get('content', str(result))
                else:
                    final_result = f"阶段1达到最大迭代次数({max_iterations})，返回最后状态"

            return final_result, debug_messages

        except NetworkError:
            # 网络错误直接上抛，由上层统一处理重试
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            debug_messages.append({
                "role": "assistant",
                "content": f"阶段1执行失败: {str(e)}"
            })
            # 抛出异常，不掩盖错误
            raise RuntimeError(f"Stage 1 执行失败: {str(e)}") from e

    @classmethod
    def _execute_function_calls(cls, function_calls: List[Dict[str, Any]],
                                 args: Dict[str, Any],
                                 context: Any = None) -> List[str]:
        """执行函数调用列表

        Args:
            function_calls: 函数调用列表
            args: LLM 传入的参数
            context: Agent 实例

        Returns:
            list: 函数执行结果列表（所有元素都是字符串类型）
        """
        results = []

        for function_call in function_calls:
            function_name = function_call.get('name', '')
            function_args = function_call.get('arguments', '{}')

            # 执行函数
            struct_result, text_result = cls._execute_builtin_function(
                function_name, function_args, context
            )
            
            # 确保结果是字符串类型
            result_str = text_result if text_result else str(struct_result)
            results.append(str(result_str))

        return results

    @classmethod
    def _execute_stage2(cls, stage2_input: str, system_prompt: str,
                         llm_config: Dict[str, Any],
                         step_config: Dict[str, Any],
                         args: Dict[str, Any],
                         context: Any = None,
                         data_sources: Dict[str, Any] = None,
                         stage1_executed: bool = False) -> tuple:
        """执行阶段2：JSON格式化

        LLM 将输入整理为结构化的 JSON 输出。
        根据 stage1 是否执行，采用不同的提示语。

        Args:
            stage2_input: 阶段2的输入（Stage 1 的推理结果 或 原始 prompt）
            system_prompt: 系统提示词（JSON格式要求）
            llm_config: LLM 配置
            step_config: 步骤配置
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 数据源结果
            stage1_executed: Stage 1 是否执行（影响提示语）

        Returns:
            tuple: (str, list) JSON 格式的结果 和 debug messages
        """
        debug_messages = []
        
        # 提前导入 NetworkError，确保在 try/except 块中可用
        from .step_exceptions import NetworkError
        
        try:
            from snail_avatar.backend.llm.deploy import LLMDeploy

            # 调整 LLM 配置（阶段2使用 json 输出格式）
            stage2_config = dict(llm_config)
            stage2_config['output_format'] = 'json'

            # 创建 LLM 实例
            llm = LLMDeploy(cls.step_id, system_prompt, stage2_config)

            # 根据 stage1 是否执行，构建不同的 user prompt
            if stage1_executed:
                # Stage 1 已执行：Stage 2 只负责格式整理
                formatted_user_prompt = f"""以下是推理分析结果：

{stage2_input}

"""
            else:
                # Stage 1 未执行：Stage 2 是正常的推理步骤，不需要额外格式化指令
                # system prompt 已包含完整的任务说明和格式要求
                formatted_user_prompt = stage2_input

            # 构建对话历史
            conversation_history = [
                {"role": "user", "content": formatted_user_prompt}
            ]
            
            # 添加 user message 到 debug
            debug_messages.append({
                "role": "user",
                "content": formatted_user_prompt
            })

            # 调用 LLM
            import time as _time2
            _t_llm = _time2.time()
            result = llm.generate_response("", conversation_history, tools=None)

            # 检查是否为网络错误（结构化检测，同时匹配英文 "network" 和中文 "网络错误"）
            if isinstance(result, dict) and result.get("error_type") in ("network", "网络错误"):
                raise NetworkError(result.get("content", "网络连接失败"))

            # 解析结果
            if isinstance(result, dict):
                content = result.get('content', '')
                
                # 添加 assistant response 到 debug
                debug_messages.append({
                    "role": "assistant",
                    "content": str(content) if content else str(result)
                })
                
                if content:
                    if isinstance(content, dict):
                        result_json = json.dumps(content, ensure_ascii=False)
                        return result_json, debug_messages
                    # 尝试解析 JSON
                    try:
                        parsed = json.loads(content)
                        result_json = json.dumps(parsed, ensure_ascii=False)
                        return result_json, debug_messages
                    except json.JSONDecodeError as e:
                        # 降级 1: 尝试规则解析（处理 markdown 包裹、大括号提取等）
                        rule_formatted = cls._rule_format_extract(content)
                        if rule_formatted is not None:
                            return rule_formatted, debug_messages
                        # 降级 2: 构造最小合法 JSON 结构，将 content 放入 reasoning_logic
                        result_content = json.dumps({
                            "structured_data": {},
                            "reasoning_logic": str(content)
                        }, ensure_ascii=False)
                        return result_content, debug_messages

            # 默认返回空结果
            result_content = json.dumps({
                "structured_data": {},
                "reasoning_logic": "LLM 返回结果为空"
            }, ensure_ascii=False)
            
            debug_messages.append({
                "role": "assistant",
                "content": result_content
            })
            return result_content, debug_messages

        except NetworkError:
            # 网络错误直接上抛，由上层统一处理重试
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_content = json.dumps({
                "structured_data": {},
                "reasoning_logic": f"LLM 调用失败: {str(e)}"
            }, ensure_ascii=False)
            
            debug_messages.append({
                "role": "assistant",
                "content": error_content
            })
            return error_content, debug_messages

    @classmethod
    def _rule_format_extract(cls, raw_text: str) -> Optional[str]:
        """规则降级解析：当 LLM 返回非严格 JSON 时尝试提取结构化数据

        处理场景：
        1. LLM 输出被 ```json markdown 包裹
        2. JSON 前后夹杂解释文本
        3. JSON 被截断（末尾缺括号）
        4. 同时包含 structured_data 和 reasoning_logic 的自然语言

        Args:
            raw_text: LLM 返回的原始文本

        Returns:
            可被上层 json.loads 成功解析的 JSON 字符串；无法提取返回 None
        """
        import re

        if not raw_text or not isinstance(raw_text, str):
            return None

        text = raw_text.strip()

        # 策略 1: 尝试剥离 markdown 代码块
        md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL | re.IGNORECASE)
        if md_match:
            inner = md_match.group(1).strip()
            result = cls._try_parse_and_wrap(inner)
            if result is not None:
                return result
            text = inner  # markdown 剥离后继续尝试

        # 策略 2: 提取第一个 '{' 到最后一个 '}' 的 JSON 子串
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            candidate = text[start:end + 1]
            result = cls._try_parse_and_wrap(candidate)
            if result is not None:
                return result

        # 策略 3: 尝试从完整文本中用 _parse_json_content 解析
        try:
            from snail_avatar.backend.llm.deploy import LLMDeploy
            parsed = LLMDeploy._parse_json_content(text)
            if parsed is not None:
                result = cls._ensure_structured_wrapper(parsed)
                return result
        except Exception:
            pass

        return None

    @staticmethod
    def _try_parse_and_wrap(candidate: str) -> Optional[str]:
        """尝试解析 candidate 并包装为标准的 {structured_data, reasoning_logic} 格式"""
        import json as _json

        # 先用 json.loads 尝试
        data = None
        try:
            data = _json.loads(candidate)
        except Exception:
            # 再用 deploy 的稳健解析
            try:
                from snail_avatar.backend.llm.deploy import LLMDeploy
                data = LLMDeploy._parse_json_content(candidate)
            except Exception:
                pass

        if data is None:
            return None

        return ProcessLLMStep._ensure_structured_wrapper(data)

    @staticmethod
    def _ensure_structured_wrapper(data: Any) -> str:
        """将任意解析出的数据包装为标准的 {structured_data, reasoning_logic} 格式"""
        import json as _json

        if isinstance(data, dict):
            # 已经是标准格式
            if "structured_data" in data or "reasoning_logic" in data:
                return _json.dumps(data, ensure_ascii=False)
            # 不是标准格式，把整个 dict 作为 structured_data
            return _json.dumps({
                "structured_data": data,
                "reasoning_logic": ""
            }, ensure_ascii=False)
        else:
            return _json.dumps({
                "structured_data": data if data else {},
                "reasoning_logic": ""
            }, ensure_ascii=False)

    @classmethod
    def _save_to_process_data(cls, step_id: str, sandbox, context, args) -> None:
        """将 LLM 步骤结果写入 process_data"""
        if sandbox is None:
            return

        # 检查 yaml 配置是否禁用 process_data 写入
        try:
            step_config = cls._get_effective_config(context)
            if not step_config.get('save_to_process_data', True):
                return
        except Exception:
            pass

        full_step_id = cls._get_full_step_id(step_id, context, args)

        try:
            step_result = sandbox.get_step_result(full_step_id)
            if step_result and isinstance(step_result, dict):
                # step_result 是 _save_to_sandbox 存入的已解析 dict
                # 格式为 {"structured_data": {...}, "reasoning_logic": "..."}
                # 直接读取字段，无需再解析 content
                structured_data = step_result.get('structured_data', {})
                if structured_data:
                    sandbox.set_process_data(f"{full_step_id}_structured", structured_data)
                # 保存 reasoning_logic
                reasoning_logic = step_result.get('reasoning_logic', '')
                if reasoning_logic:
                    sandbox.set_process_data(f"{full_step_id}_reasoning", reasoning_logic)
        except Exception:
            pass
