# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_5A_EVEnergyConsumptionHtem.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""高温工况整车能耗计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_5A_EVEnergyConsumptionHtem.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode


class EVEnergyConsumptionHtemNode(CalculationNode):
    """高温工况整车能耗计算器节点类

    最小物理过程5A：高温工况整车能耗综合计算
    职责：在标准工况基础上增加热管理系统能耗，计算高温工况下的能耗和里程衰减率
    """

    def numerical_solve(self, memory_db=None):
        """数值求解器：执行高温工况整车能耗计算

        【约定优于配置架构】
        - 输入：从 self.ssts_values 和 self.intermediate_input_values 获取
        - 输出：写入 self.intermediate_output_values

        Args:
            memory_db: 内存数据库引用（已废弃，保留兼容性）

        Returns:
            bool: 计算是否成功
        """
        try:
            # =============================================================
            # 读取输入（变量名与YAML完全对应）
            # =============================================================
            # 从 node_5 获取标准工况结果（VTS读取）
            e_dc_std = self.ssts_values.get("e_dc")
            e_ac_std = self.ssts_values.get("e_ac")
            mile_ev_std = self.ssts_values.get("mile_ev")

            # 从 node_1 获取循环参数
            cycle_distance = self.intermediate_input_values.get("cycle_distance")
            cycle_time = self.intermediate_input_values.get("cycle_time")

            # 从 SSTS 参数读取高温工况参数
            thermal_power_30 = self.ssts_values.get("thermal_power_30")
            bat_eff = self.ssts_values.get("bat_eff")
            obc_eff = self.ssts_values.get("obc_eff")
            charge_lp = self.ssts_values.get("charge_lp")
            charge_dcdc_eff = self.ssts_values.get("charge_dcdc_eff")
            charge_time = self.ssts_values.get("charge_time")

            # =============================================================
            # 纯算法逻辑（参考 ev_eco_Htem_calculator.py）
            # =============================================================

            # 计算热管理能耗（kWh）
            # E_therm = Thermal_Power_30 * cycle_time / 1000 / 3600
            e_therm = thermal_power_30 * cycle_time / 1000 / 3600

            # 热管理单位能耗（kWh/100km）
            e_therm_per_100km = e_therm / cycle_distance * 100

            # 高温工况车端能耗 = 标准工况车端能耗 + 热管理单位能耗
            e_dc_htem = e_dc_std + e_therm_per_100km

            # 高温工况续驶里程（假设电池容量不变，能耗增加导致里程减少）
            # mile_ev_htem = mile_ev_std * (e_dc_std / e_dc_htem)
            mile_ev_htem = mile_ev_std * (e_dc_std / e_dc_htem)

            # 高温工况网端能耗（含充电低压能耗分摊）
            # 第一部分：行驶能量的电网损耗
            e_ac_driving = e_dc_htem / bat_eff / obc_eff
            # 第二部分：充电低压能耗分摊到每100km
            e_ac_charge_lp = charge_lp / charge_dcdc_eff * charge_time / 1000 / mile_ev_htem * 100
            # 总网端能耗
            e_ac_htem = e_ac_driving + e_ac_charge_lp

            # 里程衰减率（百分比）
            mile_decay_30 = (1 - mile_ev_htem / mile_ev_std) * 100

            # =============================================================
            # 组织统计特征参数
            # =============================================================
            thermal_energy_stats = {
                "e_dc_std_kwh_per_100km": float(e_dc_std),
                "e_dc_htem_kwh_per_100km": float(e_dc_htem),
                "e_ac_std_kwh_per_100km": float(e_ac_std),
                "e_ac_htem_kwh_per_100km": float(e_ac_htem),
                "mile_ev_std_km": float(mile_ev_std),
                "mile_ev_htem_km": float(mile_ev_htem),
                "mile_decay_30_pct": float(mile_decay_30),
                "e_therm_kwh": float(e_therm),
                "e_therm_kwh_per_100km": float(e_therm_per_100km),
                "thermal_power_30_w": float(thermal_power_30),
                "bat_eff": float(bat_eff),
                "obc_eff": float(obc_eff),
                "charge_lp_w": float(charge_lp),
                "charge_dcdc_eff": float(charge_dcdc_eff),
                "charge_time_h": float(charge_time),
            }

            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            # 核心能耗指标（输出到 intermediate）
            self.intermediate_output_values["e_dc_htem"] = float(e_dc_htem)
            self.intermediate_output_values["e_ac_htem"] = float(e_ac_htem)
            self.intermediate_output_values["mile_ev_htem"] = float(mile_ev_htem)

            # 里程衰减率（输出到 VTS）
            self._sync_ssts_vts_output(memory_db, "mile_decay_30", float(mile_decay_30))

            # 统计特征（输出到 intermediate）
            self.intermediate_output_values["thermal_energy_stats"] = thermal_energy_stats

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False

    def semantic_solve(self) -> str:
        """语义求解器：生成高温工况能耗分析的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 高温工况能耗分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("thermal_energy_stats", {})
        ssts = self.ssts_values

        report = f"""### node_5A_EVEnergyConsumptionHtem（高温工况能耗分析）计算节点分析报告

#### 计算结果摘要

##### 标准工况基准
- 车端能耗：{stats.get('e_dc_std_kwh_per_100km', 0):.4f} kWh/100km
- 网端能耗：{stats.get('e_ac_std_kwh_per_100km', 0):.4f} kWh/100km
- 纯电续驶里程：{stats.get('mile_ev_std_km', 0):.2f} km

##### 高温工况修正
- 热管理功率：{stats.get('thermal_power_30_w', 0):.1f} W
- 热管理能耗增量：{stats.get('e_therm_kwh_per_100km', 0):.4f} kWh/100km

##### 高温工况结果
- 车端能耗：{stats.get('e_dc_htem_kwh_per_100km', 0):.4f} kWh/100km
- 网端能耗：{stats.get('e_ac_htem_kwh_per_100km', 0):.4f} kWh/100km
- 纯电续驶里程：{stats.get('mile_ev_htem_km', 0):.2f} km

##### 衰减分析
- 高温工况@30℃里程衰减率：{stats.get('mile_decay_30_pct', 0):.2f}%

#### 计算逻辑说明

- 输入：标准工况车端能耗、网端能耗、续驶里程（来自标准工况节点/VTS），循环里程/时间（来自驾驶循环节点），SSTS参数（热管理功率、效率参数）
- 计算方法：
  * 热管理能耗：E_therm = thermal_power_30 × cycle_time / 3.6e6
  * 热管理单位能耗：E_therm_per_100km = E_therm / cycle_distance × 100
  * 高温车端能耗：e_dc_htem = e_dc_std + E_therm_per_100km
  * 高温续驶里程：mile_ev_htem = mile_ev_std × (e_dc_std / e_dc_htem)
  * 高温网端能耗：e_ac_htem = e_dc_htem / bat_eff / obc_eff + 充电低压分摊
  * 里程衰减率：mile_decay_30 = (1 - mile_ev_htem / mile_ev_std) × 100
- 输出：高温工况车端能耗、网端能耗、续驶里程，里程衰减率（写入 VTS）

#### 可调参数清单（用于 DOE 分析）

- thermal_power_30: 高温热管理功率, 单位: W, 当前值: {ssts.get('thermal_power_30', 0):.1f}
- ev_lp: 行驶低压功率, 单位: W, 当前值: {ssts.get('ev_lp', 0):.1f}
- dcdc_eff: DC/DC效率, 单位: 无量纲, 当前值: {ssts.get('dcdc_eff', 0):.3f}
- bat_eff: 电池效率, 单位: 无量纲, 当前值: {ssts.get('bat_eff', 0):.3f}
- obc_eff: OBC效率, 单位: 无量纲, 当前值: {ssts.get('obc_eff', 0):.3f}

#### 输出参数清单（用于 DOE 的 output_vars）

- e_dc_htem: 高温车端能耗, 单位: kWh/100km
- e_ac_htem: 高温网端能耗, 单位: kWh/100km
- mile_ev_htem: 高温续驶里程, 单位: km
- mile_decay_30_pct: 高温里程衰减率, 单位: %"""

        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report

        return report