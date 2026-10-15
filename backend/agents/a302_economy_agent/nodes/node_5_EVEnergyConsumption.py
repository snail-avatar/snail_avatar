# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_5_EVEnergyConsumption.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""纯电整车能耗计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_5_EVEnergyConsumption.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode


class EVEnergyConsumptionNode(CalculationNode):
    """纯电整车能耗计算器节点类
    
    最小物理过程5：纯电整车能耗综合计算
    职责：计算电池驱动能量、回收能量、低压能耗、车端能耗、网端能耗及纯电续驶里程
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行纯电整车能耗计算
        
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
            # 从上游节点读取
            cycle_distance = self.intermediate_input_values.get("cycle_distance")
            cycle_time = self.intermediate_input_values.get("cycle_time")
            e_elc_div_ts = self.intermediate_input_values.get("e_elc_div")
            e_elc_reg_ts = self.intermediate_input_values.get("e_elc_reg")
            
            # 从 SSTS 参数读取
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
            # 纯算法逻辑（参考 ev_eco_calculator.py #L202-207）
            # =============================================================
            
            # 获取电驱能量数组
            e_elc_div = e_elc_div_ts.value
            e_elc_reg = e_elc_reg_ts.value
            
            # 计算电池驱动能量 (kWh)
            # Bat_mot = np.sum(E_elc_div) / 1000 / 3600
            bat_mot = np.sum(e_elc_div) / 1000 / 3600
            
            # 计算电池回收能量 (kWh)
            # Bat_reg = np.sum(E_elc_reg) / 1000 / 3600
            bat_reg = np.sum(e_elc_reg) / 1000 / 3600
            
            # 计算低压能耗 (kWh)
            # E_low = L_V_Power / DCDC_Eff * Tim[-1] / 1000 / 3600
            e_low = ev_lp / dcdc_eff * cycle_time / 1000 / 3600
            
            # 计算车端能耗 (kWh/100km)
            # E_DC = (Bat_mot + Bat_reg + E_low) / L * 100 * E_gain
            e_dc = (bat_mot + bat_reg + e_low) / cycle_distance * 100 * e_gain
            
            # 计算纯电续驶里程 (km)
            # Mile_ev = Bat_eng * Bat_deepth / E_DC * 100
            mile_ev = bat_eng * bat_deepth / e_dc * 100

            # 计算网端能耗 (kWh/100km)
            # E_AC = E_DC / Bat_Eff / OBC_Eff + (Charge_LP / Charge_DCDC_Eff * Charge_Time / 1000 / Mile_ev * 100)
            # 第一部分：行驶能量的电网损耗
            e_ac_driving = e_dc / bat_eff / obc_eff
            # 第二部分：充电低压能耗分摊到每100km
            e_ac_charge_lp = charge_lp / charge_dcdc_eff * charge_time / 1000 / mile_ev * 100
            # 总网端能耗
            e_ac = e_ac_driving + e_ac_charge_lp
            
            # =============================================================
            # 组织统计特征参数
            # =============================================================
            vehicle_energy_stats = {
                "bat_mot_kwh": float(bat_mot),
                "bat_reg_kwh": float(bat_reg),
                "e_low_kwh": float(e_low),
                "e_dc_kwh_per_100km": float(e_dc),
                "e_ac_driving_kwh_per_100km": float(e_ac_driving),
                "e_ac_charge_lp_kwh_per_100km": float(e_ac_charge_lp),
                "e_ac_kwh_per_100km": float(e_ac),
                "mile_ev_km": float(mile_ev),
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
            # 核心能耗指标（输出到 VTS）
            # 使用 _sync_ssts_vts_output 方法写入 MemoryCore
            self._sync_ssts_vts_output(memory_db, "e_dc", float(e_dc))
            self._sync_ssts_vts_output(memory_db, "e_ac", float(e_ac))
            self._sync_ssts_vts_output(memory_db, "mile_ev", float(mile_ev))
            
            # 统计特征（输出到 intermediate）
            self.intermediate_output_values["vehicle_energy_stats"] = vehicle_energy_stats
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成整车能耗分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 整车能耗分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("vehicle_energy_stats", {})
        ssts = self.ssts_values
        
        report = f"""### node_5_EVEnergyConsumption（EV能耗）计算节点分析报告

#### 计算结果摘要

##### 能耗指标
- 电池驱动能量：{stats.get('bat_mot_kwh', 0):.4f} kWh
- 电池回收能量：{stats.get('bat_reg_kwh', 0):.4f} kWh
- 低压能耗：{stats.get('e_low_kwh', 0):.4f} kWh

##### 效率参数
- DC/DC效率：{stats.get('dcdc_eff', 0):.3f}
- 充电DC/DC效率：{stats.get('charge_dcdc_eff', 0):.3f}
- 电池效率：{stats.get('bat_eff', 0):.3f}
- OBC效率：{stats.get('obc_eff', 0):.3f}
- 能耗修正系数：{stats.get('e_gain', 0):.3f}

##### 充电参数
- 行驶低压功率：{stats.get('ev_lp_w', 0):.1f} W
- 充电低压功率：{stats.get('charge_lp_w', 0):.1f} W
- 充电时间：{stats.get('charge_time_h', 0):.1f} h

##### 综合能耗
- 车端能耗：{stats.get('e_dc_kwh_per_100km', 0):.4f} kWh/100km
- 行驶网端能耗：{stats.get('e_ac_driving_kwh_per_100km', 0):.4f} kWh/100km
- 充电低压分摊能耗：{stats.get('e_ac_charge_lp_kwh_per_100km', 0):.4f} kWh/100km
- 总网端能耗：{stats.get('e_ac_kwh_per_100km', 0):.4f} kWh/100km

##### 续航里程
- 纯电续驶里程：{stats.get('mile_ev_km', 0):.2f} km

#### 计算逻辑说明

- 输入：电驱驱动/回收能量（来自电驱能量节点），循环里程/时间（来自驾驶循环节点），SSTS参数（效率参数、电池参数、低压功耗）
- 计算方法：
  * 电池驱动能量：bat_mot = Σ(e_elc_div) / 3.6e6
  * 电池回收能量：bat_reg = Σ(e_elc_reg) / 3.6e6
  * 低压能耗：e_low = ev_lp / dcdc_eff × cycle_time / 3.6e6
  * 车端能耗：e_dc = (bat_mot + bat_reg + e_low) / cycle_distance × 100 × e_gain
  * 纯电续驶里程：mile_ev = bat_eng × bat_deepth / e_dc × 100
  * 网端能耗：e_ac = e_dc / bat_eff / obc_eff + 充电低压分摊
- 输出：车端能耗、网端能耗、纯电续驶里程（写入 VTS），能耗统计参数

#### 修正方法

- 能耗修正系数 e_gain：{ssts.get('e_gain', 0):.3f}，根据实车测试数据标定，调整理论计算与实测的偏差

#### 可调参数清单（用于 DOE 分析）

- ev_lp: 行驶低压功率, 单位: W, 当前值: {ssts.get('ev_lp', 0):.1f}
- charge_lp: 充电低压功率, 单位: W, 当前值: {ssts.get('charge_lp', 0):.1f}
- dcdc_eff: DC/DC效率, 单位: 无量纲, 当前值: {ssts.get('dcdc_eff', 0):.3f}
- charge_dcdc_eff: 充电DC/DC效率, 单位: 无量纲, 当前值: {ssts.get('charge_dcdc_eff', 0):.3f}
- charge_time: 充电时间, 单位: h, 当前值: {ssts.get('charge_time', 0):.1f}
- e_gain: 能耗修正系数, 单位: 无量纲, 当前值: {ssts.get('e_gain', 0):.3f}
- bat_eff: 电池效率, 单位: 无量纲, 当前值: {ssts.get('bat_eff', 0):.3f}
- obc_eff: OBC效率, 单位: 无量纲, 当前值: {ssts.get('obc_eff', 0):.3f}
- bat_eng: 电池标称能量, 单位: kWh, 当前值: {ssts.get('bat_eng', 0):.1f}
- bat_deepth: 电池放电深度, 单位: 无量纲, 当前值: {ssts.get('bat_deepth', 0):.3f}

#### 输出参数清单（用于 DOE 的 output_vars）

- e_dc: 车端能耗, 单位: kWh/100km
- e_ac: 网端能耗, 单位: kWh/100km
- mile_ev: 纯电续驶里程, 单位: km"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report