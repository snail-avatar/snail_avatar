# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_2_save_process_data.py
# @Desc    : Public Function (a101 step2_2): SSTS 映射信息合并到 process_data
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_2): SSTS 映射信息合并到 process_data

将 LLM 输出的 sub_category 分组结构与 sandbox process_data 中的 VTS 数据
按二级专业匹配，将 SSTS 参数和计算公式合并回填到对应的二级专业组中。

process_data 中 vts_category_data 的结构：{专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: ""}}, ...}

必需参数（YAML 需显式声明）：
- step_id: 步骤ID（用于从沙箱取步骤结果）
- sandbox: 沙箱实例

约定默认（YAML 无需显式声明）：
- professional_category: 由框架自动注入
- context: 由 execute() 第 2 参数传入
"""

from __future__ import annotations

from snail_avatar.backend.core.work_log import WorkLogger

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class A101Step2_2SaveProcessData(AtomicFunction):
    """SSTS 映射合并到 process_data Public Function"""

    name: str = "save_to_process_data"

    # 缓存 embedding 实例，避免重复初始化
    _embedding_instance = None
    _embedding_cache = {}  # 缓存标准名的向量

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "将 SSTS 映射信息合并到 process_data：\n"
                    "  从步骤结果提取 sub_category 分组结构，按二级专业匹配，\n"
                    "  将 SSTS_parameter 和计算公式回填到对应二级专业组。\n"
                    "  process_data 中 vts_category_data 结构：{专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: \"\"}}, ...}\n"
                    "professional_category 自动注入；step_id 和 sandbox 需显式声明。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "step_id": {
                            "type": "string",
                            "description": "步骤ID（用于从沙箱取步骤结果）",
                        },
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                    },
                    "required": ["step_id", "sandbox"],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "a101_step2_2",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 process_data 合并

        Args:
            args: 参数字典，需包含 step_id 和 sandbox；
                  professional_category 由框架自动注入到顶层
            context: Agent 实例（由 execute() 第 2 参数传入）
        """
        step_id = args.get("step_id", "")
        sandbox = args.get("sandbox")
        ctx = args.get("context") or context

        return cls.merge_ssts_to_process_data(step_id, sandbox, ctx, args)

    # ==================================================================
    # 合并方法
    # ==================================================================

    @classmethod
    def merge_ssts_to_process_data(
        cls, step_id: str, sandbox: Any, context: Any, args: Dict[str, Any]
    ) -> None:
        """将 SSTS 映射信息合并保存到 process_data

        优先使用传入的 mapping 参数（验证后的数据），如果没有则从 sandbox 读取步骤结果。
        与 process_data 中的 vts_category_data 匹配，按二级专业将 SSTS 参数和计算公式合并。

        process_data 中 vts_category_data 结构：{专业名: {二级专业: {VTS_items: [...], SSTS_parameter: [], 计算公式: ""}}, ...}

        Args:
            step_id: 步骤ID
            sandbox: 沙箱实例
            context: Agent 实例
            args: 参数字典（含 professional_category、mapping 可选）
        """
        import importlib

        _ssts_mod = importlib.import_module(
            "snail_avatar.backend.agents.core.public_functions.300_pubfn_ssts_validator"
        )
        PubfnSstsValidator = _ssts_mod.PubfnSstsValidator

        try:
            category = args.get("professional_category", "")
            
            if not category:
                return

            # 获取 sub_category 分组结构
            mapping_data = args.get("mapping")
            sub_categories = []
            
            if mapping_data:
                if isinstance(mapping_data, dict):
                    sub_categories = mapping_data.get("sub_category", [])
                    if not sub_categories and "structured_data" in mapping_data:
                        structured_data = mapping_data["structured_data"]
                        if isinstance(structured_data, dict):
                            sub_categories = structured_data.get("sub_category", [])
                    elif not sub_categories:
                        # 深度搜索 sub_category
                        for key in mapping_data.keys():
                            val = mapping_data[key]
                            if isinstance(val, dict) and "sub_category" in val:
                                sub_categories = val.get("sub_category", [])
                                break
                        # 如果有 content 字段且是 dict，也搜索 content 内部
                        if not sub_categories and 'content' in mapping_data and isinstance(mapping_data['content'], dict):
                            content = mapping_data['content']
                            for key in content.keys():
                                val = content[key]
                                if isinstance(val, dict) and "sub_category" in val:
                                    sub_categories = val.get("sub_category", [])
                                    break
                                elif isinstance(val, dict):
                                    for subkey in val.keys():
                                        subval = val[subkey]
                                        if isinstance(subval, dict) and "sub_category" in subval:
                                            sub_categories = subval.get("sub_category", [])
                                            break
            else:
                # Fallback: 从 sandbox 读取步骤结果
                full_step_id = f"{category}_{step_id}"
                step_result = sandbox.get_step_result(full_step_id)
                if not step_result:
                    step_result = sandbox.get_step_result(step_id)

                if not step_result:
                    return

                structured_data = step_result.get("structured_data", {})
                sub_categories = structured_data.get("sub_category", [])

            if not sub_categories:
                WorkLogger.warn(f"步骤 {step_id}：未找到 sub_category 数据")
                return

            # 获取 process_data 中的 VTS 数据（新嵌套结构）
            vts_category_data = sandbox.get_process_data("vts_category_data") or {}
            category_data = vts_category_data.get(category, {})
            
            if not category_data:
                WorkLogger.warn(f"步骤 {step_id}：process_data 中不存在专业 {category} 的 VTS 数据")
                return

            # 执行合并：按二级专业匹配
            merged_count = 0
            unmatched_subcats = []
            ssts_backfilled_count = 0  # 新增：追踪SSTS回填数量

            for group in sub_categories:
                if not isinstance(group, dict):
                    continue
                for sub_cat_name, group_list in group.items():
                    if not isinstance(group_list, list):
                        continue

                    # 获取 LLM 返回的该二级专业组内容
                    for group_content in group_list:
                        if not isinstance(group_content, dict):
                            continue

                        # 兼容 VTS_items 和 VTS_item（单复数）
                        llm_vts_items = (
                            group_content.get("VTS_items", []) 
                            or group_content.get("VTS_item", [])
                        )
                        # 兼容 SSTS_parameter 和 SSTS_parameters（单复数）
                        llm_ssts_params = (
                            group_content.get("SSTS_parameter", []) 
                            or group_content.get("SSTS_parameters", [])
                        )
                        # 兼容 计算公式 和 calculation_formulas（中英文）
                        llm_formula = (
                            group_content.get("计算公式", "") 
                            or group_content.get("calculation_formulas", "")
                        )
                        # 如果 calculation_formulas 是字典格式，转换为字符串
                        if isinstance(llm_formula, dict):
                            llm_formula = "; ".join([f"{k} = {v}" for k, v in llm_formula.items()])

                        # 读取 category_mapping（用于名称标准化）
                        category_mapping = sandbox.get_process_data("category_mapping") or {}

                        # 检查 process_data 中是否存在该二级专业
                        if sub_cat_name not in category_data:
                            try:
                                # 两阶段名称标准化（失败会直接抛异常）
                                normalized_name = cls._normalize_sub_category_name(
                                    sub_cat_name, category_mapping, category
                                )
                                
                                # 使用标准化后的名称重新匹配
                                if normalized_name in category_data:
                                    sub_cat_name = normalized_name  # 使用标准化名称
                                else:
                                    # 这里理论上不会走到，因为 _normalize_sub_category_name 会在失败时抛异常
                                    error_msg = (
                                        f"二级专业名称映射异常: "
                                        f"'{sub_cat_name}' -> '{normalized_name}'，但标准化名称仍未匹配到"
                                    )
                                    WorkLogger.error(error_msg)
                                    raise RuntimeError(error_msg)
                                    
                            except (ValueError, RuntimeError) as e:
                                # 名称映射失败，直接报错（严格策略）
                                error_msg = (
                                    f"专业「{category}」的二级专业「{sub_cat_name}」"
                                    f"名称映射失败: {e}"
                                )
                                WorkLogger.error(error_msg)
                                raise RuntimeError(error_msg)

                        # 匹配二级专业组
                        target_group = category_data[sub_cat_name]
                        current_ssts = target_group.get("SSTS_parameter", [])

                        # 收集该组所有 VTS param_values 的 db_key 及其基础名（去掉 _target_xxx 后缀）
                        vts_db_keys_set = set()
                        vts_base_names_set = set()
                        for vi in llm_vts_items:
                            for pv in vi.get("param_values", []):
                                key = pv.get("db_key", "")
                                if key:
                                    vts_db_keys_set.add(key)
                                    # 去掉 _target_xxx 后缀得到基础名
                                    if "_target_" in key:
                                        vts_base_names_set.add(key.split("_target_")[0])

                        # 1. 回填 SSTS_parameter（组级别共享）
                        #    过滤掉 db_key 与 VTS param_values 重复的项（直接对应公式不应有 SSTS）
                        #    同时兜底补全后缀：如果 db_key 只有基础名（不含 _target_ / _result_），补上 _target_{suffix}
                        if llm_ssts_params:
                            # 从 VTS db_key 中提取 vehicle_suffix（如 "reevlto"）
                            vehicle_suffix = ""
                            for vts_key in vts_db_keys_set:
                                if "_target_" in vts_key:
                                    vehicle_suffix = vts_key.split("_target_")[1]
                                    break

                            filtered_ssts = []
                            for ssts in llm_ssts_params:
                                ssts_key = ssts.get("db_key", "")
                                if not ssts_key:
                                    continue
                                # 检查1：SSTS db_key 是否直接等于某个 VTS db_key
                                if ssts_key in vts_db_keys_set:
                                    WorkLogger.info(
                                        f"过滤重复 SSTS: '{sub_cat_name}' 组 "
                                        f"SSTS db_key='{ssts_key}' 与 VTS db_key 完全相同，已移除"
                                    )
                                    continue
                                # 检查2：SSTS db_key 是否等于某个 VTS 的基础名（SSTS 无后缀 vs VTS 有后缀）
                                if ssts_key in vts_base_names_set:
                                    WorkLogger.info(
                                        f"过滤重复 SSTS: '{sub_cat_name}' 组 "
                                        f"SSTS db_key='{ssts_key}' 与 VTS 基础名相同（补全后缀后会重复），已移除"
                                    )
                                    continue
                                # 兜底补后缀：如果 db_key 不含 _target_ 或 _result_，说明只有基础名
                                if "_target_" not in ssts_key and "_result_" not in ssts_key and vehicle_suffix:
                                    original_key = ssts_key
                                    ssts_key = f"{ssts_key}_target_{vehicle_suffix}"
                                    ssts["db_key"] = ssts_key
                                    WorkLogger.info(
                                        f"补全 SSTS 后缀: '{sub_cat_name}' 组 "
                                        f"'{original_key}' → '{ssts_key}'"
                                    )
                                filtered_ssts.append(ssts)
                            target_group["SSTS_parameter"] = filtered_ssts
                            ssts_backfilled_count += 1

                        # 2. 回填 计算公式
                        if llm_formula:
                            target_group["计算公式"] = llm_formula

                        # 3. 回填 VTS_items 中的 param_values（按 db_key 匹配）
                        target_vts_items = target_group.get("VTS_items", [])
                        for llm_vts in llm_vts_items:
                            llm_db_keys = []
                            for pv in llm_vts.get("param_values", []):
                                key = pv.get("db_key", "")
                                if key:
                                    llm_db_keys.append(key)

                            if not llm_db_keys:
                                continue

                            # 在目标 VTS_items 中查找匹配项
                            for target_vts in target_vts_items:
                                target_db_keys = []
                                for pv in target_vts.get("param_values", []):
                                    key = pv.get("db_key", "")
                                    if key:
                                        target_db_keys.append(key)

                                matched = False
                                for llm_key in llm_db_keys:
                                    matched_key = PubfnSstsValidator.match_db_key(llm_key, target_db_keys)
                                    if matched_key:
                                        matched = True
                                        break

                                if matched:
                                    # 回填 VTS 参数信息
                                    if llm_vts.get("name"):
                                        target_vts["name"] = llm_vts["name"]
                                    if llm_vts.get("unit"):
                                        target_vts["unit"] = llm_vts["unit"]
                                    merged_count += 1

            vts_category_data[category] = category_data
            sandbox.set_process_data("vts_category_data", vts_category_data)
            
            if unmatched_subcats:
                WorkLogger.warn(f"步骤 {step_id}：以下二级专业未匹配到 process_data：{unmatched_subcats}")
            WorkLogger.info(f"步骤 {step_id} process_data 更新完成：匹配 {merged_count} 个 VTS 项")

        except Exception as e:
            WorkLogger.error(f"步骤 {step_id} 保存 process_data 失败: {str(e)}")
            import traceback
            traceback.print_exc()

    # ==================================================================
    # 两阶段名称映射方法（严格报错策略）
    # ==================================================================

    @classmethod
    def _get_embedding(cls):
        """获取嵌入模型实例（缓存）"""
        if cls._embedding_instance is None:
            from snail_avatar.backend.core.tools.embedding import MultiModalEmbedding
            cls._embedding_instance = MultiModalEmbedding()
        return cls._embedding_instance

    @classmethod
    def _cosine_similarity(cls, vec1: list, vec2: list) -> float:
        """计算余弦相似度"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    @classmethod
    def _vector_similarity_match(
        cls, llm_name: str, standard_names: list, threshold: float = 0.7
    ) -> str:
        """Stage 2: 基于向量余弦相似度的名称匹配

        严格策略：如果匹配失败，抛出异常。

        Args:
            llm_name: LLM 输出的名称
            standard_names: 标准名称列表
            threshold: 相似度阈值

        Returns:
            str: 最佳匹配的标准名

        Raises:
            ValueError: 匹配失败时抛出
            RuntimeError: embedding 服务不可用时抛出
        """
        try:
            embedding = cls._get_embedding()
        except Exception as e:
            error_msg = f"[名称映射] embedding 服务不可用: {e}"
            WorkLogger.error(error_msg)
            raise RuntimeError(error_msg)

        # 计算 LLM 名称的向量
        llm_vec = embedding.embed_text(llm_name)
        if llm_vec is None:
            error_msg = f"[名称映射] embedding 向量化失败: '{llm_name}'"
            WorkLogger.error(error_msg)
            raise RuntimeError(error_msg)

        # 计算所有标准名的向量（带缓存）
        best_score = 0.0
        best_name = None

        for std_name in standard_names:
            # 从缓存获取或计算标准名向量
            if std_name in cls._embedding_cache:
                std_vec = cls._embedding_cache[std_name]
            else:
                std_vec = embedding.embed_text(std_name)
                if std_vec is not None:
                    cls._embedding_cache[std_name] = std_vec

            if std_vec is None:
                continue

            # 计算相似度
            similarity = cls._cosine_similarity(llm_vec, std_vec)
            if similarity > best_score:
                best_score = similarity
                best_name = std_name

        # 严格策略：匹配失败直接报错
        if best_score < threshold:
            error_msg = (
                f"[名称映射] 向量化匹配失败: "
                f"'{llm_name}' 与标准名列表 {standard_names} "
                f"最高相似度仅为 {best_score:.3f}，低于阈值 {threshold}"
            )
            WorkLogger.error(error_msg)
            raise ValueError(error_msg)

        WorkLogger.info(
            f"向量化匹配成功: '{llm_name}' -> '{best_name}' "
            f"(相似度={best_score:.3f})"
        )
        return best_name

    @classmethod
    def _normalize_sub_category_name(
        cls,
        llm_name: str,
        category_mapping: dict,
        professional_category: str,
    ) -> str:
        """两阶段名称标准化（严格报错策略）

        Stage 1: 精确匹配（字典查找）
        Stage 2: 向量化匹配（余弦相似度）

        严格策略：如果 Stage 2 也失败，直接抛出异常。

        Args:
            llm_name: LLM 输出的二级专业名
            category_mapping: process_data 中的映射表
            professional_category: 当前一级专业名

        Returns:
            str: 标准化后的名称

        Raises:
            ValueError: Stage 2 匹配失败时抛出
            RuntimeError: embedding 服务不可用时抛出
        """
        # ========== Stage 1: 精确匹配 ==========

        # 1. 从全局索引查找
        sub_index = category_mapping.get("sub_category_index", {})
        if llm_name in sub_index:
            result = sub_index[llm_name]
            if result != llm_name:
                WorkLogger.info(f"精确匹配（全局索引）: '{llm_name}' -> '{result}'")
            return result

        # 2. 从专业映射查找
        cat_mapping = category_mapping.get("category_mapping", {})
        cat_data = cat_mapping.get(professional_category, {})
        if llm_name in cat_data:
            result = cat_data[llm_name]
            if result != llm_name:
                WorkLogger.info(f"精确匹配（专业映射）: '{llm_name}' -> '{result}'")
            return result

        # ========== Stage 2: 向量化匹配（严格报错）==========
        standard_names = list(cat_data.keys())
        if not standard_names:
            error_msg = (
                f"[名称映射] 无法向量化匹配："
                f"专业 '{professional_category}' 无标准名列表"
            )
            WorkLogger.error(error_msg)
            raise ValueError(error_msg)

        WorkLogger.warning(
            f"精确匹配失败，尝试向量化匹配: "
            f"'{llm_name}' vs {standard_names}"
        )
        
        # Stage 2 失败会直接抛出异常
        return cls._vector_similarity_match(llm_name, standard_names)
