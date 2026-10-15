# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_5B_EVEnergyConsumptionLtem_m7.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""低温-7℃工况整车能耗计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_5B_EVEnergyConsumptionLtem_m7.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode


class EVEnergyConsumptionLtemM7Node(CalculationNode):
    """低温-7℃工况整车能耗计算器节点类

    最小物理过程5B：低温-7℃工况整车能耗综合计算
    职责：计算低温-7℃环境下的车端能耗、网端能耗、续驶里程及里程衰减率
    """

    def numerical_solve(self, memory_db=None):
        """数值求解器：执行低温-7℃工况整车能耗计算

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
            # 从 node_1 获取循环参数
            cycle_distance = self.intermediate_input_values.get("cycle_distance")
            cycle_time = self.intermediate_input_values.get("cycle_time")

            # 从 node_4B 获取低温-7℃电驱能量
            e_elc_div_m7_ts = self.intermediate_input_values.get("e_elc_div_m7")
            e_elc_reg_m7_ts = self.intermediate_input_values.get("e_elc_reg_m7")

            # 从 node_5 获取标准工况结果（VTS读取）
            e_dc_std = self.ssts_values.get("e_dc")
            mile_ev_std = self.ssts_values.get("mile_ev")
            e_ac_std = self.ssts_values.get("e_ac")

            # 从 SSTS 参数读取 - 低温-7℃修正因子
            thermal_power_m7 = self.ssts_values.get("thermal_power_m7")
            bat_loss_m7 = self.ssts_values.get("bat_loss_m7")

            # 从 SSTS 参数读取 - 复用参数
            ev_lp = self.ssts_values.get("ev_lp")
            charge_lp = self.ssts_values.get("charge_lp")
            dcdc_eff = self.ssts_values.get("dcdc_eff")
            charge_dcdc_eff = self.ssts_values.get("charge_dcdc_eff")
            charge_time = self.ssts_values.get("charge_time")
            e_gain = self.ssts_values.get("e_gain")
            bat_eff = self.ssts_values.get("bat_eff")
            obc_eff = self.ssts_values.get("obc_eff")
            bat_eng = self.ssts_values.get("bat_eng")
            bat_deepth = self.ssts_values.get("bat_deepth")

            # =============================================================
            # 纯算法逻辑（参考 ev_eco_Ltem_calculator.py）
            # =============================================================

            # 获取低温-7℃电驱能量数组
            e_elc_div_m7 = e_elc_div_m7_ts.value
            e_elc_reg_m7 = e_elc_reg_m7_ts.value

            # 计算低温-7℃电池驱动能量 (kWh)
            bat_mot_m7 = np.sum(e_elc_div_m7) / 1000 / 3600

            # 计算低温-7℃电池回收能量 (kWh)
            bat_reg_m7 = np.sum(e_elc_reg_m7) / 1000 / 3600

            # 计算低温-7℃低压能耗 (kWh)
            e_low_m7 = ev_lp / dcdc_eff * cycle_time / 1000 / 3600

            # 计算低温-7℃热管理能耗 (kWh)
            e_therm_m7 = thermal_power_m7 * cycle_time / 1000 / 3600

            # 计算低温-7℃车端能耗 (kWh/100km)
            e_dc_ltem_m7 = (bat_mot_m7 + bat_reg_m7 + e_low_m7 + e_therm_m7) / cycle_distance * 100 * e_gain

            # 计算低温-7℃续驶里程（考虑电池能量衰减）
            mile_ev_ltem_m7 = bat_eng * bat_deepth * bat_loss_m7 / e_dc_ltem_m7 * 100

            # 计算低温-7℃网端能耗
            e_ac_driving_m7 = e_dc_ltem_m7 / bat_eff / obc_eff
            e_ac_charge_lp_m7 = charge_lp / charge_dcdc_eff * charge_time / 1000 / mile_ev_ltem_m7 * 100 #充电网端能耗
            e_ac_ltem_m7 = e_ac_driving_m7 + e_ac_charge_lp_m7

            # 计算里程衰减率（百分比）
            mile_decay_m7 = (1 - mile_ev_ltem_m7 / mile_ev_std) * 100

            # =============================================================
            # 组织统计特征参数
            # =============================================================
            ltem_energy_stats_m7 = {
                "e_dc_std_kwh_per_100km": float(e_dc_std),
                "e_dc_ltem_m7_kwh_per_100km": float(e_dc_ltem_m7),
                "e_ac_std_kwh_per_100km": float(e_ac_std),
                "e_ac_ltem_m7_kwh_per_100km": float(e_ac_ltem_m7),
                "mile_ev_std_km": float(mile_ev_std),
                "mile_ev_ltem_m7_km": float(mile_ev_ltem_m7),
                "mile_decay_m7_pct": float(mile_decay_m7),
                "bat_mot_m7_kwh": float(bat_mot_m7),
                "bat_reg_m7_kwh": float(bat_reg_m7),
                "e_low_m7_kwh": float(e_low_m7),
                "e_therm_m7_kwh": float(e_therm_m7),
                "thermal_power_m7_w": float(thermal_power_m7),
                "bat_loss_m7": float(bat_loss_m7),
                "ev_lp_w": float(ev_lp),
                "charge_lp_w": float(charge_lp),
                "dcdc_eff": float(dcdc_eff),
                "charge_dcdc_eff": float(charge_dcdc_eff),
                "charge_time_h": float(charge_time),
                "e_gain": float(e_gain),
                "bat_eff": float(bat_eff),
                "obc_eff": float(obc_eff),
                "bat_eng_kwh": float(bat_eng),
                "bat_deepth": float(bat_deepth),
            }

            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            # 核心能耗指标（输出到 intermediate）
            self.intermediate_output_values["e_dc_ltem_m7"] = float(e_dc_ltem_m7)
            self.intermediate_output_values["e_ac_ltem_m7"] = float(e_ac_ltem_m7)
            self.intermediate_output_values["mile_ev_ltem_m7"] = float(mile_ev_ltem_m7)

            # 里程衰减率（输出到 VTS）
            self._sync_ssts_vts_output(memory_db, "mile_decay_m7", float(mile_decay_m7))

            # 统计特征（输出到 intermediate）
            self.intermediate_output_values["ltem_energy_stats_m7"] = ltem_energy_stats_m7

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False

    def semantic_solve(self) -> str:
        """语义求解器：生成低温-7℃工况能耗分析的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 低温-7℃工况能耗分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("ltem_energy_stats_m7", {})
        ssts = self.ssts_values

        report = f"""### node_5B_EVEnergyConsumptionLtem_m7（低温-7℃EV能耗）计算节点分析报告

#### 计算结果摘要

##### 标准工况基准
- 车端能耗：{stats.get('e_dc_std_kwh_per_100km', 0):.4f} kWh/100km
- 网端能耗：{stats.get('e_ac_std_kwh_per_100km', 0):.4f} kWh/100km
- 纯电续驶里程：{stats.get('mile_ev_std_km', 0):.2f} km

##### 低温-7℃修正因子
- 低温加热功率：{stats.get('thermal_power_m7_w', 0):.1f} W
- 低温电池能量衰减率：{stats.get('bat_loss_m7', 0):.3f}

##### 低温-7℃能耗增量
- 低温电池驱动能量：{stats.get('bat_mot_m7_kwh', 0):.4f} kWh
- 低温电池回收能量：{stats.get('bat_reg_m7_kwh', 0):.4f} kWh
- 低温低压能耗：{stats.get('e_low_m7_kwh', 0):.4f} kWh
- 低温热管理能耗：{stats.get('e_therm_m7_kwh', 0):.4f} kWh

##### 低温-7℃工况结果
- 车端能耗：{stats.get('e_dc_ltem_m7_kwh_per_100km', 0):.4f} kWh/100km
- 网端能耗：{stats.get('e_ac_ltem_m7_kwh_per_100km', 0):.4f} kWh/100km
- 纯电续驶里程：{stats.get('mile_ev_ltem_m7_km', 0):.2f} km

##### 衰减分析
- 低温工况@-7℃里程衰减率：{stats.get('mile_decay_m7_pct', 0):.2f}%

#### 计算逻辑说明

- 输入：低温-7℃电驱驱动/回收能量（来自低温电驱能量节点），标准工况续驶里程（来自 VTS），循环里程/时间（来自驾驶循环节点），SSTS参数（热管理功率、电池衰减率、效率参数）
- 计算方法：
  * 低温电池驱动能量：bat_mot_m7 = Σ(e_elc_div_m7) / 3.6e6
  * 低温低压能耗：e_low_m7 = ev_lp / dcdc_eff × cycle_time / 3.6e6
  * 低温热管理能耗：e_therm_m7 = thermal_power_m7 × cycle_time / 3.6e6
  * 低温车端能耗：e_dc_ltem_m7 = (bat_mot_m7 + bat_reg_m7 + e_low_m7 + e_therm_m7) / cycle_distance × 100 × e_gain
  * 低温续驶里程：mile_ev_ltem_m7 = bat_eng × bat_deepth × bat_loss_m7 / e_dc_ltem_m7 × 100
  * 里程衰减率：mile_decay_m7 = (1 - mile_ev_ltem_m7 / mile_ev_std) × 100
- 输出：低温-7℃车端能耗、网端能耗、续驶里程，里程衰减率（写入 VTS）

#### 可调参数清单（用于 DOE 分析）

- thermal_power_m7: 低温加热功率, 单位: W, 当前值: {ssts.get('thermal_power_m7', 0):.1f}
- bat_loss_m7: 低温电池能量衰减率, 单位: 无量纲, 当前值: {ssts.get('bat_loss_m7', 0):.3f}
- ev_lp: 行驶低压功率, 单位: W, 当前值: {ssts.get('ev_lp', 0):.1f}
- dcdc_eff: DC/DC效率, 单位: 无量纲, 当前值: {ssts.get('dcdc_eff', 0):.3f}
- e_gain: 能耗修正系数, 单位: 无量纲, 当前值: {ssts.get('e_gain', 0):.3f}

#### 输出参数清单（用于 DOE 的 output_vars）

- e_dc_ltem_m7: 低温车端能耗, 单位: kWh/100km
- e_ac_ltem_m7: 低温网端能耗, 单位: kWh/100km
- mile_ev_ltem_m7: 低温续驶里程, 单位: km
- mile_decay_m7_pct: 低温里程衰减率, 单位: %"""

        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report

        return report