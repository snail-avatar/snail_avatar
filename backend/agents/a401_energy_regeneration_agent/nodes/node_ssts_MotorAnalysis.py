# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_MotorAnalysis.py
# @Desc    : 电驱参数分析节点（沙箱 → motor_variants 中间变量）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
电驱参数分析节点

职责（与 node_0 VehicleParam 并列，属输入准备层）：
  1. 遍历 SSTSSandbox 中所有 suffix × Motor component × instance × variant，
     提取每个方案的 external_characteristin（电驱外特性曲线）和 eff_map（效率 MAP）。
  2. 对每个方案计算统计量：max_torque_Nm / max_power_kw / speed_range /
     avg_efficiency / max_efficiency / eff_std / grid_shape。
  3. 统一输出成 motor_variants 三层嵌套 dict，key 格式为 "axle/variant_name"
     （如 "front/motor_parameter", "rear/motor_AAA"），天然支持下游 node_6 的
     _group_by_axle 拆分逻辑和 AWD 前后轴方案笛卡尔积融合。

输出结构：
  motor_variants = {
      suffix: {
          "front/motor_parameter": {
              "axle": "front",
              "variant_name": "motor_parameter",
              "sheets": {
                  "external_characteristin": {...curve_1d dict...},
                  "eff_map": {...map_2d dict...},
              },
              "stats": {max_torque_Nm, max_power_kw, speed_range_rpm,
                        avg_efficiency, max_efficiency, eff_std, grid_shape},
          },
          "rear/motor_AAA": {...},
      },
  }

下游节点：
  node_4 MotorLimit：遍历 motor_variants，按 key 取 curve_1d 算 F_edrv 数组。
  node_5 BatteryLimit：从 motor_variants["front/xxx"]["sheets"]["eff_map"] 取效率。
"""

from __future__ import annotations

import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import SSTSCalculationNode


class MotorAnalysisNode(SSTSCalculationNode):
    """电驱参数分析（沙箱 → 结构化中间变量）"""

    # =========================================================================
    # 统计量计算工具
    # =========================================================================

    @staticmethod
    def _compute_curve_stats(curve: dict) -> dict:
        """从 curve_1d 格式 dict 计算外特性统计量"""
        if curve is None or curve.get("type") != "curve_1d":
            return {
                "max_torque_Nm": 0.0,
                "max_power_kw": 0.0,
                "speed_range_rpm": [0.0, 0.0],
                "n_points_ext": 0,
            }

        x = np.array(curve.get("x", []), dtype=float)      # rpm
        y_abs = np.array(curve.get("y_abs") or curve.get("y", []), dtype=float)  # |Nm|

        if len(x) == 0 or len(y_abs) == 0:
            return {
                "max_torque_Nm": 0.0,
                "max_power_kw": 0.0,
                "speed_range_rpm": [0.0, 0.0],
                "n_points_ext": 0,
            }

        # max_power_kw = max(T * n / 9554)，T 取绝对值，n 只取正
        with np.errstate(divide='ignore', invalid='ignore'):
            power_kw = np.where(x > 0, y_abs * x / 9554.0, 0.0)

        return {
            "max_torque_Nm": float(np.max(y_abs)),
            "max_power_kw": float(np.max(power_kw)) if len(power_kw) > 0 else 0.0,
            "speed_range_rpm": [float(np.min(x)), float(np.max(x))],
            "n_points_ext": len(x),
        }

    @staticmethod
    def _compute_map_stats(map_dict: dict) -> dict:
        """从 map_2d 格式 dict 计算效率统计量"""
        if map_dict is None or map_dict.get("type") != "map_2d":
            return {
                "avg_efficiency": 0.0,
                "max_efficiency": 0.0,
                "min_efficiency": 0.0,
                "eff_std": 0.0,
                "grid_shape": [0, 0],   # (y_len, x_len) —— 效率 MAP 的网格形状
            }

        z = np.array(map_dict.get("z", []), dtype=float)   # [[z00, z01, ...], [z10, ...]]
        x = map_dict.get("x", [])
        y = map_dict.get("y", [])

        if z.size == 0:
            return {
                "avg_efficiency": 0.0,
                "max_efficiency": 0.0,
                "min_efficiency": 0.0,
                "eff_std": 0.0,
                "grid_shape": [len(y), len(x)],
            }

        return {
            "avg_efficiency": float(np.mean(z)),
            "max_efficiency": float(np.max(z)),
            "min_efficiency": float(np.min(z)),
            "eff_std": float(np.std(z)),
            "grid_shape": [len(y), len(x)],
        }

    @staticmethod
    def _merge_stats(curve_stats: dict, map_stats: dict) -> dict:
        """合并 curve 统计量和 map 统计量到单一 stats dict"""
        merged = {}
        merged.update(curve_stats or {})
        merged.update(map_stats or {})
        return merged

    # =========================================================================
    # 减速器折算：电机端特性 → 轮端特性
    # =========================================================================

    @staticmethod
    def _apply_reducer_curve(raw_curve: dict, gear_ratio: float) -> dict:
        """把电机端外特性曲线折算成轮端外特性曲线

        折算公式（驱动/馈电方向一致）：
          n_wheel = n_motor / gear_ratio    （转速除以减速比）
          T_wheel = T_motor × gear_ratio    （扭矩乘以减速比）

        gear_ratio=1.0 时恒等变换（数值不变）。
        gear_eff 不体现在扭矩曲线折算上——效率影响在 node_5 BatteryLimit
        的 eta_total = eta_motor × gear_eff 里体现。

        Args:
            raw_curve: curve_1d 格式 dict（电机端）
            gear_ratio: 主减速比（= 电机转速 / 轮端转速）

        Returns:
            curve_1d 格式 dict（轮端）
        """
        if raw_curve is None or raw_curve.get("type") != "curve_1d":
            return raw_curve

        gr = gear_ratio if gear_ratio and gear_ratio > 0 else 1.0

        result = dict(raw_curve)   # 浅拷贝，保留 labels 等元数据
        x = np.array(raw_curve.get("x", []), dtype=float)
        y = np.array(raw_curve.get("y", []), dtype=float)
        y_abs = np.array(raw_curve.get("y_abs") or [], dtype=float)

        result["x"] = list(x / gr)          # 轮端转速 = 电机转速 / 减速比
        result["y"] = list(y * gr)           # 轮端扭矩 = 电机扭矩 × 减速比
        result["y_abs"] = list(y_abs * gr)   # 绝对值同步放大
        return result

    @staticmethod
    def _apply_reducer_map(raw_map: dict, gear_ratio: float) -> dict:
        """把电机端效率 MAP 折算成轮端效率 MAP

        x 轴（转速）和 y 轴（扭矩）分别按 gear_ratio 缩放；
        z 轴（效率值）不变——效率是无量纲量，电机端和轮端的效率值是同一个数。

        gear_ratio=1.0 时恒等变换。
        """
        if raw_map is None or raw_map.get("type") != "map_2d":
            return raw_map

        gr = gear_ratio if gear_ratio and gear_ratio > 0 else 1.0

        result = dict(raw_map)
        x = np.array(raw_map.get("x", []), dtype=float)
        y = np.array(raw_map.get("y", []), dtype=float)

        result["x"] = list(x / gr)   # 转速轴除以减速比
        result["y"] = list(y * gr)   # 扭矩轴乘以减速比
        return result

    # =========================================================================
    # 默认方案（沙箱无数据时的 fallback）
    # =========================================================================

    @staticmethod
    def _build_default(axle: str) -> dict:
        """构造一个默认方案（沙箱无数据时兜底）

        轴无关：FWD 前轴、RWD 后轴、AWD 前后轴都可能需要。
        用通用值：T=120Nm, η=0.88, 转速 0~10000rpm。
        """
        default_curve = {
            "type": "curve_1d",
            "x_label": "rpm", "y_label": "Nm",
            "x": list(range(0, 10001, 500)),
            "y": [120.0] * 21,
            "y_abs": [120.0] * 21,
        }
        default_map = {
            "type": "map_2d",
            "x_label": "rpm", "y_label": "Nm", "z_label": "efficiency",
            "x": list(range(0, 10001, 500)),
            "y": list(range(20, 220, 20)),
            "z": [[0.88] * 21 for _ in range(10)],
        }

        curve_stats = MotorAnalysisNode._compute_curve_stats(default_curve)
        map_stats = MotorAnalysisNode._compute_map_stats(default_map)
        stats = MotorAnalysisNode._merge_stats(curve_stats, map_stats)
        stats["gear_ratio"] = 1.0
        stats["gear_eff"] = 1.0

        return {
            "axle": axle,
            "variant_name": "default",
            "sheets": {
                "external_characteristin": default_curve,
                "eff_map": default_map,
            },
            "stats": stats,
            "reducer": {"gear_ratio": 1.0, "gear_eff": 1.0},
        }

    # =========================================================================
    # 主流程
    # =========================================================================

    def numerical_solve(self, memory_db=None):
        sb = getattr(self, 'sandbox', None)
        if sb is None:
            # 沙箱不可用 → 给所有已注册 suffix 填充默认方案
            motor_variants = {
                suffix: {
                    "front/default": self._build_default("front"),
                    "rear/default": self._build_default("rear"),
                }
                for suffix in getattr(self, 'vehicle_suffixes', [])
            }
            self.intermediate_output_values["motor_variants"] = motor_variants
            return True

        motor_variants = {}

        for suffix in sb.vehicle_suffixes:
            suffix_variants = {}

            # 遍历所有 Motor 零部件的所有 instance
            for inst in sb.list_instances("Motor", suffix):
                axle = sb.get_axle("Motor", inst, suffix)
                if axle not in ("front", "rear"):
                    continue

                for vn in sb.list_variant_names("Motor", inst, suffix):
                    ext = sb.get_sheet_data(suffix, "Motor", inst, vn, "external_characteristin")
                    eff = sb.get_sheet_data(suffix, "Motor", inst, vn, "eff_map")

                    if ext is None:
                        # 没有外特性曲线 → 跳过这个方案
                        continue

                    # ---- 减速器参数：直接从 components_reader 输出的 scalar_dict 拿 ----
                    # reducer sheet 格式为 2 行 header+value（如 gear_radio/efficiency），
                    # components_reader 规则 0 已自动识别成 scalar_dict
                    reducer = {"gear_ratio": 1.0, "gear_eff": 1.0}
                    reducer_data = sb.get_sheet_data(suffix, "Motor", inst, vn, "reducer")
                    if reducer_data and reducer_data.get("type") == "scalar_dict":
                        d = reducer_data.get("data", {})
                        # 宽松匹配 key 名（gear_ratio / gear_radio / efficiency / gear_eff）
                        for k, v in d.items():
                            kl = k.lower()
                            if "ratio" in kl or "radio" in kl:
                                reducer["gear_ratio"] = float(v)
                            elif "eff" in kl:
                                reducer["gear_eff"] = float(v)

                    gr = reducer["gear_ratio"]
                    ge = reducer["gear_eff"]

                    # ---- 减速器折算：电机端特性 → 轮端特性 ----
                    ext_wheel = self._apply_reducer_curve(ext, gr)
                    eff_wheel = self._apply_reducer_map(eff, gr)

                    curve_stats = self._compute_curve_stats(ext_wheel)
                    map_stats = self._compute_map_stats(eff_wheel)
                    stats = self._merge_stats(curve_stats, map_stats)
                    # 把减速器参数也放进 stats（供语义分析展示 + 下游引用 gear_eff）
                    stats["gear_ratio"] = gr
                    stats["gear_eff"] = ge

                    suffix_variants[f"{axle}/{vn}"] = {
                        "axle": axle,
                        "variant_name": vn,
                        "sheets": {
                            "external_characteristin": ext_wheel,
                            "eff_map": eff_wheel,
                        },
                        "stats": stats,
                        "reducer": reducer,   # 原始减速器参数，下游按需读取
                    }

            # fallback：该 suffix 下没有任何 Motor 数据 → 默认方案
            if not suffix_variants:
                suffix_variants = {
                    "front/default": self._build_default("front"),
                    "rear/default": self._build_default("rear"),
                }

            motor_variants[suffix] = suffix_variants

        self.intermediate_output_values["motor_variants"] = motor_variants
        return True

    def semantic_solve(self) -> str:
        """电驱参数一览表（只展示当前激活车型 suffix）"""
        mv = self.intermediate_output_values.get("motor_variants", {})

        if not mv:
            return "### MotorAnalysis（电驱参数分析）计算节点分析报告\n\n数据为空。"

        # 只展示当前激活 suffix（与 generate_visualization、下游节点取值逻辑一致）
        active_suffix = getattr(self, 'vehicle_suffix', None)
        if active_suffix and active_suffix in mv:
            display_suffix = active_suffix
        else:
            display_suffix = list(mv.keys())[0]
        variants = mv.get(display_suffix, {})

        # 覆盖车型后缀（完整 intermediate 里有哪些 suffix）
        all_suffixes = list(mv.keys())

        lines = [
            "### MotorAnalysis（电驱参数分析）计算节点分析报告",
            "",
            "#### 参数来源",
            "- 数据来源：SSTSSandbox 项目文件夹加载的 Motor 零部件文件",
            f"- 覆盖车型后缀：{all_suffixes}",
            f"- 当前激活后缀：**{display_suffix}**",
            "",
            f"#### {display_suffix} 电驱参数一览",
            "",
        ]

        # 按 axle 分组展示
        by_axle = {"front": [], "rear": []}
        for key, entry in variants.items():
            axle = entry.get("axle", "front")
            if axle in by_axle:
                by_axle[axle].append((key, entry))

        axle_label = {"front": "前轴", "rear": "后轴"}

        for axle in ("front", "rear"):
            entries = by_axle[axle]
            if not entries:
                lines.append(f"**{axle_label[axle]}**：无方案")
                lines.append("")
                continue

            # 按 max_torque_Nm 降序
            entries.sort(key=lambda kv: kv[1]["stats"].get("max_torque_Nm", 0), reverse=True)

            lines.append(f"**{axle_label[axle]}** — 共 {len(entries)} 个方案")
            for key, entry in entries:
                st = entry.get("stats", {})
                lines.append(
                    f"  - `{key}`：Tmax={st.get('max_torque_Nm', 0):.0f} Nm, "
                    f"Pmax={st.get('max_power_kw', 0):.1f} kW, "
                    f"转速范围 {st.get('speed_range_rpm', [0, 0])[0]:.0f}~"
                    f"{st.get('speed_range_rpm', [0, 0])[1]:.0f} rpm"
                )
                if st.get("max_efficiency", 0) > 0:
                    lines.append(
                        f"    效率 MAP ({st.get('grid_shape', [0, 0])[0]}×"
                        f"{st.get('grid_shape', [0, 0])[1]})："
                        f"η_avg={st.get('avg_efficiency', 0):.3f}, "
                        f"η_max={st.get('max_efficiency', 0):.3f}, "
                        f"η_std={st.get('eff_std', 0):.4f}"
                    )
                # 减速器参数展示（gear_ratio=1 且 gear_eff=1 时为总成数据默认值）
                gr = st.get("gear_ratio", 1.0)
                ge = st.get("gear_eff", 1.0)
                lines.append(
                    f"    减速器：i0={gr:.3f}, η_gear={ge:.3f}"
                    + ("（总成数据，默认 1.0）" if gr == 1.0 and ge == 1.0 else "")
                )
            lines.append("")

        return "\n".join(lines)

    def generate_visualization(self):
        """返回电驱外特性曲线叠加图"""
        mv = self.intermediate_output_values.get("motor_variants", {})

        if not mv:
            return None

        suffix = self.vehicle_suffix if hasattr(self, 'vehicle_suffix') else None
        if suffix is None or suffix not in mv:
            suffix = list(mv.keys())[0]

        variants = mv.get(suffix, {})
        if not variants:
            return None

        series = []
        colors = {"front": "#e74c3c", "rear": "#3498db"}

        for key, entry in variants.items():
            axle = entry.get("axle", "front")
            curve = entry.get("sheets", {}).get("external_characteristin")
            if curve is None or curve.get("type") != "curve_1d":
                continue

            x = curve.get("x", [])
            y_abs = curve.get("y_abs") or curve.get("y", [])
            if len(x) == 0:
                continue

            series.append({
                "name": f"{key}",
                "x": list(x),
                "y": [float(v) for v in y_abs],
                "color": colors.get(axle),
            })

        if not series:
            return None

        return {
            "chart_type": "line",
            "title": f"电驱外特性曲线叠加（{suffix}）",
            "x_label": "转速 rpm",
            "y_label": "扭矩绝对值 Nm",
            "series": series,
        }
