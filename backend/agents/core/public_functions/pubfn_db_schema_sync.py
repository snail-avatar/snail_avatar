# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : pubfn_db_schema_sync.py
# @Desc    : Public Function（通用）：从 DB schema 反查参数权威信息，修正 LLM 输出的 db_key / name / unit
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
通用公共函数：db_schema_sync（参数 schema 校验 + 修正）

功能：
  1. 从 DB 的 target_ssts + target_vts sheet 构建参数权威信息字典
  2. 递归遍历 mapping 中的所有参数项（含 db_key / name / unit 的 dict）
  3. 用 DB 权威信息覆盖 LLM 可能编造的 name、unit，补全 db_key 后缀
  4. 可选：同时覆盖 sandbox step_results，确保下游步骤读到正确数据

解决的问题：
  - LLM 自编 SSTS/VTS 参数中文名（如"后电驱最大扭矩" → DB 权威名"后电驱轮端峰值扭矩"）
  - LLM 输出基础名 db_key（如 edu_tmax_r），需要补全为完整后缀（edu_tmax_r_target_reevlto）
  - step_results 存的是 LLM 原始输出，下游步骤（step2_3+）读到错误名称

设计原则：
  - 通用性：递归 + db_key 模式匹配，支持 SSTS_parameter[]、VTS_items[]、optimized_SSTS_items[] 等任意结构
  - 自包含：一个函数完成 DB 查询 + 后缀补全 + name/unit 覆盖，无需前置依赖
  - 可选写回：write_back=True 时同步覆盖 step_results

必需参数（YAML 需显式声明）：
  mapping:        LLM 输出的结构化数据（dict，含 sub_category 或其他嵌套结构）
  memory_db:      MemoryDatabase 实例
  instance_key:   memorycore 中的车型键名（如 "增程车型_reevlto"）

可选参数（YAML 按需声明）：
  write_back:     bool，是否同步覆盖 step_results（默认 False）
  step_id:        str，write_back=True 时用于构建 step_results 的 key
  professional_category: str，write_back=True 时用于构建 step_results 的 key
  sheet:          str，"target_ssts" / "target_vts" / "all"（默认 "all"）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionBase
from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import iter_flat_items


class DbSchemaSync(FunctionBase):
    """DB schema 校验 + 修正公共函数（通用，适用于所有 a101 step）"""

    name: str = "db_schema_sync"

    # ------------------------------------------------------------------
    # Schema（框架用于 function-calling + 参数校验）
    # ------------------------------------------------------------------
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "DB schema 校验 + 修正：从 DB schema 反查参数权威信息，"
                    "覆盖 LLM 输出的错误 name/unit，补全 db_key 后缀，"
                    "可选同步覆盖 sandbox step_results。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mapping": {
                            "type": "object",
                            "description": "LLM 输出的结构化数据（含 sub_category 或其他嵌套）",
                        },
                        "memory_db": {
                            "type": "object",
                            "description": "MemoryDatabase 实例",
                        },
                        "instance_key": {
                            "type": "string",
                            "description": "memorycore 中的车型键名",
                        },
                        "write_back": {
                            "type": "boolean",
                            "description": "是否同步覆盖 step_results（默认 False）",
                        },
                        "step_id": {
                            "type": "string",
                            "description": "write_back=True 时使用的 step_id",
                        },
                        "professional_category": {
                            "type": "string",
                            "description": "write_back=True 时使用的专业名",
                        },
                        "sheet": {
                            "type": "string",
                            "enum": ["target_ssts", "target_vts", "all"],
                            "description": "查哪张 sheet（默认 all）",
                        },
                        "remove_unknown": {
                            "type": "boolean",
                            "description": "是否删除 DB 中不存在的幻觉 db_key 参数项（默认 False）",
                        },
                    },
                    "required": ["mapping", "memory_db", "instance_key"],
                },
            },
            "metadata": {
                "type": "data_sync",
                "pubfn_index": "core",
            },
        }

    # ------------------------------------------------------------------
    # 框架调用入口
    # ------------------------------------------------------------------
    @classmethod
    def execute(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """框架统一入口

        返回值设计：
          返回 dict(synced_mapping, result=修正后JSON字符串)
          - synced_mapping: 保持原有 mapping 结构（sub_category, reasoning_logic 等）
            供 output_key 捕获（如 post.synced_mapping）
          - result key: 完整的 {"structured_data": mapping, "reasoning_logic": ...} JSON 字符串
            触发框架 _execute_post_process L917-918 的 result 更新机制，
            避免 base.py._execute 最后的 _save_to_sandbox 用原始 LLM 输出覆盖修正后的 step_result
        """
        import json as _json

        mapping = args.get("mapping", {})
        memory_db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        write_back = args.get("write_back", False)
        step_id = args.get("step_id", "")
        professional_category = args.get("professional_category", "")
        sheet = args.get("sheet", "all")
        remove_unknown = args.get("remove_unknown", False)
        sandbox = args.get("sandbox") or (getattr(context, "sandbox", None) if context else None)

        synced = cls.sync(
            mapping=mapping,
            memory_db=memory_db,
            instance_key=instance_key,
            write_back=write_back,
            step_id=step_id,
            professional_category=professional_category,
            sheet=sheet,
            sandbox=sandbox,
            remove_unknown=remove_unknown,
        )

        # 构建完整 result JSON，触发框架 result 更新机制
        # 注意：step2_4 等 step 的 LLM 输出把 reasoning_logic 放在 structured_data 内部，
        # 用 pop 把它提出来放到顶层，避免 result.content 里同时出现两条 reasoning_logic
        reasoning = synced.pop("reasoning_logic", "") if isinstance(synced, dict) else ""
        result_json = _json.dumps(
            {"structured_data": synced, "reasoning_logic": reasoning},
            ensure_ascii=False,
        )

        # 在 synced 基础上加 result key（不破坏原有 mapping 结构）
        if isinstance(synced, dict):
            return dict(synced, result=result_json)
        return synced

    # ------------------------------------------------------------------
    # 主逻辑
    # ------------------------------------------------------------------
    @classmethod
    def sync(
        cls,
        mapping: Dict[str, Any],
        memory_db: Any,
        instance_key: str,
        write_back: bool = False,
        step_id: str = "",
        professional_category: str = "",
        sheet: str = "all",
        sandbox: Any = None,
        remove_unknown: bool = False,
    ) -> Dict[str, Any]:
        """从 DB schema 反查参数权威信息，修正 mapping 中的 db_key / name / unit

        Args:
            mapping: LLM 输出的结构化数据
            memory_db: MemoryDatabase 实例
            instance_key: memorycore 中的车型键名
            write_back: 是否同步覆盖 step_results
            step_id: write_back 时的 step_id
            professional_category: write_back 时的专业名
            sheet: 查哪张 sheet
            sandbox: 沙箱实例（write_back=True 时必需）
            remove_unknown: 是否删除 DB 中不存在的幻觉 db_key 参数项

        Returns:
            Dict: 修正后的 mapping（原地修改 + 返回）
        """
        if not mapping or not memory_db:
            return mapping

        # 步骤 1: 构建 DB 参数字典
        # full_to_info: 完整后缀 db_key → {name, unit}
        # base_to_full: 基础名 → 完整后缀 db_key（补后缀时用）
        full_to_info: Dict[str, Dict[str, Any]] = {}
        base_to_full: Dict[str, str] = {}
        vehicle_suffix_list: List[str] = []

        sheets_to_query: List[str] = (
            ["target_ssts", "target_vts"] if sheet == "all" else [sheet]
        )

        for sheet_key in sheets_to_query:
            sheet_data = get_sheet_data(memory_db, instance_key, sheet_key)
            if not sheet_data:
                continue

            for item in iter_flat_items(sheet_data):
                name = item.get("name", "").strip()
                raw_unit = item.get("单位")
                unit = str(raw_unit).strip() if raw_unit is not None else ""

                # 遍历参数值的三种 db_key（目标值、当前值、达标标识）
                for suffix_key in ("目标值_db_key", "当前值_db_key", "达标标识_db_key"):
                    full_db_key = item.get(suffix_key, "")
                    if not full_db_key or full_db_key in full_to_info:
                        continue

                    full_to_info[full_db_key] = {"name": name, "unit": unit}

                    # 基础名 → 完整后缀映射（优先用目标值的 db_key 做映射）
                    base_key = cls._extract_base_key(full_db_key)
                    if base_key:
                        if suffix_key == "目标值_db_key" or base_key not in base_to_full:
                            base_to_full[base_key] = full_db_key

                    # 收集车型后缀（如 reevlto），用于补基础名后缀
                    veh_suffix = cls._extract_vehicle_suffix(full_db_key)
                    if veh_suffix and veh_suffix not in vehicle_suffix_list:
                        vehicle_suffix_list.append(veh_suffix)

        if not full_to_info:
            return mapping

        # 步骤 2: 递归遍历 mapping，修正每个参数项
        cls._walk_and_sync(mapping, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown)

        # 步骤 3: 可选覆盖 step_results
        if write_back and sandbox and step_id:
            full_step_id = f"{professional_category}_{step_id}" if professional_category else step_id
            old_result = sandbox.get_step_result(full_step_id) or {}
            new_result = dict(old_result)
            new_result["structured_data"] = mapping
            sandbox.set_step_result(full_step_id, new_result)

        return mapping

    # ------------------------------------------------------------------
    # 辅助工具：db_key 拆解
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_base_key(full_db_key: str) -> str:
        """edu_tmax_r_target_reevlto → edu_tmax_r"""
        for separator in ("_target_", "_result_", "_pass_"):
            if separator in full_db_key:
                base_key = full_db_key.split(separator)[0]
                if base_key:
                    return base_key
        return full_db_key

    @staticmethod
    def _extract_vehicle_suffix(full_db_key: str) -> Optional[str]:
        """edu_tmax_r_target_reevlto → reevlto"""
        for separator in ("_target_", "_result_", "_pass_"):
            if separator in full_db_key:
                tail = full_db_key.split(separator)[1]
                if tail:
                    return tail
        return None

    # ------------------------------------------------------------------
    # 辅助工具：递归遍历修正
    # ------------------------------------------------------------------
    @classmethod
    def _walk_and_sync(
        cls,
        node: Any,
        full_to_info: Dict[str, Dict[str, Any]],
        base_to_full: Dict[str, str],
        vehicle_suffix_list: List[str],
        remove_unknown: bool,
    ) -> None:
        """递归遍历 node，对每个含有 db_key 的 dict 进行修正

        识别规则：dict 含有 "db_key" key 且值是非空字符串 → 视为参数项
        （支持 SSTS_parameter[]、VTS_items[].param_values[]、optimized_SSTS_items[] 等任意嵌套结构）

        remove_unknown=True 时，DB 中找不到 db_key 的参数项会从所在 list 中被删除。
        """
        if isinstance(node, dict):
            db_key = node.get("db_key", "")
            if isinstance(db_key, str) and db_key:
                cls._fix_param_item(
                    node, db_key, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown
                )
            for value in node.values():
                cls._walk_and_sync(value, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown)

        elif isinstance(node, list):
            # remove_unknown 时需要过滤掉被标记删除的 item
            i = 0
            while i < len(node):
                item = node[i]
                if cls._walk_and_sync_item(item, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown):
                    i += 1
                else:
                    node.pop(i)

    @classmethod
    def _walk_and_sync_item(
        cls,
        item: Any,
        full_to_info: Dict[str, Dict[str, Any]],
        base_to_full: Dict[str, str],
        vehicle_suffix_list: List[str],
        remove_unknown: bool,
    ) -> bool:
        """对 list 中的单个 item 执行修正 + 递归子节点

        Returns:
            bool: True 表示 item 保留，False 表示应删除（remove_unknown 且 db_key 不在 DB 中）
        """
        if isinstance(item, dict):
            db_key = item.get("db_key", "")
            if isinstance(db_key, str) and db_key:
                should_remove = cls._fix_param_item(
                    item, db_key, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown
                )
                if should_remove:
                    return False

            # 递归子节点
            for value in item.values():
                cls._walk_and_sync(value, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown)
            return True

        elif isinstance(item, list):
            cls._walk_and_sync(item, full_to_info, base_to_full, vehicle_suffix_list, remove_unknown)
            return True

        else:
            return True

    @classmethod
    def _fix_param_item(
        cls,
        param_item: Dict[str, Any],
        db_key: str,
        full_to_info: Dict[str, Dict[str, Any]],
        base_to_full: Dict[str, str],
        vehicle_suffix_list: List[str],
        remove_unknown: bool,
    ) -> bool:
        """修正单个参数项（原地修改 param_item）

        Returns:
            bool: True 表示此参数项应删除（DB 找不到且 remove_unknown=True）
        """
        lookup_key = db_key
        has_full_suffix = any(sep in db_key for sep in ("_target_", "_result_", "_pass_"))
        found_in_db = False

        if not has_full_suffix:
            # db_key 是基础名 → 补全后缀
            full_candidate = base_to_full.get(db_key)
            if full_candidate:
                lookup_key = full_candidate
                param_item["db_key"] = full_candidate
                found_in_db = True
            elif vehicle_suffix_list:
                for suffix in vehicle_suffix_list:
                    for kind in ("target", "result"):
                        trial = f"{db_key}_{kind}_{suffix}"
                        if trial in full_to_info:
                            lookup_key = trial
                            param_item["db_key"] = trial
                            found_in_db = True
                            break
                    if found_in_db:
                        break

        # 用 lookup_key 反查 DB 权威信息 → 覆盖 name / unit
        info = full_to_info.get(lookup_key)
        if info:
            found_in_db = True
            auth_name = info.get("name", "")
            auth_unit = info.get("unit", "")
            if auth_name:
                param_item["name"] = auth_name
            if auth_unit and not param_item.get("unit"):
                param_item["unit"] = auth_unit

        # remove_unknown 且 DB 找不到 → 标记删除
        if remove_unknown and not found_in_db:
            return True

        return False
