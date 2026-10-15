# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : ssts_sandbox.py
# @Desc    : SSTS Agent 的局部沙箱（v3：按 component/instance/axle/variant 分层）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
SSTS Agent 的局部沙箱（v3 版）

【v3 核心改动】
零部件参数按 车型后缀 → 零部件类型 → 实例 → 方案 → sheet 名 分层存储，
所有方案文件全量加载（不设默认、不挑选、不合并）。

与全局 MemoryDatabase 的关系：
  - 隔离：私有零部件参数只在沙箱内，不污染全局
  - 只读桥接：get_global(name, suffix) 读取全局 SSTS/VTS 参数
  - 可选回写：mark_for_commit(name) + commit() 写回全局

【_params 数据结构】
{
    "reevlto": {                              # 顶层 key = 车型后缀（与 node.vehicle_suffix 对齐）
        "Motor": {                            # component（零部件类型）
            "Emotor_F": {                     # instance（具体实例 = 磁盘子文件夹名）
                "_axle": "front",             # 自动识别的轴标注（可选）
                "_file_count": 1,             # 该实例下方案文件数量
                "_variants": {                # 所有方案全量存放（v3 新增）
                    "motor_parameter": {      # key = 文件名（去扩展名）
                        "_meta": {
                            "file_name": "motor_parameter.xlsx",
                            "file_path": ".../Emotor_F/motor_parameter.xlsx",
                            "loaded_at": "2026-10-09T12:00:00",
                            "sheet_count": 2,
                        },
                        "external_characteristin": {...},   # sheet 名 → 统一格式数据
                        "eff_map": {...},
                    },
                },
            },
            "Emotor_R": {
                "_axle": "rear",
                "_file_count": 2,
                "_variants": {
                    "motor_parameter_1": {...},
                    "motor_parameter_2": {...},
                },
            },
        },
        "_flat_params": {                     # 扁平标量参数（json/yaml 或 MemoryDB 桥接）
            "V_min_regen": 5.0,
            "SOC_max_regen": 0.95,
        },
    },
}

【_instance_index 反向索引】
{
    "reevlto": {
        "Motor": {
            "front": "Emotor_F",    # axle → instance 名（1:1 映射）
            "rear":  "Emotor_R",
        }
    }
}
用于 get_all_variants_by_axle() 快速定位实例。

统一数据格式（components_reader 输出）：
  curve_1d: {"type": "curve_1d", "x_label", "y_label", "x": [...], "y": [...], "y_abs": [...]}
  map_2d:   {"type": "map_2d",   "x_label", "y_label", "z_label", "x": [...], "y": [...], "z": [[...]]}
  scalar:   {"type": "scalar",   "value": Any}
"""

from __future__ import annotations

import datetime
import glob
import os
from typing import Any, Dict, List, Optional, Set

from snail_avatar.backend.agents.core.workflow_base.components_reader import ComponentsReader
from snail_avatar.backend.core.work_log import WorkLogger


class SSTSSandbox:
    """SSTS Agent 局部沙箱（v3：全方案全量加载 + 分层存储）"""

    # =========================================================================
    # 初始化
    # =========================================================================

    def __init__(self, global_db: Any = None):
        """
        Args:
            global_db: MemoryDatabase 实例（可选，用于 get_global / commit）
        """
        # ----- 分层数据存储 -----
        self._params: Dict[str, Dict[str, Any]] = {}
        # _params[suffix][component][instance]["_variants"][variant_name][sheet_name] = uniform_data

        # ----- 反向索引：axle → instance -----
        self._instance_index: Dict[str, Dict[str, Dict[str, str]]] = {}
        # _instance_index[suffix][component]["front"] = "Emotor_F"

        # ----- commit 机制 -----
        self._commit_keys: Set[str] = set()

        # ----- 全局 DB 桥接 -----
        self._global_db = global_db

        # ----- 项目关联属性（由 auto_load_for_agent 自动填充）-----
        self.project_folder: Optional[str] = None          # 项目根（data/项目名）
        self._suffix_subfolder_map: Dict[str, str] = {}    # suffix → 车型子目录完整路径
        self.memory_db_file_path: Optional[str] = None
        self.loaded_file_count: int = 0
        self.last_load_time: Optional[datetime.datetime] = None

        # ----- 车型元数据 -----
        self.vehicle_suffixes: List[str] = []
        self.vehsuffix_table: List[dict] = []

        # ----- 当前加载时用的 agent_config（含 axle_rules 等）-----
        self._agent_config: Dict[str, Any] = {}

    # =========================================================================
    # 基础：后缀 / component / instance 结构维护
    # =========================================================================

    def add_vehicle_suffix(self, suffix: str) -> None:
        """注册一个车型后缀到沙箱（空结构，后续 load_from_folder 填充）"""
        if suffix not in self._params:
            self._params[suffix] = {}
        if suffix not in self.vehicle_suffixes:
            self.vehicle_suffixes.append(suffix)
        if suffix not in self._instance_index:
            self._instance_index[suffix] = {}

    def _ensure_component(self, suffix: str, component: str) -> None:
        """确保 _params[suffix][component] 存在"""
        if suffix not in self._params:
            self.add_vehicle_suffix(suffix)
        if component not in self._params[suffix]:
            self._params[suffix][component] = {}
        if component not in self._instance_index[suffix]:
            self._instance_index[suffix][component] = {}

    def _ensure_instance(self, suffix: str, component: str, instance: str,
                         axle: Optional[str] = None) -> None:
        """确保 _params[suffix][component][instance] 存在"""
        self._ensure_component(suffix, component)
        inst = self._params[suffix][component]
        if instance not in inst:
            inst[instance] = {"_variants": {}, "_file_count": 0}
        if axle is not None:
            inst[instance]["_axle"] = axle
            # 同步更新反向索引
            self._instance_index[suffix][component][axle] = instance

    # =========================================================================
    # 文件加载主入口
    # =========================================================================

    def load_from_folder(self, folder_path: str,
                         filter_patterns: Optional[List[str]] = None,
                         agent_config: Optional[Dict[str, Any]] = None) -> int:
        """
        扫描项目子目录，加载所有零部件参数文件

        核心逻辑：
          1. 按 filter_patterns 收集所有支持的文件
          2. 对每个文件分类：component / instance / axle / variant（从路径段识别）
          3. ComponentsReader 读取 → 写入 _params 分层结构
          4. 所有方案全量加载，不挑选、不合并

        Args:
            folder_path: 车型子文件夹绝对路径
            filter_patterns: glob 模式列表（如 ["Motor/**", "Brake/**"]）
            agent_config: 可选 agent 配置（含 axle_rules）

        Returns:
            成功加载的文件数量
        """
        if not folder_path or not os.path.isdir(folder_path):
            WorkLogger.warn(f"[SSTSSandbox] 文件夹不存在: {folder_path}")
            return 0

        if agent_config:
            self._agent_config = agent_config

        # 1. 收集文件
        all_files = self._collect_files(folder_path, filter_patterns)
        if not all_files:
            WorkLogger.info(f"[SSTSSandbox] 未找到匹配的参数文件（filter={filter_patterns}）")
            return 0

        # 2. 获取当前车型后缀（取已注册的第一个，或直接用文件夹名）
        suffix = self._detect_current_suffix(folder_path)
        if suffix is None:
            WorkLogger.warn(f"[SSTSSandbox] 无法确定车型后缀，跳过加载")
            return 0

        # 3. 逐个分类 + 加载
        axle_rules = self._agent_config.get("axle_rules", {})
        front_kw = set(axle_rules.get("front_keywords", ["_F", "Emotor_F", "Motor_F", "Fmotor"]))
        rear_kw  = set(axle_rules.get("rear_keywords",  ["_R", "Emotor_R", "Motor_R", "Rmotor"]))

        loaded_count = 0
        for file_path in all_files:
            rel = os.path.relpath(file_path, folder_path)
            parts = rel.split(os.sep)
            # parts 示例: ["Motor", "Emotor_R", "motor_parameter_2.xlsx"]

            # ---- 解析路径段 ----
            component, instance, variant_name = self._parse_path_parts(parts)
            if component is None:
                continue

            # ---- axle 识别 ----
            axle = None
            if any(kw in instance for kw in front_kw):
                axle = "front"
            elif any(kw in instance for kw in rear_kw):
                axle = "rear"

            # ---- ComponentsReader 读取 ----
            file_data = ComponentsReader.read_file(file_path)
            if not file_data:
                WorkLogger.warn(f"[SSTSSandbox] 解析失败，跳过: {rel}")
                continue

            # ---- 写入分层结构 ----
            self._ensure_instance(suffix, component, instance, axle)
            entry = self._params[suffix][component][instance]

            # 同一个 variant_name 可能因 sheet 名覆盖（不同文件同 sheet）
            # 这里按文件全量覆盖写，保留 _meta
            entry["_variants"][variant_name] = {
                "_meta": {
                    "file_name": os.path.basename(file_path),
                    "file_path": file_path,
                    "loaded_at": datetime.datetime.now().isoformat(),
                    "sheet_count": len(file_data),
                },
                **file_data,
            }
            entry["_file_count"] = len(entry["_variants"])
            loaded_count += 1

        # 4. 更新状态
        # 注意：不在此覆盖 self.project_folder，由 auto_load_for_agent 设为项目根
        self.loaded_file_count = loaded_count
        self.last_load_time = datetime.datetime.now()

        WorkLogger.info(
            f"[SSTSSandbox] load_from_folder 完成: "
            f"loaded={loaded_count} 个文件, suffix={suffix}, "
            f"components={list(self._params[suffix].keys())}"
        )
        return loaded_count

    # =========================================================================
    # 文件扫描与路径分类（内部工具）
    # =========================================================================

    def _collect_files(self, folder_path: str,
                       filter_patterns: Optional[List[str]]) -> List[str]:
        """收集文件夹内所有支持的文件"""
        supported_exts = {".xlsx", ".xls", ".json", ".yaml", ".yml", ".csv"}
        file_list: List[str] = []

        if filter_patterns:
            for pattern in filter_patterns:
                matched = glob.glob(os.path.join(folder_path, pattern), recursive=True)
                file_list.extend(matched)
        else:
            for ext in ("*.xlsx", "*.xls", "*.json", "*.yaml", "*.yml", "*.csv"):
                file_list.extend(glob.glob(os.path.join(folder_path, "**", ext), recursive=True))

        return [f for f in file_list
                if os.path.isfile(f)
                and os.path.splitext(f)[1].lower() in supported_exts]

    @staticmethod
    def _parse_path_parts(parts: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        解析文件相对路径段

        parts 示例: ["Motor", "Emotor_R", "motor_parameter_2.xlsx"]
        返回: (component="Motor", instance="Emotor_R", variant_name="motor_parameter_2")

        只有一个文件段时（扁平结构）:
          ["motor_parameter.xlsx"]
          返回: (component=None, instance=None, variant_name="motor_parameter")
          → 调用方跳过（无法分类）
        """
        if len(parts) < 2:
            return None, None, None

        component = parts[0]                              # "Motor"
        instance = parts[1] if len(parts) > 2 else None   # "Emotor_R"
        file_name = parts[-1]                              # "motor_parameter_2.xlsx"
        variant_name = os.path.splitext(file_name)[0]      # "motor_parameter_2"

        return component, instance, variant_name

    def _detect_current_suffix(self, folder_path: str) -> Optional[str]:
        """从 folder_path（车型子目录）推断 suffix"""
        base = os.path.basename(folder_path)  # "增程车型_reevlto"

        # 规则 1: 后缀在目录名里（用 _ 分隔）
        if "_" in base:
            suffix = base.rsplit("_", 1)[-1]
            if suffix in self.vehicle_suffixes:
                return suffix

        # 规则 2: 目录名本身就是后缀
        if base in self.vehicle_suffixes:
            return base

        # 规则 3: 取 vehicle_suffixes 里第一个
        if self.vehicle_suffixes:
            return self.vehicle_suffixes[0]

        return None

    # =========================================================================
    # 核心查询接口（node 代码主要用这几个）
    # =========================================================================

    def get_all_variants(self, component: str, instance: str,
                         sheet_name: str,
                         vehicle_suffix: str) -> Dict[str, dict]:
        """
        获取某个实例下所有方案的某个 sheet 数据

        Args:
            component: 零部件类型（如 "Motor"）
            instance: 实例名（如 "Emotor_R"）
            sheet_name: sheet 名（如 "external_characteristin"）
            vehicle_suffix: 车型后缀

        Returns:
            {
                "motor_parameter_1": {type: "curve_1d", x: [...], y_abs: [...]},
                "motor_parameter_2": {type: "curve_1d", x: [...], y_abs: [...]},
            }
            如果没有匹配 → 返回 {}
        """
        if vehicle_suffix not in self._params:
            return {}
        if component not in self._params[vehicle_suffix]:
            return {}
        if instance not in self._params[vehicle_suffix][component]:
            return {}

        variants = self._params[vehicle_suffix][component][instance].get("_variants", {})
        result = {}
        for vname, vdata in variants.items():
            if sheet_name in vdata:
                result[vname] = vdata[sheet_name]
        return result

    def get_all_variants_by_axle(self, component: str, axle: str,
                                 sheet_name: str,
                                 vehicle_suffix: str) -> Dict[str, dict]:
        """
        按轴名查询（自动匹配 instance）

        底层通过 _instance_index 反向索引找到 instance 名，
        然后调 get_all_variants。

        Args:
            component: "Motor" / "Brake" / ...
            axle: "front" | "rear" | None（None 表示不区分轴）
            sheet_name: sheet 名
            vehicle_suffix: 车型后缀

        Returns:
            {variant_name: uniform_data}
        """
        if vehicle_suffix not in self._instance_index:
            return {}

        idx_comp = self._instance_index[vehicle_suffix].get(component, {})
        instance = idx_comp.get(axle)
        if instance is None:
            return {}

        return self.get_all_variants(component, instance, sheet_name, vehicle_suffix)

    def get_sheet_data(self, suffix: str, component: str, instance: str,
                       variant: str, sheet_name: str) -> Optional[Dict[str, Any]]:
        """精确取某个 variant 下某个 sheet 的完整数据（含 x/y/z 数组）。

        从 _params[suffix][component][instance]["_variants"][variant][sheet_name] 取值，
        不存在返回 None。注意跳过 "_meta" key（它和 sheet 同级但不是 sheet 数据）。
        """
        if suffix not in self._params:
            return None
        comp = self._params[suffix].get(component)
        if not comp:
            return None
        inst = comp.get(instance)
        if not inst:
            return None
        vdata = inst.get("_variants", {}).get(variant)
        if not vdata:
            return None
        sheet_data = vdata.get(sheet_name)
        if not isinstance(sheet_data, dict):
            return None
        return sheet_data

    # =========================================================================
    # 遍历辅助接口
    # =========================================================================

    def list_components(self, vehicle_suffix: str) -> List[str]:
        """返回某车型下已加载的零部件类型列表"""
        if vehicle_suffix not in self._params:
            return []
        return [c for c in self._params[vehicle_suffix].keys()
                if not c.startswith("_")]

    def list_instances(self, component: str, vehicle_suffix: str) -> List[str]:
        """返回某零部件下所有实例名（如 ["Emotor_F", "Emotor_R"]）"""
        if vehicle_suffix not in self._params:
            return []
        comp = self._params[vehicle_suffix].get(component, {})
        return [k for k in comp.keys() if not k.startswith("_")]

    def list_variant_names(self, component: str, instance: str,
                           vehicle_suffix: str) -> List[str]:
        """返回某实例下所有方案名（如 ["motor_parameter_1", "motor_parameter_2"]）"""
        if vehicle_suffix not in self._params:
            return []
        variants = (self._params[vehicle_suffix]
                       .get(component, {}).get(instance, {})
                       .get("_variants", {}))
        return list(variants.keys())

    def list_sheet_names(self, component: str, instance: str, variant_name: str,
                         vehicle_suffix: str) -> List[str]:
        """返回某方案文件里所有 sheet 名"""
        if vehicle_suffix not in self._params:
            return []
        vdata = (self._params[vehicle_suffix]
                    .get(component, {}).get(instance, {})
                    .get("_variants", {}).get(variant_name, {}))
        return [k for k in vdata.keys() if not k.startswith("_")]

    def get_axle(self, component: str, instance: str,
                 vehicle_suffix: str) -> Optional[str]:
        """返回某实例的 axle 标注（"front"/"rear"/None）"""
        if vehicle_suffix not in self._params:
            return None
        return self._params[vehicle_suffix].get(component, {}).get(
            instance, {}).get("_axle")

    # =========================================================================
    # 扁平参数（JSON/YAML 或 MemoryDB 桥接）—— 保留原接口
    # =========================================================================

    def get_flat(self, name: str, vehicle_suffix: str,
                 default: Any = None) -> Any:
        """
        读取扁平标量参数

        优先顺序：_flat_params → get_global（MemoryDB）
        """
        flat = self._params.get(vehicle_suffix, {}).get("_flat_params", {})
        if name in flat:
            return flat[name]
        return self.get_global(name, vehicle_suffix) or default

    def set_flat(self, name: str, vehicle_suffix: str, value: Any) -> None:
        """写入扁平标量参数"""
        if vehicle_suffix not in self._params:
            self.add_vehicle_suffix(vehicle_suffix)
        if "_flat_params" not in self._params[vehicle_suffix]:
            self._params[vehicle_suffix]["_flat_params"] = {}
        self._params[vehicle_suffix]["_flat_params"][name] = value

    # =========================================================================
    # 全局 DB 桥接（只读）
    # =========================================================================

    def get_global(self, name: str, vehicle_suffix: str,
                   param_type: str = "result") -> Any:
        """
        只读桥接全局 MemoryDatabase

        Args:
            name: base key（不带后缀）
            vehicle_suffix: 车型后缀
            param_type: "result"（当前值）/ "target"（目标值）/ "pass"（达标标识）
                        或 None（基础产品定义，不带 type 段）
        """
        if self._global_db is None:
            return None

        if param_type is None:
            db_key = f"{name}_{vehicle_suffix}"
        else:
            db_key = f"{name}_{param_type}_{vehicle_suffix}"

        try:
            return self._global_db.get_ssts_vts_param(db_key)
        except Exception as e:
            WorkLogger.warn(f"[SSTSSandbox] 读取全局参数失败 db_key={db_key}: {e}")
            return None

    # =========================================================================
    # commit 回写机制（保留原接口）
    # =========================================================================

    def mark_for_commit(self, *names: str) -> None:
        for name in names:
            self._commit_keys.add(name)

    def unmark_for_commit(self, *names: str) -> None:
        for name in names:
            self._commit_keys.discard(name)

    def clear_commit_marks(self) -> None:
        self._commit_keys.clear()

    def commit(self, param_type: str = "result") -> int:
        """将 _flat_params 里标记的参数写回全局 MemoryDatabase"""
        if self._global_db is None:
            WorkLogger.warn("[SSTSSandbox] global_db 未设置，无法 commit")
            return 0
        if not self._commit_keys:
            return 0

        success_count = 0
        for param_name in self._commit_keys:
            for veh_suffix in self.vehicle_suffixes:
                flat = self._params.get(veh_suffix, {}).get("_flat_params", {})
                if param_name not in flat:
                    continue
                db_key = f"{param_name}_{param_type}_{veh_suffix}"
                try:
                    if hasattr(self._global_db, 'set_ssts_vts_param'):
                        self._global_db.set_ssts_vts_param(db_key, flat[param_name])
                        success_count += 1
                except Exception as e:
                    WorkLogger.warn(f"[SSTSSandbox] commit 失败 db_key={db_key}: {e}")

        WorkLogger.info(f"[SSTSSandbox] commit 完成: {success_count} 个参数回写")
        return success_count

    # =========================================================================
    # 状态查询 / 快照 / 清空
    # =========================================================================

    def is_project_loaded(self) -> bool:
        """是否已关联项目文件夹并加载了零部件参数"""
        return self.loaded_file_count > 0

    def is_empty(self) -> bool:
        """沙箱是否为空（无任何后缀的数据）"""
        return all(len(self.list_components(s)) == 0
                   and not self._params[s].get("_flat_params")
                   for s in self.vehicle_suffixes)

    def get_commit_marked_keys(self) -> List[str]:
        return sorted(self._commit_keys)

    def snapshot(self) -> Dict[str, Any]:
        """导出当前状态（供 UI 检视 / LLM 工具调用）

        不展开数组数据（x/y/z 等 numpy list 不传给前端），
        只返回结构元信息 + 每个 sheet 的 type + shape 摘要，
        避免 payload 爆炸。
        """
        compact = {}
        for suffix in self.vehicle_suffixes:
            compact[suffix] = {}
            for comp in self.list_components(suffix):
                compact[suffix][comp] = {}
                for inst in self.list_instances(comp, suffix):
                    variants_info = {}
                    for vn in self.list_variant_names(comp, inst, suffix):
                        vdata = self._params[suffix][comp][inst]["_variants"].get(vn, {})
                        meta = vdata.get("_meta", {})
                        sheets_summary = {}
                        for sn, sheet_data in vdata.items():
                            if sn == "_meta" or not isinstance(sheet_data, dict):
                                continue
                            sheets_summary[sn] = self._summarize_sheet(sheet_data)
                        variants_info[vn] = {"_meta": meta, "sheets": sheets_summary}
                    compact[suffix][comp][inst] = {
                        "_axle": self.get_axle(comp, inst, suffix),
                        "_file_count": len(variants_info),
                        "_variants": variants_info,
                    }

        return {
            "is_project_loaded": self.is_project_loaded(),
            "project_folder": self.project_folder,
            "suffix_subfolder_map": dict(self._suffix_subfolder_map),
            "memory_db_file_path": self.memory_db_file_path,
            "loaded_file_count": self.loaded_file_count,
            "last_load_time": self.last_load_time.isoformat() if self.last_load_time else None,
            "vehicle_suffixes": list(self.vehicle_suffixes),
            "commit_marked_keys": self.get_commit_marked_keys(),
            "data": compact,
        }

    @staticmethod
    def _summarize_sheet(sheet_data: dict) -> dict:
        """从统一格式 sheet dict 提取 type + shape 摘要（snapshot 内部工具）"""
        t = sheet_data.get("type", "unknown")
        if t == "curve_1d":
            nx = len(sheet_data.get("x", []))
            return {
                "type": "curve_1d",
                "shape": f"{nx}p" if nx else "-",
                "x_label": sheet_data.get("x_label", ""),
                "y_label": sheet_data.get("y_label", ""),
            }
        if t == "map_2d":
            nx = len(sheet_data.get("x", []))
            ny = len(sheet_data.get("y", []))
            return {
                "type": "map_2d",
                "shape": f"{ny}×{nx}" if (nx and ny) else "-",
                "x_label": sheet_data.get("x_label", ""),
                "y_label": sheet_data.get("y_label", ""),
                "z_label": sheet_data.get("z_label", ""),
            }
        if t == "scalar":
            val = sheet_data.get("value")
            preview = str(val)[:60] if val is not None else ""
            return {"type": "scalar", "shape": "-", "preview": preview}
        return {"type": t, "shape": "-"}

    def clear(self) -> None:
        """清空所有加载的数据（保留项目关联属性，由上层重新设置）"""
        self._params.clear()
        self._instance_index.clear()
        self._commit_keys.clear()
        self.vehicle_suffixes.clear()
        self.loaded_file_count = 0
        self.last_load_time = None
        self._agent_config = {}

    # =========================================================================
    # 高层自动加载入口（agent 路径 + HTTP 路径共用）
    # =========================================================================

    def auto_load_for_agent(self, agent_config: dict, memory_db) -> int:
        """
        高层入口：从 memory_db + agent_config 自动完成索引 + 加载

        这是 agent 路径和 HTTP 路径共用的唯一自动加载入口。
        内部做的事：
          1. memory_db.file_path → 提取项目名 stem → 拼 data_dir / project_name
          2. 找不到项目根 → 返回 0
          3. memory_db.vehsuffix → 拿到车型后缀列表
          4. 项目根下扫子目录 → 后缀精确匹配（"reevlto" in "增程车型_reevlto"）
          5. 逐个调 self.load_from_folder(subfolder, filter, agent_config)

        Args:
            agent_config: agent 配置字典，至少包含 sandbox_config 子字典，
                         含 load_paths、axle_rules 等
            memory_db: MemoryDatabase 实例（含 file_path / vehsuffix）

        Returns:
            总加载文件数
        """
        sandbox_config = (agent_config or {}).get("sandbox_config", agent_config or {})
        filter_patterns = sandbox_config.get("load_paths") or None

        # ---- 1. 项目根检测 ----
        file_path = getattr(memory_db, "file_path", None) if memory_db else None
        if not file_path or not os.path.isfile(file_path):
            WorkLogger.info("[SSTSSandbox.auto_load] memory_db.file_path 无效，跳过")
            return 0

        data_dir = os.path.dirname(os.path.abspath(file_path))
        project_folder = self._detect_project_root(file_path, data_dir)
        if project_folder is None:
            WorkLogger.info(f"[SSTSSandbox.auto_load] 项目根未找到，data_dir={data_dir}")
            return 0

        self.project_folder = project_folder
        self.memory_db_file_path = file_path
        self._agent_config = agent_config or {}

        # ---- 2. 车型后缀列表 ----
        vehsuffix = list(getattr(memory_db, "vehsuffix", []) or [])
        self.vehsuffix_table = vehsuffix
        suffixes = [v.get("车型后缀", "") for v in vehsuffix if isinstance(v, dict) and v.get("车型后缀")]

        # ---- 3. 扫项目根 → 后缀精确匹配子目录 ----
        try:
            entries = sorted(os.listdir(project_folder))
        except Exception:
            entries = []

        suffix_to_subfolder: Dict[str, str] = {}
        for suffix in suffixes:
            # 规则 1: 后缀精确匹配目录名最后一段（防子串陷阱：evlto 不该匹配 reevlto）
            matched_subfolder = None
            for entry in entries:
                entry_path = os.path.join(project_folder, entry)
                if not os.path.isdir(entry_path):
                    continue
                # 目录名按 _ split，最后一段必须 == suffix（大小写不敏感）
                last_seg = entry.rsplit("_", 1)[-1].lower() if "_" in entry else entry.lower()
                if last_seg == suffix.lower():
                    matched_subfolder = entry
                    break

            # 规则 2: 回退 —— suffix 整体 in entry（目录名没有 _ 分隔符的情况）
            if matched_subfolder is None:
                for entry in entries:
                    entry_path = os.path.join(project_folder, entry)
                    if not os.path.isdir(entry_path):
                        continue
                    if entry.lower() == suffix.lower() or suffix.lower() in entry.lower():
                        matched_subfolder = entry
                        break

            # 规则 3: 再回退 —— 模糊匹配能源形式 / 车型名
            if matched_subfolder is None:
                veh = next((v for v in vehsuffix if v.get("车型后缀") == suffix), {})
                energy = veh.get("能源形式", "") if isinstance(veh, dict) else ""
                name = veh.get("车型", "") if isinstance(veh, dict) else ""
                for entry in entries:
                    entry_path = os.path.join(project_folder, entry)
                    if not os.path.isdir(entry_path):
                        continue
                    if (energy and energy in entry) or (name and name in entry):
                        matched_subfolder = entry
                        break

            if matched_subfolder:
                suffix_to_subfolder[suffix] = matched_subfolder

        if not suffix_to_subfolder:
            WorkLogger.info("[SSTSSandbox.auto_load] 项目根下没有匹配的车型子目录")
            return 0

        # 注册后缀到沙箱 + 记录 suffix → 完整子目录路径
        for suffix, subfolder in suffix_to_subfolder.items():
            self.add_vehicle_suffix(suffix)
            self._suffix_subfolder_map[suffix] = os.path.join(project_folder, subfolder)

        # ---- 4. 逐个加载 ----
        total = 0
        for suffix, subfolder in suffix_to_subfolder.items():
            veh_folder = os.path.join(project_folder, subfolder)
            if not os.path.isdir(veh_folder):
                continue
            WorkLogger.info(
                f"[SSTSSandbox.auto_load] 加载车型子目录: "
                f"suffix={suffix} → {subfolder}"
            )
            n = self.load_from_folder(veh_folder, filter_patterns, agent_config)
            total += n

        WorkLogger.info(
            f"[SSTSSandbox.auto_load] 完成: "
            f"{len(suffix_to_subfolder)} 个车型, 共 {total} 个参数文件"
        )
        return total

    @staticmethod
    def _detect_project_root(excel_path: str, data_dir: str) -> Optional[str]:
        """
        从 Excel 路径自动推断项目根目录

        真实使用场景（两种）：
          a) 原始 Excel 直接放在 data/ 下
             例: data/蜗牛项目-V6.0_ini.xlsx → 项目根 data/蜗牛项目/
          b) FastAPI 上传到 uploads/（加时间戳），但 data/ 是 uploads/ 的同级
             例: uploads/蜗牛项目-V6.0_ini_1791630630.xlsx
             → 向上爬一层到 uploads 的父目录
             → 父目录下有 data/ 子目录
             → 在 data/ 下找项目根

        识别规则（按优先级）：
          1. 从 stem 提取 "X项目" token → 拼 data_dir/token，存在就返回
          2. 向上爬找到同级 data/ 目录（处理 uploads/ 场景）
          3. 已知项目名兜底（蜗牛/越野/峰璟）
          4. 模糊 token 匹配

        返回绝对路径，找不到返回 None
        """
        stem = os.path.splitext(os.path.basename(excel_path))[0]

        # ---- 候选目录集：data_dir + 向上爬找到的同级 data/ ----
        candidate_dirs = [data_dir]

        # 规则 B: 处理 uploads 场景——向上爬，找同级 "data" 目录
        parent = os.path.dirname(data_dir)
        if parent != data_dir:   # 防止根目录死循环
            for sibling in os.listdir(parent):
                if sibling.lower() == "data":
                    sibling_data = os.path.join(parent, sibling)
                    if os.path.isdir(sibling_data) and sibling_data not in candidate_dirs:
                        candidate_dirs.append(sibling_data)
            # 也加 parent 自己（data/ 就在 snail_avatar 根下的情况）
            if parent not in candidate_dirs:
                candidate_dirs.append(parent)

        # ---- 规则 1: stem 里找含"项目"的 token ----
        idx = stem.find("项目")
        if idx > 0:
            sep_idx = max(stem.rfind("_", 0, idx), stem.rfind("-", 0, idx), stem.rfind(" ", 0, idx))
            token = stem[sep_idx + 1 if sep_idx >= 0 else 0: idx + 2]
            for cd in candidate_dirs:
                candidate = os.path.join(cd, token)
                if os.path.isdir(candidate):
                    return candidate

        # ---- 规则 2: 已知项目名兜底 ----
        for known in ["蜗牛", "越野", "峰璟"]:
            if known in stem:
                full = f"{known}项目"
                for cd in candidate_dirs:
                    candidate = os.path.join(cd, full)
                    if os.path.isdir(candidate):
                        return candidate

        # ---- 规则 3: 模糊 token 匹配 ----
        search_tokens = ["蜗牛", "越野", "峰璟", "项目"]
        for cd in candidate_dirs:
            if not os.path.isdir(cd):
                continue
            try:
                for entry in os.listdir(cd):
                    entry_path = os.path.join(cd, entry)
                    if not os.path.isdir(entry_path):
                        continue
                    if any(tok and tok in entry and tok in stem
                           for tok in search_tokens if tok in stem):
                        return entry_path
            except Exception:
                continue

        return None
