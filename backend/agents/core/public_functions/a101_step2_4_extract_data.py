# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_4_extract_data.py
# @Desc    : Public Function (a101 step2_4): 初版目标值定义步骤数据提取
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_4): 初版目标值定义步骤数据提取

为 step2_4 (DEFINE_INITIAL) 提供数据提取能力：
1. get_product_info: 从 step_results 提取产品定义信息
2. get_mappings: 从 process_data.vts_category_data 提取 VTS/SSTS 映射关系（全量）
3. get_filtered_mappings: 提取映射关系，过滤掉 DB 中已有值的 SSTS → LLM 只需要填未定义的
4. get_defined_ssts_db: 获取 DB 中已定义的 SSTS 字典（供 post_process 回填时使用）
5. get_references: 从 step_results 提取法规要求及参考数据

核心设计：
  一个 SSTS 参数可能被多个专业（空气动力学→动力性→经济性）共享引用。
  当空气动力学先跑完 step2_4 后，DB 里就有了 cd_style_target_reevlto 的值。
  后续动力性、经济性 step2_4 不再需要 LLM 重新定义这些共享 SSTS——
  直接从 DB 取值即可，LLM 只需要关注本专业独有的、DB 里还没有值的 SSTS。

  get_filtered_mappings 负责：过滤掉 DB 已有值的 SSTS，只给 LLM 看"未定义的"。
  get_defined_ssts_db 负责：把 DB 已定义的 SSTS 字典传给 post_process（validate/save），
                              让 validate_targets 不要把"被过滤的 SSTS"当成缺失，
                              让 save_targets 回填时用 DB 值覆盖 process_data。

数据来源：
- process_data: vts_category_data 字段（VTS/SSTS 映射数据）
- memory_db: SSTS target value 存储（通过 set_ssts_vts_param 写入）
- step_results: 其他步骤的结果（产品定义、法规参考等）

必需参数（YAML 需显式声明）：
- sandbox: 沙箱实例
- operation: 操作类型
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import iter_flat_items


class A101Step2_4ExtractData(AtomicFunction):
    """Step2_4 数据提取 Public Function"""

    name: str = "step2_4_extract_data"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "Step2_4 专属数据提取工具。提供以下操作：\n"
                    "  - get_product_info: 从 step_results 提取产品定义信息\n"
                    "  - get_mappings: 从 process_data 提取 VTS/SSTS 映射关系\n"
                    "  - get_references: 从 step_results 提取法规要求及参考数据"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": (
                                "操作类型：\n"
                                "  get_product_info / get_mappings / get_references"
                            ),
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                    },
                    "required": ["operation", "sandbox"],
                },
            },
            "metadata": {
                "type": "data_extract",
                "pubfn_index": "a101_step2_4",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行数据提取

        Args:
            args: 参数字典，必须包含 operation 和 sandbox；
                  professional_category/vehicle_suffix 由框架自动注入
            context: Agent 实例（由 execute() 第 2 参数传入）
        """
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        sandbox = args.get("sandbox") or (getattr(context, "sandbox", None) if context else None)

        try:
            if operation == "get_product_info":
                return cls.extract_product_info(sandbox, args)
            elif operation == "get_mappings":
                return cls.extract_mappings(sandbox, args)
            elif operation == "get_filtered_mappings":
                return cls.extract_filtered_mappings(sandbox, args)
            elif operation == "get_defined_ssts_db":
                return cls.extract_defined_ssts_db(sandbox, args)
            elif operation == "get_references":
                return cls.extract_references(sandbox, args)
            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    # ==================================================================
    # 从 step_results 提取产品定义信息
    # ==================================================================

    @classmethod
    def extract_product_info(cls, sandbox: Any, args: Dict[str, Any]) -> str:
        """从 step_results 提取产品定义信息

        从 ANALYZE_PRODUCT 步骤结果中获取产品定义信息。

        Args:
            sandbox: 沙箱实例
            args: 步骤参数（包含 professional_category, vehicle_suffix）

        Returns:
            str: 产品定义信息 JSON 字符串
        """
        if not sandbox:
            return "{}"

        category = args.get("professional_category", "")

        try:
            # key 格式为 {category}_{step_id}，如 "空气动力学_ANALYZE_PRODUCT"
            full_step_id = f"{category}_ANALYZE_PRODUCT" if category else "ANALYZE_PRODUCT"
            step_result = sandbox.get_step_result(full_step_id)

            if not step_result:
                step_result = sandbox.get_step_result("ANALYZE_PRODUCT")
        except Exception:
            step_result = None

        if not step_result:
            return "{}"

        structured_data = step_result.get("structured_data", {})
        product_info = structured_data.get("product_information", [])

        if not product_info:
            return "{}"

        result = {
            "product_information": product_info
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ==================================================================
    # 从 process_data 提取 VTS/SSTS 映射关系
    # ==================================================================

    @classmethod
    def extract_mappings(cls, sandbox: Any, args: Dict[str, Any]) -> str:
        """从 process_data.vts_category_data 提取 VTS/SSTS 映射关系

        Args:
            sandbox: 沙箱实例
            args: 步骤参数（包含 professional_category）

        Returns:
            str: VTS/SSTS 映射关系 JSON 字符串
        """
        if not sandbox:
            return "{}"

        category = args.get("professional_category", "")

        try:
            vts_category_data = sandbox.get_process_data("vts_category_data")
        except Exception as e:
            vts_category_data = None

        if not vts_category_data or not isinstance(vts_category_data, dict):
            return "{}"

        category_data = vts_category_data.get(category, {})
        
        if not isinstance(category_data, dict) or not category_data:
            return "{}"

        # 格式化为所需的结构
        mappings = cls._format_vts_mappings(category_data, category)
        return json.dumps(mappings, ensure_ascii=False, indent=2)

    # ==================================================================
    # 从 DB 查询已定义的 SSTS 参数（公共辅助）
    # ==================================================================

    @classmethod
    def _query_defined_ssts_db(
        cls, memory_db: Any, instance_key: str
    ) -> Dict[str, Dict[str, Any]]:
        """从 DB 查询所有已定义（target value 非空）的 SSTS 参数

        遍历 target_ssts sheet 拿到所有 SSTS target db_key，
        再查 memory_db.get_ssts_vts_param(db_key) 是否有有效值。

        Args:
            memory_db: MemoryDatabase 实例
            instance_key: memorycore 中的车型键名

        Returns:
            dict: {db_key: {"name": str, "value": Any, "unit": str}}
                  只包含 DB 中 target value 非空的 SSTS
        """
        defined: Dict[str, Dict[str, Any]] = {}

        if not memory_db or not instance_key:
            return defined

        # 1. 从 target_ssts sheet 获取所有 SSTS target db_key + 权威 name
        sheet_data = get_sheet_data(memory_db, instance_key, "target_ssts")
        if not sheet_data:
            return defined

        for item in iter_flat_items(sheet_data):
            name = str(item.get("name", "")).strip()
            raw_unit = item.get("单位")
            unit = str(raw_unit).strip() if raw_unit is not None else ""
            target_db_key = item.get("目标值_db_key", "")

            if not target_db_key:
                continue

            # 2. 查 memory_db 中这个 db_key 的值是否已定义
            val = cls._read_db_value(memory_db, target_db_key)
            if val is not None:
                defined[target_db_key] = {"name": name, "value": val, "unit": unit}

        return defined

    @staticmethod
    def _read_db_value(memory_db: Any, db_key: str) -> Any:
        """从 memory_db 读取单个 db_key 的 target value

        Returns:
            值（float/str 等）；空值（None, NaN, 空字符串）统一返回 None
        """
        try:
            val = memory_db.get_ssts_vts_param(db_key)
            if val is None:
                return None
            if isinstance(val, float) and math.isnan(val):
                return None
            if isinstance(val, str) and val.strip() == "":
                return None
            return val
        except Exception:
            return None

    # ==================================================================
    # get_filtered_mappings：从 process_data 提取映射，过滤掉 DB 已定义的 SSTS
    # ==================================================================

    @classmethod
    def extract_filtered_mappings(cls, sandbox: Any, args: Dict[str, Any]) -> str:
        """提取 VTS/SSTS 映射关系，过滤掉 DB 中已有 target value 的 SSTS

        LLM 只需要关注"未定义"的 SSTS；已定义的由前置专业（或本专业之前的二级专业）
        step2_4 写入 DB，可以直接引用。

        同时生成"已定义 SSTS 参考文本"，拼入 mappings_json 的顶层，
        让 LLM 知道哪些值已经确定、是多少。

        Args:
            sandbox: 沙箱实例
            args: 包含 professional_category, memory_db, instance_key

        Returns:
            str: 过滤后的映射 JSON 字符串
        """
        if not sandbox:
            return "{}"

        category = args.get("professional_category", "")
        memory_db = args.get("memory_db")
        instance_key = args.get("instance_key", "")

        try:
            vts_category_data = sandbox.get_process_data("vts_category_data")
        except Exception:
            vts_category_data = None

        if not vts_category_data or not isinstance(vts_category_data, dict):
            return "{}"

        category_data = vts_category_data.get(category, {})
        if not isinstance(category_data, dict) or not category_data:
            return "{}"

        # 1. 查 DB 已定义的 SSTS
        defined_ssts = cls._query_defined_ssts_db(memory_db, instance_key)

        # 2. 过滤每个二级专业的 SSTS_parameter
        sub_category_list = []
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue

            vts_items = group_content.get("VTS_items", [])
            all_ssts = group_content.get("SSTS_parameter", [])
            formula = group_content.get("计算公式", "")

            # 按 db_key 分两组：已定义 vs 未定义
            undefined_ssts = []
            for ssts in all_ssts:
                if not isinstance(ssts, dict):
                    continue
                db_key = ssts.get("db_key", "")
                if db_key and db_key in defined_ssts:
                    # 已定义：跳过（不展示给 LLM）
                    continue
                undefined_ssts.append(ssts)

            group = {
                "VTS_items": vts_items,
                "SSTS_parameter": undefined_ssts,  # ★ 只含未定义的
                "计算公式": formula,
            }
            sub_category_list.append({sub_cat_name: [group]})

        mappings = {
            "专业": category,
            "sub_category": sub_category_list,
        }

        # 3. 在 mappings 顶层加一个"已定义 SSTS 参考"文本块
        #    让 LLM 知道这些值已经确定，不要重复定义
        if defined_ssts:
            ref_lines = ["【已由前置专业定义的SSTS参数（值已确定，本专业直接引用）】"]
            for db_key, info in defined_ssts.items():
                ref_lines.append(
                    f"- {info['name']} {db_key} = {info['value']} {info['unit']}".strip()
                )
            ref_lines.append("")
            ref_lines.append("本专业只需定义未在上面列出的 SSTS 参数。")
            mappings["已定义SSTS参考"] = "\n".join(ref_lines)

        return json.dumps(mappings, ensure_ascii=False, indent=2)

    # ==================================================================
    # get_defined_ssts_db：获取 DB 中已定义的 SSTS 字典（供 post_process 使用）
    # ==================================================================

    @classmethod
    def extract_defined_ssts_db(cls, sandbox: Any, args: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """返回 DB 中已定义的 SSTS 字典

        供 validate_targets 做 baseline 过滤、供 save_targets 回填时用 DB 值覆盖。

        Returns:
            dict: {db_key: {"name": str, "value": Any, "unit": str}}
        """
        memory_db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        return cls._query_defined_ssts_db(memory_db, instance_key)

    # ==================================================================
    # 从 step_results 提取法规要求及参考数据
    # ==================================================================

    @classmethod
    def extract_references(cls, sandbox: Any, args: Dict[str, Any]) -> str:
        """从 step_results 提取法规要求及参考数据

        从 CHECK_REGULATIONS_AND_REFERENCES 步骤结果中获取法规和参考数据。

        Args:
            sandbox: 沙箱实例
            args: 步骤参数（包含 professional_category）

        Returns:
            str: 法规要求及参考数据 JSON 字符串
        """
        if not sandbox:
            return "{}"

        category = args.get("professional_category", "")

        try:
            # key 格式为 {category}_{step_id}，如 "空气动力学_CHECK_REGULATIONS_AND_REFERENCES"
            full_step_id = f"{category}_CHECK_REGULATIONS_AND_REFERENCES" if category else "CHECK_REGULATIONS_AND_REFERENCES"
            step_result = sandbox.get_step_result(full_step_id)

            if not step_result:
                step_result = sandbox.get_step_result("CHECK_REGULATIONS_AND_REFERENCES")
        except Exception:
            step_result = None

        if not step_result:
            return "{}"

        structured_data = step_result.get("structured_data", {})
        
        # 提取法规和参考数据
        regulations = structured_data.get("regulations", [])
        references = structured_data.get("VTS/SSTS_references", {})

        result = {
            "regulations": regulations,
            "VTS/SSTS_references": references
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ==================================================================
    # 辅助方法
    # ==================================================================

    @classmethod
    def _format_vts_mappings(cls, category_data: Dict, category: str) -> Dict:
        """将嵌套 VTS 格式按二级专业分组输出

        输出格式：按二级专业分组，每组包含 VTS_items、SSTS_parameter 和计算公式。
        避免同一 SSTS 参数在多个 VTS 中重复，体现 VTS 间的关联性。

        Args:
            category_data: 嵌套结构 {二级专业: {VTS_items, SSTS_parameter, 计算公式}}
            category: 专业分类

        Returns:
            dict: 格式化后的映射数据（嵌套结构）
        """
        sub_category_list = []

        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue

            vts_items = group_content.get("VTS_items", [])
            ssts_params = group_content.get("SSTS_parameter", [])
            formula = group_content.get("计算公式", "")

            # 构造二级专业组，包含 VTS 列表、共享的 SSTS 参数和计算公式
            group = {
                "VTS_items": vts_items,
                "SSTS_parameter": ssts_params,
                "计算公式": formula
            }

            sub_category_list.append({sub_cat_name: [group]})

        return {
            "专业": category,
            "sub_category": sub_category_list
        }
