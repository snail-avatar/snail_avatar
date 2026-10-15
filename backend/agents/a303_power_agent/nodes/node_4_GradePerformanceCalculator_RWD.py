# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_4_GradePerformanceCalculator_RWD.py
# @Desc    : 爬坡性能计算节点（RWD后驱模式）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""爬坡性能计算节点（RWD后驱模式）

计算后驱配置下的坡道起步能力、最大爬坡度和指定坡度最高车速

物理模型：
    坡道起步能力：取附着力约束和电机扭矩约束的较小值
        - 附着力约束：直接读取node_1B含阻力的附着力极限爬坡度
        - 电机扭矩约束：arcsin解析求解
    最大爬坡度 = 坡道起步能力 + 工程修正系数
    坡道最高车速：取功率限制车速和驱动力限制车速的较小值
        - 功率限制：基于300s持续功率，使用立方根公式求解
        - 驱动力限制：逐速度迭代，找到驱动力等于阻力的平衡点
"""

import math
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class GradePerformanceCalculator_RWD(CalculationNode):
    """爬坡性能计算节点（RWD后驱模式）

    计算后驱配置下的坡道起步能力、最大爬坡度和指定坡度最高车速
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.g = 9.81
        self.pi = 3.141593

    def calculate_motor_torque_rwd(self, edu_spd, params):
        """计算后驱模式下电驱扭矩外特性

        Args:
            edu_spd: 当前电驱转速，rpm
            params: 包含电驱参数的字典

        Returns:
            edu_spd_tor_r: 后电驱扭矩，Nm
        """
        edu_tmax_r = params.get('edu_tmax_r', 2923.5)
        edu_pmax_r = params.get('edu_pmax_r', 151.2)
        edu_spd_max_r = params.get('edu_spd_max_r', 1358.0)
        edu_pow_gain_r = params.get('edu_pow_gain_r', 0.9)

        if edu_tmax_r > 0:
            edu_spd_base_r = 9550 * edu_pmax_r / edu_tmax_r
        else:
            edu_spd_base_r = 0

        if edu_spd <= edu_spd_base_r:
            edu_spd_tor_r = edu_tmax_r
        else:
            edu_spd_tor_r = 9550 * edu_pmax_r / edu_spd * (
                1 - (edu_spd - edu_spd_base_r) /
                (edu_spd_max_r - edu_spd_base_r) *
                (1 - edu_pow_gain_r)
            )

        return edu_spd_tor_r

    def calculate_cubic_root(self, x):
        """计算实数立方根（支持负数）"""
        if x >= 0:
            return x ** (1/3)
        else:
            return -((-x) ** (1/3))

    def calculate_grade_max_speed(self, params, mass_full_load, edu_spd_max,
                                  edp_300s_pmax, axle_eff, rad, drg_tor,
                                  s1, s2, alpha_1, alpha_2, v_max_1km):
        """坡道最高车速计算

        对两个指定坡度分别计算功率限制车速和驱动力限制车速，
        取较小值作为该坡度的最高车速。

        Args:
            params: 包含阻力参数的字典
            mass_full_load: 满载质量，kg
            edu_spd_max: 电驱最高转速，rpm
            edp_300s_pmax: 三电系统轮端300s持续功率，kW
            axle_eff: 半轴效率
            rad: 轮胎滚动半径，m
            drg_tor: 拖滞力矩，Nm
            s1: 爬坡坡度1，%
            s2: 爬坡坡度2，%
            alpha_1: 坡度1对应的角度，rad
            alpha_2: 坡度2对应的角度，rad
            v_max_1km: 1km最高车速，km/h（来自node_3）

        Returns:
            grade_speed_results: 两个坡度的最高车速计算结果字典
        """
        # 阻力二次系数
        C = (0.5 * params.get('dst', 1.225)
             * params.get('cd_wt', 0.28)
             * params.get('cd_gain', 1.15)
             * params.get('aero', 2.45))

        # 基础阻力常数
        drag_f = drg_tor / rad
        tire_f = (mass_full_load * self.g
                  * params.get('rr_part', 6.5) / 1000
                  * params.get('rr_gain', 1.2))
        B_0 = drag_f + tire_f

        # 最高速度上限（取node_3计算的1km最高车速）
        v_max_limit = v_max_1km / 3.6

        grade_speed_results = {}

        for slope_num, (s, alpha) in enumerate([(s1, alpha_1), (s2, alpha_2)], 1):
            # 该坡度的阻力常数（基础阻力 + 坡道重力分量）
            B = B_0 + mass_full_load * self.g * math.sin(alpha)

            # 功率限制最高车速（使用300s持续功率）
            P = edp_300s_pmax
            if C > 0:
                term1 = 500 * P / C
                term2 = ((500 * P / C) ** 2 + (B / (3 * C)) ** 3) ** 0.5
                cube_root1 = self.calculate_cubic_root(term1 + term2)
                cube_root2 = self.calculate_cubic_root(term1 - term2)
                v_max_slop_P = cube_root1 + cube_root2
            else:
                v_max_slop_P = 0

            # 驱动力限制最高车速（逐速度迭代）
            v_max_slop_F = 0
            for v_test in range(1, int(v_max_limit * 3.6) + 1):
                v_mps = v_test / 3.6

                # 当前速度对应的电驱转速
                edu_spd = (v_mps * 60) / (2 * self.pi * rad)
                edu_spd = min(edu_spd, edu_spd_max)

                # 电驱外特性
                edu_tor = self.calculate_motor_torque_rwd(edu_spd, params) * axle_eff

                # 轮端驱动力
                Slop_F = edu_tor / rad

                # 坡道总阻力
                Fd = B + C * v_mps ** 2

                if Fd >= Slop_F:
                    v_max_slop_F = (v_test - 1) / 3.6
                    break
                else:
                    v_max_slop_F = v_mps

            # 综合最高车速
            v_max_slop = 3.6 * min(v_max_slop_P, v_max_slop_F)

            grade_speed_results[f'slope_{slope_num}'] = {
                's': s,
                'v_max_slop_P': v_max_slop_P * 3.6,
                'v_max_slop_F': v_max_slop_F * 3.6,
                'v_max_slop': v_max_slop
            }

        return grade_speed_results

    def numerical_solve(self, memory_db=None):
        """数值求解：计算后驱配置下的坡道起步能力、最大爬坡度和坡道最高车速"""
        # =============================================================
        # 从上游节点读取中间变量
        # =============================================================
        mass_full_load = self.intermediate_input_values.get('mass_full_load')
        grade_max_rwd = self.intermediate_input_values.get('grade_max_rwd')
        N_r_at_max_rwd = self.intermediate_input_values.get('N_r_at_max_rwd')
        edu_tmax_r = self.intermediate_input_values.get('edu_tmax_r')
        edu_pmax_r = self.intermediate_input_values.get('edu_pmax_r')
        edu_spd_max_r = self.intermediate_input_values.get('edu_spd_max_r')
        edu_pow_gain_r = self.intermediate_input_values.get('edu_pow_gain_r')
        edu_spd_max = self.intermediate_input_values.get('edu_spd_max')
        edp_300s_pmax = self.intermediate_input_values.get('edp_300s_pmax')
        axle_eff = self.intermediate_input_values.get('axle_eff')
        v_max_1km = self.intermediate_input_values.get('v_max_1km')

        # =============================================================
        # 从 SSTS/VTS 参数读取
        # =============================================================
        params = self.ssts_values
        wheel_base = params.get('wheel_base', 2.85)
        mass_centroid_x = params.get('mass_centroid_x', 1.246)
        mass_centroid_z = params.get('mass_centroid_z', 0.21)
        rad = params.get('rad', 0.359)
        road_adh = params.get('road_adh', 0.9)
        f_brake_res = params.get('f_brake_res', 1.5)
        r_brake_res = params.get('r_brake_res', 1.5)
        f_bearing_res = params.get('f_bearing_res', 0.8)
        r_bearing_res = params.get('r_bearing_res', 0.8)
        grade_s1 = params.get('grade_s1', 4.0)
        grade_s2 = params.get('grade_s2', 12.0)
        slop_start_delta = params.get('slop_start_delta', -2.0)
        slop_max_delta = params.get('slop_max_delta', 5.0)
        v_max_s1_delta = params.get('v_max_s1_delta', -2.0)
        v_max_s2_delta = params.get('v_max_s2_delta', -2.0)

        # =============================================================
        # 步骤1：计算基本参数
        # =============================================================
        a = mass_centroid_x
        h = mass_centroid_z + rad
        alpha_1 = math.atan(grade_s1 / 100)
        alpha_2 = math.atan(grade_s2 / 100)

        # 拖滞力矩
        drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) * 2

        # 拖滞阻力
        drag_f = drg_tor / rad

        # 滚动阻力
        tire_f = (mass_full_load * self.g
                  * params.get('rr_part', 6.5) / 1000
                  * params.get('rr_gain', 1.2))

        # 构建电驱参数字典（供扭矩外特性计算使用）
        edu_params = {
            'edu_tmax_r': edu_tmax_r,
            'edu_pmax_r': edu_pmax_r,
            'edu_spd_max_r': edu_spd_max_r,
            'edu_pow_gain_r': edu_pow_gain_r,
        }

        # =============================================================
        # 步骤2：坡道起步能力计算（解析法）
        # =============================================================

        # 电机扭矩约束：arcsin直接求解
        # 电机轮端最大驱动力 - 阻力 = 重力坡面分量的临界条件
        D = edu_tmax_r * axle_eff / rad - drag_f - tire_f
        if D > 0:
            sin_alpha_motor = min(D / (mass_full_load * self.g), 1.0)
            grade_motor = math.tan(math.asin(sin_alpha_motor)) * 100.0
        else:
            grade_motor = 0.0

        # 附着力约束：直接读取node_1B含阻力的附着力极限爬坡度
        grade_adhesion = grade_max_rwd if grade_max_rwd is not None else 0.0

        # 取两者较小值
        grade_start = min(grade_motor, grade_adhesion)

        # =============================================================
        # 步骤3：最大爬坡度计算
        # =============================================================
        grade_start_corrected = grade_start + slop_start_delta
        grade_max_corrected = grade_start_corrected + slop_max_delta

        # =============================================================
        # 步骤4：坡道最高车速计算
        # =============================================================
        grade_speed_results = self.calculate_grade_max_speed(
            params, mass_full_load, edu_spd_max,
            edp_300s_pmax, axle_eff, rad, drg_tor,
            grade_s1, grade_s2, alpha_1, alpha_2, v_max_1km
        )

        # 提取s1坡道结果
        s1_result = grade_speed_results['slope_1']
        v_max_s1_power = s1_result['v_max_slop_P']
        v_max_s1_force = s1_result['v_max_slop_F']
        v_max_s1 = s1_result['v_max_slop']
        v_max_s1_corrected = v_max_s1 + v_max_s1_delta

        # 提取s2坡道结果
        s2_result = grade_speed_results['slope_2']
        v_max_s2_power = s2_result['v_max_slop_P']
        v_max_s2_force = s2_result['v_max_slop_F']
        v_max_s2 = s2_result['v_max_slop']
        v_max_s2_corrected = v_max_s2 + v_max_s2_delta

        # =============================================================
        # 保存计算结果到中间变量
        # =============================================================
        self.intermediate_output_values["grade_motor"] = grade_motor
        self.intermediate_output_values["grade_adhesion"] = grade_adhesion
        self.intermediate_output_values["grade_start"] = grade_start
        self.intermediate_output_values["grade_start_corrected"] = grade_start_corrected
        self.intermediate_output_values["grade_max_corrected"] = grade_max_corrected
        self.intermediate_output_values["v_max_s1_power"] = v_max_s1_power
        self.intermediate_output_values["v_max_s1_force"] = v_max_s1_force
        self.intermediate_output_values["v_max_s1"] = v_max_s1
        self.intermediate_output_values["v_max_s1_corrected"] = v_max_s1_corrected
        self.intermediate_output_values["v_max_s2_power"] = v_max_s2_power
        self.intermediate_output_values["v_max_s2_force"] = v_max_s2_force
        self.intermediate_output_values["v_max_s2"] = v_max_s2
        self.intermediate_output_values["v_max_s2_corrected"] = v_max_s2_corrected

        # 核心爬坡性能指标（输出到 VTS）
        self._sync_ssts_vts_output(memory_db, "grade_start", float(grade_start_corrected))
        self._sync_ssts_vts_output(memory_db, "grade_max", float(grade_max_corrected))
        self._sync_ssts_vts_output(memory_db, "v_max_s1", float(v_max_s1_corrected))
        self._sync_ssts_vts_output(memory_db, "v_max_s2", float(v_max_s2_corrected))

        return True

    def semantic_solve(self) -> str:
        """语义求解器：生成爬坡性能计算的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 爬坡性能计算的自然语言报告（中文格式）
        """
        grade_motor = self.intermediate_output_values.get("grade_motor", 0.0)
        grade_adhesion = self.intermediate_output_values.get("grade_adhesion", 0.0)
        grade_start = self.intermediate_output_values.get("grade_start", 0.0)
        grade_start_corrected = self.intermediate_output_values.get("grade_start_corrected", 0.0)
        grade_max_corrected = self.intermediate_output_values.get("grade_max_corrected", 0.0)
        v_max_s1 = self.intermediate_output_values.get("v_max_s1", 0.0)
        v_max_s1_corrected = self.intermediate_output_values.get("v_max_s1_corrected", 0.0)
        v_max_s2 = self.intermediate_output_values.get("v_max_s2", 0.0)
        v_max_s2_corrected = self.intermediate_output_values.get("v_max_s2_corrected", 0.0)

        # 从SSTS参数获取坡度值用于显示
        grade_s1 = self.ssts_values.get('grade_s1', 4.0)
        grade_s2 = self.ssts_values.get('grade_s2', 12.0)

        report = f"""### node_4_GradePerformanceCalculator_RWD（爬坡性能计算）计算节点分析报告

### 计算结果摘要

##### 坡道起步能力
- 电机扭矩约束最大爬坡度：{grade_motor:.1f}%
- 附着力约束最大爬坡度：{grade_adhesion:.1f}%
- 坡道起步能力（计算值）：{grade_start:.1f}%
- 坡道起步能力（修正后）：{grade_start_corrected:.1f}%

##### 最大爬坡度
- 最大爬坡度（修正后）：{grade_max_corrected:.1f}%

##### 坡道最高车速
- {grade_s1:.0f}%坡道最高车速：{v_max_s1:.1f} km/h（修正后 {v_max_s1_corrected:.1f} km/h）
- {grade_s2:.0f}%坡道最高车速：{v_max_s2:.1f} km/h（修正后 {v_max_s2_corrected:.1f} km/h）

#### 计算逻辑说明

- 输入：满载质量、后驱附着力极限爬坡度（来自node_1B），电驱参数、三电系统300s持续功率、半轴效率（来自node_2），1km最高车速（来自node_3），坡度参数（来自SSTS参数）
- 坡道起步能力计算：
  * 电机扭矩约束：grade_motor = tan(arcsin(D/mg)) × 100，其中 D = 电驱轮端最大驱动力 - 阻力
  * 附着力约束：grade_adhesion = node_1B计算的含阻力后驱爬坡度
  * 坡道起步能力（计算值）= min(电机扭矩约束, 附着力约束)
- 最大爬坡度计算：最大爬坡度 = 坡道起步能力 + slop_start_delta + slop_max_delta
- 坡道最高车速计算：
  * 功率限制车速（立方根公式）：基于300s持续功率求解 P = Fv = (B + Cv²)v
  * 驱动力限制车速：逐速度迭代，找到驱动力等于阻力的平衡点
  * 综合最高车速 = min(功率限制车速, 驱动力限制车速)
- 输出：坡道起步能力、最大爬坡度、两个指定坡度的最高车速

#### 修正方法

- slop_start_delta：{self.ssts_values.get('slop_start_delta', 0):.2f} %，坡道起步能力修正值
- slop_max_delta：{self.ssts_values.get('slop_max_delta', 0):.2f} %，最大爬坡度修正值
- v_max_s1_delta：{self.ssts_values.get('v_max_s1_delta', 0):.2f} km/h，坡度1最高车速修正值
- v_max_s2_delta：{self.ssts_values.get('v_max_s2_delta', 0):.2f} km/h，坡度2最高车速修正值
- 修正后值 = 原始计算值 + 修正值

#### 参数计算关系

- 拖滞力矩: drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) × 2 = ({self.ssts_values.get('f_brake_res', 0):.1f} + {self.ssts_values.get('r_brake_res', 0):.1f} + {self.ssts_values.get('f_bearing_res', 0):.1f} + {self.ssts_values.get('r_bearing_res', 0):.1f}) × 2 = {(self.ssts_values.get('f_brake_res', 0) + self.ssts_values.get('r_brake_res', 0) + self.ssts_values.get('f_bearing_res', 0) + self.ssts_values.get('r_bearing_res', 0)) * 2:.1f} N·m
- 拖滞阻力: drag_f = drg_tor / rad = {(self.ssts_values.get('f_brake_res', 0) + self.ssts_values.get('r_brake_res', 0) + self.ssts_values.get('f_bearing_res', 0) + self.ssts_values.get('r_bearing_res', 0)) * 2:.1f} / {self.ssts_values.get('rad', 0):.3f} = {(self.ssts_values.get('f_brake_res', 0) + self.ssts_values.get('r_brake_res', 0) + self.ssts_values.get('f_bearing_res', 0) + self.ssts_values.get('r_bearing_res', 0)) * 2 / self.ssts_values.get('rad', 0):.1f} N
- 电机驱动力余量: D = edu_tmax_r × axle_eff / rad - drag_f - tire_f
- 电机扭矩约束爬坡度: grade_motor = tan(arcsin(D/mg)) × 100
- 坡道起步能力: grade_start = min(grade_motor, grade_adhesion)
- 修正后坡道起步能力: grade_start_corrected = grade_start + slop_start_delta
- 修正后最大爬坡度: grade_max_corrected = grade_start_corrected + slop_max_delta
- 修正后坡道最高车速: v_max_s1_corrected = v_max_s1 + v_max_s1_delta, v_max_s2_corrected = v_max_s2 + v_max_s2_delta

#### 可调参数清单（用于 DOE 分析）

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
- dst: 空气密度, 单位: kg/m³, 当前值: {self.ssts_values.get('dst', 0):.3f}
- cd_wt: 风阻系数, 单位: 无量纲, 当前值: {self.ssts_values.get('cd_wt', 0):.3f}
- cd_gain: 风阻增益, 单位: 无量纲, 当前值: {self.ssts_values.get('cd_gain', 0):.2f}
- aero: 迎风面积, 单位: m², 当前值: {self.ssts_values.get('aero', 0):.2f}
- grade_s1: 爬坡坡度1, 单位: %, 当前值: {self.ssts_values.get('grade_s1', 0):.1f}
- grade_s2: 爬坡坡度2, 单位: %, 当前值: {self.ssts_values.get('grade_s2', 0):.1f}
- slop_start_delta: 坡道起步能力修正值, 单位: %, 当前值: {self.ssts_values.get('slop_start_delta', 0):.2f}
- slop_max_delta: 最大爬坡度修正值, 单位: %, 当前值: {self.ssts_values.get('slop_max_delta', 0):.2f}
- v_max_s1_delta: 坡度1最高车速修正值, 单位: km/h, 当前值: {self.ssts_values.get('v_max_s1_delta', 0):.2f}
- v_max_s2_delta: 坡度2最高车速修正值, 单位: km/h, 当前值: {self.ssts_values.get('v_max_s2_delta', 0):.2f}

#### 输出参数清单（用于 DOE 的 output_vars）

- grade_motor: 电机扭矩约束最大爬坡度, 单位: %
- grade_adhesion: 附着力约束最大爬坡度, 单位: %
- grade_start: 坡道起步能力(计算值), 单位: %
- grade_start_corrected: 坡道起步能力(修正后), 单位: %
- grade_max_corrected: 最大爬坡度(修正后), 单位: %
- v_max_s1_power: 坡度1功率限制车速, 单位: km/h
- v_max_s1_force: 坡度1驱动力限制车速, 单位: km/h
- v_max_s1: 坡度1最高车速(计算值), 单位: km/h
- v_max_s1_corrected: 坡度1最高车速(修正后), 单位: km/h
- v_max_s2_power: 坡度2功率限制车速, 单位: km/h
- v_max_s2_force: 坡度2驱动力限制车速, 单位: km/h
- v_max_s2: 坡度2最高车速(计算值), 单位: km/h
- v_max_s2_corrected: 坡度2最高车速(修正后), 单位: km/h"""

        self.intermediate_output_values["semantic_summary"] = report

        return report
