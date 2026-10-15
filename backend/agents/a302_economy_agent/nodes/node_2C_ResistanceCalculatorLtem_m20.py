# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_2C_ResistanceCalculatorLtem_m20.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""低温-20℃行驶阻力计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_2C_ResistanceCalculatorLtem_m20.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class ResistanceCalculatorLtemM20Node(CalculationNode):
    """低温-20℃行驶阻力计算器节点类
    
    最小物理过程2C：低温-20℃行驶阻力计算
    职责：计算低温-20℃环境下的滚阻、风阻、拖滞阻力，应用低温修正因子
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行低温-20℃行驶阻力计算
        
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
            vel = self.intermediate_input_values.get("vel")
            vel_ave = self.intermediate_input_values.get("vel_ave")
            a = self.intermediate_input_values.get("a")
            
            # 从 SSTS 参数读取 - 标准工况参数
            mass_curb = self.ssts_values.get("mass_curb")
            mass_maxload = self.ssts_values.get("mass_maxload")
            rr_part = self.ssts_values.get("rr_part")
            rr_gain = self.ssts_values.get("rr_gain")
            cd_wt = self.ssts_values.get("cd_wt")
            cd_gain = self.ssts_values.get("cd_gain")
            aero = self.ssts_values.get("aero")
            f_brake_res = self.ssts_values.get("f_brake_res")
            r_brake_res = self.ssts_values.get("r_brake_res")
            f_bearing_res = self.ssts_values.get("f_bearing_res")
            r_bearing_res = self.ssts_values.get("r_bearing_res")
            rad = self.ssts_values.get("rad")
            r_in = self.ssts_values.get("r_in")
            
            # 计算拖滞扭矩：四轮拖滞力矩之和
            drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) * 2
            
            # 从 SSTS 参数读取 - 低温-20℃修正因子
            dst_m20 = self.ssts_values.get("dst_m20")
            rr_gain_m20 = self.ssts_values.get("rr_gain_m20")
            res_gain_m20 = self.ssts_values.get("res_gain_m20")
            
            # =============================================================
            # 计算经济性测试质量（半载）
            # =============================================================
            mass = mass_curb + 100 + (mass_maxload - 100) * 0.15
            
            # =============================================================
            # 纯算法逻辑（参考 ev_eco_Ltem_calculator.py）
            # =============================================================
            
            # 计算低温-20℃滚阻系数（‰ 转无量纲）
            rr_m20 = rr_part * rr_gain * rr_gain_m20 / 1000
            
            # 计算低温-20℃滚动阻力（恒定值）
            f_roll_m20 = mass * 9.8 * rr_m20
            
            # 计算实际风阻系数（与标准工况相同）
            cd = cd_wt * cd_gain
            
            # 获取速度数组
            vel_value = vel.value
            
            # 计算低温-20℃空气阻力（使用低温空气密度）
            f_aer_m20 = 0.5 * dst_m20 * cd * aero * (
                ((vel_value[1:] + vel_value[:-1]) * (vel_value[1:]**2 + vel_value[:-1]**2)) / 4
            ) ** (2/3)
            
            # 计算低温-20℃拖滞阻力（应用低温增益）
            drg_tor_m20 = drg_tor * res_gain_m20
            f_drg_m20 = drg_tor_m20 / rad
            
            # 计算低温-20℃总行驶阻力（随速度变化的时间序列）
            f_road_load_m20 = f_aer_m20 + f_roll_m20 + f_drg_m20

            # 计算低温-20℃惯性力（随速度变化的时间序列）
            # 考虑整车等效转动惯量：等效质量 = 平移质量 + 转动惯量等效质量
            mass_rot = r_in / (rad * rad)  # 转动惯量等效质量
            f_inert_m20 = (mass + mass_rot) * a.value
            
            # =============================================================
            # 创建 TimeSeries 输出
            # =============================================================
            # 使用 vel_ave 的时间轴（N-1 长度）
            time = vel_ave.time
            
            f_aer_m20_ts = TimeSeries(
                time=time,
                value=f_aer_m20,
                name="f_aer_m20",
                unit="N",
                desc="低温-20℃空气阻力"
            )
            
            f_road_load_m20_ts = TimeSeries(
                time=time,
                value=f_road_load_m20,
                name="f_road_load_m20",
                unit="N",
                desc="低温-20℃道路阻力"
            )
            
            f_inert_m20_ts = TimeSeries(
                time=time,
                value=f_inert_m20,
                name="f_inert_m20",
                unit="N",
                desc="低温-20℃惯性力"
            )
            
            # =============================================================
            # 计算阻力统计特征参数
            # =============================================================
            drag_force_stats_m20 = {
                "f_roll_m20_N": float(f_roll_m20),
                "f_drg_m20_N": float(f_drg_m20),
                "f_aer_m20_mean_N": float(np.mean(f_aer_m20)),
                "f_aer_m20_max_N": float(np.max(f_aer_m20)),
                "f_aer_m20_min_N": float(np.min(f_aer_m20)),
                "f_road_load_m20_mean_N": float(np.mean(f_road_load_m20)),
                "f_road_load_m20_max_N": float(np.max(f_road_load_m20)),
                "cd_actual": float(cd),
                "rr_m20_actual": float(rr_m20 * 1000),
                "mass_kg": float(mass),
                "roll_m20_ratio_pct": float(f_roll_m20 / np.mean(f_road_load_m20) * 100),
                "aer_m20_ratio_pct": float(np.mean(f_aer_m20) / np.mean(f_road_load_m20) * 100),
                "drg_m20_ratio_pct": float(f_drg_m20 / np.mean(f_road_load_m20) * 100),
                "dst_m20_kg_per_m3": float(dst_m20),
                "rr_gain_m20": float(rr_gain_m20),
                "res_gain_m20": float(res_gain_m20),
            }
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            
            # 基础参数输出
            self.intermediate_output_values["mass"] = mass
            
            # 阻力值输出（恒定值）
            self.intermediate_output_values["f_roll_m20"] = f_roll_m20
            self.intermediate_output_values["f_drg_m20"] = f_drg_m20
            
            # 时间序列输出（TimeSeries 对象）
            self.intermediate_output_values["f_aer_m20"] = f_aer_m20_ts
            self.intermediate_output_values["f_road_load_m20"] = f_road_load_m20_ts
            self.intermediate_output_values["f_inert_m20"] = f_inert_m20_ts
            
            # 统计特征输出
            self.intermediate_output_values["drag_force_stats_m20"] = drag_force_stats_m20
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成低温-20℃阻力分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 低温-20℃阻力分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("drag_force_stats_m20", {})
        mass = self.intermediate_output_values.get("mass", 0)
        ssts = self.ssts_values
        
        report = f"""### node_2C_ResistanceCalculatorLtem_m20（低温-20℃阻力计算）计算节点分析报告

#### 计算结果摘要

##### 低温-20℃修正因子
- 低温空气密度：{stats.get('dst_m20_kg_per_m3', 0):.3f} kg/m³
- 低温滚阻增益：{stats.get('rr_gain_m20', 0):.2f}
- 低温拖滞力矩增益：{stats.get('res_gain_m20', 0):.2f}

##### 测试质量
- 测试质量（半载）：{mass:.2f} kg

##### 低温-20℃阻力系数
- 实际风阻系数：{stats.get('cd_actual', 0):.4f}
- 低温滚阻系数：{stats.get('rr_m20_actual', 0):.2f} ‰

##### 低温-20℃恒定阻力
- 低温滚动阻力：{stats.get('f_roll_m20_N', 0):.2f} N
- 低温拖滞阻力：{stats.get('f_drg_m20_N', 0):.2f} N

##### 低温-20℃空气阻力（随速度变化）
- 平均低温空气阻力：{stats.get('f_aer_m20_mean_N', 0):.2f} N
- 最大低温空气阻力：{stats.get('f_aer_m20_max_N', 0):.2f} N
- 最小低温空气阻力：{stats.get('f_aer_m20_min_N', 0):.2f} N

##### 低温-20℃总行驶阻力
- 平均低温道路阻力：{stats.get('f_road_load_m20_mean_N', 0):.2f} N
- 最大低温道路阻力：{stats.get('f_road_load_m20_max_N', 0):.2f} N

##### 低温-20℃阻力占比
- 低温滚阻占比：{stats.get('roll_m20_ratio_pct', 0):.1f}%
- 低温风阻占比：{stats.get('aer_m20_ratio_pct', 0):.1f}%
- 低温拖滞占比：{stats.get('drg_m20_ratio_pct', 0):.1f}%

#### 计算逻辑说明

- 输入：速度、加速度时间序列（来自驾驶循环节点），SSTS参数（质量、阻力系数、低温修正因子）
- 计算方法：
  * 与标准工况相同的基础计算框架
  * 低温滚阻系数：rr_m20 = rr_part × rr_gain × rr_gain_m20 / 1000
  * 低温空气阻力：使用低温空气密度 dst_m20
  * 低温拖滞阻力：drg_tor_m20 = drg_tor × res_gain_m20
- 输出：低温-20℃各阻力分量及时间序列，阻力统计特征参数

#### 可调参数清单（用于 DOE 分析）

- mass_curb: 整备质量, 单位: kg, 当前值: {ssts.get('mass_curb', 0):.2f}
- mass_maxload: 最大载荷质量, 单位: kg, 当前值: {ssts.get('mass_maxload', 0):.2f}
- r_in: 等效转动惯量, 单位: kg·m², 当前值: {ssts.get('r_in', 0):.2f}
- dst_m20: 低温空气密度, 单位: kg/m³, 当前值: {ssts.get('dst_m20', 0):.4f}
- rr_gain_m20: 低温滚阻增益, 单位: 无量纲, 当前值: {ssts.get('rr_gain_m20', 0):.3f}
- res_gain_m20: 低温拖滞增益, 单位: 无量纲, 当前值: {ssts.get('res_gain_m20', 0):.3f}

#### 输出参数清单（用于 DOE 的 output_vars）

- cd: 实际风阻系数, 单位: 无量纲
- rr_m20: 低温滚阻系数, 单位: ‰
- mass: 测试质量, 单位: kg"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report