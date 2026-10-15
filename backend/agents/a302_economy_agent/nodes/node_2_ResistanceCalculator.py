# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_2_ResistanceCalculator.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""行驶阻力计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_2_ResistanceCalculator.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class ResistanceCalculatorNode(CalculationNode):
    """行驶阻力计算器节点类
    
    最小物理过程2：行驶阻力计算
    职责：计算滚阻、风阻、拖滞阻力（稳态阻力，不含惯性力）
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行行驶阻力计算
        
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
            
            # 从 SSTS 参数读取
            mass_curb = self.ssts_values.get("mass_curb")
            mass_maxload = self.ssts_values.get("mass_maxload")
            rr_part = self.ssts_values.get("rr_part")
            rr_gain = self.ssts_values.get("rr_gain")
            cd_wt = self.ssts_values.get("cd_wt")
            cd_gain = self.ssts_values.get("cd_gain")
            aero = self.ssts_values.get("aero")
            dst = self.ssts_values.get("dst")
            f_brake_res = self.ssts_values.get("f_brake_res")
            r_brake_res = self.ssts_values.get("r_brake_res")
            f_bearing_res = self.ssts_values.get("f_bearing_res")
            r_bearing_res = self.ssts_values.get("r_bearing_res")
            rad = self.ssts_values.get("rad")
            r_in = self.ssts_values.get("r_in")
            
            # 计算拖滞扭矩：四轮拖滞力矩之和
            drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) * 2
            
            # =============================================================
            # 计算经济性测试质量（半载）
            # =============================================================
            mass = mass_curb + 100 + (mass_maxload - 100) * 0.15
            
            # =============================================================
            # 纯算法逻辑（参考 ev_eco_calculator.py）
            # =============================================================
            
            # 计算实际滚阻系数（‰ 转无量纲）
            rr = rr_part * rr_gain / 1000
            
            # 计算滚动阻力（恒定值）
            f_roll = mass * 9.8 * rr
            
            # 计算实际风阻系数
            cd = cd_wt * cd_gain
            
            # 获取速度数组
            vel_value = vel.value
            
            # 计算空气阻力（随速度变化的时间序列）
            f_aer = 0.5 * dst * cd * aero * (
                ((vel_value[1:] + vel_value[:-1]) * (vel_value[1:]**2 + vel_value[:-1]**2)) / 4
            ) ** (2/3)
            
            # 计算拖滞阻力（恒定值）
            f_drg = drg_tor / rad
            
            # 计算总行驶阻力（随速度变化的时间序列）
            f_road_load = f_aer + f_roll + f_drg

            # 计算惯性力（随速度变化的时间序列）
            # 考虑整车等效转动惯量：等效质量 = 平移质量 + 转动惯量等效质量
            mass_rot = r_in / (rad * rad)  # 转动惯量等效质量
            f_inert = (mass + mass_rot) * a.value
            
            # =============================================================
            # 创建 TimeSeries 输出
            # =============================================================
            # 使用 vel_ave 的时间轴（N-1 长度）
            time = vel_ave.time
            
            f_aer_ts = TimeSeries(
                time=time,
                value=f_aer,
                name="f_aer",
                unit="N",
                desc="空气阻力"
            )
            
            f_road_load_ts = TimeSeries(
                time=time,
                value=f_road_load,
                name="f_road_load",
                unit="N",
                desc="道路阻力"
            )
            
            f_inert_ts = TimeSeries(
                time=time,
                value=f_inert,
                name="f_inert",
                unit="N",
                desc="惯性力"
            )
            
            # =============================================================
            # 计算阻力统计特征参数
            # =============================================================
            drag_force_stats = {
                "f_roll_N": float(f_roll),
                "f_drg_N": float(f_drg),
                "f_aer_mean_N": float(np.mean(f_aer)),
                "f_aer_max_N": float(np.max(f_aer)),
                "f_aer_min_N": float(np.min(f_aer)),
                "f_road_load_mean_N": float(np.mean(f_road_load)),
                "f_road_load_max_N": float(np.max(f_road_load)),
                "cd_actual": float(cd),
                "rr_actual": float(rr * 1000),
                "mass_kg": float(mass),
                "roll_ratio_pct": float(f_roll / np.mean(f_road_load) * 100),
                "aer_ratio_pct": float(np.mean(f_aer) / np.mean(f_road_load) * 100),
                "drg_ratio_pct": float(f_drg / np.mean(f_road_load) * 100),
            }
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            
            # 基础参数输出
            self.intermediate_output_values["mass"] = mass
            self.intermediate_output_values["cd"] = cd
            self.intermediate_output_values["rr"] = rr * 1000  # 转回‰
            
            # 阻力值输出（恒定值）
            self.intermediate_output_values["f_roll"] = f_roll
            self.intermediate_output_values["f_drg"] = f_drg
            
            # 时间序列输出（TimeSeries 对象）
            self.intermediate_output_values["f_aer"] = f_aer_ts
            self.intermediate_output_values["f_road_load"] = f_road_load_ts
            self.intermediate_output_values["f_inert"] = f_inert_ts
            
            # 统计特征输出
            self.intermediate_output_values["drag_force_stats"] = drag_force_stats
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成阻力分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 阻力分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("drag_force_stats", {})
        mass = self.intermediate_output_values.get("mass", 0)
        cd = self.intermediate_output_values.get("cd", 0)
        
        # 获取所有SSTS参数值用于显示
        ssts = self.ssts_values
        
        report = f"""### node_2_ResistanceCalculator（阻力计算）计算节点分析报告

#### 计算结果摘要

##### 测试质量
- 整备质量：{ssts.get('mass_curb', 0):.2f} kg
- 最大载荷：{ssts.get('mass_maxload', 0):.2f} kg
- 测试质量（半载）：{mass:.2f} kg

##### 阻力系数
- 实际风阻系数：{cd:.4f}
- 实际滚阻系数：{stats.get('rr_actual', 0):.2f} ‰

##### 恒定阻力
- 滚动阻力：{stats.get('f_roll_N', 0):.2f} N
- 拖滞阻力：{stats.get('f_drg_N', 0):.2f} N

##### 空气阻力（随速度变化）
- 平均空气阻力：{stats.get('f_aer_mean_N', 0):.2f} N
- 最大空气阻力：{stats.get('f_aer_max_N', 0):.2f} N
- 最小空气阻力：{stats.get('f_aer_min_N', 0):.2f} N

##### 总行驶阻力
- 平均道路阻力：{stats.get('f_road_load_mean_N', 0):.2f} N
- 最大道路阻力：{stats.get('f_road_load_max_N', 0):.2f} N

#### 阻力占比
- 滚阻占比：{stats.get('roll_ratio_pct', 0):.1f}%
- 风阻占比：{stats.get('aer_ratio_pct', 0):.1f}%
- 拖滞占比：{stats.get('drg_ratio_pct', 0):.1f}%

#### 计算逻辑说明

- 输入：速度、加速度时间序列（来自驾驶循环节点），SSTS参数（质量、阻力系数、转动惯量等）
- 计算方法：
  * 测试质量：整备质量 + 100kg驾驶员 + 15%最大载荷
  * 滚动阻力：f_roll = mass × g × rr（rr = rr_part × rr_gain / 1000）
  * 空气阻力：f_aer = 0.5 × ρ × cd × A × v^2（使用区间速度的复合平均）
  * 拖滞阻力：f_drg = 总拖滞扭矩 / 车轮半径
  * 惯性力：f_inert = (mass + mass_rot) × a（考虑等效转动惯量）
  * 道路阻力：f_road_load = f_aer + f_roll + f_drg
- 输出：各阻力分量及时间序列，惯性力，阻力统计特征参数

#### 修正方法

- 滚阻修正系数 rr_gain：{ssts.get('rr_gain', 0):.3f}，调整理论滚阻系数与实测的偏差
- 风阻修正系数 cd_gain：{ssts.get('cd_gain', 0):.3f}，调整理论风阻系数与实测的偏差
- 等效转动惯量 r_in：{ssts.get('r_in', 0):.1f} kg·m²，考虑传动系统旋转部件的惯量影响

#### 可调参数清单（用于 DOE 分析）

- mass_curb: 整备质量, 单位: kg, 当前值: {ssts.get('mass_curb', 0):.2f}
- mass_maxload: 最大载荷质量, 单位: kg, 当前值: {ssts.get('mass_maxload', 0):.2f}
- r_in: 等效转动惯量, 单位: kg·m², 当前值: {ssts.get('r_in', 0):.2f}
- rad: 车轮半径, 单位: m, 当前值: {ssts.get('rad', 0):.3f}
- rr_part: 轮胎台架滚阻系数, 单位: ‰, 当前值: {ssts.get('rr_part', 0):.2f}
- rr_gain: 滚动阻力增益, 单位: 无量纲, 当前值: {ssts.get('rr_gain', 0):.3f}
- cd_wt: 风阻系数基准值, 单位: 无量纲, 当前值: {ssts.get('cd_wt', 0):.4f}
- cd_gain: 风阻系数增益, 单位: 无量纲, 当前值: {ssts.get('cd_gain', 0):.3f}
- aero: 迎风面积, 单位: m², 当前值: {ssts.get('aero', 0):.2f}
- dst: 空气密度, 单位: kg/m³, 当前值: {ssts.get('dst', 0):.3f}
- f_brake_res: 前轮制动卡钳拖滞力矩, 单位: Nm, 当前值: {ssts.get('f_brake_res', 0):.2f}
- r_brake_res: 后轮制动卡钳拖滞力矩, 单位: Nm, 当前值: {ssts.get('r_brake_res', 0):.2f}
- f_bearing_res: 前轮轴承拖滞力矩, 单位: Nm, 当前值: {ssts.get('f_bearing_res', 0):.2f}
- r_bearing_res: 后轮轴承拖滞力矩, 单位: Nm, 当前值: {ssts.get('r_bearing_res', 0):.2f}

#### 参数计算关系

- 实际风阻系数: cd = cd_wt × cd_gain = {ssts.get('cd_wt', 0):.4f} × {ssts.get('cd_gain', 0):.3f} = {cd:.4f}
- 实际滚阻系数: rr = rr_part × rr_gain = {ssts.get('rr_part', 0):.2f} × {ssts.get('rr_gain', 0):.3f} = {stats.get('rr_actual', 0):.2f} ‰
- 测试质量: mass = mass_curb + 100 + (mass_maxload - 100) × 0.15 = {ssts.get('mass_curb', 0):.2f} + 100 + ({ssts.get('mass_maxload', 0):.2f} - 100) × 0.15 = {mass:.2f} kg

#### 输出参数清单（用于 DOE 的 output_vars）

- cd: 实际风阻系数, 单位: 无量纲
- rr: 实际滚阻系数, 单位: ‰
- mass: 测试质量, 单位: kg
- f_roll: 滚动阻力, 单位: N
- f_drg: 拖滞阻力, 单位: N
- f_aer: 空气阻力时间序列, 单位: N
- f_road_load: 道路阻力时间序列, 单位: N
- f_inert: 惯性力时间序列, 单位: N"""
        
        # 将语义摘要写入输出，供下游节点使用
        self.intermediate_output_values["semantic_summary"] = report
        
        return report
