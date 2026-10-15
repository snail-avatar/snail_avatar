# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_3C_WheelEnergyLtem_m20.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""低温-20℃轮端能量计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_3C_WheelEnergyLtem_m20.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class WheelEnergyLtemM20Node(CalculationNode):
    """低温-20℃轮端能量计算器节点类
    
    最小物理过程3C：低温-20℃轮端能量积分计算
    职责：计算低温-20℃环境下的各阻力能耗和动能变化，最终得到低温轮端驱动/制动能量
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行低温-20℃轮端能量计算
        
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
            # 从 node_1 获取中间变量
            cycle_distance = self.intermediate_input_values.get("cycle_distance")
            acc_mask = self.intermediate_input_values.get("acc_mask")
            dec_mask = self.intermediate_input_values.get("dec_mask")
            const_mask = self.intermediate_input_values.get("const_mask")
            vel_ave = self.intermediate_input_values.get("vel_ave")
            lth = self.intermediate_input_values.get("lth")
            a = self.intermediate_input_values.get("a")
            
            # 从 node_2C 获取低温-20℃阻力
            f_road_load_m20 = self.intermediate_input_values.get("f_road_load_m20")
            f_aer_m20 = self.intermediate_input_values.get("f_aer_m20")
            f_roll_m20 = self.intermediate_input_values.get("f_roll_m20")
            f_drg_m20 = self.intermediate_input_values.get("f_drg_m20")
            mass = self.intermediate_input_values.get("mass")
            
            # 从 SSTS 参数读取
            r_in = self.ssts_values.get("r_in")
            rad = self.ssts_values.get("rad")
            
            # =============================================================
            # 纯算法逻辑（参考 node_3_WheelEnergy.py）
            # =============================================================
            
            # 计算转动惯量等效质量
            mass_rot = r_in / (rad * rad)
            
            # 获取时间轴和数据
            time = lth.time
            lth_value = lth.value
            
            # 计算低温-20℃各能耗分量（力 × 距离）
            e_aer_m20 = f_aer_m20.value * lth_value
            e_roll_m20 = f_roll_m20 * lth_value
            e_drg_m20 = f_drg_m20 * lth_value
            e_road_load_m20 = f_road_load_m20.value * lth_value
            
            # 计算低温-20℃动能变化
            e_kin_m20 = (mass + mass_rot) * a.value * lth_value
            
            # 计算低温-20℃轮端总能量
            e_wheel_m20 = e_road_load_m20 + e_kin_m20
            
            # 计算低温-20℃驱动能量和制动能量
            e_wheel_div_m20 = np.where(e_wheel_m20 > 0, e_wheel_m20, 0)
            e_wheel_reg_m20 = np.where(e_wheel_m20 < 0, e_wheel_m20, 0)
            
            # =============================================================
            # 计算统计特征参数
            # =============================================================
            
            # 计算单位能耗转换因子
            distance_factor = 100.0 / cycle_distance if cycle_distance > 0 else 0.0
            
            wheel_energy_stats_m20 = {
                # 单位能耗 (kWh/100km)
                "e_aer_m20_sum_kwh_per_100km": float(np.sum(e_aer_m20) / 1000 / 3600 * distance_factor),
                "e_roll_m20_sum_kwh_per_100km": float(np.sum(e_roll_m20) / 1000 / 3600 * distance_factor),
                "e_drg_m20_sum_kwh_per_100km": float(np.sum(e_drg_m20) / 1000 / 3600 * distance_factor),
                "e_road_load_m20_sum_kwh_per_100km": float(np.sum(e_road_load_m20) / 1000 / 3600 * distance_factor),
                "e_kin_m20_sum_kwh_per_100km": float(np.sum(e_kin_m20) / 1000 / 3600 * distance_factor),
                "e_wheel_div_m20_sum_kwh_per_100km": float(np.sum(e_wheel_div_m20) / 1000 / 3600 * distance_factor),
                "e_wheel_reg_m20_sum_kwh_per_100km": float(np.sum(e_wheel_reg_m20) / 1000 / 3600 * distance_factor),
                
                # 加速段单位能耗
                "e_aer_m20_acc_sum_kwh_per_100km": float(np.sum(e_aer_m20[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_roll_m20_acc_sum_kwh_per_100km": float(np.sum(e_roll_m20[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_drg_m20_acc_sum_kwh_per_100km": float(np.sum(e_drg_m20[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_road_load_m20_acc_sum_kwh_per_100km": float(np.sum(e_road_load_m20[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_kin_m20_acc_sum_kwh_per_100km": float(np.sum(e_kin_m20[acc_mask]) / 1000 / 3600 * distance_factor),
                
                # 恒速段单位能耗
                "e_aer_m20_const_sum_kwh_per_100km": float(np.sum(e_aer_m20[const_mask]) / 1000 / 3600 * distance_factor),
                "e_roll_m20_const_sum_kwh_per_100km": float(np.sum(e_roll_m20[const_mask]) / 1000 / 3600 * distance_factor),
                "e_drg_m20_const_sum_kwh_per_100km": float(np.sum(e_drg_m20[const_mask]) / 1000 / 3600 * distance_factor),
                "e_road_load_m20_const_sum_kwh_per_100km": float(np.sum(e_road_load_m20[const_mask]) / 1000 / 3600 * distance_factor),
                "e_kin_m20_const_sum_kwh_per_100km": float(np.sum(e_kin_m20[const_mask]) / 1000 / 3600 * distance_factor),
                
                # 减速段单位能耗
                "e_aer_m20_dec_sum_kwh_per_100km": float(np.sum(e_aer_m20[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_roll_m20_dec_sum_kwh_per_100km": float(np.sum(e_roll_m20[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_drg_m20_dec_sum_kwh_per_100km": float(np.sum(e_drg_m20[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_road_load_m20_dec_sum_kwh_per_100km": float(np.sum(e_road_load_m20[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_kin_m20_dec_sum_kwh_per_100km": float(np.sum(e_kin_m20[dec_mask]) / 1000 / 3600 * distance_factor),
            }
            
            # =============================================================
            # 创建 TimeSeries 输出
            # =============================================================
            e_aer_m20_ts = TimeSeries(
                time=time,
                value=e_aer_m20,
                name="e_aer_m20",
                unit="J",
                desc="低温-20℃风阻能耗"
            )
            
            e_roll_m20_ts = TimeSeries(
                time=time,
                value=e_roll_m20,
                name="e_roll_m20",
                unit="J",
                desc="低温-20℃滚阻能耗"
            )
            
            e_drg_m20_ts = TimeSeries(
                time=time,
                value=e_drg_m20,
                name="e_drg_m20",
                unit="J",
                desc="低温-20℃拖滞能耗"
            )
            
            e_road_load_m20_ts = TimeSeries(
                time=time,
                value=e_road_load_m20,
                name="e_road_load_m20",
                unit="J",
                desc="低温-20℃道路阻力能耗"
            )
            
            e_kin_m20_ts = TimeSeries(
                time=time,
                value=e_kin_m20,
                name="e_kin_m20",
                unit="J",
                desc="低温-20℃动能变化"
            )
            
            e_wheel_m20_ts = TimeSeries(
                time=time,
                value=e_wheel_m20,
                name="e_wheel_m20",
                unit="J",
                desc="低温-20℃轮端总能量"
            )
            
            e_wheel_div_m20_ts = TimeSeries(
                time=time,
                value=e_wheel_div_m20,
                name="e_wheel_div_m20",
                unit="J",
                desc="低温-20℃驱动能量"
            )
            
            e_wheel_reg_m20_ts = TimeSeries(
                time=time,
                value=e_wheel_reg_m20,
                name="e_wheel_reg_m20",
                unit="J",
                desc="低温-20℃回收能量"
            )
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            self.intermediate_output_values["e_aer_m20"] = e_aer_m20_ts
            self.intermediate_output_values["e_roll_m20"] = e_roll_m20_ts
            self.intermediate_output_values["e_drg_m20"] = e_drg_m20_ts
            self.intermediate_output_values["e_road_load_m20"] = e_road_load_m20_ts
            self.intermediate_output_values["e_kin_m20"] = e_kin_m20_ts
            self.intermediate_output_values["e_wheel_m20"] = e_wheel_m20_ts
            self.intermediate_output_values["e_wheel_div_m20"] = e_wheel_div_m20_ts
            self.intermediate_output_values["e_wheel_reg_m20"] = e_wheel_reg_m20_ts
            self.intermediate_output_values["wheel_energy_stats_m20"] = wheel_energy_stats_m20
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成低温-20℃轮端能量分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 低温-20℃轮端能量分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("wheel_energy_stats_m20", {})
        ssts = self.ssts_values
        
        report = f"""### node_3C_WheelEnergyLtem_m20（低温-20℃车轮能量）计算节点分析报告

#### 计算结果摘要

##### 低温-20℃阻力能耗（总循环）
- 低温风阻能耗：{stats.get('e_aer_m20_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温滚阻能耗：{stats.get('e_roll_m20_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温拖滞能耗：{stats.get('e_drg_m20_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温道路阻力总能耗：{stats.get('e_road_load_m20_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 低温-20℃轮端能量
- 低温轮端驱动能量总和：{stats.get('e_wheel_div_m20_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温轮端最大可回收能量：{stats.get('e_wheel_reg_m20_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 低温-20℃加速段能耗
- 低温风阻能耗：{stats.get('e_aer_m20_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温滚阻能耗：{stats.get('e_roll_m20_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温拖滞能耗：{stats.get('e_drg_m20_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温道路阻力能耗：{stats.get('e_road_load_m20_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温加速段动能增加：{stats.get('e_kin_m20_acc_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 低温-20℃恒速段能耗
- 低温风阻能耗：{stats.get('e_aer_m20_const_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温滚阻能耗：{stats.get('e_roll_m20_const_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温拖滞能耗：{stats.get('e_drg_m20_const_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温道路阻力能耗：{stats.get('e_road_load_m20_const_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 低温-20℃减速段能耗
- 低温风阻能耗：{stats.get('e_aer_m20_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温滚阻能耗：{stats.get('e_roll_m20_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温拖滞能耗：{stats.get('e_drg_m20_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温道路阻力能耗：{stats.get('e_road_load_m20_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温减速段动能减少：{stats.get('e_kin_m20_dec_sum_kwh_per_100km', 0):.4f} kWh/100km

#### 计算逻辑说明

- 输入：低温-20℃阻力分量（来自低温阻力计算节点），行驶距离、工况掩码（来自驾驶循环节点）
- 计算方法：与标准工况相同的能量积分框架
  * 各阻力能耗：E = F × s（使用低温阻力值）
  * 动能变化：ΔE_kin = (mass + mass_rot) × a × s
  * 轮端总能量：E_wheel_m20 = E_road_load_m20 + E_kin_m20
- 输出：低温-20℃各能耗分量时间序列，轮端驱动/回收能量，分工况统计参数

#### 可调参数清单（用于 DOE 分析）

- r_in: 等效转动惯量, 单位: kg·m², 当前值: {ssts.get('r_in', 0):.2f}
- rad: 车轮半径, 单位: m, 当前值: {ssts.get('rad', 0):.3f}

#### 输出参数清单（用于 DOE 的 output_vars）

- e_aer_m20: 低温风阻能耗时间序列, 单位: J
- e_roll_m20: 低温滚阻能耗时间序列, 单位: J
- e_drg_m20: 低温拖滞能耗时间序列, 单位: J
- e_road_load_m20: 低温道路阻力能耗时间序列, 单位: J
- e_kin_m20: 低温动能变化时间序列, 单位: J
- e_wheel_m20: 低温轮端总能量时间序列, 单位: J
- e_wheel_div_m20: 低温驱动能量时间序列, 单位: J
- e_wheel_reg_m20: 低温回收能量时间序列, 单位: J"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report