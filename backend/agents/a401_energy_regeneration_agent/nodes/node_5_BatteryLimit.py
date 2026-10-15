# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_5_BatteryLimit.py
# @Desc    : 电池充电功率限值节点（v4：eff_map 改从上游 MotorAnalysis 读）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
电池充电功率回收制动力限值

计算方法文档 §8：
  F_bat = 9554 · P_max(SOC, T) / (η(n) · n · R)   （V > Vmin 且 SOC < SOCmax）

v5 变化：
  - 基类改为 CalculationNode（不再直接碰沙箱）。
  - Battery 的 P_charge_map（电池最大充电功率）未来从上游 node_BatteryAnalysis
    的 intermediate 读取；当前 Battery 文件夹不存在，使用默认值 P=120kW。
  - eff_map（电机效率 MAP）从上游 node_ssts_MotorAnalysis 的
    motor_variants 里取前轴第一个方案的 eff_map。
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class BatteryLimitNode(CalculationNode):
    """电池充电功率限值"""

    # =========================================================================
    # 工具方法
    # =========================================================================

    @staticmethod
    def _interp(n_rpm, speed_arr, val_arr):
        """线性插值"""
        if len(speed_arr) == 0:
            return 0.0
        speed_arr = np.array(speed_arr, dtype=float)
        val_arr = np.array(val_arr, dtype=float)
        if n_rpm <= speed_arr[0]:
            return val_arr[0]
        if n_rpm >= speed_arr[-1]:
            return val_arr[-1]
        return float(np.interp(n_rpm, speed_arr, val_arr))

    # =========================================================================
    # 主流程
    # =========================================================================

    def numerical_solve(self, memory_db=None):
        R = self.intermediate_input_values.get("R", 0.0)
        suffix = self.vehicle_suffix

        V_min = self.ssts_values.get("V_min_regen", 5.0)
        SOC_max = self.ssts_values.get("SOC_max_regen", 0.95)
        SOC_ref = 0.3   # 标定条件：SOC=0.3, T_bat=25℃

        # Z 扫描：与 node_3 对齐，81 点
        Z_arr = np.round(np.arange(0.0, 0.801, 0.01), 3)
        V_arr = np.maximum(10.0, 120.0 - 125.0 * Z_arr)
        # 轮端转速（所有特性已是轮端，减速器折算已在 node_ssts_MotorAnalysis 完成）
        n_arr = V_arr / (0.377 * R) if R > 0 else np.zeros_like(V_arr)

        # ---- 从上游 motor_variants 取 eff_map + gear_eff ----
        motor_variants = self.intermediate_input_values.get("motor_variants", {})
        suffix_variants = motor_variants.get(suffix, {})

        # gear_eff：从第一个 front（或 rear）方案取——减速器效率是硬件属性，和方案无关
        gear_eff = 1.0
        for key, entry in suffix_variants.items():
            gear_eff = entry.get("reducer", {}).get("gear_eff", 1.0)
            break

        eta_speed, eta_val = None, None
        # 优先取 front 方案的 eff_map
        for key, entry in suffix_variants.items():
            if key.startswith("front/"):
                eff_map = entry.get("sheets", {}).get("eff_map")
                if eff_map and eff_map.get("type") == "map_2d":
                    # map_2d: x=rpm, y=Nm, z=efficiency
                    # 降维：取 z 的第一行（按 rpm 切，取第一个扭矩下的效率）
                    z = eff_map.get("z", [])
                    x = eff_map.get("x", [])
                    if len(z) > 0:
                        eta_speed = x
                        eta_val = z[0] if isinstance(z[0], list) else z
                    break
        # 没有 front → fallback 到 rear
        if eta_speed is None:
            for key, entry in suffix_variants.items():
                if key.startswith("rear/"):
                    eff_map = entry.get("sheets", {}).get("eff_map")
                    if eff_map and eff_map.get("type") == "map_2d":
                        z = eff_map.get("z", [])
                        x = eff_map.get("x", [])
                        if len(z) > 0:
                            eta_speed = x
                            eta_val = z[0] if isinstance(z[0], list) else z
                        break

        # ---- Battery P_charge_map：当前无 Battery 文件 → 默认值 ----
        # 未来 node_BatteryAnalysis 输出 battery_specs 后从 intermediate 读取
        P_arr, P_val = None, None

        # 默认值 fallback
        default_eta = 0.88
        default_P_kw = 120.0

        F_bat = np.zeros(81)
        for i in range(81):
            if V_arr[i] <= V_min or SOC_ref >= SOC_max:
                continue
            n = n_arr[i]
            if n <= 0:
                continue

            eta_motor = self._interp(n, eta_speed, eta_val) if eta_speed is not None else default_eta
            # 总效率 = 电机效率 × 减速器效率（馈电方向：轮端功率 → 减速器损耗 → 电机效率 → 电池）
            eta = eta_motor * gear_eff

            if P_arr is not None and P_val is not None and len(P_arr) > 0:
                P_kw = float(np.interp(SOC_ref, P_arr, P_val))
            else:
                P_kw = default_P_kw

            F_bat[i] = 9554.0 * P_kw / (eta * n * R) if R > 0 else 0.0

        self.intermediate_output_values["F_bat_max"] = F_bat
        return True

    def semantic_solve(self) -> str:
        SOC_max = self.ssts_values.get("SOC_max_regen", 0.95)
        F_bat = self.intermediate_output_values.get("F_bat_max", np.array([]))
        max_F = float(np.max(F_bat)) if len(F_bat) > 0 else 0.0
        suffix = self.vehicle_suffix

        motor_variants = self.intermediate_input_values.get("motor_variants", {})
        suffix_variants = motor_variants.get(suffix, {})

        eta_loaded = False
        for key, entry in suffix_variants.items():
            eff_map = entry.get("sheets", {}).get("eff_map")
            if eff_map and eff_map.get("type") == "map_2d":
                eta_loaded = True
                break

        P_arr, P_val = None, None   # 当前无 Battery 文件 → 默认值
        P_loaded = False

        lines = [
            "### BatteryLimit（电池充电功率限值）计算节点分析报告",
            "",
            "#### 计算结果摘要",
            f"- 关闭回收 SOC 阈值 SOC_max = {SOC_max}",
            f"- 参考 SOC=0.3, T_bat=25℃ 条件下",
            f"- eta_map: {'已加载' if eta_loaded else '未加载（默认 η=0.88）'}",
            f"- P_charge_map: {'已加载' if P_loaded else '未加载（默认 P=120kW）'}",
            f"- 电池侧最大回收制动力限值 ≈ {max_F:.1f} N",
            "",
            "#### 说明",
            f"- F_bat_max 为总量，与驱动形式无关",
            f"- eff_map 来自上游 node_ssts_MotorAnalysis 的 motor_variants",
            f"- P_charge_map 来自沙箱 Battery component（当前 Battery 文件夹不存在，使用默认值）",
        ]

        return "\n".join(lines)
