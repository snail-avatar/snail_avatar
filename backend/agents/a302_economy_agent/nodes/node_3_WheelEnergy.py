# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_3_WheelEnergy.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""轮端能量计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_3_WheelEnergy.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class WheelEnergyNode(CalculationNode):
    """轮端能量计算器节点类
    
    最小物理过程3：轮端能量积分计算
    职责：力×距离 = 能量，计算各阻力能耗和动能变化，最终得到轮端驱动/制动能量
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行轮端能量计算
        
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
            # 从上游节点读取中间变量（TimeSeries 对象）
            cycle_distance = self.intermediate_input_values.get("cycle_distance")  # 循环总里程（km）
            acc_mask = self.intermediate_input_values.get("acc_mask")             # 加速段掩码
            dec_mask = self.intermediate_input_values.get("dec_mask")             # 减速段掩码
            const_mask = self.intermediate_input_values.get("const_mask")         # 恒速段掩码
            vel_ave = self.intermediate_input_values.get("vel_ave")               # 区间平均速度，N-1长度
            vel = self.intermediate_input_values.get("vel")                       # 原始速度，N长度（用于计算时间间隔）
            lth = self.intermediate_input_values.get("lth")                       # 行驶距离，N-1长度
            f_road_load = self.intermediate_input_values.get("f_road_load")  # 道路阻力，N-1长度
            f_aer = self.intermediate_input_values.get("f_aer")       # 空气阻力，N-1长度
            a = self.intermediate_input_values.get("a")               # 加速度，N-1长度
            
            # 从上游节点读取标量
            f_roll = self.intermediate_input_values.get("f_roll")     # 滚动阻力，常数
            f_drg = self.intermediate_input_values.get("f_drg")       # 拖滞阻力，常数
            mass = self.intermediate_input_values.get("mass")         # 测试质量
            
            # 从 SSTS 参数读取
            r_in = self.ssts_values.get("r_in")                       # 转动惯量
            rad = self.ssts_values.get("rad")                         # 车轮半径
            
            # =============================================================
            # 纯算法逻辑（参考 ev_eco_calculator.py）
            # =============================================================
            
            # 计算转动惯量等效质量
            mass_rot = r_in / (rad * rad)
            
            # 获取时间轴和数据
            time = lth.time           # N-1 长度时间轴
            lth_value = lth.value     # 行驶距离数组
            vel_ave_value = vel_ave.value  # 区间平均速度（N-1长度，直接从node_1获取）
            
            # 计算各能耗分量（力 × 距离）
            e_aer = f_aer.value * lth_value              # 风阻能耗
            e_roll = f_roll * lth_value                  # 滚阻能耗（常数 × 距离数组）
            e_drg = f_drg * lth_value                    # 拖滞能耗（常数 × 距离数组）
            e_road_load = f_road_load.value * lth_value  # 道路总阻力能耗
            
            # 计算动能变化（使用动能定理：力 × 距离 = 能量变化）
            # ΔE_kin = m * a * s = (mass + mass_rot) * a * lth_value
            e_kin = (mass + mass_rot) * a.value * lth_value
            
            # 计算轮端总能量
            e_wheel = e_road_load + e_kin
            
            # 计算驱动能量和制动能量
            e_wheel_div = np.where(e_wheel > 0, e_wheel, 0)  # 驱动能量（正值）
            e_wheel_reg = np.where(e_wheel < 0, e_wheel, 0)  # 回收能量（负值）
            
            # =============================================================
            # 计算统计特征参数
            # =============================================================
            
            # 计算单位能耗转换因子 (kWh/100km = kWh / km * 100)
            distance_factor = 100.0 / cycle_distance if cycle_distance > 0 else 0.0
            
            wheel_energy_stats = {
                # 单位能耗 (kWh/100km)
                "e_aer_sum_kwh_per_100km": float(np.sum(e_aer) / 1000 / 3600 * distance_factor),
                "e_roll_sum_kwh_per_100km": float(np.sum(e_roll) / 1000 / 3600 * distance_factor),
                "e_drg_sum_kwh_per_100km": float(np.sum(e_drg) / 1000 / 3600 * distance_factor),
                "e_road_load_sum_kwh_per_100km": float(np.sum(e_road_load) / 1000 / 3600 * distance_factor),
                "e_kin_sum_kwh_per_100km": float(np.sum(e_kin) / 1000 / 3600 * distance_factor),
                "e_wheel_div_sum_kwh_per_100km": float(np.sum(e_wheel_div) / 1000 / 3600 * distance_factor),
                "e_wheel_reg_sum_kwh_per_100km": float(np.sum(e_wheel_reg) / 1000 / 3600 * distance_factor),
                
                # 加速段单位能耗
                "e_aer_acc_sum_kwh_per_100km": float(np.sum(e_aer[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_roll_acc_sum_kwh_per_100km": float(np.sum(e_roll[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_drg_acc_sum_kwh_per_100km": float(np.sum(e_drg[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_road_load_acc_sum_kwh_per_100km": float(np.sum(e_road_load[acc_mask]) / 1000 / 3600 * distance_factor),
                "e_kin_acc_sum_kwh_per_100km": float(np.sum(e_kin[acc_mask]) / 1000 / 3600 * distance_factor),
                
                # 恒速段单位能耗
                "e_aer_const_sum_kwh_per_100km": float(np.sum(e_aer[const_mask]) / 1000 / 3600 * distance_factor),
                "e_roll_const_sum_kwh_per_100km": float(np.sum(e_roll[const_mask]) / 1000 / 3600 * distance_factor),
                "e_drg_const_sum_kwh_per_100km": float(np.sum(e_drg[const_mask]) / 1000 / 3600 * distance_factor),
                "e_road_load_const_sum_kwh_per_100km": float(np.sum(e_road_load[const_mask]) / 1000 / 3600 * distance_factor),
                "e_kin_const_sum_kwh_per_100km": float(np.sum(e_kin[const_mask]) / 1000 / 3600 * distance_factor),
                
                # 减速段单位能耗
                "e_aer_dec_sum_kwh_per_100km": float(np.sum(e_aer[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_roll_dec_sum_kwh_per_100km": float(np.sum(e_roll[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_drg_dec_sum_kwh_per_100km": float(np.sum(e_drg[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_road_load_dec_sum_kwh_per_100km": float(np.sum(e_road_load[dec_mask]) / 1000 / 3600 * distance_factor),
                "e_kin_dec_sum_kwh_per_100km": float(np.sum(e_kin[dec_mask]) / 1000 / 3600 * distance_factor),
            }
            
            # =============================================================
            # 创建 TimeSeries 输出
            # 单位说明：力（N）× 距离（m）= 能量（J），所以所有能耗单位都是焦耳
            # =============================================================
            e_aer_ts = TimeSeries(
                time=time,
                value=e_aer,
                name="e_aer",
                unit="J",
                desc="风阻能耗"
            )
            
            e_roll_ts = TimeSeries(
                time=time,
                value=e_roll,
                name="e_roll",
                unit="J",
                desc="滚阻能耗"
            )
            
            e_drg_ts = TimeSeries(
                time=time,
                value=e_drg,
                name="e_drg",
                unit="J",
                desc="拖滞能耗"
            )
            
            e_road_load_ts = TimeSeries(
                time=time,
                value=e_road_load,
                name="e_road_load",
                unit="J",
                desc="道路阻力能耗"
            )
            
            e_kin_ts = TimeSeries(
                time=time,
                value=e_kin,
                name="e_kin",
                unit="J",
                desc="动能变化"
            )
            
            e_wheel_ts = TimeSeries(
                time=time,
                value=e_wheel,
                name="e_wheel",
                unit="J",
                desc="轮端总能量"
            )
            
            e_wheel_div_ts = TimeSeries(
                time=time,
                value=e_wheel_div,
                name="e_wheel_div",
                unit="J",
                desc="驱动能量"
            )
            
            e_wheel_reg_ts = TimeSeries(
                time=time,
                value=e_wheel_reg,
                name="e_wheel_reg",
                unit="J",
                desc="回收能量"
            )
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            self.intermediate_output_values["e_aer"] = e_aer_ts
            self.intermediate_output_values["e_roll"] = e_roll_ts
            self.intermediate_output_values["e_drg"] = e_drg_ts
            self.intermediate_output_values["e_road_load"] = e_road_load_ts
            self.intermediate_output_values["e_kin"] = e_kin_ts
            self.intermediate_output_values["e_wheel"] = e_wheel_ts
            self.intermediate_output_values["e_wheel_div"] = e_wheel_div_ts
            self.intermediate_output_values["e_wheel_reg"] = e_wheel_reg_ts
            self.intermediate_output_values["wheel_energy_stats"] = wheel_energy_stats
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成轮端能量分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 轮端能量分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("wheel_energy_stats", {})
        ssts = self.ssts_values
        
        report = f"""### node_3_WheelEnergy（车轮能量）计算节点分析报告

#### 计算结果摘要

##### 阻力能耗（总循环）
- 风阻能耗：{stats.get('e_aer_sum_kwh_per_100km', 0):.4f} kWh/100km
- 滚阻能耗：{stats.get('e_roll_sum_kwh_per_100km', 0):.4f} kWh/100km
- 拖滞能耗：{stats.get('e_drg_sum_kwh_per_100km', 0):.4f} kWh/100km
- 道路阻力总能耗：{stats.get('e_road_load_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 轮端能量
- 轮端驱动能量总和：{stats.get('e_wheel_div_sum_kwh_per_100km', 0):.4f} kWh/100km
- 轮端最大可回收能量：{stats.get('e_wheel_reg_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 加速段能耗
- 风阻能耗：{stats.get('e_aer_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 滚阻能耗：{stats.get('e_roll_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 拖滞能耗：{stats.get('e_drg_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 道路阻力能耗：{stats.get('e_road_load_acc_sum_kwh_per_100km', 0):.4f} kWh/100km
- 加速段动能增加：{stats.get('e_kin_acc_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 恒速段能耗
- 风阻能耗：{stats.get('e_aer_const_sum_kwh_per_100km', 0):.4f} kWh/100km
- 滚阻能耗：{stats.get('e_roll_const_sum_kwh_per_100km', 0):.4f} kWh/100km
- 拖滞能耗：{stats.get('e_drg_const_sum_kwh_per_100km', 0):.4f} kWh/100km
- 道路阻力能耗：{stats.get('e_road_load_const_sum_kwh_per_100km', 0):.4f} kWh/100km

##### 减速段能耗
- 风阻能耗：{stats.get('e_aer_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 滚阻能耗：{stats.get('e_roll_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 拖滞能耗：{stats.get('e_drg_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 道路阻力能耗：{stats.get('e_road_load_dec_sum_kwh_per_100km', 0):.4f} kWh/100km
- 减速段动能减少：{stats.get('e_kin_dec_sum_kwh_per_100km', 0):.4f} kWh/100km

#### 计算逻辑说明

- 输入：行驶距离、各阻力分量（来自阻力计算节点），工况掩码（来自驾驶循环节点）
- 计算方法：
  * 各阻力能耗：E = F × s（力×距离逐点积分）
  * 动能变化：ΔE_kin = (mass + mass_rot) × a × s（动能定理）
  * 轮端总能量：E_wheel = E_road_load + E_kin
  * 驱动能量：E_wheel_div = max(E_wheel, 0)
  * 回收能量：E_wheel_reg = min(E_wheel, 0)
- 输出：各能耗分量时间序列，轮端驱动/回收能量，分工况统计参数

#### 修正方法

- 等效转动惯量 r_in：{ssts.get('r_in', 0):.1f} kg·m²，将旋转部件惯量转换为等效平移质量，影响动能计算精度

#### 可调参数清单（用于 DOE 分析）

- r_in: 等效转动惯量, 单位: kg·m², 当前值: {ssts.get('r_in', 0):.2f}
- rad: 车轮半径, 单位: m, 当前值: {ssts.get('rad', 0):.3f}

#### 参数计算关系

- 等效转动惯量: mass_rot = r_in / rad²（本节点计算使用）

#### 输出参数清单（用于 DOE 的 output_vars）

- e_aer: 风阻能耗时间序列, 单位: J
- e_roll: 滚阻能耗时间序列, 单位: J
- e_drg: 拖滞能耗时间序列, 单位: J
- e_road_load: 道路阻力能耗时间序列, 单位: J
- e_kin: 动能变化时间序列, 单位: J
- e_wheel: 轮端总能量时间序列, 单位: J
- e_wheel_div: 轮端驱动能量时间序列, 单位: J
- e_wheel_reg: 轮端回收能量时间序列, 单位: J"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report