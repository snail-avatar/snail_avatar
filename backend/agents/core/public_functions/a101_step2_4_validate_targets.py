# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_4_validate_targets.py
# @Desc    : Public Function (a101 step2_4): 验证 LLM 输出的 VTS/SSTS 目标值
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_4): 验证 LLM 输出的 VTS/SSTS 目标值

以沙箱中本专业的 VTS/SSTS 为基准，验证 LLM 输出：
- 无遗漏：基准中的每个参数都必须在输出中
- 无幻觉：输出中的每个 db_key 必须在基准中存在

★ 新增 defined_ssts_db 参数：
  当 DB 中已有其他专业（如空气动力学）定义的 SSTS 时，
  这些 SSTS 会在 data_sources 阶段被过滤掉（不展示给 LLM），
  因此验证时也不应将它们当作"缺失"。
  defined_ssts_db 中的 db_key 会从 baseline 中排除。

验证规则：
1. LLM 输出的 db_key 在基准中存在 → 保留
2. LLM 输出的 db_key 不在基准中 → 删除（幻觉）
3. 基准中的 db_key 在 LLM 输出中缺失 → 补充占位，value 设为 None
   （defined_ssts_db 中的 db_key 不触发此补充，因为它们不是本 step 要填的）

必需参数（YAML 需显式声明）：
- sandbox: 沙箱实例
- professional_category: 专业分类
- result: LLM 输出的 structured_data

可选参数：
- defined_ssts_db: DB 中已定义的 SSTS 字典（{db_key: {name, value, unit}}）
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.core.work_log import WorkLogger


class A101Step2_4ValidateTargets(AtomicFunction):
    """验证 LLM 输出的 VTS/SSTS 目标值"""

    name: str = "step2_4_validate_targets"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "验证 LLM 输出的 VTS/SSTS 目标值：\n"
                    "  以沙箱中本专业的 VTS/SSTS 为基准，验证无遗漏、无幻觉。\n"
                    "  删除幻觉参数，标记缺失参数。\n"
                    "  defined_ssts_db 中的 db_key 不参与验证（已由前置专业定义）。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类",
                        },
                        "result": {
                            "type": "object",
                            "description": "LLM 输出的 structured_data",
                        },
                        "defined_ssts_db": {
                            "type": "object",
                            "description": "DB 中已定义的 SSTS 字典（可选）",
                        },
                    },
                    "required": ["sandbox", "professional_category", "result"],
                },
            },
            "metadata": {
                "type": "validation",
                "pubfn_index": "a101_step2_4",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行验证"""
        sandbox = args.get("sandbox")
        category = args.get("professional_category", "")
        result = args.get("result", {})
        defined_ssts_db = args.get("defined_ssts_db") or {}

        return cls.validate_targets(sandbox, category, result, defined_ssts_db)

    @classmethod
    def validate_targets(
        cls,
        sandbox: Any,
        category: str,
        result: Dict[str, Any],
        defined_ssts_db: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """验证 LLM 输出的目标值

        Args:
            sandbox: 沙箱实例
            category: 专业分类
            result: LLM 输出的 structured_data
            defined_ssts_db: DB 中已定义的 SSTS 字典，这些 db_key 不参与 baseline 校验

        Returns:
            验证后的 targets 数据（扁平列表格式）+ 验证报告
        """
        defined_ssts_db = defined_ssts_db or {}

        try:
            if not sandbox or not category:
                WorkLogger.warn(f"Step2_4 验证：缺少必要参数 sandbox={bool(sandbox)}, category={bool(category)}")
                return {"vts_targets": [], "validation_report": {"status": "error", "message": "缺少必要参数"}}

            # 1. 从沙箱获取基准数据（嵌套结构）
            vts_category_data = sandbox.get_process_data("vts_category_data") or {}
            category_data = vts_category_data.get(category, {})

            if not category_data or not isinstance(category_data, dict):
                WorkLogger.warn(f"Step2_4 验证：process_data 中不存在专业 {category} 的 VTS 基准数据")
                return {"vts_targets": [], "validation_report": {"status": "warning", "message": f"无基准数据"}}

            # ========= DEBUG: 基准数据全貌 =========
            baseline_total_vts = 0
            baseline_total_ssts = 0
            for sc_name, sc_content in category_data.items():
                if isinstance(sc_content, dict):
                    v_count = len([v for v in sc_content.get("VTS_items", []) if isinstance(v, dict)])
                    s_count = len([s for s in sc_content.get("SSTS_parameter", []) if isinstance(s, dict)])
                    baseline_total_vts += v_count
                    baseline_total_ssts += s_count

            # 2. 提取基准 db_key 集合（排除已定义的 SSTS）
            baseline_db_keys = cls._extract_baseline_db_keys(category_data, defined_ssts_db)

            # 3. 从 LLM 输出中提取目标值
            llm_vts_targets = cls._extract_llm_targets(result)

            # 4. 验证
            validated_vts, report = cls._validate_vts_targets(
                llm_vts_targets, baseline_db_keys, category_data, defined_ssts_db
            )

            # ========= DEBUG: 验证结果 =========
            for i, v in enumerate(validated_vts):
                ssts = v.get("SSTS_parameter", [])
                ssts_with_value = [s for s in ssts if s.get("value") is not None]
                ssts_none = [s for s in ssts if s.get("value") is None]


            WorkLogger.info(
                f"Step2_4 验证完成：保留 {report['validated_count']} 个，"
                f"删除幻觉 {report['hallucination_count']} 个，"
                f"补充缺失 {report['missing_count']} 个"
            )

            return {
                "vts_targets": validated_vts,
                "validation_report": report
            }

        except Exception as e:
            WorkLogger.error(f"Step2_4 验证失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"vts_targets": [], "validation_report": {"status": "error", "message": str(e)}}

    @classmethod
    def _extract_llm_targets(cls, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 LLM 输出中提取目标值，兼容两种格式

        Returns:
            扁平列表格式的目标值
        """
        if not isinstance(result, dict):
            return []

        # 旧格式（vts_targets 扁平列表）
        if "vts_targets" in result:
            return result.get("vts_targets", [])

        # 新格式（sub_category 嵌套结构），转换为扁平列表
        result_list = []
        sub_categories = result.get("sub_category", [])

        if not sub_categories or not isinstance(sub_categories, list):
            return result_list

        for sub_cat_entry in sub_categories:
            if not isinstance(sub_cat_entry, dict):
                continue

            for sub_cat_name, groups in sub_cat_entry.items():
                if not isinstance(groups, list):
                    continue

                for group in groups:
                    if not isinstance(group, dict):
                        continue

                    ssts_params = group.get("SSTS_parameter", [])
                    formula = group.get("计算公式", "")
                    vts_items = group.get("VTS_items", [])

                    for vts_item in vts_items:
                        if not isinstance(vts_item, dict):
                            continue

                        flat_item = {
                            "name": vts_item.get("name", ""),
                            "db_key": vts_item.get("db_key", ""),
                            "value": vts_item.get("value"),
                            "unit": vts_item.get("unit", ""),
                            "confidence": vts_item.get("confidence", "low"),
                            "basis": vts_item.get("basis", ""),
                            "sub_category": sub_cat_name,
                            "计算公式": formula,
                            "SSTS_parameter": ssts_params
                        }
                        result_list.append(flat_item)

        return result_list

    @classmethod
    def _extract_baseline_db_keys(
        cls,
        category_data: Dict,
        defined_ssts_db: Dict[str, Any],
    ) -> set:
        """从基准数据中提取所有 db_key 集合

        排除 defined_ssts_db 中的 SSTS db_key——这些已由前置专业定义，
        不属于本 step2_4 要验证/补充的范围。

        VTS db_key 不排除——VTS 总是需要验证的。
        """
        db_keys = set()
        defined_keys = set(defined_ssts_db.keys()) if defined_ssts_db else set()

        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue

            # VTS 级别的 db_key（全部收集，不排除）
            vts_items = group_content.get("VTS_items", [])
            for vts_item in vts_items:
                if not isinstance(vts_item, dict):
                    continue
                param_values = vts_item.get("param_values", [])
                for pv in param_values:
                    key = pv.get("db_key", "")
                    if key:
                        db_keys.add(key)

            # SSTS 级别的 db_key（排除已定义的）
            ssts_params = group_content.get("SSTS_parameter", [])
            for ssts in ssts_params:
                if not isinstance(ssts, dict):
                    continue
                key = ssts.get("db_key", "")
                if key and key not in defined_keys:
                    db_keys.add(key)

        return db_keys

    @classmethod
    def _validate_vts_targets(
        cls,
        llm_vts_targets: List[Dict[str, Any]],
        baseline_db_keys: set,
        category_data: Dict,
        defined_ssts_db: Dict[str, Any],
    ) -> tuple:
        """验证 VTS 目标值列表

        baseline_db_keys 已经排除了 defined_ssts_db 中的 SSTS db_key，
        所以 LLM 不需要输出这些 SSTS——它们被省略不被当成缺失。
        """
        validated = []
        hallucination_count = 0
        missing_count = 0
        processed_baseline_keys = set()

        # 建立 VTS db_key → 基准组的索引
        vts_key_to_group = {}
        defined_keys = set(defined_ssts_db.keys()) if defined_ssts_db else set()

        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            vts_items = group_content.get("VTS_items", [])
            ssts_params = group_content.get("SSTS_parameter", [])
            # 从基准 SSTS 中排除已定义的（后续补充时也不补这些）
            undefined_baseline_ssts = [
                s for s in ssts_params
                if isinstance(s, dict) and s.get("db_key", "") not in defined_keys
            ]
            for vts_item in vts_items:
                if not isinstance(vts_item, dict):
                    continue
                for pv in vts_item.get("param_values", []):
                    key = pv.get("db_key", "")
                    if key:
                        vts_key_to_group[key] = {
                            "vts_item": vts_item,
                            "ssts_params": undefined_baseline_ssts,  # ★ 只用未定义的做基准
                            "all_ssts_params": ssts_params,  # 全量的用于后续回填
                            "sub_cat_name": sub_cat_name,
                        }

        # 处理 LLM 输出的 VTS
        for vts_target in llm_vts_targets:
            vts_db_key = cls._get_vts_db_key(vts_target)

            if not vts_db_key or vts_db_key not in baseline_db_keys:
                hallucination_count += 1
                continue

            # 验证 SSTS_parameter（只保留在 baseline 里的——已排除了 defined）
            validated_ssts = []
            for ssts_target in vts_target.get("SSTS_parameter", []):
                ssts_db_key = ssts_target.get("db_key", "")
                if ssts_db_key in baseline_db_keys:
                    validated_ssts.append(ssts_target)
                else:
                    hallucination_count += 1

            validated_vts = {
                "name": vts_target.get("name", ""),
                "db_key": vts_db_key,
                "value": vts_target.get("value"),
                "unit": vts_target.get("unit", ""),
                "confidence": vts_target.get("confidence", "low"),
                "basis": vts_target.get("basis", ""),
                "SSTS_parameter": validated_ssts
            }
            validated.append(validated_vts)
            processed_baseline_keys.add(vts_db_key)

        # 不再进行任何补充操作——validate 只负责删除幻觉，
        # 不负责补 None 占位。LLM 未输出的参数（如去重后后续 sub_category 的 SSTS）
        # 不会被补占位，也不触发 revise_if_needed。
        # save_targets 通过 llm_ssts_by_key 扁平索引按 db_key 唯一写入，天然支持去重模式。

        report = {
            "status": "success",
            "validated_count": len(validated),
            "hallucination_count": hallucination_count,
            "missing_count": missing_count,
            "message": f"验证完成：保留 {len(validated)} 个，删除幻觉 {hallucination_count} 个，补充缺失 {missing_count} 个"
        }

        return validated, report

    @classmethod
    def _get_vts_db_key(cls, vts_target: Dict[str, Any]) -> str:
        """获取 VTS 目标值的 db_key"""
        db_key = vts_target.get("db_key", "")
        if db_key:
            return db_key

        param_values = vts_target.get("param_values", [])
        if param_values:
            return param_values[0].get("db_key", "")

        return ""
