# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step2_4_save_targets.py
# @Desc    : Public Function (a101 step2_4): 将验证后的目标值回填沙箱和写入DB
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step2_4): 将验证后的目标值回填沙箱和写入DB

功能：
1. 将验证后的 VTS/SSTS 目标值回填到沙箱的 process_data 中
2. 按 db_key 匹配，将 value 写入 memory_db

★ defined_ssts_db 设计：
  当 DB 中已有前置专业定义的 SSTS（如空气动力学定义了 cd_style）时，
  process_data 的 SSTS_parameter 仍包含全量 SSTS，但 LLM 输出只有未定义的。
  回填时：
  - defined_ssts_db 里有的 db_key → 直接用 DB 值（来自前置专业的 step2_4）
  - 其他 db_key → 用 LLM 输出的值（来自本 step2_4）

这样 process_data 里所有 SSTS（不管是哪个专业定义的）都有正确的值。

回填字段：
- value: 目标值
- confidence: 置信度
- basis: 设定依据

必需参数（YAML 需显式声明）：
- sandbox: 沙箱实例
- memory_db: 内存数据库实例
- instance_key: 车型键名
- targets: 验证后的 targets 数据（含 vts_targets）

可选参数：
- defined_ssts_db: DB 中已定义的 SSTS 字典（{db_key: {name, value, unit}}）
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction
from snail_avatar.backend.core.work_log import WorkLogger


class A101Step2_4SaveTargets(AtomicFunction):
    """将验证后的目标值回填沙箱和写入DB"""

    name: str = "step2_4_save_targets"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "将验证后的 VTS/SSTS 目标值回填沙箱和写入DB：\n"
                    "  1. 回填 value/confidence/basis 到 process_data\n"
                    "  2. 按 db_key 写入 memory_db"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sandbox": {
                            "type": "object",
                            "description": "沙箱实例",
                        },
                        "memory_db": {
                            "type": "object",
                            "description": "内存数据库实例",
                        },
                        "instance_key": {
                            "type": "string",
                            "description": "车型键名",
                        },
                        "targets": {
                            "type": "object",
                            "description": "验证后的 targets 数据",
                        },
                    },
                    "required": ["sandbox", "memory_db", "instance_key", "targets"],
                },
            },
            "metadata": {
                "type": "persistence",
                "pubfn_index": "a101_step2_4",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行回填和写入DB"""
        sandbox = args.get("sandbox")
        memory_db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        targets = args.get("targets", {})
        defined_ssts_db = args.get("defined_ssts_db") or {}

        return cls.save_targets(sandbox, memory_db, instance_key, targets, args, defined_ssts_db)

    @classmethod
    def save_targets(
        cls,
        sandbox: Any,
        memory_db: Any,
        instance_key: str,
        targets: Dict[str, Any],
        args: Dict[str, Any],
        defined_ssts_db: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """将验证后的目标值回填沙箱和写入DB

        Args:
            sandbox: 沙箱实例
            memory_db: 内存数据库实例
            instance_key: 车型键名
            targets: 验证后的 targets 数据
            args: 参数字典（含 professional_category）
            defined_ssts_db: DB 中已定义的 SSTS 字典

        Returns:
            操作结果摘要
        """
        defined_ssts_db = defined_ssts_db or {}

        try:
            category = args.get("professional_category", "")
            
            if not sandbox or not category:
                WorkLogger.warn(f"Step2_4 保存：缺少必要参数 sandbox={bool(sandbox)}, category={bool(category)}")
                return {"status": "error", "message": "缺少必要参数"}

            # 统一转换为扁平列表格式（兼容新旧两种格式）
            vts_targets = cls._flatten_targets(targets)

            for i, vt in enumerate(vts_targets):
                ssts_keys = [s.get('db_key', '?') for s in vt.get('SSTS_parameter', [])]

            if not vts_targets:
                WorkLogger.warn(f"Step2_4 保存：未提取到任何目标值")
                return {"status": "warning", "message": "未提取到任何目标值", "sandbox_updated": 0, "db_written": 0, "db_skipped": 0}

            # 1. 回填沙箱（传入 defined_ssts_db 用于填充已定义 SSTS）
            sandbox_result = cls._backfill_sandbox(sandbox, category, vts_targets, defined_ssts_db)

            # 2. 写入DB（只有 LLM 输出的、本 step 定义的值需要写入）
            db_result = cls._write_to_db(memory_db, instance_key, vts_targets)

            return {
                "status": "success",
                "sandbox_updated": sandbox_result["updated"],
                "db_written": db_result["written"],
                "db_skipped": db_result["skipped"],
                "message": f"回填沙箱 {sandbox_result['updated']} 个参数，写入DB {db_result['written']} 个参数，跳过已有值 {db_result['skipped']} 个"
            }

        except Exception as e:
            import traceback
            WorkLogger.error(f"Step2_4 保存目标值失败: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    @classmethod
    def _flatten_targets(cls, targets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将 LLM 输出的目标值数据统一转换为扁平列表格式

        支持两种格式：
        1. 旧格式：{"vts_targets": [...]} 直接使用
        2. 新格式：{"sub_category": [{"二级专业": [{"VTS_items": [...], "SSTS_parameter": [...]}]}]}
           转换为扁平列表，并将 SSTS_parameter 关联到每个 VTS 项

        Args:
            targets: LLM 输出的目标值数据

        Returns:
            扁平列表格式的目标值，每个 VTS 项包含其关联的 SSTS_parameter
        """
        # 如果是旧格式（扁平列表），直接返回
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

    @staticmethod
    def _safe_float(value: Any) -> Any:
        """安全地将 LLM 输出的 value 转换为 float 类型。

        LLM 可能将数值以字符串形式输出（如 "3.6" 而非 3.6），
        此方法统一将其转换为 float；对于非数字字符串（如 "WLTC"、"BEV"），
        保留原始字符串值不做转换；NaN 值统一转为 None。

        Args:
            value: LLM 输出的原始 value（可能是 str/float/int/None）

        Returns:
            float 值（数字字符串或数值类型）；
            非数字字符串返回原值；
            NaN 或 None 返回 None
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
    def _backfill_sandbox(
        cls,
        sandbox: Any,
        category: str,
        vts_targets: List[Dict[str, Any]],
        defined_ssts_db: Dict[str, Any],
    ) -> Dict[str, int]:
        """将目标值回填到沙箱的 process_data

        核心逻辑：process_data 的 SSTS_parameter 包含全量 SSTS，
        LLM 输出的 SSTS_parameter 只包含"未定义"的 SSTS。
        回填时对每个 SSTS_parameter 里的 db_key：
          - defined_ssts_db 里有 → 用 DB 值（来自前置专业）
          - 否则 → 找 LLM 输出值；没有就保持 process_data 原值

        Args:
            sandbox: 沙箱实例
            category: 专业分类
            vts_targets: 验证后的 VTS 目标值列表
            defined_ssts_db: DB 中已定义的 SSTS 字典

        Returns:
            更新数量统计
        """
        updated_count = 0
        defined_keys = set(defined_ssts_db.keys()) if defined_ssts_db else set()

        # 获取当前专业的 VTS 数据（嵌套结构）
        vts_category_data = sandbox.get_process_data("vts_category_data") or {}
        category_data = vts_category_data.get(category, {})

        if not category_data or not isinstance(category_data, dict):
            WorkLogger.warn(f"Step2_4 回填：process_data 中不存在专业 {category} 的 VTS 数据")
            return {"updated": 0}

        # 建立 db_key → 二级专业组 索引
        db_key_to_group = {}
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            vts_items = group_content.get("VTS_items", [])
            ssts_params = group_content.get("SSTS_parameter", [])
            for vts_item in vts_items:
                if not isinstance(vts_item, dict):
                    continue
                for pv in vts_item.get("param_values", []):
                    key = pv.get("db_key", "")
                    if key:
                        db_key_to_group[key] = {
                            "vts_item": vts_item,
                            "pv": pv,
                            "ssts_params": ssts_params,
                        }

        # 建立 LLM 输出的 SSTS db_key → 条目 索引（扁平汇总所有 vts_targets 的 SSTS）
        llm_ssts_by_key: Dict[str, Dict[str, Any]] = {}
        for vt in vts_targets:
            for s in vt.get("SSTS_parameter", []):
                if isinstance(s, dict):
                    k = s.get("db_key", "")
                    if k:
                        llm_ssts_by_key[k] = s

        # 遍历验证后的目标值 → 回填 VTS 级别
        for vts_target in vts_targets:
            target_db_key = vts_target.get("db_key", "")
            llm_value = vts_target.get("value")
            group_info = db_key_to_group.get(target_db_key)
            if not group_info:
                continue

            vts_item = group_info["vts_item"]
            pv = group_info["pv"]

            # 回填 VTS value
            new_vts_value = cls._safe_float(vts_target.get("value"))
            pv["value"] = new_vts_value
            vts_item["confidence"] = vts_target.get("confidence", "low")
            vts_item["basis"] = vts_target.get("basis", "")
            updated_count += 1

        # 遍历 process_data 的全量 SSTS_parameter → 回填 SSTS
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            ssts_params = group_content.get("SSTS_parameter", [])
            for ssts in ssts_params:
                if not isinstance(ssts, dict):
                    continue
                ssts_db_key = ssts.get("db_key", "")
                if not ssts_db_key:
                    continue

                if ssts_db_key in defined_keys:
                    # ★ 已定义：用 DB 值覆盖（前置专业写入的）
                    db_info = defined_ssts_db[ssts_db_key]
                    db_val = cls._safe_float(db_info.get("value"))
                    if db_val is not None:
                        ssts["value"] = db_val
                        # name/unit 保持 process_data 原值（step2_2 生成的）
                        # 只覆盖 value，不要覆盖 confidence/basis——那些是 step2_2 的占位
                        updated_count += 1
                else:
                    # 未定义：找 LLM 输出值
                    llm_ssts = llm_ssts_by_key.get(ssts_db_key)
                    if llm_ssts:
                        new_val = cls._safe_float(llm_ssts.get("value"))
                        if new_val is not None:
                            ssts["value"] = new_val
                            ssts["confidence"] = llm_ssts.get("confidence", "low")
                            ssts["basis"] = llm_ssts.get("basis", "")
                            updated_count += 1
                        # LLM 也没给值 → 保持 process_data 原值（可能是 None）

        # 保存回沙箱
        vts_category_data[category] = category_data
        sandbox.set_process_data("vts_category_data", vts_category_data)

        WorkLogger.info(f"Step2_4 回填沙箱完成：更新 {updated_count} 个参数")
        return {"updated": updated_count}

    @classmethod
    def _write_to_db(
        cls, memory_db: Any, instance_key: str, vts_targets: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """将目标值写入 memory_db（已有非空值的参数跳过）

        Args:
            memory_db: 内存数据库实例
            instance_key: 车型键名
            vts_targets: 验证后的 VTS 目标值列表

        Returns:
            写入数量统计 {"written": 写入数, "skipped": 跳过数}
        """
        written_count = 0
        skipped_count = 0
        ssts_written = 0
        ssts_skipped = 0
        ssts_no_value = 0

        if not memory_db:
            WorkLogger.warn("Step2_4 写入DB：memory_db 未提供")
            return {"written": 0, "skipped": 0}

        try:
            for vts_idx, vts_target in enumerate(vts_targets):
                # 写入 VTS 级别（统一将 value 转为 float 类型）
                vts_db_key = vts_target.get("db_key", "")
                vts_value = cls._safe_float(vts_target.get("value"))


                if vts_db_key and vts_value is not None:
                    if cls._has_existing_value(memory_db, vts_db_key):
                        skipped_count += 1
                    else:
                        success = cls._update_db_value(memory_db, vts_db_key, vts_value, instance_key)
                        if success:
                            written_count += 1

                # 写入 SSTS 级别（统一将 value 转为 float 类型）
                ssts_params = vts_target.get("SSTS_parameter", [])
                if ssts_params:
                    for ssts_idx, ssts in enumerate(ssts_params):
                        ssts_db_key = ssts.get("db_key", "")
                        ssts_value = cls._safe_float(ssts.get("value"))

                        if not ssts_db_key:
                            ssts_no_value += 1
                            continue
                            
                        if ssts_value is None:
                            ssts_no_value += 1
                            continue
                            
                        if cls._has_existing_value(memory_db, ssts_db_key):
                            ssts_skipped += 1
                            continue
                            
                        success = cls._update_db_value(memory_db, ssts_db_key, ssts_value, instance_key)
                        if success:
                            ssts_written += 1

            WorkLogger.info(f"Step2_4 写入DB完成：写入 {written_count} 个参数，跳过 {skipped_count} 个已有值")

        except Exception as e:
            WorkLogger.error(f"Step2_4 写入DB失败: {str(e)}")

        return {"written": written_count, "skipped": skipped_count}

    @classmethod
    def _has_existing_value(cls, memory_db: Any, db_key: str) -> bool:
        """检查 DB 中指定 db_key 是否已有非空有效值

        Args:
            memory_db: 内存数据库实例
            db_key: 数据库键名

        Returns:
            bool: True 表示已有非空有效值，应跳过写入
        """
        try:
            existing = memory_db.get_ssts_vts_param(db_key)
            if existing is None:
                return False
            if isinstance(existing, str) and existing.strip() == "":
                return False
            if isinstance(existing, float) and math.isnan(existing):
                return False # NaN 视为空值，允许写入
            return True
        except Exception:
            return False

    @classmethod
    def _update_db_value(
        cls, memory_db: Any, db_key: str, value: Any, instance_key: str
    ) -> bool:
        """更新单个 db_key 的值

        Args:
            memory_db: 内存数据库实例
            db_key: 数据库键名
            value: 目标值
            instance_key: 车型键名

        Returns:
            bool: 是否写入成功
        """
        try:
            # 使用 MemoryDatabase 的 set_ssts_vts_param 方法
            if hasattr(memory_db, 'set_ssts_vts_param'):
                success = memory_db.set_ssts_vts_param(db_key, value)
                return success
            else:
                return False
        except Exception as e:
            return False
