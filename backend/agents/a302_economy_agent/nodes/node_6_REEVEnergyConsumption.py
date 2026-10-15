# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_6_REEVEnergyConsumption.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""增程整车能耗计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_6_REEVEnergyConsumption.yaml （单一真相源）
- 变量自动注册：workflow_reev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode


class REEVEnergyConsumptionNode(CalculationNode):
    """增程整车能耗计算器节点类
    
    最小物理过程6：增程式整车能耗综合计算
    职责：计算馈电油耗和综合续驶里程
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行增程整车能耗计算
        
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
            # 从上游节点读取中间变量
            cycle_distance = self.intermediate_input_values.get("cycle_distance")
            cycle_time = self.intermediate_input_values.get("cycle_time")
            
            # 从 SSTS 参数读取（包括从 node_5 输出到 VTS 的变量）
            e_dc = self.ssts_values.get("e_dc")
            e_ac = self.ssts_values.get("e_ac")
            mile_ev = self.ssts_values.get("mile_ev")
            ev_lp = self.ssts_values.get("ev_lp")
            reev_lp = self.ssts_values.get("reev_lp")
            dcdc_eff = self.ssts_values.get("dcdc_eff")
            re_eff = self.ssts_values.get("re_eff")
            fuel_tank = self.ssts_values.get("fuel_tank")
            
            # =============================================================
            # 纯算法逻辑（参考 reev_eco_calculator.py）
            # =============================================================
            
            # 计算增程模式低压能耗增加量 (kWh/100km)
            # Reev_Lpower_Plus = (L_V_Power_reev - L_V_Power)/DCDC_Eff * t_cycle / 3600 / 1000 / L_cycle * 100
            reev_lpower_plus = (reev_lp - ev_lp) / dcdc_eff * cycle_time / 3600 / 1000 / cycle_distance * 100
            
            # 计算馈电油耗 (L/100km)
            # CS_fuel = (E_DC + Reev_Lpower_Plus) / Range_Ext_Eff
            cs_fuel = (e_dc + reev_lpower_plus) / re_eff
            
            # 计算综合续驶里程 (km)
            # Mile_reev = Fuel_Tank / CS_fuel * 100 + Mile_ev
            mile_reev = fuel_tank / cs_fuel * 100 + mile_ev
            
            # =============================================================
            # 组织统计特征参数
            # =============================================================
            reev_energy_stats = {
                "ev_lp_w": float(ev_lp),
                "reev_lp_w": float(reev_lp),
                "dcdc_eff": float(dcdc_eff),
                "re_eff_kwh_per_l": float(re_eff),
                "fuel_tank_l": float(fuel_tank),
                "reev_lpower_plus_kwh_per_100km": float(reev_lpower_plus),
                "e_dc_kwh_per_100km": float(e_dc),
                "e_ac_kwh_per_100km": float(e_ac),
                "cs_fuel_l_per_100km": float(cs_fuel),
                "mile_ev_km": float(mile_ev),
                "mile_reev_km": float(mile_reev),
            }
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            # 核心能耗指标（输出到 VTS）
            # 使用 _sync_ssts_vts_output 方法写入 MemoryCore
            self._sync_ssts_vts_output(memory_db, "cs_fuel", float(cs_fuel))
            self._sync_ssts_vts_output(memory_db, "mile_reev", float(mile_reev))
            
            # 统计特征（输出到 intermediate）
            self.intermediate_output_values["reev_energy_stats"] = reev_energy_stats
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成增程整车能耗分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 增程整车能耗分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("reev_energy_stats", {})
        ssts = self.ssts_values
        
        report = f"""### node_6_ReEVEnergyConsumption（ReEV能耗）计算节点分析报告

#### 计算结果摘要

##### 低压功耗
- 纯电模式低压功耗：{stats.get('ev_lp_w', 0):.2f} W
- 增程模式低压功耗：{stats.get('reev_lp_w', 0):.2f} W
- 增程模式低压能耗增加量：{stats.get('reev_lpower_plus_kwh_per_100km', 0):.4f} kWh/100km

##### 效率参数
- 增程器发电效率：{stats.get('re_eff_kwh_per_l', 0):.2f} kWh/L

##### 能耗指标
- 纯电车端能耗：{stats.get('e_dc_kwh_per_100km', 0):.4f} kWh/100km
- 纯电网端能耗：{stats.get('e_ac_kwh_per_100km', 0):.4f} kWh/100km
- 馈电油耗：{stats.get('cs_fuel_l_per_100km', 0):.2f} L/100km

##### 续航里程
- 油箱容积：{stats.get('fuel_tank_l', 0):.0f} L
- 纯电续驶里程：{stats.get('mile_ev_km', 0):.2f} km
- 综合续驶里程：{stats.get('mile_reev_km', 0):.2f} km

#### 计算逻辑说明

- 输入：纯电车端能耗、纯电续驶里程（来自纯电整车能耗节点/VTS），循环里程/时间（来自驾驶循环节点），SSTS参数（低压功耗、增程器效率、油箱容积）
- 计算方法：
  * 增程低压能耗增加量：reev_lpower_plus = (reev_lp - ev_lp) / dcdc_eff × cycle_time / 3.6e6 / cycle_distance × 100
  * 馈电油耗：cs_fuel = (e_dc + reev_lpower_plus) / re_eff
  * 综合续驶里程：mile_reev = fuel_tank / cs_fuel × 100 + mile_ev
- 输出：馈电油耗、综合续驶里程（写入 VTS），能耗统计参数

#### 可调参数清单（用于 DOE 分析）

- ev_lp: 纯电模式低压功率, 单位: W, 当前值: {ssts.get('ev_lp', 0):.1f}
- reev_lp: 增程模式低压功率, 单位: W, 当前值: {ssts.get('reev_lp', 0):.1f}
- dcdc_eff: DC/DC效率, 单位: 无量纲, 当前值: {ssts.get('dcdc_eff', 0):.3f}
- re_eff: 增程器发电效率, 单位: kWh/L, 当前值: {ssts.get('re_eff', 0):.2f}
- fuel_tank: 油箱容积, 单位: L, 当前值: {ssts.get('fuel_tank', 0):.1f}

#### 输出参数清单（用于 DOE 的 output_vars）

- cs_fuel: 馈电油耗, 单位: L/100km
- mile_reev: 综合续驶里程, 单位: km"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report