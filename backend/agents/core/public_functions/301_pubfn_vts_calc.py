# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 301_pubfn_vts_calc.py
# @Desc    : Public Function: VTS 校核模块
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 301: VTS 校核

提供 VTS 校核计算的完整流程，包括：
- 备份当前 SSTS 当前值
- 恢复备份的当前值
- 将 SSTS 目标值复制到当前值
- 执行完整的 VTS 校核流程（备份→复制→计算→检查→恢复）
"""

from __future__ import annotations

from typing import Any, Dict

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnVtsCalc(AtomicFunction):
    """VTS 校核 Public Function

    提供 VTS 校核计算的原子操作，支持完整的校核流程：
    备份 → 复制目标值 → 运行 VTS 计算 → 检查达标 → 恢复备份。
    """

    name: str = "vts_calc"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "VTS 校核工具。提供以下操作：\n"
                    "  - backup_current_values: 备份当前 SSTS 当前值\n"
                    "  - restore_current_values: 恢复备份的当前值\n"
                    "  - copy_target_to_current: 将 SSTS 目标值复制到当前值\n"
                    "  - run_vts_validation_flow: 执行完整的 VTS 校核流程"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": (
                                "操作类型，可选值：\n"
                                "  backup_current_values / restore_current_values /\n"
                                "  copy_target_to_current / run_vts_validation_flow"
                            ),
                        },
                        "memory_db": {
                            "type": "object",
                            "description": "MemoryDatabase 实例",
                        },
                        "instance_key": {
                            "type": "string",
                            "description": "memorycore 键名",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "专业分类（可选，用于筛选指定专业）",
                        },
                        "vehicle_suffix": {
                            "type": "string",
                            "description": "车型后缀（如 'reevlto'）",
                        },
                        "backup": {
                            "type": "object",
                            "description": "备份数据（用于 restore_current_values）",
                        },
                    },
                    "required": ["operation"],
                },
            },
            "metadata": {
                "type": "calculation",
                "pubfn_index": "301",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行 VTS 校核原子操作

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
            db = args.get("memory_db") or (context.db if context else None)

            if operation == "backup_current_values":
                vkey = args.get("instance_key", "")
                return cls.backup_current_values(db, vkey)

            elif operation == "restore_current_values":
                backup = args.get("backup", {})
                return cls.restore_current_values(db, backup)

            elif operation == "copy_target_to_current":
                vkey = args.get("instance_key", "")
                category = args.get("professional_category", "")
                sandbox = args.get("sandbox")
                return cls.copy_target_to_current(db, vkey, category, sandbox)

            elif operation == "run_vts_validation_flow":
                vkey = args.get("instance_key", "")
                category = args.get("professional_category", "")
                vehicle_suffix = args.get("vehicle_suffix", "")
                return cls.run_vts_validation_flow(db, vkey, category, vehicle_suffix)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    # ==================================================================
    # 校核方法
    # ==================================================================

    @classmethod
    def backup_current_values(cls, db, instance_key: str) -> Dict[str, Any]:
        """备份当前 SSTS 当前值

        遍历 SSTS 数据表，保存所有参数的当前值到字典中。

        Args:
            db: MemoryDatabase 实例
            instance_key: memorycore 键名

        Returns:
            Dict: {db_key: 当前值} 备份字典
        """
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data

        backup = {}
        sheet_data = get_sheet_data(db, instance_key, "target_ssts")
        if sheet_data and isinstance(sheet_data, dict):
            for cat1, cat2_dict in sheet_data.items():
                if isinstance(cat2_dict, dict):
                    for cat2, param_list in cat2_dict.items():
                        if isinstance(param_list, list):
                            for param in param_list:
                                if isinstance(param, dict):
                                    param_values = param.get("参数值", [])
                                    if isinstance(param_values, list):
                                        for pv in param_values:
                                            if isinstance(pv, dict) and pv.get("名称") == "当前值":
                                                key = pv.get("db_key", "")
                                                if key:
                                                    try:
                                                        backup[key] = db.get_ssts_vts_param(key)
                                                    except Exception:
                                                        pass
        return backup

    @classmethod
    def restore_current_values(cls, db, backup: Dict[str, Any]) -> None:
        """恢复备份的当前值

        Args:
            db: MemoryDatabase 实例
            backup: backup_current_values 返回的备份字典
        """
        from snail_avatar.backend.core.work_log import WorkLogger

        restored_count = 0
        for key, value in backup.items():
            try:
                db.set_ssts_vts_param(key, value)
                restored_count += 1
            except Exception as e:
                WorkLogger.warn(
                    f"VTS校核恢复值: {key} 恢复失败, 错误: {str(e)}"
                )

        WorkLogger.info(
            f"VTS校核恢复值完成: 恢复 {restored_count}/{len(backup)} 个参数"
        )

    @classmethod
    def copy_target_to_current(cls, db, instance_key: str, category: str = "", sandbox=None) -> None:
        """将 VTS 和 SSTS 目标值都复制到当前值（按 db_key 匹配）

        VTS 复制的必要性：有些 VTS 参数是"纯输入"（其他 VTS 计算的前置条件，
        本身无计算公式），需要从 target 复制到 result 才能参与后续计算。
        那些作为计算输出的 VTS，后续 VTS 校核计算会自动覆盖其 result 值。

        流程：
        1. 从 sandbox 读取指定专业的 VTS + SSTS db_key 列表（作为筛选器）
        2. 从 Memory Core 读取 target_ssts 数据（VTS 节 + SSTS 节）
        3. 在 Memory Core 中查找匹配的 db_key 对应的目标值
        4. 将目标值写入对应的 result db_key（_target_ → _result_ 后缀替换）

        Args:
            db: MemoryDatabase 实例
            instance_key: memorycore 键名
            category: 专业分类
            sandbox: ProcessSandbox 实例
        """
        from snail_avatar.backend.core.work_log import WorkLogger
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data

        if not sandbox or not db:
            return

        # 1. 从沙箱获取当前专业的 SSTS db_key 列表（新嵌套结构）
        vts_category_data = sandbox.get_process_data("vts_category_data")
        if not vts_category_data or not isinstance(vts_category_data, dict):
            return

        # 新结构：{专业: {二级专业: {VTS_items, SSTS_parameter, 计算公式}}}
        category_data = vts_category_data.get(category, {})
        if not isinstance(category_data, dict) or not category_data:
            return

        # 收集 SSTS 和 VTS 的 target db_key
        # 说明：VTS 参数中有些是"纯输入"（其他 VTS 计算的前置条件，本身无计算公式），
        # 也需要从 target → result 复制，否则它们的 result 值会是 null 或脏数据。
        # 后续 VTS 校核计算会自动覆盖那些作为计算结果的 VTS 的 result 值。
        target_db_keys = set()
        for sub_cat_name, group_content in category_data.items():
            if not isinstance(group_content, dict):
                continue
            # SSTS_parameter
            for ssts in group_content.get("SSTS_parameter", []):
                if isinstance(ssts, dict) and ssts.get("db_key"):
                    target_db_keys.add(ssts["db_key"])
            # VTS_items — db_key 嵌套在 param_values 里
            for vts in group_content.get("VTS_items", []):
                if isinstance(vts, dict):
                    for pv in vts.get("param_values", []):
                        if isinstance(pv, dict) and pv.get("db_key"):
                            target_db_keys.add(pv["db_key"])

        if not target_db_keys:
            return

        # [DEBUG] 打印收集到的 target db_keys

        # 2. 从 Memory Core 读取目标值数据（需要同时读 SSTS 和 VTS 两个表）
        #    step2_4 save_targets 把 SSTS 存入 target_ssts 表，VTS 存入 target_vts 表
        sheet_data_ssts = get_sheet_data(db, instance_key, "target_ssts")
        sheet_data_vts = get_sheet_data(db, instance_key, "target_vts")

        # 合并两个表的数据
        all_sheet_data = {}
        if isinstance(sheet_data_ssts, dict):
            all_sheet_data.update(sheet_data_ssts)
        if isinstance(sheet_data_vts, dict):
            all_sheet_data.update(sheet_data_vts)

        if not all_sheet_data:
            return


        # 3. 在 Memory Core 中查找匹配的 db_key 并复制值
        copied_count = 0
        for cat1, cat2_dict in all_sheet_data.items():
            # cat1 可能是:
            #   - target_ssts 表: "SSTS"、"VTS"（按参数类型分节）
            #   - target_vts 表: "空气动力学"、"动力性"、"经济性"（按专业分节）
            #   两种都要处理，不再按 cat1 名称过滤
            if not isinstance(cat2_dict, dict):
                continue

            for cat2, param_list in cat2_dict.items():
                if not isinstance(param_list, list):
                    continue

                for param in param_list:
                    if not isinstance(param, dict):
                        continue

                    param_values = param.get("参数值", [])
                    if not isinstance(param_values, list):
                        continue

                    # 找到"目标值"的 db_key 和值
                    target_db_key = ""
                    target_value = None
                    for pv in param_values:
                        if isinstance(pv, dict) and pv.get("名称") == "目标值":
                            target_db_key = pv.get("db_key", "")
                            target_value = pv.get("值")
                            break

                    if not target_db_key or target_value is None:
                        continue

                    # 检查是否在沙箱的 target db_key 列表中
                    if target_db_key not in target_db_keys:
                        continue

                    # 4. 构造 result db_key 并写入（VTS 和 SSTS 共用同一套 _target_/_result_ 后缀约定）
                    result_db_key = target_db_key.replace("_target_", "_result_")
                    try:
                        db.set_ssts_vts_param(result_db_key, target_value)
                        copied_count += 1
                    except Exception as e:
                        WorkLogger.warn(
                            f"VTS校核复制目标值: {result_db_key} 写入失败, 错误: {str(e)}"
                        )

        WorkLogger.info(
            f"VTS校核复制目标值完成: 专业={category}, 复制 {copied_count} 个参数"
        )

    @classmethod
    def run_vts_validation_flow(
        cls, db, instance_key: str, category: str = "", vehicle_suffix: str = ""
    ) -> Dict[str, Any]:
        """执行完整的 VTS 校核流程

        流程：备份当前值 → 复制目标值到当前值 → 运行 VTS 计算 → 检查达标情况 → 恢复备份

        Args:
            db: MemoryDatabase 实例
            instance_key: memorycore 键名
            category: 专业分类（可选）
            vehicle_suffix: 车型后缀（可选）

        Returns:
            Dict: 校核结果，包含 {ok, msg, pass_status, summary}
        """
        from snail_avatar.backend.core.work_log import WorkLogger
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import collect_vehicles
        from snail_avatar.backend.agents.core.public_functions_core.vts.vts_calc_helper import run_vts_calculation

        WorkLogger.info(
            f"VTS校核开始: 车型={vehicle_suffix}, 专业={category}"
        )

        if db is None:
            WorkLogger.warn("VTS校核: memory_db 为空，跳过校核")
            return {"ok": False, "msg": "当前未加载数据（memory_db 为空）", "pass_status": None}

        if instance_key:
            vehicle_names = [vehicle_suffix]
            name_to_instance_key = {vehicle_suffix: instance_key}
        else:
            vehicle_names, name_to_instance_key = collect_vehicles(db)

        if not vehicle_names:
            WorkLogger.warn("VTS校核: 未找到任何车型数据")
            return {"ok": False, "msg": "未找到任何车型数据。", "pass_status": None}

        all_fail_items = []
        summary_rows = []

        for vehicle_name in vehicle_names:
            key = name_to_instance_key.get(vehicle_name, vehicle_name)

            WorkLogger.info(f"VTS校核: 车型 {vehicle_name} 备份当前值")
            backup = cls.backup_current_values(db, key)

            try:
                cls.copy_target_to_current(db, key, category)

                ok, msg, report = run_vts_calculation(db)

                if not ok:
                    WorkLogger.error(
                        f"VTS校核计算失败: 车型={vehicle_name}, 错误={msg}"
                    )
                    return {
                        "ok": False,
                        "msg": f"【{vehicle_name}】VTS 校核计算失败: {msg}",
                        "pass_status": None,
                    }

                import importlib
                _mod = importlib.import_module(
                    "snail_avatar.backend.agents.core.public_functions.102_pubfn_pass_status_checker"
                )
                pass_status = _mod.PubfnPassStatusChecker.get_pass_status({"memory_db": db, "instance_key": key, "professional_category": category})

                rate = pass_status["passed"] / pass_status["total"] * 100 if pass_status["total"] > 0 else 0
                summary_rows.append({
                    "车型": vehicle_name,
                    "总参数": pass_status["total"],
                    "达标": pass_status["passed"],
                    "不达标": pass_status["failed"],
                    "达标率": f"{rate:.1f}%",
                })

                WorkLogger.info(
                    f"VTS校核: 车型={vehicle_name}, "
                    f"达标={pass_status['passed']}/{pass_status['total']} ({rate:.1f}%)"
                )

                for item in pass_status["failed_items"]:
                    all_fail_items.append({
                        "车型": vehicle_name,
                        "参数名称": item["name"],
                        "单位": item.get("unit", ""),
                        "当前值": item["current"],
                        "目标值": item["target"],
                    })
            finally:
                cls.restore_current_values(db, backup)

        WorkLogger.info("VTS校核完成")

        return {
            "ok": True,
            "msg": "校核完成",
            "pass_status": {
                "summary_rows": summary_rows,
                "fail_items": all_fail_items,
            },
        }