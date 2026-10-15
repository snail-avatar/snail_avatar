# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_process.py
# @Desc    : 直接执行型步骤基类 - ProcessProcessStep
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
ProcessProcessStep - 直接执行型步骤基类

特点：
- 不经过 LLM 推理或子 Agent 调用
- 直接执行数据操作（验证、转换、保存等）
- 通过 execution_pipeline 配置驱动执行流水线
- 每个流水线节点调用一个 public function

工作流程：
1. 加载步骤配置（YAML）
2. 从 execution_pipeline 读取执行顺序
3. 按顺序调用每个 public function
4. 累积执行结果
5. 返回最终结果

使用场景：
- 数据验证步骤
- 数据转换步骤
- 结果保存步骤
- 不需要 LLM 推理的纯数据操作
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import ProcessStep


class ProcessProcessStep(ProcessStep):
    """直接执行型步骤基类

    工作模式：
    1. 从配置获取 execution_pipeline（执行流水线）
    2. 流水线是一组按顺序执行的 public function 节点
    3. 每个节点从前置节点获取输入，输出传递给后续节点
    4. 最终结果是最后一个节点的输出

    配置驱动（YAML）：
        execution_pipeline: 执行流水线配置
            - function: 节点调用的 public function 名称
              args_mapping: 参数映射（支持 $prev、$args、$memory_db 等变量）
              output: 节点输出的键名（可选）
        data_sources: 可选的数据源预加载
        post_process: 可选的后处理钩子

    使用示例：
        execution_pipeline:
          - function: "vts_ssts_validator"
            args_mapping:
              operation: "validate_targets"
              targets: "$args.targets"
            output: "validation_result"
          - function: "save_mapping_to_controller"
            output: "save_result"
    """

    # 可选的子类配置
    execution_pipeline: List[Dict[str, Any]] = []

    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """执行直接型步骤

        Args:
            args: LLM 传入的参数
            context: Agent 实例

        Returns:
            str: JSON 格式的执行结果
        """
        debug_messages = []
        
        # 1. 加载步骤配置
        step_config = cls._get_effective_config(context)

        # 添加初始信息到 debug
        debug_messages.append({
            "role": "user",
            "content": f"开始执行步骤: {cls.step_name}"
        })

        # 2. 执行数据源预加载（如果有）
        data_sources_result = cls._execute_data_sources(step_config, args, context)

        # 3. 获取执行流水线
        pipeline_config = step_config.get('execution_pipeline', cls.execution_pipeline)

        if not pipeline_config:
            # 无流水线配置，直接返回成功
            result_content = json.dumps({
                "structured_data": {},
                "reasoning_logic": "步骤执行成功（无操作）"
            }, ensure_ascii=False)
            
            debug_messages.append({
                "role": "assistant",
                "content": result_content
            })
            
            return {
                "type": "text",
                "content": result_content,
                "debug_info": {
                    "messages": debug_messages,
                    "step_id": cls.step_id,
                    "step_name": cls.step_name,
                }
            }

        # 4. 按顺序执行流水线
        pipeline_results = {}
        last_result = None

        for node_config in pipeline_config:
            function_name = node_config.get('function', '')
            output_key = node_config.get('output', '')
            args_mapping = node_config.get('args_mapping', {})

            if not function_name:
                continue

            # 构建变量解析上下文
            resolve_context = {
                'args': args,
                'prev': last_result,
                'results': pipeline_results,
                'data_sources': data_sources_result,
            }

            # 解析参数
            resolved_args = cls._resolve_node_args(args_mapping, args, context, resolve_context)

            # 用统一变量解析补全缺失的公共变量
            resolved_args = cls._resolve_variables(context, args, resolved_args)

            # 执行节点
            try:
                node_result = cls._execute_node(function_name, resolved_args, context)

                # 保存结果
                if output_key:
                    pipeline_results[output_key] = node_result

                last_result = node_result

            except Exception as e:
                # 节点执行失败
                error_result = {
                    "error": f"节点 {function_name} 执行失败: {str(e)}",
                    "is_error": True
                }
                if output_key:
                    pipeline_results[output_key] = error_result
                last_result = error_result

                # 出错时可以选择中断或继续
                break

        # 5. 执行后处理（如果有）
        final_result = cls._build_final_result(last_result, pipeline_results)

        post_process_result = cls._execute_post_process(step_config, final_result,
                                                        args, context, data_sources_result)

        final_content = post_process_result or final_result
        
        # 添加最终结果到 debug
        debug_messages.append({
            "role": "assistant",
            "content": final_content
        })

        return {
            "type": "text",
            "content": final_content,
            "debug_info": {
                "messages": debug_messages,
                "step_id": cls.step_id,
                "step_name": cls.step_name,
            }
        }

    @classmethod
    def _get_effective_config(cls, context: Any = None) -> Dict[str, Any]:
        """获取有效的步骤配置"""
        config = getattr(cls, '_step_config', {})
        if config:
            return config

        cls._load_step_config(context)
        return getattr(cls, '_step_config', {}) or {}

    @classmethod
    def _resolve_node_args(cls, args_mapping: Dict[str, Any],
                            args: Dict[str, Any],
                            context: Any,
                            resolve_context: Dict[str, Any]) -> Dict[str, Any]:
        """解析节点参数映射

        Args:
            args_mapping: 参数映射配置
            args: LLM 传入的参数
            context: Agent 实例
            resolve_context: 解析上下文

        Returns:
            dict: 解析后的参数
        """
        resolved = {}

        for key, value in args_mapping.items():
            if isinstance(value, str) and value.startswith('$'):
                resolved[key] = cls._resolve_node_variable(value, args, context, resolve_context)
            else:
                resolved[key] = value

        return resolved

    @classmethod
    def _resolve_node_variable(cls, var_path: str, args: Dict[str, Any],
                                context: Any,
                                resolve_context: Dict[str, Any]) -> Any:
        """解析节点变量引用

        支持：
        - $args.xxx: LLM 传入参数
        - $prev: 上一个节点的结果
        - $results.xxx: 之前节点的命名结果
        - $memory_db: memory_db 实例
        - $context: Agent 实例
        - $data_sources.xxx: 数据源结果

        Args:
            var_path: 变量路径
            args: LLM 传入的参数
            context: Agent 实例
            resolve_context: 解析上下文

        Returns:
            变量值
        """
        if not var_path.startswith('$'):
            return var_path

        path = var_path[1:]

        # $prev 特殊处理
        if path == 'prev':
            return resolve_context.get('prev')

        # $args.xxx
        if path.startswith('args.'):
            key = path[5:]
            return args.get(key)

        # $results.xxx
        if path.startswith('results.'):
            key = path[8:]
            results = resolve_context.get('results', {})
            return results.get(key)

        # $data_sources.xxx
        if path.startswith('data_sources.'):
            key = path[13:]
            data_sources = resolve_context.get('data_sources', {})
            return data_sources.get(key)

        # $memory_db
        if path == 'memory_db':
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            return get_memory_db()

        # $context
        if path == 'context':
            return context

        return var_path

    @classmethod
    def _execute_node(cls, function_name: str, args: Dict[str, Any],
                       context: Any = None) -> Any:
        """执行单个流水线节点

        Args:
            function_name: public function 名称
            args: 节点参数
            context: Agent 实例

        Returns:
            节点执行结果
        """
        from snail_avatar.backend.agents.core.public_functions import get_public_function

        pub_fn_cls = get_public_function(function_name)
        if pub_fn_cls is None:
            raise ValueError(f"未找到 public function: {function_name}")

        return pub_fn_cls.execute(args, context)

    @classmethod
    def _build_final_result(cls, last_result: Any,
                               pipeline_results: Dict[str, Any]) -> str:
        """构建最终结果

        将流水线结果整理为标准 JSON 格式。

        Args:
            last_result: 最后一个节点的结果
            pipeline_results: 所有命名结果

        Returns:
            str: JSON 格式的最终结果
        """
        # 处理最后一个结果
        if isinstance(last_result, dict) and 'structured_data' in last_result:
            # 已经是标准格式
            return json.dumps(last_result, ensure_ascii=False)

        # 构建标准格式
        structured_data = {}
        reasoning_logic = ""

        if isinstance(last_result, dict):
            if 'error' in last_result:
                # 错误结果
                return json.dumps({
                    "structured_data": {},
                    "reasoning_logic": f"执行失败: {last_result.get('error')}"
                }, ensure_ascii=False)
            # 普通 dict 结果
            structured_data = last_result
        elif isinstance(last_result, str):
            # 字符串结果
            try:
                parsed = json.loads(last_result)
                if isinstance(parsed, dict):
                    structured_data = parsed.get('structured_data', parsed)
                    reasoning_logic = parsed.get('reasoning_logic', '')
                else:
                    structured_data = {"result": parsed}
            except json.JSONDecodeError:
                structured_data = {"result": last_result}
        else:
            structured_data = {"result": last_result}

        return json.dumps({
            "structured_data": structured_data,
            "reasoning_logic": reasoning_logic or "步骤执行完成"
        }, ensure_ascii=False)

    @classmethod
    def _save_to_process_data(cls, step_id: str, sandbox, context, args) -> None:
        """将步骤结果写入 process_data"""
        if sandbox is None:
            return

        full_step_id = cls._get_full_step_id(step_id, context, args)

        try:
            step_result = sandbox.get_step_result(full_step_id)
            if step_result and isinstance(step_result, dict):
                content = step_result.get('content', '{}')
                try:
                    content_dict = json.loads(content) if isinstance(content, str) else content
                    structured_data = content_dict.get('structured_data', {})
                    if structured_data:
                        sandbox.set_process_data(f"{full_step_id}_structured", structured_data)
                except Exception:
                    pass
        except Exception:
            pass
