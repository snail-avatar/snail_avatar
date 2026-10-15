# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_4C_EDUEnergyLtem_m20.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""低温-20℃电驱能量计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_4C_EDUEnergyLtem_m20.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class EDUEnergyLtemM20Node(CalculationNode):
    """低温-20℃电驱能量计算器节点类
    
    最小物理过程4C：低温-20℃电驱电功率计算
    职责：将低温-20℃轮端能量通过电驱系统效率转换为低温电驱端的能量需求
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行低温-20℃电驱能量计算
        
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
            # 从 node_1 获取循环总里程
            cycle_distance = self.intermediate_input_values.get("cycle_distance")
            
            # 从 node_3C 获取低温-20℃轮端能量
            e_wheel_div_m20_ts = self.intermediate_input_values.get("e_wheel_div_m20")
            e_wheel_reg_m20_ts = self.intermediate_input_values.get("e_wheel_reg_m20")
            
            # 从 SSTS 参数读取效率参数
            mot_div_eff = self.ssts_values.get("mot_div_eff")
            mot_reg_eff = self.ssts_values.get("mot_reg_eff")
            axle_eff = self.ssts_values.get("axle_eff")
            m_b_energy = self.ssts_values.get("m_b_energy")
            
            # =============================================================
            # 纯算法逻辑（参考 node_4_EDUEnergy.py）
            # =============================================================
            
            # 获取数据数组
            e_wheel_div_m20 = e_wheel_div_m20_ts.value
            e_wheel_reg_m20 = e_wheel_reg_m20_ts.value
            time = e_wheel_div_m20_ts.time
            
            # 计算低温-20℃电端驱动能量
            e_elc_div_m20 = e_wheel_div_m20 / mot_div_eff / axle_eff
            
            # 计算低温-20℃电端回收能量
            e_elc_reg_m20 = e_wheel_reg_m20 * (1 - m_b_energy) * mot_reg_eff * axle_eff
            
            # =============================================================
            # 计算统计特征参数
            # =============================================================
            
            # 计算单位能耗转换因子
            distance_factor = 100.0 / cycle_distance if cycle_distance > 0 else 0.0
            
            # 计算单位能耗（kWh/100km）
            e_elc_div_m20_sum_kwh_per_100km = np.sum(e_elc_div_m20) / 1000 / 3600 * distance_factor
            e_elc_reg_m20_sum_kwh_per_100km = np.sum(e_elc_reg_m20) / 1000 / 3600 * distance_factor
            
            # 计算系统综合效率
            system_div_eff = mot_div_eff * axle_eff
            system_reg_eff = (1 - m_b_energy) * mot_reg_eff * axle_eff
            
            edu_energy_stats_m20 = {
                "e_elc_div_m20_sum_kwh_per_100km": float(e_elc_div_m20_sum_kwh_per_100km),
                "e_elc_reg_m20_sum_kwh_per_100km": float(e_elc_reg_m20_sum_kwh_per_100km),
                "mot_div_eff": float(mot_div_eff),
                "mot_reg_eff": float(mot_reg_eff),
                "axle_eff": float(axle_eff),
                "system_div_eff": float(system_div_eff),
                "system_reg_eff": float(system_reg_eff),
                "m_b_energy": float(m_b_energy),
            }
            
            # =============================================================
            # 创建 TimeSeries 输出
            # =============================================================
            e_elc_div_m20_ts = TimeSeries(
                time=time,
                value=e_elc_div_m20,
                name="e_elc_div_m20",
                unit="J",
                desc="低温-20℃电驱驱动能量"
            )
            
            e_elc_reg_m20_ts = TimeSeries(
                time=time,
                value=e_elc_reg_m20,
                name="e_elc_reg_m20",
                unit="J",
                desc="低温-20℃电驱回收能量"
            )
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            self.intermediate_output_values["e_elc_div_m20"] = e_elc_div_m20_ts
            self.intermediate_output_values["e_elc_reg_m20"] = e_elc_reg_m20_ts
            self.intermediate_output_values["edu_energy_stats_m20"] = edu_energy_stats_m20
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成低温-20℃电驱能量分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 低温-20℃电驱能量分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("edu_energy_stats_m20", {})
        ssts = self.ssts_values
        
        report = f"""### node_4C_EDUEnergyLtem_m20（低温-20℃EDU能量）计算节点分析报告

#### 计算结果摘要

##### 系统效率
- 电机驱动效率：{stats.get('mot_div_eff', 0):.3f}
- 电机回收效率：{stats.get('mot_reg_eff', 0):.3f}
- 传动效率：{stats.get('axle_eff', 0):.3f}
- 机械制动能量比例：{stats.get('m_b_energy', 0):.4f}
- 驱动系统综合效率：{stats.get('system_div_eff', 0):.3f}
- 回收系统综合效率：{stats.get('system_reg_eff', 0):.3f}

##### 低温-20℃电驱能量
- 低温电驱驱动电耗：{stats.get('e_elc_div_m20_sum_kwh_per_100km', 0):.4f} kWh/100km
- 低温电驱回收电能：{stats.get('e_elc_reg_m20_sum_kwh_per_100km', 0):.4f} kWh/100km

#### 计算逻辑说明

- 输入：低温-20℃轮端驱动/回收能量（来自低温轮端能量节点），SSTS参数（电机效率、传动效率、机械制动比例）
- 计算方法：与标准工况相同的效率转换框架
  * 低温电驱驱动能量：E_elc_div_m20 = E_wheel_div_m20 / mot_div_eff / axle_eff
  * 低温电驱回收能量：E_elc_reg_m20 = E_wheel_reg_m20 × (1 - m_b_energy) × mot_reg_eff × axle_eff
- 输出：低温-20℃电驱驱动/回收能量时间序列，系统效率统计参数

#### 可调参数清单（用于 DOE 分析）

- mot_div_eff: 电机驱动效率, 单位: 无量纲, 当前值: {ssts.get('mot_div_eff', 0):.3f}
- mot_reg_eff: 电机回收效率, 单位: 无量纲, 当前值: {ssts.get('mot_reg_eff', 0):.3f}
- axle_eff: 传动效率, 单位: 无量纲, 当前值: {ssts.get('axle_eff', 0):.4f}
- m_b_energy: 机械制动能量比例, 单位: 无量纲, 当前值: {ssts.get('m_b_energy', 0):.4f}

#### 输出参数清单（用于 DOE 的 output_vars）

- e_elc_div_m20: 低温电驱驱动能量时间序列, 单位: J
- e_elc_reg_m20: 低温电驱回收能量时间序列, 单位: J"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report