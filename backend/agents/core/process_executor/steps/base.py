# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : step_base.py
# @Desc    : 流程步骤执行器基类 - ProcessStep
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
ProcessStep 流程步骤执行器基类

提供步骤执行器的核心基础功能：
- 流程状态感知（通过 context 获取 ProcessController）
- 函数执行（public_functions 注册中心）
- 步骤配置加载（从 YAML 文件加载）
- 执行结果记录与沙箱写入
- 错误判断与结果摘要
"""

from __future__ import annotations

import os
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions import (
    get_public_function,
)
from snail_avatar.backend.core.work_log import WorkLogger

from ..utils.llm_config_loader import merge_with_global_llm_config


class ProcessStep(FunctionBase):
    """流程步骤执行器基类

    特点：
    - 流程状态感知（通过 context 获取 ProcessController）
    - 可调用其他 Agent
    - 可执行标准动作
    - 需要记录步骤结果
    - Tier 2 Agent（流程编排 Agent）使用
    - 私域沙箱数据支持：所有步骤可读写私域数据
    - 权限控制：只有特定步骤可写入公共 memory core

    子类只需实现：
        step_id: str                 步骤标识（对应流程定义中的 ID）
        step_name: str               步骤显示名称
        _execute_step(args, context) -> str  执行步骤逻辑

    辅助方法：
        _get_db()                    获取 memory_db 实例（供子类访问数据使用）
        _get_sandbox()               获取沙箱实例（供子类读写私域数据）
    """

    step_id: str = ""
    step_name: str = ""
    WRITE_PERMISSION: bool = False

    _step_config_name: str = ""     # 步骤配置文件名（不含.yaml后缀）
    _step_config: Dict[str, Any] = {}  # 缓存已加载的步骤配置

    # ==================================================================
    # 函数执行（public_functions 注册中心）
    # ==================================================================

    @classmethod
    def _get_step_functions(cls, agent=None) -> list:
        """获取步骤可用的函数列表（配置驱动）

        从 step 配置中的 functions（builtin_functions 列表）查找对应函数，
        从 public_functions 注册中心获取。
        """
        step_config = getattr(cls, '_step_config', {}) or {}
        function_names = step_config.get("functions", step_config.get("builtin_functions", []))

        function_schemas = []
        for function_name in function_names:
            pub_fn_cls = get_public_function(function_name)
            if pub_fn_cls:
                schema = pub_fn_cls.get_schema()
                function_schemas.append(schema)
        return function_schemas

    @classmethod
    def _execute_builtin_function(cls, function_name: str, arguments_json: str, agent=None) -> tuple:
        """执行步骤可用的函数

        仅查找通过 YAML functions 配置声明的函数（从 public_functions 注册中心），
        不会回退到 Agent 注册的函数，确保 Step 函数调用的独立性。

        Args:
            function_name: 函数名称
            arguments_json: 函数参数（支持 JSON 字符串或 dict 对象两种格式）
            agent: Agent 实例（可选）

        Returns:
            tuple: (structured_data, text_version) 或 (None, error_msg)
        """
        import json

        args = {}
        if arguments_json:
            try:
                # 兼容两种参数格式：
                # 1. JSON 字符串：'{"expressions": [1, 2]}'
                # 2. Python 对象：{"expressions": [1, 2]}
                if isinstance(arguments_json, dict):
                    args = arguments_json
                elif isinstance(arguments_json, str):
                    args = json.loads(arguments_json)
                else:
                    return None, f"参数格式错误: 不支持的类型 {type(arguments_json)}"
            except json.JSONDecodeError as e:
                return None, f"参数解析失败: {str(e)}"
            except Exception as e:
                return None, f"参数处理失败: {str(e)}"

        # 查找 public_functions 注册中心
        pub_fn_cls = get_public_function(function_name)
        if pub_fn_cls:
            try:
                result = pub_fn_cls.execute(args, agent)
                if isinstance(result, dict) and 'type' in result:
                    structured_data = result
                    text_version = result.get('content', str(result))
                else:
                    structured_data = {'type': 'text', 'content': str(result)}
                    text_version = str(result)
                return structured_data, text_version
            except Exception as e:
                return None, f"Public Function 执行失败: {str(e)}"

        return None, f"错误: 未找到函数 '{function_name}'。请在 Step YAML 的 functions 配置中声明此函数。"

    # ==================================================================
    # 步骤配置加载
    # ==================================================================

    @classmethod
    def _load_step_config(cls, agent=None) -> Dict[str, Any]:
        """加载步骤配置文件（与全局默认配置合并）

        优先从 agent._agent_dir 获取配置路径；
        若未提供 agent，则通过类定义文件路径推断 agent 目录。

        Args:
            agent: Agent 实例（可选，未提供时通过类路径推断）

        Returns:
            dict: 步骤配置
        """
        if not cls._step_config_name:
            cls._step_config = {}
            return cls._step_config

        step_config = {}
        try:
            import yaml

            # 优先从 agent 实例获取目录
            agent_dir = getattr(agent, '_agent_dir', None) if agent else None

            # 回退 1：从类属性获取（动态创建的步骤类由 factory 设置 _agent_dir）
            if not agent_dir:
                agent_dir = getattr(cls, '_agent_dir', None)

            # 回退：通过类定义文件路径推断
            if not agent_dir:
                try:
                    import inspect
                    class_file = inspect.getfile(cls)
                    if class_file and 'steps' in class_file:
                        steps_dir = os.path.dirname(class_file)
                        agent_dir = os.path.dirname(steps_dir)
                except (TypeError, OSError):
                    pass

            if not agent_dir:
                agent_dir = os.path.dirname(os.path.dirname(__file__))

            config_dir = os.path.join(agent_dir, "config", "steps")
            config_path = os.path.join(config_dir, f"{cls._step_config_name}.yaml")

            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    step_config = yaml.safe_load(f) or {}
        except Exception:
            pass

        # 与全局 LLM 配置合并（LLM 步骤需要，Agent 步骤无影响）
        cls._step_config = merge_with_global_llm_config(step_config)
        return cls._step_config

    # ==================================================================
    # 步骤执行主流程
    # ==================================================================

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行步骤

        Args:
            args: LLM 传入的参数
            context: Agent 实例，包含 _process_controller

        Returns:
            dict: {"type": "text", "content": "...", "is_error": bool, "function_trace": [...]}
        """
        from .step_exceptions import NetworkError

        cls._ensure_memory_db(context)

        # 网络错误自动重试逻辑
        max_retry_count = 3  # 最大重试次数（不含首次执行）
        retry_count = 0
        result = None
        is_network_error = False
        stopped = False

        # 检查 context 是否提供 is_stopped 方法
        has_stop_check = hasattr(context, 'is_stopped')

        WorkLogger.info(f"步骤 {cls.step_id} 开始执行")

        while True:
            # 检查停止命令
            if has_stop_check and context.is_stopped():
                stopped = True
                WorkLogger.info(f"步骤 {cls.step_id} 因停止命令中断")
                break

            try:
                result = cls._execute_step(args, context)
                is_network_error = False
                break  # 成功，跳出重试循环
            except NetworkError as e:
                retry_count += 1
                if retry_count >= max_retry_count:
                    # 重试耗尽，构建错误结果返回
                    import json
                    result = {
                        "type": "text",
                        "content": json.dumps({
                            "structured_data": {},
                            "reasoning_logic": f"步骤 {cls.step_id} 网络连接失败，已重试{max_retry_count}次"
                        }, ensure_ascii=False),
                        "is_error": True,
                        "error_type": "network",
                        "retry_count": retry_count,
                    }
                    is_network_error = True
                    break
                # 退避等待后重试，同时检查停止命令
                import time
                wait_time = 2 * retry_count
                WorkLogger.warn(f"步骤 {cls.step_id} 网络错误，第{retry_count}/{max_retry_count}次重试，等待{wait_time}秒...")
                # 分段 sleep，每0.5秒检查一次停止命令
                for _ in range(wait_time * 2):
                    if has_stop_check and context.is_stopped():
                        stopped = True
                        WorkLogger.info(f"步骤 {cls.step_id} 在重试等待中因停止命令中断")
                        break
                    time.sleep(0.5)
                if stopped:
                    break
            except Exception as e:
                # 非网络错误，直接抛出
                raise

        # 如果因停止命令中断，抛出异常
        if stopped:
            raise RuntimeError(f"步骤 {cls.step_id} 执行被用户停止")

        # 如果是网络错误导致的重试耗尽，返回错误结果但不抛异常
        if is_network_error:
            result_dict = result
            # 属性模式下，步骤的记录和推进由 process_engine.py 统一管理
            is_attribute_mode = cls._check_attribute_mode(context, args)
            full_step_id = cls._get_full_step_id(cls.step_id, context, args)
            controller = cls._get_controller(context, args)
            if controller and not is_attribute_mode:
                controller.record_result(step_id=full_step_id, step_result=result_dict)
                # 网络错误时不推进状态
            cls._save_to_sandbox(cls.step_id, result_dict, context, args)
            return result_dict

        # 兼容：_execute_step 可能返回 dict 或字符串
        if isinstance(result, dict):
            result_dict = result.copy()
        else:
            result_dict = {"type": "text", "content": result, "function_trace": []}

        result_dict["is_error"] = False

        # 属性模式下，步骤的记录和推进由 process_engine.py 统一管理，跳过此处的重复调用
        is_attribute_mode = cls._check_attribute_mode(context, args)

        # 获取带专业名称前缀的完整步骤ID
        full_step_id = cls._get_full_step_id(cls.step_id, context, args)

        controller = cls._get_controller(context, args)
        if controller and not is_attribute_mode:
            # 仅在非属性模式下记录（属性模式由 process_engine 统一处理）
            controller.record_result(
                step_id=full_step_id,
                step_result=result_dict,
            )
            controller.advance(full_step_id, completed=True, step_result=result_dict)

        cls._save_to_sandbox(cls.step_id, result_dict, context, args)

        # 自动处理循环配置（框架自动处理）
        cls._auto_process_loop_config(result_dict, context, args)

        return result_dict

    @classmethod
    def _save_to_sandbox(cls, step_id: str, result: Dict, context, args) -> None:
        """将步骤结果写入沙箱
        
        对于 JSON 格式的 content，解析后保存为结构化数据；
        对于文本格式的 content（如 stage2_enabled=false 的步骤），直接保存原始内容。
        """
        sandbox = cls._get_sandbox(context, args)
        if sandbox:
            import json
            content = result.get("content", "")
            full_step_id = cls._get_full_step_id(step_id, context, args)

            try:
                structured_result = json.loads(content)
                if isinstance(structured_result, dict):
                    # JSON 格式正确，保存结构化数据
                    sandbox.set_step_result(full_step_id, structured_result)
                elif structured_result is None:
                    error_msg = f"步骤 {step_id} 执行失败：LLM 返回结果为 null"
                    WorkLogger.error(error_msg)
                    sandbox.set_step_result(full_step_id, {"error": error_msg, "is_error": True})
                else:
                    # JSON 解析成功但不是 dict，保存原始内容
                    sandbox.set_step_result(full_step_id, {"content": content})
            except (json.JSONDecodeError, ValueError):
                # 非 JSON 格式（如文本模式步骤），直接保存原始内容
                sandbox.set_step_result(full_step_id, {"content": content})
            except Exception as e:
                error_msg = f"步骤 {step_id} 执行失败：{str(e)}"
                WorkLogger.error(error_msg)
                sandbox.set_step_result(full_step_id, {"content": content, "error": str(e)})

            cls._save_to_process_data(step_id, sandbox, context, args)

    @classmethod
    def _save_to_process_data(cls, step_id: str, sandbox, context, args) -> None:
        """根据步骤类型写入 process_data（子类可覆盖）"""
        pass

    @classmethod
    def _execute_step(cls, args: Dict[str, Any], context: Any = None) -> str:
        """子类实现：具体步骤逻辑"""
        raise NotImplementedError

    # ==================================================================
    # 上下文与控制器获取
    # ==================================================================

    @classmethod
    def _get_context_provider(cls, context, args=None,
                               skip_controller: bool = False) -> Optional[Any]:
        """获取 ContextProvider（统一入口）

        获取顺序：
        1. 优先从 context（Agent 实例）获取
        2. 回退：从 ProcessController 获取（skip_controller=True 时跳过）

        Args:
            context: Agent 实例
            args: 步骤参数
            skip_controller: 是否跳过从 controller 获取（避免循环依赖）

        Returns:
            IContextProvider 实例或 None
        """
        if context is None:
            return None

        # 优先从 context 获取
        context_provider = getattr(context, '_context_provider', None)
        if context_provider is not None:
            return context_provider

        # 回退：从 controller 获取
        if not skip_controller:
            controller = cls._get_controller(context, args)
            if controller:
                return getattr(controller, '_context_provider', None)

        return None

    @classmethod
    def _get_controller(cls, context, args=None) -> Any:
        """从Agent实例获取ProcessController

        通用化的控制器查找机制：
        1. 通过 context_vars 中声明的 controller_key 变量名查找
        2. 回退到遍历 args 中的值匹配控制器
        3. 最终回退到 _process_controller 属性
        """
        if context is None:
            return None

        # 获取控制器字典
        controllers = getattr(context, '_controllers', None)

        if not controllers:
            # 无多控制器场景，直接返回单个控制器
            return getattr(context, '_process_controller', None)

        # 尝试通过 context_provider 获取 controller_key 的变量名
        controller_key_var = None
        context_provider = cls._get_context_provider(context, skip_controller=True)
        if context_provider:
            # 从 context_provider 配置中获取 controller_key 对应的变量名
            # 例如 controller_key.mapping = "instance_key"
            try:
                cp_config = getattr(context_provider, '_config', {})
                ck_entry = cp_config.get('controller_key', {})
                if 'mapping' in ck_entry:
                    controller_key_var = ck_entry['mapping']
                elif 'source' in ck_entry:
                    controller_key_var = ck_entry['source']
            except Exception:
                pass

        if controller_key_var and args and controller_key_var in args:
            # 使用配置声明的变量名查找
            key_value = args[controller_key_var]
            if key_value in controllers:
                return controllers[key_value]

        # 回退：遍历 args 中的所有值，尝试匹配控制器
        if args:
            for arg_value in args.values():
                if isinstance(arg_value, str) and arg_value in controllers:
                    return controllers[arg_value]

        # 回退：尝试上下文属性
        for attr_name in ('_instance_key',):
            attr_value = getattr(context, attr_name, '')
            if attr_value and attr_value in controllers:
                return controllers[attr_value]

        # 最终回退：返回第一个控制器
        if controllers:
            return next(iter(controllers.values()))

        return getattr(context, '_process_controller', None)

    @classmethod
    def _check_attribute_mode(cls, context, args) -> bool:
        """检查是否为属性模式（属性模式下由 process_engine 统一管理步骤记录）

        注意：属性模式为唯一执行模式，此方法始终返回 True。
        保留此方法以兼容外部调用。
        """
        return True

    @classmethod
    def _get_full_step_id(cls, step_id: str, context, args) -> str:
        """获取带循环项前缀的完整步骤ID

        只要当前在循环内（有 current_loop_item），就加前缀。
        与 controller._record_result 的逻辑保持一致，
        避免条件分支步骤（如 OPTIMIZE_SSTS）因不在状态树中而丢前缀。
        """
        controller = cls._get_controller(context, args)
        if controller:
            controller_state = controller.get_state()
            current_loop_item = controller_state.get("current_loop_item", "")
            if current_loop_item:
                prefix = f"{current_loop_item}_"
                if not step_id.startswith(prefix):
                    return f"{prefix}{step_id}"

        return step_id

    # ==================================================================
    # 统一变量解析（模板变量解析 + 公共函数参数注入共用）
    # ==================================================================

    @classmethod
    def _resolve_variables(cls, context, step_args=None, extra_vars=None) -> Dict[str, Any]:
        """统一变量解析（所有变量来源的唯一入口）

        用于两个场景：
        1. 模板变量解析：先用 data_sources 结果，再用 context_vars 补全
        2. 公共函数参数注入：先用 args_mapping 解析结果，再用 context_vars 补全

        Args:
            context: Agent 实例
            step_args: 步骤参数
            extra_vars: 已知值（如 data_sources 结果、args_mapping 解析结果）

        Returns:
            dict: 所有变量的解析结果
        """
        result = {}

        # 0. 放入所有 step_args 作为基础变量
        if step_args:
            result.update(step_args)

        # 1. 放入已知值（优先级最高，可覆盖 step_args）
        if extra_vars:
            result.update(extra_vars)

        # 2. memory_db 特殊处理：始终注入
        if "memory_db" not in result:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            result["memory_db"] = get_memory_db()

        # 3. 用 context_vars 配置补全缺失的业务变量
        context_provider = cls._get_context_provider(context)
        if context_provider:
            cp_config = getattr(context_provider, '_config', {})
            for var_name, rule in cp_config.items():
                if var_name in result:
                    continue

                if 'mapping' in rule:
                    # mapping 类型：从 step_args 或执行状态中查找
                    source = rule['mapping']
                    if step_args and source in step_args:
                        result[var_name] = step_args[source]
                    else:
                        # 回退：从执行状态查找
                        state = cls._get_execution_state_safe(context)
                        if state and source in state:
                            result[var_name] = state[source]

                elif 'value' in rule:
                    # value 类型：常量值
                    result[var_name] = rule['value']

        return result

    @classmethod
    def _get_execution_state_safe(cls, context) -> Optional[Dict[str, Any]]:
        """安全获取执行状态（用于 context_vars 回退查找）"""
        if context is None:
            return None
        controller = cls._get_controller(context)
        if controller:
            return controller.get_state()
        return None

    # ==================================================================
    # 循环配置处理
    # ==================================================================

    @classmethod
    def _auto_process_loop_config(cls, result: Dict[str, Any],
                                   context: Any,
                                   args: Dict[str, Any]) -> None:
        """自动处理循环配置

        从步骤配置中读取 loop_config，自动执行循环项保存操作。
        Agent ID 的设置已迁移到 post_process 中通过 set_step_agent 公共函数处理。

        配置示例：
        loop_config:
          loop_items_source: "structured_data.categories"
          target_loop_id: "CATEGORY_LOOP"

        Args:
            result: 步骤执行结果
            context: Agent 实例
            args: 步骤参数
        """
        import json

        # 获取步骤配置
        step_config = cls._get_effective_config(context) if hasattr(cls, '_get_effective_config') else {}
        loop_config = step_config.get('loop_config', {})

        if not loop_config:
            return

        # 解析结果
        content = result.get("content", "{}")
        try:
            result_data = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            return

        # 获取控制器
        controller = cls._get_controller(context, args)
        if not controller:
            return

        # 处理循环项
        loop_items_source = loop_config.get('loop_items_source', 'structured_data.categories')
        loop_items = cls._resolve_data_path(result_data, loop_items_source)
        if loop_items and isinstance(loop_items, list):
            target_loop_id = loop_config.get('target_loop_id')
            controller.set_loop_items(loop_items, loop_step_id=target_loop_id)

        # 注意：Agent 类型映射（calculator/expert）的设置已迁移到 post_process 中通过 set_step_agent 公共函数处理
        # 此处不再处理 agent 配置

    @staticmethod
    def _resolve_data_path(data: Any, path: str) -> Any:
        """解析数据路径

        支持点号分隔的路径，如 "structured_data.categories"

        Args:
            data: 数据字典
            path: 路径字符串

        Returns:
            解析后的数据，未找到返回 None
        """
        if not path or not data:
            return None

        keys = path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    # ==================================================================
    # 数据源加载与变量解析（公共方法，供 LLMStep / ProcessStep 共用）
    # ==================================================================

    @classmethod
    def _execute_data_sources(cls, step_config: Dict[str, Any],
                               args: Dict[str, Any],
                               context: Any = None) -> Dict[str, Any]:
        """执行数据源加载

        从配置的 data_sources 列表中加载数据，
        结果存入字典供 prompt 模板和 post_process 使用。

        Args:
            step_config: 步骤配置
            args: LLM 传入的参数
            context: Agent 实例

        Returns:
            dict: 数据源名称到结果的映射
        """
        data_sources_config = step_config.get('data_sources', [])
        
        if not data_sources_config:
            return {}

        result = {}

        for source_config in data_sources_config:
            function_name = source_config.get('function', '')
            output_key = source_config.get('output', '')
            args_mapping = source_config.get('args_mapping', {})

            if not function_name or not output_key:
                continue

            # 解析参数映射
            resolved_args = cls._resolve_args_mapping(args_mapping, args, context, result)

            # 用统一变量解析补全缺失的公共变量
            resolved_args = cls._resolve_variables(context, args, resolved_args)

            # 调用 public function
            from snail_avatar.backend.agents.core.public_functions import get_public_function
            pub_fn_cls = get_public_function(function_name)

            if pub_fn_cls:
                try:
                    fn_result = pub_fn_cls.execute(resolved_args, context)
                    result[output_key] = fn_result
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    result[output_key] = None

        return result

    @classmethod
    def _resolve_args_mapping(cls, args_mapping: Dict[str, Any],
                               args: Dict[str, Any],
                               context: Any = None,
                               data_sources: Dict[str, Any] = None,
                               resolve_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """解析参数映射中的变量引用

        支持的变量格式：
        - $args.xxx: LLM 传入参数
        - $memory_db: memory_db 实例
        - $context: Agent 实例
        - $result / $result.xxx: 步骤执行结果（需 resolve_context）
        - $post.xxx: 之前 post_process 的输出
        - $data_sources.xxx: 数据源的输出

        Args:
            args_mapping: 参数映射配置
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 已加载的数据源结果
            resolve_context: 后处理解析上下文（含 result, data_sources, post）

        Returns:
            dict: 解析后的参数字典
        """
        resolved = {}

        for key, value in args_mapping.items():
            if isinstance(value, str) and value.startswith('$'):
                resolved[key] = cls._resolve_variable(value, args, context, data_sources, resolve_context)
            elif isinstance(value, dict):
                # 递归解析嵌套字典中的变量（如 step_id_mapping 中的值）
                resolved[key] = cls._resolve_args_mapping(value, args, context, data_sources, resolve_context)
            else:
                resolved[key] = value

        return resolved

    @classmethod
    def _resolve_variable(cls, var_path: str, args: Dict[str, Any],
                           context: Any = None,
                           data_sources: Dict[str, Any] = None,
                           resolve_context: Dict[str, Any] = None) -> Any:
        """解析单个变量引用

        支持的变量路径：
        - $args.xxx: 从 LLM 传入参数获取
        - $memory_db: 获取 memory_db 实例
        - $context: 返回 Agent 实例
        - $result: 步骤执行结果（需 resolve_context）
        - $result.xxx: 结果中的嵌套字段（需 resolve_context）
        - $post.xxx: 从 resolve_context.post 或 data_sources 获取
        - $data_sources.xxx: 从 resolve_context.data_sources 或 data_sources 获取

        Args:
            var_path: 变量路径（如 $args.xxx, $memory_db）
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 数据源结果
            resolve_context: 后处理解析上下文（含 result, data_sources, post）

        Returns:
            变量值
        """
        if not var_path.startswith('$'):
            return var_path

        path = var_path[1:]

        # $result / $result.xxx → 从 resolve_context 获取
        if path == 'result':
            result_val = resolve_context.get('result') if resolve_context else None
            return result_val

        if path.startswith('result.'):
            result_data = resolve_context.get('result') if resolve_context else None
            if result_data:
                try:
                    import json
                    result_dict = json.loads(result_data) if isinstance(result_data, str) else result_data
                    keys = path[7:].split('.')
                    current = result_dict
                    for k in keys:
                        if isinstance(current, dict) and k in current:
                            current = current[k]
                        else:
                            return None
                    return current
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return None
            return None

        # $data_sources.xxx → 优先从 resolve_context 获取
        if path.startswith('data_sources.'):
            key = path[13:]
            if resolve_context:
                ds = resolve_context.get('data_sources', {})
                if key in ds:
                    return ds[key]
            if data_sources and key in data_sources:
                return data_sources[key]
            return None

        # $post.xxx → 优先从 resolve_context 获取
        if path.startswith('post.'):
            key = path[5:]
            if resolve_context:
                post_results = resolve_context.get('post', {})
                if key in post_results:
                    val = post_results[key]
                    return val
            if data_sources and key in data_sources:
                return data_sources[key]
            return None

        # $args.xxx → 从 LLM 传入参数获取
        if path.startswith('args.'):
            key = path[5:]
            val = args.get(key)
            return val

        # $memory_db → 获取 memory_db
        if path == 'memory_db':
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            db = get_memory_db()
            return db

        # $sandbox → 获取沙箱实例
        if path == 'sandbox':
            sandbox = cls._get_sandbox(context, args)
            return sandbox

        # $context → 返回 Agent 实例
        if path == 'context':
            return context

        # $step_context → 从沙箱获取所有步骤结果作为上下文
        if path == 'step_context' or path.startswith('step_context'):
            sandbox = cls._get_sandbox(context, args)
            if sandbox:
                all_data = sandbox.get_all_data()
                step_results = all_data.get("step_results", {})
                if step_results:
                    # 转换为 {step_id: content_str} 格式
                    step_context = {}
                    for sid, result in step_results.items():
                        if isinstance(result, dict) and "structured_data" in result:
                            import json
                            step_context[sid] = json.dumps(result, ensure_ascii=False)
                        elif isinstance(result, dict) and "error" not in result:
                            import json
                            step_context[sid] = json.dumps(result, ensure_ascii=False)
                    return step_context
            return {}

        # 默认返回变量本身
        return var_path

    @classmethod
    def _execute_post_process(cls, step_config: Dict[str, Any],
                               result: str,
                               args: Dict[str, Any],
                               context: Any = None,
                               data_sources: Dict[str, Any] = None) -> str:
        """执行后处理钩子

        从配置的 post_process 列表中执行后处理函数。

        Args:
            step_config: 步骤配置
            result: 步骤执行结果
            args: LLM 传入的参数
            context: Agent 实例
            data_sources: 数据源结果

        Returns:
            str: 后处理后的结果（可能被修改）
        """
        post_process_config = step_config.get('post_process', [])
        
        if not post_process_config:
            return result

        post_results = {}

        for idx, post_config in enumerate(post_process_config):
            function_name = post_config.get('function', '')
            output_key = post_config.get('output', '')
            args_mapping = post_config.get('args_mapping', {})

            if not function_name:
                continue

            # 构建变量解析上下文
            resolve_context = {
                'result': result,
                'data_sources': data_sources,
                'post': post_results,
            }

            # 解析参数映射
            resolved_args = cls._resolve_args_mapping(args_mapping, args,
                                                       context, None, resolve_context)

            # 用统一变量解析补全缺失的公共变量
            resolved_args = cls._resolve_variables(context, args, resolved_args)

            # 注入步骤原始结果，供函数按约定默认读取（YAML 未显式声明 mapping/categories 等路径时使用）
            resolved_args.setdefault("_step_result", result)

            # 调用 public function
            from snail_avatar.backend.agents.core.public_functions import get_public_function
            pub_fn_cls = get_public_function(function_name)

            if pub_fn_cls:
                try:
                    fn_result = pub_fn_cls.execute(resolved_args, context)
                    if output_key:
                        post_results[output_key] = fn_result
                    # 某些后处理可能修改 result（返回 dict 含 result key 时触发更新）
                    if isinstance(fn_result, dict) and 'result' in fn_result:
                        result = fn_result['result']
                except Exception as e:
                    import traceback as _tb
                    _tb.print_exc()
                    if output_key:
                        post_results[output_key] = None

        return result

    # ==================================================================
    # 基础设施（memory_db / sandbox 访问）
    # ==================================================================

    @classmethod
    def _ensure_memory_db(cls, context: Any = None) -> None:
        """统一确保 memory_db 已注入到全局引用"""
        from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import (
            get_memory_db,
            set_memory_db,
        )

        db = get_memory_db()
        if db is not None:
            return

        if context is not None:
            agent_db = getattr(context, '_memory_db', None)
            if agent_db is not None:
                set_memory_db(agent_db)
                return

        # 兜底：从唯一权威槽读取
        try:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            app_db = get_memory_db()
            if app_db is not None:
                set_memory_db(app_db)
        except Exception:
            pass

    @classmethod
    def _get_db(cls) -> Any:
        """获取 memory_db 实例"""
        from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
        return get_memory_db()

    @classmethod
    def _get_sandbox(cls, context, args=None):
        """获取沙箱实例"""
        controller = cls._get_controller(context, args)
        if controller and hasattr(controller, 'get_sandbox'):
            return controller.get_sandbox()
        return None

    @classmethod
    def write_to_memory_db(cls, context, data):
        """写入公共 memory core（仅有权限的步骤）"""
        if not cls.WRITE_PERMISSION:
            raise PermissionError(f"步骤 {cls.step_id} 没有写入 memory core 的权限")

        db = cls._get_db()
        if db is None:
            raise RuntimeError("memory_db 未初始化")

        cls._write_to_memory_db_impl(db, data, context)

    @classmethod
    def _write_to_memory_db_impl(cls, db, data, context):
        """子类实现具体的写入逻辑"""
        raise NotImplementedError
