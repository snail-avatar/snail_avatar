# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_1B_GradeAdhesionLimit.py
# @Desc    : 坡道附着力极限计算节点
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""坡道附着力极限计算节点

计算满载状态坡道上，轮胎最大附着系数能够支撑的最大爬坡角（FWD/RWD/4WD模式）

物理模型：
    坡道上车辆受力平衡（含阻力）：
    - 附着力提供的驱动力 - 阻力 = 重力沿坡面分量
    - 前轴法向力：N_f = m × g × (b×cosθ - h×sinθ) / L
    - 后轴法向力：N_r = m × g × (a×cosθ + h×sinθ) / L

    阻力简化：
    - 忽略风阻（最大爬坡工况车速极低）
    - 滚阻用平路值替代（偏保守）

    各驱动模式含阻力的最大爬坡角（辅助角公式求解 A·cosα + B·sinα = C）：
    - FWD: A = μ·m·g·b/L,  B = -m·g·(μ·h/L + 1),  C = drag_f + tire_f
    - RWD: A = μ·m·g·a/L,  B = m·g·(μ·h/L - 1),    C = drag_f + tire_f
    - 4WD: A = μ·m·g,      B = -m·g,                 C = drag_f + tire_f

    纯附着力极限（无阻力）：
    - FWD: θ_max = arctan(μ × b/L / (1 + μ × h/L))
    - RWD: θ_max = arctan(μ × a/L / (1 - μ × h/L))  （当1-μ×h/L>0）
           θ_max = arctan(b/h)                         （当1-μ×h/L≤0，前轮离地限制）
    - 4WD: θ_max = arctan(μ)
"""

import math
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class GradeAdhesionLimit(CalculationNode):
    """坡道附着力极限计算节点

    计算满载状态坡道上，轮胎最大附着系数能够支撑的最大爬坡角
    同时输出含阻力（拖滞+滚阻）和纯附着力两种结果
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.g = 9.81

    def solve_grade_with_resistance(self, A, B, C):
        """辅助角公式求解 A·cosα + B·sinα = C

        物理含义：附着力等效驱动力在角度α方向的投影恰好等于阻力时，
        车辆达到附着力约束下的最大爬坡角。

        Args:
            A: cosα系数，代表平路载荷分量贡献的附着力
            B: sinα系数，代表坡道载荷转移与重力坡面分量的净效果
            C: 常数项，拖滞阻力与滚动阻力之和

        Returns:
            alpha: 最大爬坡角，rad；无解时返回0
        """
        R = math.sqrt(A**2 + B**2)
        if R > 0 and abs(C / R) <= 1:
            delta = math.atan2(B, A)
            alpha = delta + math.acos(C / R)
            if alpha > 0:
                return alpha
        return 0.0

    def numerical_solve(self, memory_db=None):
        """
        数值求解：计算各驱动模式在坡道上的附着力限制最大爬坡角
        """
        # 从内存数据库获取输入参数
        mass_curb = self.ssts_values.get("mass_curb", 1927.0)
        mass_maxload = self.ssts_values.get("mass_maxload", 2299.0)
        wheel_base = self.ssts_values.get("wheel_base", 2.85)
        mass_centroid_x = self.ssts_values.get("mass_centroid_x", 1.246)
        mass_centroid_z = self.ssts_values.get("mass_centroid_z", 0.21)
        rad = self.ssts_values.get("rad", 0.359)
        road_adh = self.ssts_values.get("road_adh", 0.9)
        f_brake_res = self.ssts_values.get("f_brake_res", 1.5)
        r_brake_res = self.ssts_values.get("r_brake_res", 1.5)
        f_bearing_res = self.ssts_values.get("f_bearing_res", 0.8)
        r_bearing_res = self.ssts_values.get("r_bearing_res", 0.8)
        rr_part = self.ssts_values.get("rr_part", 6.5)
        rr_gain = self.ssts_values.get("rr_gain", 1.2)

        # ========== 步骤1：计算基本参数 ==========

        # 满载质量（爬坡最恶劣工况）
        mass_full_load = mass_curb + mass_maxload

        # 质心到前轴距离
        a = mass_centroid_x

        # 质心到后轴距离
        b = wheel_base - mass_centroid_x

        # 质心高度（质心Z坐标 + 轮胎滚动半径）
        h = mass_centroid_z + rad

        # 附着系数
        phi = road_adh

        # 载荷转移率 k = h / L
        k = h / wheel_base

        # 阻力计算（忽略风阻，滚阻用平路值偏保守）
        drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) * 2
        drag_f = drg_tor / rad
        tire_f = mass_full_load * self.g * rr_part / 1000 * rr_gain
        C_resist = drag_f + tire_f

        # ========== 步骤2：含阻力的附着力极限（辅助角公式） ==========

        # FWD: A·cosα + B·sinα = C
        A_fwd = phi * mass_full_load * self.g * b / wheel_base
        B_fwd = -mass_full_load * self.g * (phi * h / wheel_base + 1)
        theta_max_fwd = self.solve_grade_with_resistance(A_fwd, B_fwd, C_resist)

        # RWD: A·cosα + B·sinα = C
        A_rwd = phi * mass_full_load * self.g * a / wheel_base
        B_rwd = mass_full_load * self.g * (phi * h / wheel_base - 1)
        denominator_rwd = 1.0 - k * phi
        if denominator_rwd > 0.01:
            theta_max_rwd = self.solve_grade_with_resistance(A_rwd, B_rwd, C_resist)
        else:
            # 前轮离地时退化为4WD形式
            A_4wd_equiv = phi * mass_full_load * self.g
            B_4wd_equiv = -mass_full_load * self.g
            theta_max_rwd = self.solve_grade_with_resistance(A_4wd_equiv, B_4wd_equiv, C_resist)

        # 4WD: A·cosα + B·sinα = C
        A_4wd = phi * mass_full_load * self.g
        B_4wd = -mass_full_load * self.g
        theta_max_4wd = self.solve_grade_with_resistance(A_4wd, B_4wd, C_resist)

        # ========== 步骤3：纯附着力极限（无阻力，arctan直接公式） ==========

        # FWD纯附着力极限
        tan_theta_fwd_pure = phi * b / wheel_base / (1.0 + k * phi)
        theta_max_fwd_pure = math.atan(tan_theta_fwd_pure)

        # RWD纯附着力极限
        if denominator_rwd > 0.01:
            tan_theta_rwd_pure = phi * a / wheel_base / denominator_rwd
            theta_max_rwd_pure = math.atan(tan_theta_rwd_pure)
        else:
            theta_max_rwd_pure = math.atan(b / h)

        # 4WD纯附着力极限
        theta_max_4wd_pure = math.atan(phi)

        # ========== 步骤4：计算爬坡度 ==========

        # 含阻力的爬坡度
        grade_max_fwd = math.tan(theta_max_fwd) * 100.0
        grade_max_rwd = math.tan(theta_max_rwd) * 100.0
        grade_max_4wd = math.tan(theta_max_4wd) * 100.0

        # 纯附着力极限爬坡度
        grade_max_fwd_pure = math.tan(theta_max_fwd_pure) * 100.0
        grade_max_rwd_pure = math.tan(theta_max_rwd_pure) * 100.0
        grade_max_4wd_pure = math.tan(theta_max_4wd_pure) * 100.0

        # ========== 步骤5：计算各驱动模式最大爬坡角时的轴荷（含阻力结果） ==========

        # FWD最大爬坡角时轴荷
        N_f_at_max_fwd = (mass_full_load * self.g
                          * (b * math.cos(theta_max_fwd) - h * math.sin(theta_max_fwd))
                          / wheel_base)
        N_r_at_max_fwd = (mass_full_load * self.g
                          * (a * math.cos(theta_max_fwd) + h * math.sin(theta_max_fwd))
                          / wheel_base)

        # RWD最大爬坡角时轴荷
        N_f_at_max_rwd = (mass_full_load * self.g
                          * (b * math.cos(theta_max_rwd) - h * math.sin(theta_max_rwd))
                          / wheel_base)
        N_r_at_max_rwd = (mass_full_load * self.g
                          * (a * math.cos(theta_max_rwd) + h * math.sin(theta_max_rwd))
                          / wheel_base)

        # 4WD最大爬坡角时轴荷
        N_f_at_max_4wd = (mass_full_load * self.g
                          * (b * math.cos(theta_max_4wd) - h * math.sin(theta_max_4wd))
                          / wheel_base)
        N_r_at_max_4wd = (mass_full_load * self.g
                          * (a * math.cos(theta_max_4wd) + h * math.sin(theta_max_4wd))
                          / wheel_base)

        # ========== 步骤6：角度转换为度 ==========

        theta_max_fwd_deg = math.degrees(theta_max_fwd)
        theta_max_rwd_deg = math.degrees(theta_max_rwd)
        theta_max_4wd_deg = math.degrees(theta_max_4wd)

        # ========== 保存计算结果到中间变量 ==========

        self.intermediate_output_values["mass_full_load"] = mass_full_load
        self.intermediate_output_values["theta_max_fwd"] = theta_max_fwd_deg
        self.intermediate_output_values["grade_max_fwd"] = grade_max_fwd
        self.intermediate_output_values["theta_max_rwd"] = theta_max_rwd_deg
        self.intermediate_output_values["grade_max_rwd"] = grade_max_rwd
        self.intermediate_output_values["theta_max_4wd"] = theta_max_4wd_deg
        self.intermediate_output_values["grade_max_4wd"] = grade_max_4wd
        self.intermediate_output_values["grade_max_fwd_pure"] = grade_max_fwd_pure
        self.intermediate_output_values["grade_max_rwd_pure"] = grade_max_rwd_pure
        self.intermediate_output_values["grade_max_4wd_pure"] = grade_max_4wd_pure
        self.intermediate_output_values["N_f_at_max_fwd"] = N_f_at_max_fwd
        self.intermediate_output_values["N_r_at_max_fwd"] = N_r_at_max_fwd
        self.intermediate_output_values["N_f_at_max_rwd"] = N_f_at_max_rwd
        self.intermediate_output_values["N_r_at_max_rwd"] = N_r_at_max_rwd
        self.intermediate_output_values["N_f_at_max_4wd"] = N_f_at_max_4wd
        self.intermediate_output_values["N_r_at_max_4wd"] = N_r_at_max_4wd
        self.intermediate_output_values["drag_f"] = drag_f
        self.intermediate_output_values["tire_f"] = tire_f

        return True

    def semantic_solve(self) -> str:
        """语义求解器：生成坡道附着力极限计算的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 坡道附着力极限计算的自然语言报告（中文格式）
        """
        mass_full_load = self.intermediate_output_values.get("mass_full_load", 0.0)
        theta_max_fwd = self.intermediate_output_values.get("theta_max_fwd", 0.0)
        grade_max_fwd = self.intermediate_output_values.get("grade_max_fwd", 0.0)
        theta_max_rwd = self.intermediate_output_values.get("theta_max_rwd", 0.0)
        grade_max_rwd = self.intermediate_output_values.get("grade_max_rwd", 0.0)
        theta_max_4wd = self.intermediate_output_values.get("theta_max_4wd", 0.0)
        grade_max_4wd = self.intermediate_output_values.get("grade_max_4wd", 0.0)
        grade_max_fwd_pure = self.intermediate_output_values.get("grade_max_fwd_pure", 0.0)
        grade_max_rwd_pure = self.intermediate_output_values.get("grade_max_rwd_pure", 0.0)
        grade_max_4wd_pure = self.intermediate_output_values.get("grade_max_4wd_pure", 0.0)
        N_f_at_max_fwd = self.intermediate_output_values.get("N_f_at_max_fwd", 0.0)
        N_r_at_max_fwd = self.intermediate_output_values.get("N_r_at_max_fwd", 0.0)
        N_f_at_max_rwd = self.intermediate_output_values.get("N_f_at_max_rwd", 0.0)
        N_r_at_max_rwd = self.intermediate_output_values.get("N_r_at_max_rwd", 0.0)
        N_f_at_max_4wd = self.intermediate_output_values.get("N_f_at_max_4wd", 0.0)
        N_r_at_max_4wd = self.intermediate_output_values.get("N_r_at_max_4wd", 0.0)
        drag_f = self.intermediate_output_values.get("drag_f", 0.0)
        tire_f = self.intermediate_output_values.get("tire_f", 0.0)

        report = f"""### node_1B_GradeAdhesionLimit（坡道附着力极限）计算节点分析报告

#### 计算结果摘要

##### 基本参数
- 满载质量：{mass_full_load:.1f} kg
- 拖滞阻力：{drag_f:.1f} N
- 滚动阻力（平路）：{tire_f:.1f} N

##### 含阻力的附着力极限爬坡度
- 前驱（FWD）：{theta_max_fwd:.2f}°（爬坡度 {grade_max_fwd:.1f}%）
- 后驱（RWD）：{theta_max_rwd:.2f}°（爬坡度 {grade_max_rwd:.1f}%）
- 四驱（4WD）：{theta_max_4wd:.2f}°（爬坡度 {grade_max_4wd:.1f}%）

##### 纯附着力极限爬坡度（无阻力）
- 前驱（FWD）：{grade_max_fwd_pure:.1f}%
- 后驱（RWD）：{grade_max_rwd_pure:.1f}%
- 四驱（4WD）：{grade_max_4wd_pure:.1f}%

##### 前驱最大爬坡角时轴荷
- 前轴法向力：{N_f_at_max_fwd:.1f} N
- 后轴法向力：{N_r_at_max_fwd:.1f} N

##### 后驱最大爬坡角时轴荷
- 前轴法向力：{N_f_at_max_rwd:.1f} N
- 后轴法向力：{N_r_at_max_rwd:.1f} N

##### 四驱最大爬坡角时轴荷
- 前轴法向力：{N_f_at_max_4wd:.1f} N
- 后轴法向力：{N_r_at_max_4wd:.1f} N

#### 计算逻辑说明

- 输入：整备质量、最大载质量、轴距、质心坐标、轮胎滚动半径、路面附着系数、拖滞力矩、滚阻参数（均来自SSTS参数）
- 计算方法：
  * 满载质量 = 整备质量 + 最大载质量（爬坡最恶劣工况）
  * 阻力计算：拖滞阻力 = 拖滞力矩/轮胎半径；滚阻 = mg × rr_part/1000 × rr_gain
  * 含阻力的附着力极限（辅助角公式 A·cosα + B·sinα = C）：
    - FWD: A = φ·mg·b/L, B = -mg·(φ·h/L + 1), C = 拖滞阻力 + 滚阻
    - RWD: A = φ·mg·a/L, B = mg·(φ·h/L - 1), C = 拖滞阻力 + 滚阻
    - 4WD: A = φ·mg, B = -mg, C = 拖滞阻力 + 滚阻
  * 纯附着力极限（无阻力，arctan公式）：
    - FWD: θ_max = arctan(φ × b/L / (1 + φ × h/L))
    - RWD: θ_max = arctan(φ × a/L / (1 - φ × h/L))，分母≤0时退化为 arctan(b/h)
    - 4WD: θ_max = arctan(φ)
  * 爬坡角时轴荷：N_f = mg×(b×cosθ - h×sinθ)/L，N_r = mg×(a×cosθ + h×sinθ)/L
- 输出：各驱动模式含阻力和纯附着力极限爬坡度、爬坡角时轴荷

#### 参数计算关系

- 满载质量: mass_full_load = mass_curb + mass_maxload = {self.ssts_values.get('mass_curb', 0):.1f} + {self.ssts_values.get('mass_maxload', 0):.1f} = {mass_full_load:.1f} kg
- 拖滞阻力: drag_f = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) × 2 / rad = ({self.ssts_values.get('f_brake_res', 0):.1f} + {self.ssts_values.get('r_brake_res', 0):.1f} + {self.ssts_values.get('f_bearing_res', 0):.1f} + {self.ssts_values.get('r_bearing_res', 0):.1f}) × 2 / {self.ssts_values.get('rad', 0):.3f} = {drag_f:.1f} N
- 滚动阻力: tire_f = mass_full_load × g × rr_part / 1000 × rr_gain = {mass_full_load:.1f} × 9.81 × {self.ssts_values.get('rr_part', 0):.1f} / 1000 × {self.ssts_values.get('rr_gain', 0):.2f} = {tire_f:.1f} N

#### 可调参数清单（用于 DOE 分析）

- mass_curb: 整备质量, 单位: kg, 当前值: {self.ssts_values.get('mass_curb', 0):.1f}
- mass_maxload: 最大载质量, 单位: kg, 当前值: {self.ssts_values.get('mass_maxload', 0):.1f}
- wheel_base: 轴距, 单位: m, 当前值: {self.ssts_values.get('wheel_base', 0):.2f}
- mass_centroid_x: 质心 x 坐标, 单位: m, 当前值: {self.ssts_values.get('mass_centroid_x', 0):.3f}
- mass_centroid_z: 质心 Z 坐标, 单位: m, 当前值: {self.ssts_values.get('mass_centroid_z', 0):.3f}
- rad: 轮胎滚动半径, 单位: m, 当前值: {self.ssts_values.get('rad', 0):.3f}
- road_adh: 路面附着系数, 单位: 无量纲, 当前值: {self.ssts_values.get('road_adh', 0):.2f}
- f_brake_res: 前轮制动拖滞, 单位: N, 当前值: {self.ssts_values.get('f_brake_res', 0):.1f}
- r_brake_res: 后轮制动拖滞, 单位: N, 当前值: {self.ssts_values.get('r_brake_res', 0):.1f}
- f_bearing_res: 前轮轴承拖滞, 单位: N, 当前值: {self.ssts_values.get('f_bearing_res', 0):.1f}
- r_bearing_res: 后轮轴承拖滞, 单位: N, 当前值: {self.ssts_values.get('r_bearing_res', 0):.1f}
- rr_part: 滚阻系数, 单位: ‰, 当前值: {self.ssts_values.get('rr_part', 0):.1f}
- rr_gain: 滚阻增益, 单位: 无量纲, 当前值: {self.ssts_values.get('rr_gain', 0):.2f}

#### 输出参数清单（用于 DOE 的 output_vars）

- mass_full_load: 满载质量, 单位: kg
- theta_max_fwd: FWD含阻力最大爬坡角, 单位: °
- grade_max_fwd: FWD含阻力爬坡度, 单位: %
- theta_max_rwd: RWD含阻力最大爬坡角, 单位: °
- grade_max_rwd: RWD含阻力爬坡度, 单位: %
- theta_max_4wd: 4WD含阻力最大爬坡角, 单位: °
- grade_max_4wd: 4WD含阻力爬坡度, 单位: %
- grade_max_fwd_pure: FWD纯附着力爬坡度, 单位: %
- grade_max_rwd_pure: RWD纯附着力爬坡度, 单位: %
- grade_max_4wd_pure: 4WD纯附着力爬坡度, 单位: %
- drag_f: 拖滞阻力, 单位: N
- tire_f: 滚动阻力, 单位: N"""

        self.intermediate_output_values["semantic_summary"] = report

        return report
