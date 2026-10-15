# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 000_pubfn_calculator.py
# @Desc    : Public Function: 基于 math-engine 的计算器工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 000: 计算器

基于 math-engine 库，为 LLM 提供安全、精确的数学计算能力。
作为 public function，可被所有 Agent 和 Step 通过注册获得调用权限。

支持：
- 四则运算、幂运算、数学函数、常量引用、上一步结果引用
- Decimal 精确计算，避免浮点误差
- 自动修正 LLM 常见输入错误
"""

from __future__ import annotations

import math
import re
import threading
from decimal import Decimal
from typing import Any, Dict, List, Optional

import math_engine
from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnCalculator(AtomicFunction):
    """LLM 计算器 Public Function
    
    使用 math-engine 作为计算引擎，提供 Decimal 精确计算。
    对于 math-engine 不支持的函数（abs, round, ceil, floor），
    使用 Python math 模块预处理后再计算。
    """

    name: str = "calculator"

    MAX_EXPRESSION_LENGTH = 500
    MAX_BATCH_SIZE = 20

    _last_result: Optional[Decimal] = None
    _state_lock = threading.Lock()

    _FULLWIDTH_MAP = {
        "＋": "+", "－": "-", "＊": "*", "／": "/",
        "％": "%", "＾": "^", "＿": "_",
        "（": "(", "）": ")", "【": "[", "】": "]",
        "，": ",", "。": ".",
        "×": "*", "÷": "/", "＝": "=",
    }

    _UNSUPPORTED_FUNCTIONS = {
        "abs": (lambda x: abs(x), "abs"),
        "ceil": (lambda x: float(math.ceil(x)), "ceil"),
        "floor": (lambda x: float(math.floor(x)), "floor"),
    }

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "批量数学计算器，一次调用可计算多个数学表达式，避免 LLM 计算幻觉和多轮调用开销。\n"
                    "支持：\n"
                    "  - 四则运算：+（加）、-（减）、*（乘）、/（除）\n"
                    "  - 高级运算：**（幂）、%（取模）、//（整除）\n"
                    "  - 括号优先级：如 (100 + 200) * 1.5\n"
                    "  - 数学函数：sqrt(x)、abs(x)、round(x,n)、sin(x)、cos(x)、tan(x)、log(x)、ceil(x)、floor(x)\n"
                    "  - 常量：pi（圆周率）、e（自然常数）\n"
                    "  - 引用上一步结果：ans（数组内前一个表达式的计算结果）\n"
                    "  - 精度：使用 Decimal 精确计算，避免浮点误差\n"
                    "  - 批量计算：expressions 数组中的表达式按序执行，共享 ans 状态"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expressions": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "description": "数学表达式字符串"
                            },
                            "description": (
                                "批量数学表达式数组，按顺序执行。\n"
                                "数组内表达式共享 ans 状态，可通过 ans 引用前一个表达式的结果。\n"
                                "支持的运算：+、-、*、/、**、%、//\n"
                                "支持的函数：sqrt、abs、round、sin、cos、tan、log、ceil、floor\n"
                                "支持的常量：pi、e\n"
                                "示例：[\"100 * 2 + 30\", \"ans * 1.5\", \"sqrt(144)\"]"
                            )
                        }
                    },
                    "required": ["expressions"]
                }
            },
            "metadata": {
                "type": "calculator",
                "precision": "Decimal",
                "pubfn_index": "000",
            }
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """执行计算器批量操作"""
        expressions = args.get("expressions", [])
        if not expressions or not isinstance(expressions, list):
            return {
                "type": "batch",
                "content": "计算失败：请提供有效的表达式数组（expressions）",
                "results": [],
                "summary": {"status": "error", "total": 0, "success": 0, "failed": 0}
            }

        if len(expressions) > cls.MAX_BATCH_SIZE:
            return {
                "type": "batch",
                "content": (
                    f"计算失败：表达式数量过多（{len(expressions)} 个），"
                    f"最大支持 {cls.MAX_BATCH_SIZE} 个。请分批计算。"
                ),
                "results": [],
                "summary": {"status": "error", "total": len(expressions), "success": 0, "failed": 0}
            }

        results = []
        for expr in expressions:
            result = cls._execute_single_expression(expr)
            results.append(result)

        return cls._format_batch_result(expressions, results)

    @classmethod
    def _execute_single_expression(cls, expression: str) -> Dict[str, Any]:
        """执行单个表达式计算"""
        if not expression or not isinstance(expression, str):
            return cls._format_error(
                expression or "",
                ValueError("请提供有效的数学表达式字符串"),
            )

        if len(expression) > cls.MAX_EXPRESSION_LENGTH:
            return {
                "type": "text",
                "content": (
                    f"计算失败：表达式过长（{len(expression)} 字符），"
                    f"最大支持 {cls.MAX_EXPRESSION_LENGTH} 字符。请拆分后分步计算。"
                ),
                "summary": {
                    "status": "error",
                    "expression": expression,
                    "error": "表达式过长",
                }
            }

        expression = cls._preprocess_expression(expression)

        with cls._state_lock:
            variables = {}
            if cls._last_result is not None:
                variables["ans"] = float(cls._last_result)
                expression = cls._replace_ans_aliases(expression)

            expression, preprocess_errors = cls._preprocess_unsupported_functions(
                expression, variables
            )
            if preprocess_errors:
                return cls._format_error(expression, preprocess_errors[0])

            try:
                result = math_engine.evaluate(expression, variables=variables)
            except Exception as e:
                return cls._format_error(expression, e)

            py_result, is_equation = cls._convert_result(result)

            if not is_equation and isinstance(result, Decimal):
                cls._last_result = result

        return cls._format_result(expression, py_result, is_equation)

    @classmethod
    def _format_batch_result(cls, expressions: List[str], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """格式化批量计算结果"""
        content_lines = []
        result_items = []
        success_count = 0
        failed_count = 0

        for i, (expr, result) in enumerate(zip(expressions, results)):
            is_error = result.get("summary", {}).get("status") == "error"
            if is_error:
                failed_count += 1
            else:
                success_count += 1

            result_content = result.get("content", "")
            content_lines.append(f"[{i+1}] {expr} = {result_content}")

            result_items.append({
                "index": i + 1,
                "expression": expr,
                "status": "error" if is_error else "success",
                "result": result.get("content", "") if not is_error else None,
                "error": result.get("content", "") if is_error else None,
            })

        if failed_count == 0:
            batch_status = "success"
        elif success_count > 0:
            batch_status = "partial"
        else:
            batch_status = "error"

        return {
            "type": "batch",
            "content": "\n".join(content_lines),
            "results": result_items,
            "summary": {
                "status": batch_status,
                "total": len(expressions),
                "success_count": success_count,
                "failed_count": failed_count,
            }
        }

    @classmethod
    def _preprocess_unsupported_functions(
        cls, expression: str, variables: Dict[str, Any]
    ) -> tuple:
        """预处理 math-engine 不支持的函数"""
        errors = []
        max_iterations = 10
        result_expr = expression

        for _ in range(max_iterations):
            new_expr, replaced, err = cls._replace_one_unsupported_function(
                result_expr, variables
            )
            if err:
                errors.append(err)
                return result_expr, errors
            if not replaced:
                break
            result_expr = new_expr

        return result_expr, errors

    @classmethod
    def _replace_one_unsupported_function(
        cls, expression: str, variables: Dict[str, Any]
    ) -> tuple:
        """替换表达式中最内层的一个 unsupported function 调用"""
        for func_name in cls._UNSUPPORTED_FUNCTIONS:
            keyword = func_name + "("
            idx = 0
            while idx < len(expression):
                pos = expression.lower().find(keyword, idx)
                if pos == -1:
                    break

                if pos > 0 and (expression[pos - 1].isalnum() or expression[pos - 1] == '_'):
                    idx = pos + 1
                    continue

                paren_start = pos + len(func_name)
                depth = 0
                i = paren_start
                while i < len(expression):
                    if expression[i] == '(':
                        depth += 1
                    elif expression[i] == ')':
                        depth -= 1
                        if depth == 0:
                            inner_expr = expression[paren_start + 1 : i]
                            try:
                                inner_result = math_engine.evaluate(
                                    inner_expr, variables=variables
                                )
                            except Exception:
                                break

                            func, _ = cls._UNSUPPORTED_FUNCTIONS[func_name]
                            try:
                                value = float(inner_result)
                                computed = func(value)
                            except Exception as e:
                                return expression, False, e

                            new_expr = (
                                expression[:pos] + str(computed) + expression[i + 1 :]
                            )
                            return new_expr, True, None
                    i += 1

                idx = pos + 1

        # 处理 round 函数
        pos = 0
        while pos < len(expression):
            pos = expression.lower().find("round(", pos)
            if pos == -1:
                break

            if pos > 0 and (expression[pos - 1].isalnum() or expression[pos - 1] == '_'):
                pos += 1
                continue

            paren_start = pos + 5
            depth = 0
            i = paren_start
            while i < len(expression):
                if expression[i] == '(':
                    depth += 1
                elif expression[i] == ')':
                    depth -= 1
                    if depth == 0:
                        full_inner = expression[paren_start + 1 : i]
                        comma_pos = cls._find_round_comma(full_inner)
                        if comma_pos == -1:
                            break

                        inner_expr = full_inner[:comma_pos]
                        digits_str = full_inner[comma_pos + 1:]

                        try:
                            inner_result = math_engine.evaluate(
                                inner_expr, variables=variables
                            )
                            digits_result = math_engine.evaluate(
                                digits_str, variables=variables
                            )
                        except Exception:
                            break

                        try:
                            value = float(inner_result)
                            digits = int(float(digits_result))
                            computed = round(value, digits)
                        except Exception as e:
                            return expression, False, e

                        new_expr = (
                            expression[:pos] + str(computed) + expression[i + 1 :]
                        )
                        return new_expr, True, None
                i += 1

            pos += 1

        return expression, False, None

    @staticmethod
    def _find_round_comma(expression: str) -> int:
        """在 round 函数参数中找到 depth=0 的逗号"""
        depth = 0
        for i, c in enumerate(expression):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 0:
                return i
        return -1

    @classmethod
    def reset_state(cls) -> None:
        """重置计算器状态"""
        with cls._state_lock:
            cls._last_result = None

    @classmethod
    def _preprocess_expression(cls, expression: str) -> str:
        """预处理表达式，修正 LLM 常见的输入格式错误"""
        result = []
        for char in expression:
            if char in cls._FULLWIDTH_MAP:
                result.append(cls._FULLWIDTH_MAP[char])
            elif 0xFF01 <= ord(char) <= 0xFF5E:
                result.append(chr(ord(char) - 0xFEE0))
            else:
                result.append(char)
        return "".join(result)

    @classmethod
    def _replace_ans_aliases(cls, expression: str) -> str:
        """将 ans 别名替换为标准变量名"""
        expression = expression.replace("上一步结果", "ans")
        expression = expression.replace("上一步", "ans")
        expression = expression.replace("previous", "ans")
        return expression

    @classmethod
    def _convert_result(cls, result: Any) -> tuple:
        """将 math-engine 结果转换为 Python 原生类型"""
        if isinstance(result, Decimal):
            if result == result.to_integral_value():
                return int(result), False
            return float(result), False

        if hasattr(result, '__iter__') and not isinstance(result, str):
            if isinstance(result, dict):
                converted = {}
                for k, v in result.items():
                    if isinstance(v, Decimal):
                        if v == v.to_integral_value():
                            converted[k] = int(v)
                        else:
                            converted[k] = float(v)
                    else:
                        converted[k] = v
                return converted, True

        return result, False

    @classmethod
    def _format_result(cls, expression: str, result: Any, is_equation: bool) -> Dict[str, Any]:
        """格式化计算结果为标准输出"""
        if is_equation and isinstance(result, dict):
            content_lines = [f"表达式: {expression}"]
            for var, val in result.items():
                content_lines.append(f"  {var} = {val}")
            content_lines.append("")
            content_lines.append(
                "[提示：以上为方程求解结果，已以结构化形式展示，"
                "请在回复中直接提供分析结论]"
            )
            return {
                "type": "text",
                "content": "\n".join(content_lines),
                "summary": {
                    "status": "success",
                    "expression": expression,
                    "result": result,
                }
            }

        return {
            "type": "single_value",
            "content": result,
            "name": expression,
            "unit": "",
            "summary": {
                "status": "success",
                "expression": expression,
                "result": result,
            }
        }

    @classmethod
    def _format_error(cls, expression: str, error: Exception) -> Dict[str, Any]:
        """格式化错误信息为 LLM 友好的输出"""
        error_msg = str(error)

        friendly_hints = {
            "division by zero": "除数不能为零",
            "unexpected character": (
                "表达式中存在无法识别的字符，可能使用了中文符号。"
                "建议检查：是否用 × 代替 *、÷ 代替 /、中文逗号代替英文逗号等"
            ),
            "missing": "表达式不完整，请检查括号是否匹配、运算符后是否缺少数值",
            "too long": "表达式过长，请拆分计算",
            "empty": "表达式为空，请提供有效的数学表达式",
            "unknown function": (
                "表达式中存在未识别的函数。"
                "支持的函数：sqrt、abs、round、sin、cos、tan、log、ceil、floor"
            ),
        }

        hint = ""
        for key, value in friendly_hints.items():
            if key in error_msg.lower():
                hint = f"\n\n修复建议：{value}"
                break

        return {
            "type": "text",
            "content": (
                f"计算失败：表达式 '{expression}' 有误。\n"
                f"错误详情：{error_msg}{hint}\n\n"
                f"请修正表达式后重新调用。"
            ),
            "summary": {
                "status": "error",
                "expression": expression,
                "error": str(error),
            }
        }


# 向后兼容别名
CalculatorFunction = PubfnCalculator
