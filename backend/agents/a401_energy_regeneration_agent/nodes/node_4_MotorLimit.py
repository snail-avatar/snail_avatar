# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_4_MotorLimit.py
# @Desc    : 电驱外特性限值节点（v4：从上游 MotorAnalysis 读 motor_variants）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
电驱系统最大回收制动力限值

计算方法文档 §7：
  n = V / (0.377 · R · i0)   （轮端转速 rpm）
  F_edrv = T_max(n) / R       （V > Vmin 时）
  F_edrv = 0                  （V ≤ Vmin 时）

v4 变化：不再自己查沙箱，改为从上游 node_MotorAnalysis 输出的 motor_variants
中间变量读电驱方案。key 格式 "front/xxx" / "rear/yyy" 与 node_6 的 _group_by_axle
对齐。沙箱无数据时 node_MotorAnalysis 已经给了 front/default + rear/default。
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class MotorLimitNode(CalculationNode):
    """电驱外特性限值"""

    # =========================================================================
    # 工具方法
    # =========================================================================

    @staticmethod
    def _interp_T(n_rpm, speed_arr, torque_arr):
        """线性插值查 T_max(n)"""
        if len(speed_arr) == 0:
            return 0.0
        speed_arr = np.array(speed_arr, dtype=float)
        torque_arr = np.array(torque_arr, dtype=float)
        if n_rpm <= speed_arr[0]:
            return torque_arr[0]
        if n_rpm >= speed_arr[-1]:
            return torque_arr[-1]
        return float(np.interp(n_rpm, speed_arr, torque_arr))

    @staticmethod
    def _calc_F_edrv_from_curve(curve_dict: dict, n_arr, V_arr, R, V_min):
        """
        从 curve_1d 统一格式 dict 计算 F_edrv 数组

        Args:
            curve_dict: curve_1d 格式 dict（含 x=rpm, y_abs=|Nm|）
            n_arr: 各制动强度下的转速数组
            V_arr: 各制动强度下的车速数组
            R: 轮胎滚动半径 m
            V_min: 退出回收车速 km/h

        Returns:
            F_edrv: ndarray，每个 Z 点的最大电驱制动力 N
        """
        if curve_dict is None or curve_dict.get("type") != "curve_1d":
            return None

        speed = curve_dict.get("x", [])      # rpm
        torque = curve_dict.get("y_abs") or curve_dict.get("y", [])  # |Nm|

        if len(speed) == 0 or len(torque) == 0:
            return None

        F = np.zeros(len(n_arr))
        for i in range(len(n_arr)):
            if V_arr[i] <= V_min:
                continue
            T = MotorLimitNode._interp_T(n_arr[i], speed, torque)
            F[i] = T / R if R > 0 else 0.0
        return F

    # =========================================================================
    # 主流程
    # =========================================================================

    def numerical_solve(self, memory_db=None):
        R = self.intermediate_input_values.get("R", 0.0)
        suffix = self.vehicle_suffix     # WorkflowExecutor 注入

        V_min = self.ssts_values.get("V_min_regen", 5.0)

        # Z 扫描：与 node_3 对齐，81 点
        Z_arr = np.round(np.arange(0.0, 0.801, 0.01), 3)
        V_arr = np.maximum(10.0, 120.0 - 125.0 * Z_arr)
        # 轮端转速（所有特性已是轮端，不再乘 i0；减速器折算已在 node_MotorAnalysis 完成）
        n_arr = V_arr / (0.377 * R) if R > 0 else np.zeros_like(V_arr)

        # ---- 从上游 node_MotorAnalysis 读 motor_variants ----
        all_variants = self.intermediate_input_values.get("motor_variants", {})
        suffix_variants = all_variants.get(suffix, {})

        # per_variant_F_edrv: key = "front/xxx" / "rear/yyy"
        #                     value = F_edrv ndarray（81 点）
        per_variant_F_edrv = {}
        for key, entry in suffix_variants.items():
            ext = entry.get("sheets", {}).get("external_characteristin")
            F = self._calc_F_edrv_from_curve(ext, n_arr, V_arr, R, V_min)
            if F is not None:
                per_variant_F_edrv[key] = F

        # ---- 兼容旧输出字段 ----
        # F_edrv_max: 取第一个方案（只用于降级 / 语义）
        first_F = next(iter(per_variant_F_edrv.values()), np.zeros(len(n_arr)))

        # per_axle_maps: 按轴汇总（取该轴第一个方案）
        per_axle_maps = {"front": None, "rear": None}
        for key, F in per_variant_F_edrv.items():
            axle = key.split("/")[0]
            if axle in ("front", "rear") and per_axle_maps.get(axle) is None:
                per_axle_maps[axle] = F

        self.intermediate_output_values["per_variant_F_edrv"] = per_variant_F_edrv
        self.intermediate_output_values["F_edrv_max"] = first_F
        self.intermediate_output_values["per_axle_maps"] = per_axle_maps

        # 语义分析用：50 km/h 参考点的 Tmax
        # 优先从 stats 取，fallback 插值
        T_max_at_regen = 0.0
        for key, entry in suffix_variants.items():
            st = entry.get("stats", {})
            curve_ref = entry.get("sheets", {}).get("external_characteristin")
            if curve_ref and curve_ref.get("type") == "curve_1d":
                n_ref = 50.0 / (0.377 * R) if R > 0 else 0
                T_max_at_regen = self._interp_T(
                    n_ref, curve_ref["x"],
                    curve_ref.get("y_abs") or curve_ref["y"]
                )
                break
        self.intermediate_output_values["T_max_at_regen"] = T_max_at_regen

        return True

    def semantic_solve(self) -> str:
        per_variant = self.intermediate_output_values.get("per_variant_F_edrv", {})
        V_min = self.ssts_values.get("V_min_regen", 5.0)

        front_keys = [k for k in per_variant if k.startswith("front/")]
        rear_keys = [k for k in per_variant if k.startswith("rear/")]

        max_F_all = max(
            (float(np.max(F)) for F in per_variant.values() if len(F) > 0),
            default=0.0,
        )

        lines = [
            "### MotorLimit（电驱外特性限值）计算节点分析报告",
            "",
            "#### 计算结果摘要",
            f"- 退出回收车速 V_min = {V_min} km/h",
            f"- 共加载 {len(front_keys) + len(rear_keys)} 个电驱方案",
            "",
        ]

        if front_keys:
            lines.append(f"**前轴方案** ({len(front_keys)} 个):")
            for key in front_keys:
                max_f = float(np.max(per_variant[key]))
                lines.append(f"  - {key}: max F_edrv = {max_f:.1f} N")
            lines.append("")

        if rear_keys:
            lines.append(f"**后轴方案** ({len(rear_keys)} 个):")
            for key in rear_keys:
                max_f = float(np.max(per_variant[key]))
                lines.append(f"  - {key}: max F_edrv = {max_f:.1f} N")
            lines.append("")

        lines.append(f"- 所有方案中最大电驱限值 ≈ {max_F_all:.1f} N")

        return "\n".join(lines)
