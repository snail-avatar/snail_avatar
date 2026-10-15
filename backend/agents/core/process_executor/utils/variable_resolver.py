# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : variable_resolver.py
# @Desc    : YAML 变量解析器 - VariableResolver
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
VariableResolver - YAML 变量解析器

功能：
- 解析 YAML 配置中的变量引用（如 $args.xxx, $memory_db, $sandbox 等）
- 支持变量嵌套访问（如 $result.structured_data.categories）
- 提供统一的变量解析接口

支持的变量前缀：
- $args.xxx:       LLM 传入的参数
- $memory_db:      memory_db 实例
- $context:        Agent 实例
- $result:         步骤执行结果
- $data_sources.xxx: 数据源结果
- $post.xxx:       后处理结果
- $prev:           上一个节点结果（process 步骤）
- $results.xxx:    之前节点的命名结果（process 步骤）

使用示例：
    resolver = VariableResolver(args={"vehicle_suffix": "reevlto"}, context=agent)
    value = resolver.resolve("$args.vehicle_suffix")  # 返回 "reevlto"
    value = resolver.resolve("$memory_db")  # 返回 memory_db 实例
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


from ..utils.context_provider import IContextProvider


class VariableResolver:
    """YAML 变量解析器

    支持的变量格式：
    - 简单变量：$args.xxx, $memory_db, $context
    - 嵌套访问：$result.structured_data.categories
    - 默认值：${args.xxx|default_value}
    - 业务变量：通过 IContextProvider 扩展（如 $category, $product_data）
    """

    # 变量引用正则表达式
    VAR_PATTERN = re.compile(r'\$\{?([\w.]+)\}?')

    def __init__(self, args: Dict[str, Any] = None,
                 context: Any = None,
                 context_provider: IContextProvider = None,
                 **kwargs):
        """初始化变量解析器

        Args:
            args: LLM 传入的参数
            context: Agent 实例
            context_provider: 上下文提供者（业务变量解析扩展点）
            **kwargs: 额外的变量上下文（如 data_sources, post_results 等）
        """
        self._args = args or {}
        self._context = context
        self._context_provider = context_provider
        self._extra_context = kwargs

    def resolve(self, var_path: str) -> Any:
        """解析单个变量引用

        Args:
            var_path: 变量路径（如 $args.xxx, $memory_db）

        Returns:
            解析后的变量值
        """
        if not isinstance(var_path, str) or not var_path.startswith('$'):
            return var_path

        path = var_path[1:]  # 去掉 $

        # 处理 ${...} 格式
        if path.startswith('{') and path.endswith('}'):
            path = path[1:-1]

        # 处理默认值 ${...|default}
        default_value = None
        if '|' in path:
            path, default_value = path.split('|', 1)

        # 根据前缀解析
        value = self._resolve_by_prefix(path)

        # 如果解析失败，返回默认值
        if value is None and default_value is not None:
            return default_value

        return value

    def _resolve_by_prefix(self, path: str) -> Any:
        """根据变量前缀进行解析

        Args:
            path: 变量路径（不含 $）

        Returns:
            解析后的变量值
        """
        # args 变量
        if path.startswith('args.'):
            key = path[5:]
            return self._nested_get(self._args, key)

        # memory_db
        if path == 'memory_db':
            return self._get_memory_db()

        # context
        if path == 'context':
            return self._context

        # result 变量（可能需要嵌套访问）
        if path == 'result' or path.startswith('result.'):
            return self._resolve_result(path)

        # data_sources 变量
        if path.startswith('data_sources.'):
            key = path[13:]
            data_sources = self._extra_context.get('data_sources', {})
            return self._nested_get(data_sources, key)

        # post 变量
        if path.startswith('post.'):
            key = path[5:]
            post_results = self._extra_context.get('post', {})
            return self._nested_get(post_results, key)

        # prev 变量（process 步骤）
        if path == 'prev':
            return self._extra_context.get('prev')

        # results 变量（process 步骤）
        if path.startswith('results.'):
            key = path[8:]
            results = self._extra_context.get('results', {})
            return self._nested_get(results, key)

        # sandbox
        if path == 'sandbox':
            return self._get_sandbox()

        # 业务变量扩展：通过 IContextProvider 解析
        # 当遇到未知前缀时，尝试从 context_provider 获取
        if self._context_provider:
            return self._context_provider.resolve_context(path, self._args)

        # 未知前缀，返回原值
        return None

    def _resolve_result(self, path: str) -> Any:
        """解析 result 变量

        支持：
        - $result: 整个结果
        - $result.structured_data: structured_data 部分
        - $result.structured_data.categories: 嵌套访问

        Args:
            path: 变量路径

        Returns:
            解析后的值
        """
        result = self._extra_context.get('result')
        if result is None:
            return None

        # 处理纯 $result
        if path == 'result':
            return result

        # 处理嵌套访问
        try:
            # 如果 result 是 JSON 字符串，先解析
            result_dict = result
            if isinstance(result, str):
                result_dict = json.loads(result)

            # 提取子路径
            sub_path = path[7:]  # 去掉 'result.'

            return self._nested_get(result_dict, sub_path)
        except Exception:
            return None

    def _nested_get(self, data: Any, path: str) -> Any:
        """获取嵌套路径的值

        Args:
            data: 数据对象（dict 或 list）
            path: 嵌套路径（如 'structured_data.categories'）

        Returns:
            路径对应的值
        """
        keys = path.split('.')
        current = data

        for key in keys:
            if current is None:
                return None

            if isinstance(current, dict):
                if key in current:
                    current = current[key]
                else:
                    return None
            elif isinstance(current, list):
                try:
                    index = int(key)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except ValueError:
                    # 尝试在列表元素中查找
                    return None
            else:
                return None

        return current

    def _get_memory_db(self) -> Any:
        """获取 memory_db 实例"""
        try:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            return get_memory_db()
        except Exception:
            return None

    def _get_sandbox(self) -> Any:
        """获取沙箱实例（通用化：支持多控制器场景）"""
        if self._context is None:
            return None

        # 从 context 获取 process_controller
        controller = getattr(self._context, '_process_controller', None)
        if controller and hasattr(controller, 'get_sandbox'):
            return controller.get_sandbox()

        # 获取多控制器字典
        controllers = getattr(self._context, '_controllers', None)

        if controllers:
            # 取第一个控制器的沙箱
            first_controller = next(iter(controllers.values()), None)
            if first_controller and hasattr(first_controller, 'get_sandbox'):
                return first_controller.get_sandbox()

        return None

    def resolve_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析字典中所有变量引用

        Args:
            data: 包含变量引用的字典

        Returns:
            解析后的字典
        """
        resolved = {}
        for key, value in data.items():
            resolved[key] = self._resolve_value(value)
        return resolved

    def resolve_list(self, data: List[Any]) -> List[Any]:
        """解析列表中所有变量引用

        Args:
            data: 包含变量引用的列表

        Returns:
            解析后的列表
        """
        return [self._resolve_value(item) for item in data]

    def _resolve_value(self, value: Any) -> Any:
        """递归解析值中的变量引用

        Args:
            value: 可能包含变量引用的值

        Returns:
            解析后的值
        """
        if isinstance(value, str):
            # 检查是否是纯变量引用
            if value.startswith('$'):
                return self.resolve(value)

            # 检查是否包含变量引用
            if '$' in value:
                return self._resolve_string(value)

            return value

        elif isinstance(value, dict):
            return self.resolve_dict(value)

        elif isinstance(value, list):
            return self.resolve_list(value)

        return value

    def _resolve_string(self, string: str) -> str:
        """解析字符串中的变量引用

        将字符串中的 $xxx.xxx 替换为对应的值。

        Args:
            string: 包含变量引用的字符串

        Returns:
            解析后的字符串
        """
        def replace_match(match):
            var_path = match.group(1)
            value = self.resolve('$' + var_path)
            if value is not None:
                return str(value)
            return match.group(0)  # 保持原样

        return self.VAR_PATTERN.sub(replace_match, string)

    @classmethod
    def resolve_simple(cls, value: Any, args: Dict[str, Any] = None,
                       context: Any = None,
                       context_provider: IContextProvider = None,
                       **kwargs) -> Any:
        """简化的静态解析方法

        Args:
            value: 可能包含变量引用的值
            args: LLM 传入的参数
            context: Agent 实例
            context_provider: 上下文提供者
            **kwargs: 额外的变量上下文

        Returns:
            解析后的值
        """
        resolver = cls(args=args, context=context, context_provider=context_provider, **kwargs)
        return resolver._resolve_value(value)

    @classmethod
    def is_variable(cls, value: Any) -> bool:
        """检查值是否是变量引用

        Args:
            value: 待检查的值

        Returns:
            bool: 是否是变量引用
        """
        if not isinstance(value, str):
            return False
        return value.startswith('$')
