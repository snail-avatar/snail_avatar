# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_6_update_targets.py
# @Desc    : Public Function (a101 step2_6): 优化SSTS - 更新目标值
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_6): 优化SSTS - 更新目标值

为 step2_6 (OPTIMIZE_SSTS) 提供后处理能力：

1. update_optimized_targets: 读取Agent输出的 optimized_SSTS_items，
   按 db_key 匹配，将优化后的 SSTS 参数值同步写入：
   - memory core（持久化数据库）
   - 沙箱 process_data.vts_category_data（流程内数据源）

数据流：
- 输入: Agent 结果中的 structured_data.optimized_SSTS_items
- 处理: db_key 后缀转换 _result_ → _target_
- 输出: 同时写入 memory_db 和 sandbox.process_data

必需参数（YAML 需显式声明）：
- operation: 操作类型
- memory_db: 内存数据库实例
- sandbox: 沙箱实例
- result: Agent结果JSON字符串
- professional_category: 当前专业名
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_6UpdateTargets(AtomicFunction):
    """Step2_6 优化目标值更新 Public Function"""

    name: str = "step2_6_update_targets"

    @staticmethod
    def _safe_float(value: Any) -> Any:
        """安全地将 LLM 输出的 value 转换为 float 类型。

        LLM 可能将数值以字符串形式输出（如 "3.6" 而非 3.6），
        此方法统一将其转换为 float；对于非数字字符串（如 "WLTC"、"BEV"），
        保留原始字符串值不做转换；NaN 值统一转为 None。
        """
        if value is None:
            return None
        if isinstance(value, float):
            if math.isnan(value):
                return None
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, str):
            try:
                result = float(value.strip())
                if math.isnan(result):
                    return None
                return result
            except (ValueError, TypeError):
                # 非数字字符串（如 "WLTC"、"BEV"），保留原值
                return value
        # 其他类型（如 bool），直接返回原值
        return value

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_6 专属目标值更新工具。提供以下操作：\n"
                    "  - update_optimized_targets: 将优化后的SSTS参数值写入memory core和沙箱"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "操作类型：update_optimized_targets",
                        },
                        "memory_db": {
                            "type": "object",
                            "description": "内存数据库实例",
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "result": {
                            "type": ["string", "object"],
                            "description": "Agent格式化后的JSON结果字符串或对象",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "当前专业分类名称",
                        },
                    },
                    "required": ["operation", "memory_db", "result"],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "a101_step2_6",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行目标值更新

        Args:
            args: 参数字典
            context: Agent 实例

        Returns:
            更新结果摘要
        """
        operation = args.get("operation", "")
        if not operation:
            return {"success": False, "message": "必须提供 operation 参数"}

        try:
            if operation == "update_optimized_targets":
                return cls.update_optimized_targets(args)

            else:
                return {"success": False, "message": f"未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"success": False, "message": f"执行失败：{str(e)}"}

    @classmethod
    def update_optimized_targets(cls, args: Dict[str, Any]) -> Dict[str, Any]:
        """将Agent输出的优化SSTS参数值写入memory core和沙箱process_data

        流程：
        1. 解析 $result JSON，获取 optimized_SSTS_items
        2. 遍历每个优化项，将 _result_ 后缀转换为 _target_
        3. 写入 memory core（持久化数据库）
        4. 同步更新 sandbox.process_data.vts_category_data 中的 SSTS 值
        5. 返回更新结果摘要

        Args:
            args: 参数字典（含 memory_db, sandbox, result, professional_category）

        Returns:
            Dict: 更新结果摘要
        """
        from snail_avatar.backend.core.work_log import WorkLogger

        memory_db = args.get("memory_db")
        sandbox = args.get("sandbox")
        result_str = args.get("result", "")
        instance_key = args.get("instance_key", "")
        professional_category = args.get("professional_category", "")

        WorkLogger.info(
            f"Step2_6 优化SSTS更新开始: 专业={professional_category}, "
            f"instance_key={instance_key}"
        )

        if not memory_db:
            WorkLogger.warn("Step2_6 优化SSTS更新: 缺少 memory_db，跳过DB写入")
            return {"success": False, "message": "缺少 memory_db"}

        # 1. 解析 Agent 结果
        try:
            if isinstance(result_str, str):
                data = json.loads(result_str)
            elif isinstance(result_str, dict):
                data = result_str
            else:
                WorkLogger.warn(
                    f"Step2_6 优化SSTS更新: result 类型异常 {type(result_str)}"
                )
                return {"success": False, "message": f"result 类型异常: {type(result_str)}"}
        except (json.JSONDecodeError, ValueError) as e:
            WorkLogger.error(f"Step2_6 优化SSTS更新: JSON解析失败 {str(e)}")
            return {"success": False, "message": f"JSON解析失败: {str(e)}"}

        if not isinstance(data, dict):
            WorkLogger.warn("Step2_6 优化SSTS更新: result 格式异常，非字典类型")
            return {"success": False, "message": "result 格式异常：非字典类型"}

        structured_data = data.get("structured_data", {})
        if not isinstance(structured_data, dict):
            structured_data = {}

        optimized_items = structured_data.get("optimized_SSTS_items", [])
        if not isinstance(optimized_items, list):
            optimized_items = []

        if not optimized_items:
            WorkLogger.info("Step2_6 优化SSTS更新: 无需要更新的SSTS参数")
            return {"success": True, "message": "无需要更新的SSTS参数", "updated_count": 0}

        # 2. 预处理：同时构建 target 和 result 两个后缀的写入映射
        #    step2_6 判定需要修改的 SSTS 参数，target（目标值）和 result（当前值）都要改
        write_map = {}  # {db_key: optimized_value} — 包含 target 和 result 两种后缀
        ssts_base_value_map = {}  # {基础db_key: optimized_value} — 用于沙箱 process_data 回填

        for item in optimized_items:
            if not isinstance(item, dict):
                continue
            db_key = item.get("db_key", "")
            optimized_value = item.get("optimized_value")
            if not db_key or optimized_value is None:
                continue

            # 根据 db_key 后缀，同时生成 target 和 result 两个写入 key
            if "_result_" in db_key:
                # LLM 输出 result 后缀 → 同时写 result + target
                result_db_key = db_key
                target_db_key = db_key.replace("_result_", "_target_")
                base_db_key = db_key.split("_result_")[0]  # 去掉后缀的基础 key
            elif "_target_" in db_key:
                # LLM 输出 target 后缀 → 同时写 target + result
                target_db_key = db_key
                result_db_key = db_key.replace("_target_", "_result_")
                base_db_key = db_key.split("_target_")[0]
            else:
                # 无后缀 → 只写原始 key（无法推断 target/result 对应关系）
                write_map[db_key] = optimized_value
                ssts_base_value_map[db_key] = optimized_value
                continue

            write_map[target_db_key] = optimized_value
            write_map[result_db_key] = optimized_value
            ssts_base_value_map[base_db_key] = optimized_value

        WorkLogger.info(
            f"Step2_6 优化SSTS更新: 准备写入 {len(write_map)} 个DB条目 "
            f"（target+result 双写），涉及 {len(ssts_base_value_map)} 个 SSTS 参数"
        )

        # 3. 写入 memory core（同时写 target 和 result 后缀的 key）
        success_count = 0
        fail_count = 0
        results = []

        for db_key, optimized_value in write_map.items():
            try:
                numeric_value = cls._safe_float(optimized_value)
                if hasattr(memory_db, 'set_ssts_vts_param'):
                    memory_db.set_ssts_vts_param(db_key, numeric_value)
                    results.append({
                        "db_key": db_key,
                        "value": numeric_value,
                        "status": "success"
                    })
                    success_count += 1
                    WorkLogger.info(
                        f"Step2_6 写入DB: {db_key} = {numeric_value}"
                    )
                else:
                    results.append({
                        "db_key": target_db_key,
                        "value": optimized_value,
                        "status": "fail",
                        "reason": "memory_db 缺少 set_ssts_vts_param 方法"
                    })
                    fail_count += 1
                    WorkLogger.warn(
                        f"Step2_6 写入DB失败: memory_db 缺少 set_ssts_vts_param 方法"
                    )
            except Exception as e:
                results.append({
                    "db_key": target_db_key,
                    "value": optimized_value,
                    "status": "fail",
                    "reason": str(e)
                })
                fail_count += 1
                WorkLogger.error(
                    f"Step2_6 写入DB异常: {target_db_key} = {optimized_value}, 错误: {str(e)}"
                )

        # 4. 同步写回沙箱 process_data（更新 SSTS_parameter 的 value 字段，即 result 值）
        sandbox_updated = 0
        if sandbox and professional_category and ssts_base_value_map:
            sandbox_updated = cls._update_process_data(
                sandbox, professional_category, ssts_base_value_map
            )

        WorkLogger.info(
            f"Step2_6 优化SSTS更新完成: 专业={professional_category}, "
            f"DB写入成功={success_count}, 失败={fail_count}, "
            f"沙箱更新={sandbox_updated}"
        )

        return {
            "success": True,
            "message": (
                f"SSTS目标值更新完成: 成功={success_count}, "
                f"失败={fail_count}, 沙箱更新={sandbox_updated}"
            ),
            "updated_count": success_count,
            "failed_count": fail_count,
            "sandbox_updated": sandbox_updated,
            "details": results
        }

    @classmethod
    def _update_process_data(cls, sandbox: Any, category: str,
                             key_value_map: Dict[str, Any]) -> int:
        """将优化后的 SSTS 值同步写回沙箱 process_data.vts_category_data

        在 vts_category_data 中找到当前专业的嵌套结构，
        按二级专业组遍历 SSTS_parameter 列表，按 db_key 匹配并替换 value。

        Args:
            sandbox: 沙箱实例
            category: 专业分类名
            key_value_map: {db_key: optimized_value} 映射

        Returns:
            int: 更新的条目数量
        """
        from snail_avatar.backend.core.work_log import WorkLogger

        try:
            vts_category_data = sandbox.get_process_data("vts_category_data")
            if not isinstance(vts_category_data, dict):
                WorkLogger.warn(
                    f"Step2_6 沙箱更新: vts_category_data 格式异常，跳过"
                )
                return 0

            # 获取当前专业的嵌套结构（新结构：{二级专业: {VTS_items, SSTS_parameter, 计算公式}}）
            category_data = vts_category_data.get(category, {})
            if not isinstance(category_data, dict) or not category_data:
                WorkLogger.warn(
                    f"Step2_6 沙箱更新: 专业 {category} 的VTS数据为空"
                )
                return 0

            updated_count = 0
            # 按二级专业组遍历
            for sub_cat_name, group_content in category_data.items():
                if not isinstance(group_content, dict):
                    continue

                # 组级别的 SSTS_parameter
                ssts_params = group_content.get("SSTS_parameter", [])
                if not isinstance(ssts_params, list):
                    continue

                for ssts_item in ssts_params:
                    if not isinstance(ssts_item, dict):
                        continue
                    ssts_db_key = ssts_item.get("db_key", "")
                    if ssts_db_key in key_value_map:
                        old_value = ssts_item.get("value", "N/A")
                        # 统一将 value 转为 float 类型（处理 LLM 输出可能为字符串的情况）
                        new_value = cls._safe_float(key_value_map[ssts_db_key])
                        ssts_item["value"] = new_value
                        updated_count += 1
                        WorkLogger.info(
                            f"Step2_6 沙箱更新: [{sub_cat_name}] {ssts_db_key} {old_value} → {new_value}"
                        )

            # 写回沙箱
            if updated_count > 0:
                vts_category_data[category] = category_data
                sandbox.set_process_data("vts_category_data", vts_category_data)

            return updated_count

        except Exception as e:
            WorkLogger.error(
                f"Step2_6 沙箱更新异常: {str(e)}"
            )
            return 0
