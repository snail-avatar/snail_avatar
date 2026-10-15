# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_6_FinalFusion.py
# @Desc    : 最终回收制动力融合节点（v3：多方案 × 三驱动形式全量融合）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
最终回收制动力融合（v3：多方案全量并行）

核心变化：node_4 现在输出 per_variant_F_edrv（多方案电驱限值），
FinalFusion 对所有方案组合 × FWD/RWD/AWD 三种驱动形式做笛卡尔积融合，
输出 M×N 条对比结果。

输入：
  strategy_curves: dict          ← node_3（三驱动形式策略线，不变）
  per_variant_F_edrv: dict       ← node_4（v3 多方案，新主输入）
      "front/motor_parameter": F_edrv_arr,
      "rear/motor_parameter_1": F_edrv_arr,
      "rear/motor_parameter_2": F_edrv_arr,
  per_axle_maps / F_edrv_max     ← node_4（兼容旧输出，降级用）
  F_bat_max: ndarray             ← node_5（电池总量，不分方案）

融合逻辑（与旧版相同，只是输入遍历范围扩展）：
  F_Mot^max = min(F_edrv, F_bat_axle)
  F_Mot^cmd = min(F_Mot^max, F_drive_req)
  F_mech = G·Z - F_Mot^cmd
"""

import itertools
import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class FinalFusionNode(CalculationNode):
    """最终回收制动力融合（v3：多方案 × 三驱动形式全量）"""

    # =========================================================================
    # 融合辅助函数（不变）
    # =========================================================================

    @staticmethod
    def _single_axle_fusion(F_drive_req, F_edrv, F_bat, G, Z):
        """单轴融合（FWD/RWD 用）"""
        F_mot_max = np.minimum(F_edrv, F_bat)
        F_mot_cmd = np.minimum(F_mot_max, F_drive_req)
        F_mech = G * Z - F_mot_cmd

        mask = F_drive_req > 1
        avg_eff = float(np.mean(F_mot_cmd[mask] / F_drive_req[mask])) if np.sum(mask) > 0 else 0.0

        coverage = np.where(F_mot_cmd > 0, 1.0, 0.0)
        coverage_ratio = float(np.sum(coverage) / len(Z)) if len(Z) > 0 else 0.0
        max_F = float(np.max(F_mot_cmd)) if len(F_mot_cmd) > 0 else 0.0
        Z_at_max = float(Z[np.argmax(F_mot_cmd)]) if len(Z) > 0 else 0.0

        return {
            "F_mot_cmd": F_mot_cmd,
            "F_mot_max": F_mot_max,
            "F_mech": F_mech,
            "stats": {
                "coverage_ratio": coverage_ratio,
                "avg_efficiency": avg_eff,
                "max_F_mot_cmd": max_F,
                "Z_at_max": Z_at_max,
                "total_points": len(Z),
            },
        }

    @staticmethod
    def _dual_axle_fusion(F_front_req, F_rear_req,
                          F_edrv_f, F_edrv_r, F_bat_total, G, Z):
        """分轴融合（AWD 用）：电池总量按电驱能力比例切分"""
        total_edrv = F_edrv_f + F_edrv_r
        with np.errstate(divide='ignore', invalid='ignore'):
            r_f = np.where(total_edrv > 0, F_edrv_f / np.maximum(total_edrv, 1), 0.5)
            r_r = 1.0 - r_f

        F_bat_f = F_bat_total * r_f
        F_bat_r = F_bat_total * r_r

        F_mot_max_f = np.minimum(F_edrv_f, F_bat_f)
        F_mot_max_r = np.minimum(F_edrv_r, F_bat_r)

        F_mot_cmd_f = np.minimum(F_mot_max_f, F_front_req)
        F_mot_cmd_r = np.minimum(F_mot_max_r, F_rear_req)

        F_mot_cmd = F_mot_cmd_f + F_mot_cmd_r
        F_mech = G * Z - F_mot_cmd

        F_drive_total = F_front_req + F_rear_req
        mask = F_drive_total > 1
        avg_eff = float(np.mean(F_mot_cmd[mask] / F_drive_total[mask])) if np.sum(mask) > 0 else 0.0

        coverage = np.where(F_mot_cmd > 0, 1.0, 0.0)
        coverage_ratio = float(np.sum(coverage) / len(Z)) if len(Z) > 0 else 0.0
        max_F = float(np.max(F_mot_cmd)) if len(F_mot_cmd) > 0 else 0.0
        Z_at_max = float(Z[np.argmax(F_mot_cmd)]) if len(Z) > 0 else 0.0

        return {
            "F_mot_cmd": F_mot_cmd,
            "F_mot_max": F_mot_max_f + F_mot_max_r,
            "F_mot_cmd_front": F_mot_cmd_f,
            "F_mot_cmd_rear": F_mot_cmd_r,
            "F_mech": F_mech,
            "stats": {
                "coverage_ratio": coverage_ratio,
                "avg_efficiency": avg_eff,
                "max_F_mot_cmd": max_F,
                "Z_at_max": Z_at_max,
                "total_points": len(Z),
            },
        }

    # =========================================================================
    # 方案分组辅助
    # =========================================================================

    @staticmethod
    def _group_by_axle(per_variant_F_edrv: dict) -> dict:
        """
        把 node_4 输出的 per_variant_F_edrv 按 axle 分组

        Input:  {"front/motor_parameter": F_arr,
                 "rear/motor_parameter_1": F_arr,
                 "rear/motor_parameter_2": F_arr}
        Output: {"front": {"motor_parameter": F_arr},
                 "rear":  {"motor_parameter_1": F_arr, "motor_parameter_2": F_arr}}
        """
        grouped: Dict[str, Dict[str, Any]] = {"front": {}, "rear": {}}
        for key, value in per_variant_F_edrv.items():
            if "/" in key:
                axle, variant = key.split("/", 1)
            else:
                axle, variant = "front", key
            if axle in grouped:
                grouped[axle][variant] = value
        return grouped

    @staticmethod
    def _fallback_from_legacy(per_axle_maps: dict, F_edrv_max, n: int) -> dict:
        """旧输出降级：把 per_axle_maps 转成 front/rear 各一个方案"""
        grouped = {"front": {}, "rear": {}}
        if per_axle_maps:
            F_f = per_axle_maps.get("front")
            F_r = per_axle_maps.get("rear")
            if F_f is not None and len(F_f) == n:
                grouped["front"]["legacy_front"] = F_f
            if F_r is not None and len(F_r) == n:
                grouped["rear"]["legacy_rear"] = F_r
        if not grouped["front"] and not grouped["rear"] and len(F_edrv_max) == n:
            grouped["front"]["default_axle"] = F_edrv_max
        return grouped

    # =========================================================================
    # 主流程
    # =========================================================================

    def numerical_solve(self, memory_db=None):
        G = self.intermediate_input_values.get("G", 0.0)
        Z = self.intermediate_input_values.get("Z_array", np.array([]))
        sc = self.intermediate_input_values.get("strategy_curves", {})
        F_bat_max = self.intermediate_input_values.get("F_bat_max", np.array([]))

        n = len(Z)
        if n == 0:
            return False

        def _align(arr):
            if arr is None or len(arr) == 0:
                return np.zeros(n)
            return arr if len(arr) == n else np.zeros(n)

        F_bat_max = _align(F_bat_max)

        # ---- 分组方案 ----
        per_variant = self.intermediate_input_values.get("per_variant_F_edrv", {})
        if per_variant:
            grouped = self._group_by_axle(per_variant)
        else:
            # 降级：旧输出
            pam = self.intermediate_input_values.get("per_axle_maps", {})
            F_edrv_max = self.intermediate_input_values.get("F_edrv_max", np.array([]))
            grouped = self._fallback_from_legacy(pam, F_edrv_max, n)

        front_variants = grouped["front"]   # {"mp_F": F_arr}
        rear_variants = grouped["rear"]     # {"mp_R1": F_arr, "mp_R2": F_arr}

        # ---- 多方案 × 三驱动形式笛卡尔积融合 ----
        fusion_results = {}   # key = "drive|front:xxx|rear:xxx"
        comparison = {}       # 简化版汇总（按驱动形式取最佳方案）

        # --- FWD: 只用 front 方案 ---
        fwd_entry = sc.get("fwd", {})
        if fwd_entry.get("valid") and front_variants:
            F_drive_fwd = _align(fwd_entry.get("F_drive"))
            for vname, F_edrv in front_variants.items():
                key = f"FWD|front:{vname}"
                res = self._single_axle_fusion(
                    F_drive_fwd, _align(F_edrv), F_bat_max, G, Z
                )
                res["valid"] = True
                res["invalid_reason"] = None
                res["drive_type"] = "FWD"
                res["variant_combo"] = {"front": vname, "rear": None}
                fusion_results[key] = res
        elif fwd_entry.get("valid"):
            # 无任何 front 方案 → 无效
            fusion_results["FWD|no_front"] = {
                "valid": False, "invalid_reason": "no front motor variants",
                "drive_type": "FWD",
            }

        # --- RWD: 只用 rear 方案 ---
        rwd_entry = sc.get("rwd", {})
        if rwd_entry.get("valid") and rear_variants:
            F_drive_rwd = _align(rwd_entry.get("F_drive"))
            for vname, F_edrv in rear_variants.items():
                key = f"RWD|rear:{vname}"
                res = self._single_axle_fusion(
                    F_drive_rwd, _align(F_edrv), F_bat_max, G, Z
                )
                res["valid"] = True
                res["invalid_reason"] = None
                res["drive_type"] = "RWD"
                res["variant_combo"] = {"front": None, "rear": vname}
                fusion_results[key] = res
        elif rwd_entry.get("valid"):
            fusion_results["RWD|no_rear"] = {
                "valid": False, "invalid_reason": "no rear motor variants",
                "drive_type": "RWD",
            }

        # --- AWD: front × rear 笛卡尔积 ---
        awd_entry = sc.get("awd", {})
        if awd_entry.get("valid") and (front_variants or rear_variants):
            F_front_req = _align(awd_entry.get("F_front"))
            F_rear_req = _align(awd_entry.get("F_rear"))

            # 至少一套方案：另一轴用 0 或 fallback
            front_keys = list(front_variants.keys()) or [None]
            rear_keys = list(rear_variants.keys()) or [None]

            for vf, vr in itertools.product(front_keys, rear_keys):
                F_f = _align(front_variants[vf]) if vf else np.zeros(n)
                F_r = _align(rear_variants[vr]) if vr else np.zeros(n)

                # 退化：某轴无方案时，把总量均分
                if not vf and not vr:
                    continue
                if not vf:
                    F_f = F_r * 0.5
                    F_r = F_r * 0.5
                    vf = f"{vr}_split"
                if not vr:
                    F_r = F_f * 0.5
                    F_f = F_f * 0.5
                    vr = f"{vf}_split"

                key = f"AWD|front:{vf}|rear:{vr}"
                res = self._dual_axle_fusion(
                    F_front_req, F_rear_req, F_f, F_r, F_bat_max, G, Z
                )
                res["valid"] = True
                res["invalid_reason"] = None
                res["drive_type"] = "AWD"
                res["variant_combo"] = {"front": vf, "rear": vr}
                fusion_results[key] = res
        elif awd_entry.get("valid"):
            fusion_results["AWD|no_motor"] = {
                "valid": False, "invalid_reason": "no motor variants",
                "drive_type": "AWD",
            }

        # ---- 对比汇总：按驱动形式取最佳方案 ----
        for drive in ["FWD", "RWD", "AWD"]:
            drive_entries = [(k, v) for k, v in fusion_results.items()
                           if v.get("drive_type") == drive and v.get("valid")]
            if drive_entries:
                # 按 max_F_mot_cmd 降序，取最佳
                drive_entries.sort(
                    key=lambda kv: kv[1].get("stats", {}).get("max_F_mot_cmd", 0),
                    reverse=True,
                )
                best_key, best = drive_entries[0]
                comparison[drive] = {
                    "best_variant": best_key,
                    "max_F_mot_cmd": best.get("stats", {}).get("max_F_mot_cmd", 0),
                    "coverage_ratio": best.get("stats", {}).get("coverage_ratio", 0),
                    "avg_efficiency": best.get("stats", {}).get("avg_efficiency", 0),
                    "Z_at_max": best.get("stats", {}).get("Z_at_max", 0),
                    "valid": True,
                    "total_variants": len(drive_entries),
                }
            else:
                reason = next((v.get("invalid_reason", "")
                              for k, v in fusion_results.items()
                              if v.get("drive_type") == drive), "no variants")
                comparison[drive] = {"valid": False, "invalid_reason": reason}

        self.intermediate_output_values["fusion_results"] = fusion_results
        self.intermediate_output_values["comparison"] = comparison

        return True

    def semantic_solve(self) -> str:
        results = self.intermediate_output_values.get("fusion_results", {})
        comparison = self.intermediate_output_values.get("comparison", {})

        lines = [
            "### FinalFusion（最终回收制动力融合）计算节点分析报告",
            "",
            "#### 多方案 × 三驱动形式融合结果概览",
            "",
        ]

        # 按驱动形式分组展示
        for drive in ["FWD", "RWD", "AWD"]:
            drive_entries = [(k, v) for k, v in results.items()
                           if v.get("drive_type") == drive]
            lines.append(f"**{drive}** — {len(drive_entries)} 个方案组合")

            if not drive_entries:
                lines.append("  （无有效方案）")
                lines.append("")
                continue

            # 按 max_F 排序
            drive_entries.sort(
                key=lambda kv: kv[1].get("stats", {}).get("max_F_mot_cmd", 0),
                reverse=True,
            )

            for key, entry in drive_entries:
                valid = entry.get("valid", False)
                tag = "✓" if valid else "✗"
                parts = key.split("|", 1)[1] if "|" in key else key
                lines.append(f"  {tag} {parts}")
                if valid:
                    stats = entry.get("stats", {})
                    lines.append(
                        f"    max={stats.get('max_F_mot_cmd', 0):.0f} N, "
                        f"cov={stats.get('coverage_ratio', 0)*100:.1f}%, "
                        f"eff={stats.get('avg_efficiency', 0)*100:.1f}%"
                    )
                else:
                    lines.append(f"    {entry.get('invalid_reason', '')}")
            lines.append("")

        # 对比表（每个驱动形式取最佳方案）
        valid_comp = [(d, c) for d, c in comparison.items() if c.get("valid")]
        if valid_comp:
            lines.append("#### 各驱动形式最佳方案对比")
            lines.append("")
            header = f"  {'Drive':<6} {'Best Variant':<32} {'F_max(N)':<12} {'Cov%':<8} {'Eff%':<8} {'Z@max':<8}"
            lines.append(header)
            lines.append("  " + "-" * (len(header) - 2))
            for drive, c in valid_comp:
                lines.append(
                    f"  {drive:<6} {c.get('best_variant', ''):<32.32} "
                    f"{c.get('max_F_mot_cmd', 0):<12.0f} "
                    f"{c.get('coverage_ratio', 0)*100:<8.1f} "
                    f"{c.get('avg_efficiency', 0)*100:<8.1f} "
                    f"{c.get('Z_at_max', 0):<8.3f}"
                )

        return "\n".join(lines)

    def generate_visualization(self):
        """返回各驱动形式最佳方案的实际回收对比"""
        Z = self.intermediate_input_values.get("Z_array", np.array([]))
        results = self.intermediate_output_values.get("fusion_results", {})
        comparison = self.intermediate_output_values.get("comparison", {})

        if len(Z) == 0:
            return None

        colors = {"FWD": "#e74c3c", "RWD": "#3498db", "AWD": "#2ecc71"}
        series = []

        # 只画每个驱动形式的最佳方案（避免图太乱）
        for drive in ["FWD", "RWD", "AWD"]:
            best_info = comparison.get(drive, {})
            if not best_info.get("valid"):
                continue
            best_key = best_info.get("best_variant")
            if best_key and best_key in results:
                F_cmd = results[best_key].get("F_mot_cmd", np.array([]))
                if len(F_cmd) > 0:
                    series.append({
                        "name": f"{drive} 最佳: {best_key.split('|', 1)[1] if '|' in best_key else best_key}",
                        "x": Z.tolist(),
                        "y": F_cmd.tolist(),
                        "color": colors.get(drive),
                    })

        return {
            "chart_type": "line",
            "title": "能量回收最终制动力融合（各驱动形式最佳方案对比）",
            "x_label": "制动强度 Z",
            "y_label": "制动力 (N)",
            "series": series,
        }
