# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_4_revise_if_needed.py
# @Desc    : Public Function (a101 step2_4): 条件性修订 VTS/SSTS 目标值 - 有缺失时才调用 LLM
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_4): 条件性修订 VTS/SSTS 目标值

功能：
1. 检查数据中是否有 value=None 的参数（缺失参数）
2. 如果没有缺失参数，直接返回原始数据（跳过 LLM 调用）
3. 如果有缺失参数，调用 llm_error_revision 工具进行修订

设计原则：
- 将跳过判断逻辑放在业务层，保持 llm_error_revision 的通用性
- 封装 step_a_prompt 和 step_b_prompt 的构建逻辑
- LLM 配置参数从配置文件读取，无需在调用时传递

必需参数（YAML 需显式声明）：
- targets: 待修订的目标值数据（含 vts_targets）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.core.work_log import WorkLogger


class A101Step2_4ReviseIfNeeded(AtomicFunction):
    """条件性修订 VTS/SSTS 目标值

    检查数据中是否有缺失参数，有则修订，无则跳过。
    """

    name: str = "step2_4_revise_if_needed"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "条件性修订 VTS/SSTS 目标值：\n"
                    "  - 检查数据中是否有 value=None 的参数\n"
                    "  - 有缺失时调用 llm_error_revision 修订\n"
                    "  - 无缺失时直接返回原始数据（跳过 LLM 调用）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "targets": {
                            "type": "object",
                            "description": "待修订的目标值数据（含 vts_targets）",
                        },
                    },
                    "required": ["targets"],
                },
            },
            "metadata": {
                "type": "conditional_revision",
                "pubfn_index": "a101_step2_4",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行条件性修订

        Args:
            args: 参数字典
            context: 可选上下文对象

        Returns:
            修订后的数据（或原始数据，如果跳过）
        """
        import time
        _t0 = time.time()

        targets = args.get("targets", {})

        if not targets:
            return targets

        # 检查是否有缺失参数
        missing_params = cls._find_missing_params(targets)

        if not missing_params:
            # 没有缺失参数，直接返回原始数据
            WorkLogger.info("Step2_4 修订：无缺失参数，跳过 LLM 调用")
            return targets

        # 估算传给 LLM 的 data 大小
        try:
            import json as _json
            _data_size = len(_json.dumps(targets, ensure_ascii=False))
        except Exception:
            pass

        # 有缺失参数，调用 llm_error_revision 进行修订
        WorkLogger.info(f"Step2_4 修订：发现 {len(missing_params)} 个缺失参数，开始 LLM 修订")

        result = cls._call_llm_revision(
            targets=targets,
            missing_params=missing_params,
        )

        _t1 = time.time()

        return result

    @classmethod
    def _flatten_to_list(cls, targets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将 targets 数据统一转换为扁平列表格式

        支持两种格式：
        1. 旧格式：{"vts_targets": [...]} 直接使用
        2. 新格式：{"sub_category": [{"二级专业": [{"VTS_items": [...], "SSTS_parameter": [...]}]}]}
           转换为扁平列表，并将 SSTS_parameter 关联到每个 VTS 项

        Args:
            targets: 目标值数据

        Returns:
            扁平列表格式的目标值
        """
        # 如果是旧格式（vts_targets 扁平列表），直接返回
        if "vts_targets" in targets:
            return targets.get("vts_targets", [])

        # 如果是新格式（嵌套结构），转换为扁平列表
        result = []
        sub_categories = targets.get("sub_category", [])

        if not sub_categories or not isinstance(sub_categories, list):
            return result

        for sub_cat_entry in sub_categories:
            if not isinstance(sub_cat_entry, dict):
                continue

            # 遍历二级专业分组
            for sub_cat_name, groups in sub_cat_entry.items():
                if not isinstance(groups, list):
                    continue

                for group in groups:
                    if not isinstance(group, dict):
                        continue

                    # 获取该组的 SSTS 参数（共享）
                    ssts_params = group.get("SSTS_parameter", [])
                    formula = group.get("计算公式", "")

                    # 获取该组的 VTS 项
                    vts_items = group.get("VTS_items", [])
                    for vts_item in vts_items:
                        if not isinstance(vts_item, dict):
                            continue

                        # 构造扁平项，包含 VTS 信息和共享的 SSTS 参数
                        flat_item = {
                            "name": vts_item.get("name", ""),
                            "db_key": vts_item.get("db_key", ""),
                            "value": vts_item.get("value"),
                            "unit": vts_item.get("unit", ""),
                            "confidence": vts_item.get("confidence", "low"),
                            "basis": vts_item.get("basis", ""),
                            "sub_category": sub_cat_name,
                            "计算公式": formula,
                            "SSTS_parameter": ssts_params  # 该组共享的 SSTS 参数
                        }
                        result.append(flat_item)

        return result

    @classmethod
    def _find_missing_params(cls, targets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """查找缺失参数（value=None 的项）

        支持两种输入格式：
        1. 旧格式：{"vts_targets": [...]}
        2. 新格式：{"sub_category": [...]}

        Args:
            targets: 目标值数据

        Returns:
            缺失参数列表
        """
        missing = []
        
        # 先将 targets 转换为扁平列表（兼容两种格式）
        vts_list = cls._flatten_to_list(targets)

        for vts in vts_list:
            # 检查 VTS 级别的 value
            if vts.get("value") is None:
                missing.append({
                    "level": "VTS",
                    "db_key": vts.get("db_key", ""),
                    "name": vts.get("name", ""),
                })

            # 检查 SSTS 级别的 value
            ssts_params = vts.get("SSTS_parameter", [])
            for ssts in ssts_params:
                if not isinstance(ssts, dict):
                    continue
                if ssts.get("value") is None:
                    missing.append({
                        "level": "SSTS",
                        "db_key": ssts.get("db_key", ""),
                        "name": ssts.get("name", ""),
                        "parent_vts": vts.get("db_key", ""),
                    })

        return missing

    @classmethod
    def _call_llm_revision(
        cls,
        targets: Dict[str, Any],
        missing_params: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """调用 llm_error_revision 进行修订

        Args:
            targets: 目标值数据
            missing_params: 缺失参数列表

        Returns:
            修订后的数据
        """
        try:
            from snail_avatar.backend.agents.core.tools.LLM_tools import get_llm_error_revision
            revision_tool = get_llm_error_revision()
        except Exception as e:
            WorkLogger.error(f"Step2_4 修订：获取 LLMErrorRevision 工具失败: {str(e)}")
            return targets

        # 构建 step_a_prompt
        step_a_prompt = cls._build_step_a_prompt(missing_params)
        
        # 构建 step_b_prompt
        step_b_prompt = cls._build_step_b_prompt()

        # 调用修订工具
        try:
            result = revision_tool.revise(
                data=targets,
                step_a_prompt=step_a_prompt,
                step_b_prompt=step_b_prompt,
            )

            # 处理结果
            if result.get("status") == "error":
                WorkLogger.warn(f"Step2_4 修订失败: {result.get('last_error', '未知错误')}")
                return targets

            WorkLogger.info(
                f"Step2_4 修订完成：状态={result.get('status')}, "
                f"迭代次数={result.get('attempts')}, "
                f"剩余问题={len(result.get('remaining_issues', []))}"
            )
            
            # 从结果中获取修订后的数据
            revised_data = result.get("revised_data") or result.get("data") or targets
            return revised_data

        except Exception as e:
            WorkLogger.error(f"Step2_4 修订异常: {type(e).__name__}: {str(e)[:200]}")
            return targets

    @classmethod
    def _build_step_a_prompt(cls, missing_params: List[Dict[str, Any]]) -> str:
        """构建 Step A prompt（待修订问题描述）

        Args:
            missing_params: 缺失参数列表

        Returns:
            Step A prompt
        """
        # 构建缺失参数的详细信息
        missing_details = []
        for param in missing_params:
            level = param.get("level", "")
            db_key = param.get("db_key", "")
            name = param.get("name", "")
            parent = param.get("parent_vts", "")
            
            if level == "VTS":
                missing_details.append(f"  - VTS参数: {name} (db_key: {db_key})")
            elif level == "SSTS":
                missing_details.append(f"  - SSTS参数: {name} (db_key: {db_key}, 所属VTS: {parent})")

        missing_text = "\n".join(missing_details)

        return f"""检查数据结构中 value 字段为 null 的参数，表示该参数缺失。

【缺失参数列表】
{missing_text}

【修订要求】
请为每个缺失的参数补充合理的初始值，要求：
1. 根据参数的 db_key、name、unit、所在的 VTS 上下文推断合理的初始值
2. 参考数据中其他已有 value 的同类参数，推断合理的数值
3. 根据参数的不确定性合理设置 confidence 等级（不确定时用 low，合理推断时用 medium）
4. basis 字段填写补充值的推断依据和计算过程
5. 如果 value 不为 null，保持原值不变，不要修改
6. 补充后请保持原有数据结构不变

【补充规则】
- 如果同类 VTS 的 value 已知，可参考其比例关系
- 如果有计算公式相关的参数，可根据公式推断
- 对于完全无法推断的参数，可设置为合理的默认值（如 0 或行业通用值）

请以 JSON 格式返回修订后的数据，保持原有数据结构不变。"""

    @classmethod
    def _build_step_b_prompt(cls) -> str:
        """构建 Step B prompt（达标标准描述）

        Returns:
            Step B prompt
        """
        return """验收标准：
1. 所有 vts_targets 中的参数 value 都不为 null（缺失参数已被填充）
2. 每个参数的 value 是合理的数值或字符串（不是 null、空字符串或无效值）
3. confidence 和 basis 字段已正确设置
4. 原有 value 不为 null 的参数保持不变

如果验收通过，返回 {"is_valid": true, "remaining_issues": [], "score": 100}
如果验收不通过，返回 {"is_valid": false, "remaining_issues": [{"description": "问题描述"}], "score": 分数}"""
