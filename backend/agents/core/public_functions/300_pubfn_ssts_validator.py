# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 300_pubfn_ssts_validator.py
# @Desc    : Public Function: SSTS 参数验证和转换
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (300): SSTS 参数验证和转换

提供 SSTS 参数的验证、转换和匹配功能：
1. 从 memorycore 获取有效的 SSTS db_key 列表
2. 构建 SSTS db_key 的哈希索引
3. 验证 LLM 输出的 SSTS 参数，删除编造的参数
4. 将LLM输出的SSTS基础名 base_key 转换为完整 db_key

约定默认（YAML 无需显式声明）：
- memory_db: 由框架自动注入（context.db）
- instance_key: 由框架自动注入
"""

from __future__ import annotations

from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnSstsValidator(AtomicFunction):
    """SSTS 参数验证 Public Function"""

    name: str = "ssts_validator"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "SSTS 参数验证和转换工具：\n"
                    "  - get_valid_ssts_db_keys: 获取有效的 SSTS db_key 列表\n"
                    "  - build_ssts_index: 构建 SSTS db_key 哈希索引\n"
                    "  - validate_and_convert_ssts: 验证并转换 SSTS 参数\n"
                    "  - match_db_key: 模糊匹配 db_key"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": [
                                "get_valid_ssts_db_keys",
                                "build_ssts_index",
                                "validate_and_convert_ssts",
                                "match_db_key",
                            ],
                            "description": "操作类型",
                        },
                        "mapping": {
                            "type": "object",
                            "description": "LLM 返回的 mapping（用于 validate_and_convert_ssts）",
                        },
                        "ssts_index": {
                            "type": "object",
                            "description": "SSTS 哈希索引 {基础名: 完整名}（用于 validate_and_convert_ssts）",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀（如 'reevlto'，用于 validate_and_convert_ssts）",
                        },
                        "llm_db_key": {
                            "type": "string",
                            "description": "LLM 返回的 db_key（用于 match_db_key）",
                        },
                        "process_data_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "process_data 中的 db_key 列表（用于 match_db_key）",
                        },
                        "valid_ssts_db_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "所有有效的 SSTS db_key（用于 build_ssts_index）",
                        },
                    },
                    "required": ["operation"],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "300",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 SSTS 验证原子操作

        根据 operation 字段分发到对应的方法。

        Args:
            args: 参数字典，必须包含 operation 字段
            context: 可选上下文对象

        Returns:
            对应操作的返回值
        """
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        try:
            if operation == "match_db_key":
                llm_db_key = args.get("llm_db_key", "")
                process_data_keys = args.get("process_data_keys", [])
                return cls.match_db_key(llm_db_key, process_data_keys)

            elif operation == "get_valid_ssts_db_keys":
                db = args.get("memory_db") or (context.db if context else None)
                vkey = args.get("instance_key", "")
                return cls.get_valid_ssts_db_keys(db, vkey)

            elif operation == "build_ssts_index":
                valid_ssts_db_keys = args.get("valid_ssts_db_keys", [])
                return cls.build_ssts_index(valid_ssts_db_keys)

            elif operation == "validate_and_convert_ssts":
                mapping = args.get("mapping", {})
                ssts_index = args.get("ssts_index", {})
                vehicle_suffix = args.get("vehicle_suffix", "")
                
                # 如果 mapping 包含 vts_ssts_mapping 数组，需要遍历处理
                if isinstance(mapping, dict) and 'vts_ssts_mapping' in mapping:
                    vts_ssts_mapping = mapping.get('vts_ssts_mapping', [])
                    validated_mapping_list = []
                    for item in vts_ssts_mapping:
                        if isinstance(item, dict):
                            validated_item = cls.validate_and_convert_ssts(item, ssts_index, vehicle_suffix)
                            validated_mapping_list.append(validated_item)
                        else:
                            validated_mapping_list.append(item)
                    
                    # 更新 mapping 中的 vts_ssts_mapping
                    mapping['vts_ssts_mapping'] = validated_mapping_list
                    return mapping
                elif isinstance(mapping, list):
                    # 如果 mapping 本身就是列表
                    validated_list = []
                    for item in mapping:
                        if isinstance(item, dict):
                            validated_item = cls.validate_and_convert_ssts(item, ssts_index, vehicle_suffix)
                            validated_list.append(validated_item)
                        else:
                            validated_list.append(item)
                    return validated_list
                else:
                    # 单个 mapping 项
                    return cls.validate_and_convert_ssts(mapping, ssts_index, vehicle_suffix)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    # ==================================================================
    # 验证方法
    # ==================================================================

    @classmethod
    def match_db_key(cls, llm_db_key: str, process_data_keys: list) -> str:
        """模糊匹配 db_key

        将 LLM 返回的 db_key 与 process_data 中的 db_key 进行模糊匹配，
        支持 _result_ → _target_ 转换、逐级缩减匹配、基础名匹配等策略。

        Args:
            llm_db_key: LLM 返回的 db_key，如 "cd_wt_result_reevlto"
            process_data_keys: process_data 中的 db_key 列表

        Returns:
            匹配的 db_key，未匹配返回 None
        """
        if llm_db_key in process_data_keys:
            return llm_db_key

        if '_result_' in llm_db_key:
            llm_db_key = llm_db_key.replace('_result_', '_target_')

        for key in process_data_keys:
            key_parts = key.split('_')
            while len(key_parts) > 1:
                reduced_key = '_'.join(key_parts)
                if llm_db_key == reduced_key:
                    return key
                key_parts = key_parts[:-1]

        if '_' in llm_db_key:
            llm_base = '_'.join(llm_db_key.rsplit('_', 2)[:-1])
            if llm_base.count('_') >= 1:
                llm_base = '_'.join(llm_base.rsplit('_', 1)[:-1])

                for key in process_data_keys:
                    if '_' in key:
                        key_base = '_'.join(key.rsplit('_', 2)[:-1])
                        if '_' in key_base:
                            key_base = '_'.join(key_base.rsplit('_', 1)[:-1])
                            if llm_base == key_base:
                                return key

        return None

    @classmethod
    def get_valid_ssts_db_keys(cls, db, instance_key: str) -> list:
        """从 memorycore 获取所有有效的 SSTS db_key 列表

        Args:
            db: MemoryDatabase 实例
            instance_key: memorycore 键名

        Returns:
            list: 所有有效的 SSTS db_key
                  如 ["cd_style_result_reevlto", "cd_style_target_reevlto", ...]
        """
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data

        if not db or not instance_key:
            return []
        
        ssts_data = get_sheet_data(db, instance_key, "target_ssts")
        
        valid_keys = []

        if ssts_data and isinstance(ssts_data, dict):
            for cat1, cat2_dict in ssts_data.items():
                if isinstance(cat2_dict, dict):
                    for cat2, param_list in cat2_dict.items():
                        if isinstance(param_list, list):
                            for param in param_list:
                                if isinstance(param, dict):
                                    param_values = param.get("参数值", [])
                                    if isinstance(param_values, list):
                                        for pv in param_values:
                                            if isinstance(pv, dict) and pv.get("db_key"):
                                                valid_keys.append(pv["db_key"])

        return valid_keys

    @classmethod
    def build_ssts_index(cls, valid_ssts_db_keys: list) -> dict:
        """构建 SSTS db_key 的哈希索引

        将完整的 db_key 映射到基础名，便于快速查找和匹配。
        对于 _target_ 和 _result_ 冲突，优先保留 _target_。

        Args:
            valid_ssts_db_keys: 所有有效的 SSTS db_key

        Returns:
            dict: {基础名: 完整名}
                  如 {"cd_style": "cd_style_result_reevlto", ...}
        """
        from snail_avatar.backend.core.work_log import WorkLogger

        index = {}
        conflicts = []

        for key in valid_ssts_db_keys:
            base_key = key
            if '_result_' in key:
                base_key = key.split('_result_')[0]
            elif '_target_' in key:
                base_key = key.split('_target_')[0]

            if base_key in index:
                existing_value = index[base_key]
                if '_target_' in key and '_result_' in existing_value:
                    conflicts.append(f"{base_key}: {existing_value} → {key}")
                    index[base_key] = key
                else:
                    conflicts.append(f"{base_key}: {key} (已存在 {existing_value})")
            else:
                index[base_key] = key

        if conflicts:
            WorkLogger.warn(f"SSTS db_key索引冲突: {len(conflicts)} 个冲突")
            for conflict in conflicts[:5]:
                WorkLogger.warn(f"  - {conflict}")
            if len(conflicts) > 5:
                WorkLogger.warn(f"  ... 还有 {len(conflicts) - 5} 个冲突")

        return index

    @classmethod
    def validate_and_convert_ssts(
        cls, mapping: dict, ssts_index: dict, vehicle_suffix: str
    ) -> dict:
        """验证 SSTS 参数并转换 db_key 格式（支持 sub_category 分组结构）

        功能：
        1. 删除编造的 SSTS 参数（不存在于 memorycore 中的参数）
        2. 将基础名 db_key 转换为完整 db_key（基础名 + _target_ + 车型后缀）
        3. 如果所有 SSTS 参数都被删除，删除计算公式

        Args:
            mapping: LLM 返回的 structured_data，包含 sub_category 分组结构
            ssts_index: 哈希索引 {基础名: 完整名}
            vehicle_suffix: 车型后缀（如 "reevlto"）

        Returns:
            dict: 处理后的 structured_data
        """
        from snail_avatar.backend.core.work_log import WorkLogger

        # 新格式：sub_category 分组结构
        sub_categories = mapping.get("sub_category", [])
        
        # 如果 sub_category 为空，尝试从 content 中提取
        if not sub_categories and 'content' in mapping and isinstance(mapping['content'], dict):
            content = mapping['content']
            sub_categories = content.get("sub_category", [])
        
        # 如果还为空，尝试从 structured_data 中提取
        if not sub_categories and 'structured_data' in mapping:
            structured_data = mapping['structured_data']
            if isinstance(structured_data, dict):
                sub_categories = structured_data.get("sub_category", [])
        
        if not sub_categories:
            WorkLogger.warn("未找到 sub_category 字段")
            return mapping

        total_deleted = 0
        total_fixed = 0
        validated_groups = []

        for group in sub_categories:
            if not isinstance(group, dict):
                continue
            for sub_cat_name, group_list in group.items():
                # 防御兼容：Stage 2 可能将 list 包装去掉，改为 dict 格式
                if isinstance(group_list, dict):
                    group_list = [group_list]
                if not isinstance(group_list, list):
                    continue

                validated_list = []
                for group_idx, group_content in enumerate(group_list):
                    if not isinstance(group_content, dict):
                        continue

                    # 防御兼容：同时检查单数和复数形式的 SSTS 字段名
                    ssts_parameters = group_content.get("SSTS_parameter") or group_content.get("SSTS_parameters", [])
                    # 防御兼容：同时检查中文和英文公式字段名
                    if "计算公式" not in group_content and "calculation_method" in group_content:
                        group_content["计算公式"] = group_content.pop("calculation_method")
                    vts_items = group_content.get("VTS_items", [])

                    # 防御兼容：Stage 2 可能将 SSTS 数据降级为字符串数组
                    if ssts_parameters and isinstance(ssts_parameters, list):
                        ssts_parameters = cls._normalize_ssts_format(ssts_parameters)

                    if not ssts_parameters:
                        if "SSTS_parameter" in group_content:
                            del group_content["SSTS_parameter"]
                        if "计算公式" in group_content:
                            del group_content["计算公式"]
                        if vts_items:
                            vts_names = [v.get("name", "未知") for v in vts_items]
                            WorkLogger.warn(f"二级专业「{sub_cat_name}」无SSTS参数，已删除SSTS_parameter和计算公式")
                        validated_list.append(group_content)
                        continue

                    validated_ssts = []
                    deleted_count = 0
                    fixed_count = 0

                    for ssts_idx, ssts in enumerate(ssts_parameters):
                        base_db_key = ssts.get("db_key", "")
                        
                        if not base_db_key:
                            deleted_count += 1
                            continue

                        if '_target_' not in base_db_key and '_result_' not in base_db_key:
                            target_key = f"{base_db_key}_target_{vehicle_suffix}"
                        else:
                            target_key = base_db_key

                        matched_key = ssts_index.get(target_key)

                        if not matched_key:
                            lookup_key = base_db_key
                            if '_result_' in lookup_key:
                                lookup_key = lookup_key.split('_result_')[0]
                            elif '_target_' in lookup_key:
                                lookup_key = lookup_key.split('_target_')[0]
                            matched_key = ssts_index.get(lookup_key)

                        if matched_key:
                            if matched_key != base_db_key:
                                ssts["db_key"] = matched_key
                                fixed_count += 1
                            validated_ssts.append(ssts)
                        else:
                            deleted_count += 1
                            WorkLogger.warn(f"SSTS参数验证失败：删除编造参数 {base_db_key}")

                    total_deleted += deleted_count
                    total_fixed += fixed_count

                    if not validated_ssts:
                        if "SSTS_parameter" in group_content:
                            del group_content["SSTS_parameter"]
                        if "计算公式" in group_content:
                            del group_content["计算公式"]
                        if vts_items:
                            vts_names = [v.get("name", "未知") for v in vts_items]
                            WorkLogger.warn(f"二级专业「{sub_cat_name}」的所有SSTS参数均为编造，已删除")
                    else:
                        group_content["SSTS_parameter"] = validated_ssts

                    validated_list.append(group_content)

                validated_groups.append({sub_cat_name: validated_list})

        mapping["sub_category"] = validated_groups
        WorkLogger.info(f"SSTS验证完成：删除 {total_deleted} 个编造参数，转换 {total_fixed} 个db_key")
        return mapping

    @staticmethod
    def _normalize_ssts_format(ssts_parameters: List[Any]) -> List[Dict[str, Any]]:
        """将 Stage 2 异常格式的 SSTS 参数规范化为标准对象数组格式

        处理场景：Stage 2 LLM 可能将 SSTS 参数从对象数组 [{"db_key": "xxx", ...}]
        降级为字符串数组 ["xxx", "yyy"]，此方法将其恢复为对象数组。

        Args:
            ssts_parameters: 原始 SSTS 参数列表

        Returns:
            List[Dict]: 规范化后的对象数组，每个元素至少包含 db_key 字段
        """
        if not ssts_parameters:
            return []

        normalized = []
        for item in ssts_parameters:
            if isinstance(item, dict):
                # 已是标准格式，直接保留
                normalized.append(item)
            elif isinstance(item, str) and item.strip():
                # 字符串格式，包装为对象
                normalized.append({"db_key": item.strip(), "name": item.strip()})

        return normalized
