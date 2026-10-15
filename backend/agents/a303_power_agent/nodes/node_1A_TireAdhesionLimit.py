# @Time    : 2026
# @Author  : 李涛
# @File    : node_1A_TireAdhesionLimit.py
# @Desc    : 附着力极限计算节点
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# 附着力极限计算节点
# 计算半载状态水平路面上车轮能够提供的最大驱动力和最大加速度（FWD/RWD/4WD模式）

from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode
from snail_avatar.backend.core.work_log import WorkLogger


class TireAdhesionLimit(CalculationNode):
    """附着力极限计算节点"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.g = 9.81  # 重力加速度，N/kg
        self.pi = 3.141593  # 圆周率
    
    def numerical_solve(self, memory_db=None):
        """
        数值求解：计算考虑轴荷转移后的最大加速度
        """
        # 从内存数据库获取输入参数
        mass_curb = self.ssts_values.get("mass_curb", 1927.0)  # 整备质量，kg
        mass_maxload = self.ssts_values.get("mass_maxload", 2299.0)  # 最大载质量，kg
        wheel_base = self.ssts_values.get("wheel_base", 2.85)  # 轴距，m
        mass_centroid_x = self.ssts_values.get("mass_centroid_x", 1.246)  # 质心 x 坐标，m
        mass_centroid_z = self.ssts_values.get("mass_centroid_z", 0.21)  # 质心 Z 坐标，m
        rad = self.ssts_values.get("rad", 0.359)  # 轮胎滚动半径，m
        r_in = self.ssts_values.get("r_in", 9.0)  # 转动惯量，kgm^2
        road_adh = self.ssts_values.get("road_adh", 0.9)  # 路面附着系数
        
        # ========== 步骤1：计算基本参数 ==========
        
        # 1. 半载质量（整备质量 + 最大载质量/2）
        mass_half_load = mass_curb + mass_maxload / 2.0
        
        # 2. 加速计算等效质量（含旋转部件等效质量）
        mass_half_load_equ = mass_half_load + r_in / (rad ** 2)
        
        # 3. 质心到后轮的距离
        b = wheel_base - mass_centroid_x
        
        # 4. 质心高度（质心 Z 坐标 + 轮胎滚动半径）
        h = mass_centroid_z + rad
        
        # 5. 静态后轴载荷（RWD 模式）
        g_half_r = mass_half_load * self.g * mass_centroid_x / wheel_base
        
        # 6. 静态后轮附着力
        f_half_r = g_half_r * road_adh
        
        # ========== 步骤2：计算轴荷转移系数 ==========
        
        # 载荷转移率 k = h / L
        k = h / wheel_base
        
        # 附着系数
        phi = road_adh
        
        # ========== 步骤3：计算各驱动模式最大加速度 ==========
        
        # 前驱（FWD）最大加速度
        # a_f_max = (g × b/L × φ) / (1 + k × φ)
        a_f_max = (self.g * b / wheel_base * phi) / (1.0 + k * phi)
        
        # 后驱（RWD）最大加速度
        # a_r_max = (g × a/L × φ) / (1 - k × φ)
        # 添加边界检查，防止分母接近零
        denominator_r = 1.0 - k * phi
        if denominator_r <= 0.01:  # 防止数值不稳定
            a_r_max = self.g * phi  # 退化为简单附着限制
        else:
            a_r_max = (self.g * mass_centroid_x / wheel_base * phi) / denominator_r
        
        # 四驱（4WD）最大加速度
        # a_4wd_max = g × φ
        a_4wd_max = self.g * phi
        
        # ========== 步骤4：计算RWD模式下的轴荷转移 ==========
        
        # 加速时前轴载荷
        # F_f = m × g × b/L - m × a_r_max × h/L
        F_f_acc = mass_half_load * self.g * b / wheel_base - mass_half_load * a_r_max * h / wheel_base
        
        # 加速时后轴载荷
        # F_r = m × g × a/L + m × a_r_max × h/L
        F_r_acc = mass_half_load * self.g * mass_centroid_x / wheel_base + mass_half_load * a_r_max * h / wheel_base
        
        # 轴荷转移量（从前往后转移）
        weight_transfer = F_r_acc - g_half_r
        
        # ========== 保存计算结果到中间变量 ==========
        
        # 保留原有输出参数
        self.intermediate_output_values["mass_half_load"] = mass_half_load
        self.intermediate_output_values["mass_half_load_equ"] = mass_half_load_equ
        self.intermediate_output_values["f_half_r"] = f_half_r
        self.intermediate_output_values["a_f_max"] = a_f_max
        self.intermediate_output_values["a_r_max"] = a_r_max
        self.intermediate_output_values["a_4wd_max"] = a_4wd_max
        self.intermediate_output_values["F_f_acc"] = F_f_acc
        self.intermediate_output_values["F_r_acc"] = F_r_acc
        self.intermediate_output_values["weight_transfer"] = weight_transfer
        
        return True
    
    def semantic_solve(self) -> str:
        """语义求解器：生成附着力极限计算的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 附着力极限计算的自然语言报告（中文格式）
        """
        # 获取计算结果
        a_f_max = self.intermediate_output_values.get("a_f_max", 0.0)
        a_r_max = self.intermediate_output_values.get("a_r_max", 0.0)
        a_4wd_max = self.intermediate_output_values.get("a_4wd_max", 0.0)
        weight_transfer = self.intermediate_output_values.get("weight_transfer", 0.0)
        mass_half_load = self.intermediate_output_values.get("mass_half_load", 0.0)
        f_half_r = self.intermediate_output_values.get("f_half_r", 0.0)
        F_f_acc = self.intermediate_output_values.get("F_f_acc", 0.0)
        F_r_acc = self.intermediate_output_values.get("F_r_acc", 0.0)

        report = f"""### node_1A_TireAdhesionLimit（轮胎附着力极限）计算节点分析报告

#### 计算结果摘要

##### 基本参数
- 半载质量：{mass_half_load:.1f} kg
- 后轮静态附着力：{f_half_r:.1f} N

##### 各驱动模式最大加速度
- 前驱（FWD）：{a_f_max:.2f} m/s²（{a_f_max/9.81:.2f}g）
- 后驱（RWD）：{a_r_max:.2f} m/s²（{a_r_max/9.81:.2f}g）
- 四驱（4WD）：{a_4wd_max:.2f} m/s²（{a_4wd_max/9.81:.2f}g）

##### 后驱模式轴荷转移
- 加速时前轴载荷：{F_f_acc:.1f} N
- 加速时后轴载荷：{F_r_acc:.1f} N
- 轴荷转移量：{weight_transfer:.1f} N

#### 计算逻辑说明

- 输入：整备质量、最大载质量、轴距、质心坐标、轮胎滚动半径、转动惯量、路面附着系数（均来自SSTS参数）
- 计算方法：
  * 半载质量 = 整备质量 + 最大载质量/2
  * 加速等效质量 = 半载质量 + 转动惯量/轮胎半径²（考虑旋转部件）
  * 载荷转移率 k = h/L（h为质心高度，L为轴距）
  * FWD最大加速度：a_f_max = (g × b/L × φ) / (1 + k × φ)
  * RWD最大加速度：a_r_max = (g × a/L × φ) / (1 - k × φ)，分母接近零时退化为 g×φ
  * 4WD最大加速度：a_4wd_max = g × φ（无轴荷转移影响）
  * 加速时轴荷：考虑惯性力引起的载荷转移，F_r = mg×a/L + ma×h/L
- 输出：各驱动模式最大加速度、加速时轴荷、轴荷转移量

#### 参数计算关系

- 半载质量: mass_half_load = mass_curb + mass_maxload / 2 = {self.ssts_values.get('mass_curb', 0):.1f} + {self.ssts_values.get('mass_maxload', 0):.1f} / 2 = {mass_half_load:.1f} kg
- 加速等效质量: mass_half_load_equ = mass_half_load + r_in / rad² = {mass_half_load:.1f} + {self.ssts_values.get('r_in', 0):.1f} / ({self.ssts_values.get('rad', 0):.3f})² = {self.intermediate_output_values.get('mass_half_load_equ', 0):.1f} kg
- 载荷转移率: k = h / L = ({self.ssts_values.get('mass_centroid_z', 0):.3f} + {self.ssts_values.get('rad', 0):.3f}) / {self.ssts_values.get('wheel_base', 0):.2f} = {(self.ssts_values.get('mass_centroid_z', 0) + self.ssts_values.get('rad', 0)) / self.ssts_values.get('wheel_base', 0):.3f}

#### 可调参数清单（用于 DOE 分析）

- mass_curb: 整备质量, 单位: kg, 当前值: {self.ssts_values.get('mass_curb', 0):.1f}
- mass_maxload: 最大载质量, 单位: kg, 当前值: {self.ssts_values.get('mass_maxload', 0):.1f}
- wheel_base: 轴距, 单位: m, 当前值: {self.ssts_values.get('wheel_base', 0):.2f}
- mass_centroid_x: 质心 x 坐标, 单位: m, 当前值: {self.ssts_values.get('mass_centroid_x', 0):.3f}
- mass_centroid_z: 质心 Z 坐标, 单位: m, 当前值: {self.ssts_values.get('mass_centroid_z', 0):.3f}
- rad: 轮胎滚动半径, 单位: m, 当前值: {self.ssts_values.get('rad', 0):.3f}
- r_in: 转动惯量, 单位: kg·m², 当前值: {self.ssts_values.get('r_in', 0):.1f}
- road_adh: 路面附着系数, 单位: 无量纲, 当前值: {self.ssts_values.get('road_adh', 0):.2f}

#### 输出参数清单（用于 DOE 的 output_vars）

- mass_half_load: 半载质量, 单位: kg
- mass_half_load_equ: 加速等效质量, 单位: kg
- f_half_r: 后轮静态附着力, 单位: N
- a_f_max: FWD最大加速度, 单位: m/s²
- a_r_max: RWD最大加速度, 单位: m/s²
- a_4wd_max: 4WD最大加速度, 单位: m/s²
- F_f_acc: 加速时前轴载荷, 单位: N
- F_r_acc: 加速时后轴载荷, 单位: N
- weight_transfer: 轴荷转移量, 单位: N"""

        self.intermediate_output_values["semantic_summary"] = report

        return report