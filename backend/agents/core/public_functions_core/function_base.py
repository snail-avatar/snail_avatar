# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : function_base.py
# @Desc    : function calling 基础框架
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
function calling 基础框架

提供 FunctionBase（工具抽象基类）与 FunctionRegistry（工具注册与执行）。
所有工具类只需继承 FunctionBase 并实现 get_schema() 和 execute() 两个方法。

设计原则：
- 无状态：不持有 MemoryDatabase 或其他系统引用，由上层 Agent 在需要时注入
- 纯框架：不包含任何业务逻辑（业务逻辑在各工具类中实现）
- 可扩展：新增工具只需新增 FunctionBase 子类，并在 registry 中注册
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Type


# ==========================================================================
# FunctionBase — 工具函数基类
# ==========================================================================

class FunctionBase:
    """所有工具函数的抽象基类

    子类必须实现：
        name: str                    工具唯一标识（与 schema.function.name 一致）
        get_schema() -> dict         返回符合 DashScope/OpenAI 规范的 function schema
        execute(args: dict) -> str   执行工具，返回字符串结果

    可选：
        description: str             工具描述（也可写在 schema 中）
    """

    name: str = ""

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回 function schema（DashScope 标准格式）

        格式示例:
        {
            "type": "function",
            "function": {
                "name": "get_xxx",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }
        """
        raise NotImplementedError

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行工具函数

        Args:
            args: 解析后的参数字典（从 JSON 字符串解析而来）
            context: 可选上下文对象（通常是 Agent 实例，用于共享工作流实例等状态）

        Returns:
            Any: 执行结果，可以是字符串、字典或其他类型。框架层会自动标准化为统一格式。
        """
        raise NotImplementedError


# ==========================================================================
# AtomicFunction — Tier 1 原子工具基类
# ==========================================================================

class AtomicFunction(FunctionBase):
    """Tier 1 原子工具基类

    特点：
    - 纯数据操作，不调用其他 Agent
    - 无状态，每次调用独立
    - 直接操作 memorycore 或执行计算
    - Tier 1 Agent（专家 Agent、计算 Agent）使用

    子类只需实现：
        name: str                    工具唯一标识
        get_schema() -> dict         返回 function schema
        _execute_atomic(args, context) -> Any  执行原子操作
    """

    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行原子操作（含公共上下文变量自动注入）"""
        args = cls._auto_inject_context_vars(args, context)
        return cls._execute_atomic(args, context)

    @classmethod
    def _auto_inject_context_vars(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """自动注入公共上下文变量（安全网，主注入由 ProcessStep 完成）

        对于 YAML 中未显式声明的 memory_db 等变量，
        从 context 中自动提取并注入。
        """
        # 1. memory_db - 使用唯一权威槽 get_memory_db() 获取
        if "memory_db" not in args:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            db = get_memory_db()
            args["memory_db"] = args.get("memory_db") or db

        return args

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """子类实现：具体原子操作逻辑"""
        raise NotImplementedError





# ==========================================================================
# FunctionRegistry — 工具注册与执行中心
# ==========================================================================

class FunctionRegistry:
    """工具注册与执行中心

    使用方式:
        registry = FunctionRegistry()
        registry.register(ListVehiclesFunction)
        registry.register(GetParamByDbKeyFunction)
        ...

        # 传给 LLM:
        tools = registry.get_tools_list()
        response = llm.generate_response("", history, tools)

        # 执行工具:
        result = registry.execute("get_xxx_by_dbkey", '{"db_key": "mass_curb_result_reevlto"}')
    """

    def __init__(self):
        self._functions: Dict[str, Type[FunctionBase]] = {}

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, func_class: Type[FunctionBase]) -> None:
        """注册一个工具类

        Args:
            func_class: FunctionBase 的子类
        """
        if not issubclass(func_class, FunctionBase):
            raise TypeError(f"[{func_class.__name__}] 不是 FunctionBase 的子类")
        if not func_class.name:
            raise ValueError(f"[{func_class.__name__}] 缺少必要的 name 属性")
        if func_class.name in self._functions:
            # 允许重复注册（覆盖），便于开发期调试
            pass
        self._functions[func_class.name] = func_class

    def register_all(self, func_classes: List[Type[FunctionBase]]) -> None:
        """批量注册工具类"""
        for fc in func_classes:
            self.register(fc)

    def has_function(self, name: str) -> bool:
        return name in self._functions

    # ------------------------------------------------------------------
    # schema 生成
    # ------------------------------------------------------------------

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """生成传给 LLM 的 tools 参数

        Returns:
            [schema1, schema2, ...] — 所有已注册工具的 schema 列表
        """
        return [
            func_class.get_schema()
            for func_class in self._functions.values()
        ]

    # ------------------------------------------------------------------
    # 两轮式工具选择（方案 3）新增的能力
    # ------------------------------------------------------------------

    def get_tools_catalog(self) -> str:
        """生成工具目录（名称 + 简短描述），用于两轮式 Phase 1 的工具选择

        返回格式示例:
          1. list_all_vehicles - 列出当前系统中所有可用车型
          2. get_parameter_value - 从 memorycore 中按 db_key 读取单个参数值
          ...

        说明:
          - 从每个工具的 schema.function.description 中取第一行 / 前 80 个字符
          - 保证目录紧凑，Phase 1 能快速做出选择，而不被冗长描述干扰
        """
        lines: List[str] = []
        for idx, (name, func_class) in enumerate(self._functions.items(), 1):
            try:
                schema = func_class.get_schema()
                desc = schema.get("function", {}).get("description", "")
                short_desc = desc.split("\n")[0][:80] if desc else "（无描述）"
            except Exception:
                short_desc = "（无描述）"
            lines.append(f"{idx}. {name} - {short_desc}")
        return "\n".join(lines)

    def get_tools_by_names(self, names: List[str]) -> List[Dict[str, Any]]:
        """根据工具名列表，返回对应工具的完整 schema（用于两轮式 Phase 2）

        Args:
            names: 工具名列表（需与 FunctionBase.name 一致）

        Returns:
            只包含指定工具的 schema 列表。未找到的工具名会被静默忽略。
            如果 names 为空列表，返回空列表。
        """
        result: List[Dict[str, Any]] = []
        if not names:
            return result
        for name in names:
            if name in self._functions:
                try:
                    result.append(self._functions[name].get_schema())
                except Exception:
                    pass
        return result

    def get_tool_names(self) -> List[str]:
        """返回所有已注册工具的名称列表（调试用）"""
        return list(self._functions.keys())

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def execute(self, function_name: str, arguments_json: str, context: Any = None) -> tuple:
        """执行指定工具

        Args:
            function_name: 工具名（需与 FunctionBase.name 一致）
            arguments_json: LLM 返回的 JSON 参数字符串
            context: 可选上下文对象（通常是 Agent 实例，用于共享工作流实例等状态）

        Returns:
            tuple: (structured_data, text_version)
                structured_data: 统一格式的结构化数据字典
                text_version: LLM 友好的文本版本
        """
        # 1. 查函数是否已注册
        if function_name not in self._functions:
            error_msg = f"[FunctionRegistry] 未注册的工具: {function_name}"
            return {"type": "text", "content": error_msg}, error_msg

        # 2. 解析 JSON 参数
        args: Dict[str, Any] = {}
        if arguments_json:
            try:
                args = json.loads(arguments_json)
            except Exception as e:
                error_msg = f"[FunctionRegistry] 参数解析失败: {e}\n原始参数: {arguments_json}"
                return {"type": "text", "content": error_msg}, error_msg

        # 3. 执行函数
        try:
            func_class = self._functions[function_name]
            result = func_class.execute(args, context)
            structured_data = self._normalize_result(result)
            text_version = self._dict_to_text(structured_data)
            return structured_data, text_version
        except Exception as e:
            error_msg = f"[FunctionRegistry] 执行工具 {function_name} 失败: {e}"
            return {"type": "text", "content": error_msg}, error_msg

    def _normalize_result(self, result: Any) -> Dict[str, Any]:
        """将任意返回值标准化为统一结构化格式

        Args:
            result: 工具函数的返回值

        Returns:
            Dict: 统一格式的结构化数据
        """
        if result is None:
            return {"type": "text", "content": ""}
        
        if isinstance(result, dict) and "type" in result:
            result = self._clean_nan_values(result)
            return result
        
        if isinstance(result, str):
            return {"type": "text", "content": result}
        
        if isinstance(result, (int, float)):
            result = self._clean_nan_values(result)
            return {"type": "single_value", "content": result}
        
        if isinstance(result, list):
            result = self._clean_nan_values(result)
            return {"type": "list", "content": result}
        
        return {"type": "text", "content": str(result)}
    
    def _clean_nan_values(self, data: Any) -> Any:
        """递归清理数据中的 nan 值，将其转换为 None（JSON 兼容）

        Args:
            data: 任意类型的数据

        Returns:
            Any: 清理后的 data
        """
        if isinstance(data, dict):
            return {k: self._clean_nan_values(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_nan_values(item) for item in data]
        elif isinstance(data, float) and (math.isnan(data) or math.isinf(data)):
            return None
        else:
            return data

    def _dict_to_text(self, data: Dict[str, Any]) -> str:
        """将结构化数据转换为 LLM 友好的文本

        Args:
            data: 统一格式的结构化数据

        Returns:
            str: LLM 友好的文本版本
        """
        data_type = data.get("type", "text")
        
        if data_type == "table":
            lines = []
            column_labels = data.get("column_labels", {})
            column_formats = data.get("column_formats", {})
            
            # 计算状态（如 VTS 计算执行情况）—— 如果存在则优先展示
            calc_status = data.get("calc_status", "")
            if calc_status:
                lines.append(calc_status)
                lines.append("")

            if data.get("title"):
                lines.append(data["title"])
            if data.get("columns"):
                header = " | ".join(column_labels.get(col, col) for col in data["columns"])
                lines.append(header)
                lines.append("-" * len(header))
                if data.get("rows"):
                    for row in data["rows"]:
                        formatted_values = []
                        for col in data["columns"]:
                            value = row.get(col, "")
                            fmt = column_formats.get(col)
                            if fmt and isinstance(value, (int, float)):
                                formatted_values.append(f"{value:{fmt}}")
                            else:
                                formatted_values.append(str(value))
                        lines.append(" | ".join(formatted_values))
            if data.get("summary"):
                lines.append("")
                summary_items = [f"{k}={v}" for k, v in data["summary"].items()]
                lines.append("摘要: " + ", ".join(summary_items))
            text = "\n".join(lines)
            text += "\n\n[提示：以上数据已以结构化表格形式展示给用户，请在回复中不要重复展示数据表格，直接提供分析结论和建议即可]"
            return text
        
        elif data_type == "list":
            lines = []
            if data.get("title"):
                lines.append(data["title"])
            if data.get("content"):
                for i, item in enumerate(data["content"], 1):
                    lines.append(f"{i}. {item}")
            if data.get("summary"):
                count = data["summary"].get("count", len(data.get("content", [])))
                lines.append(f"\n总数: {count}")
            text = "\n".join(lines)
            text += "\n\n[提示：以上数据已以结构化列表形式展示给用户，请在回复中不要重复展示列表数据，直接提供分析结论和建议即可]"
            return text
        
        elif data_type == "single_value":
            name = data.get("name", "") or data.get("title", "")
            unit = data.get("unit", "")
            value = data["content"]
            if name:
                text = f"{name}: {value} {unit}".strip()
            else:
                text = f"{value} {unit}".strip()
            text += "\n\n[提示：以上数据已以结构化形式展示给用户，请在回复中不要重复展示该数值，直接提供分析结论和建议即可]"
            return text
        
        else:
            return data.get("content", "")