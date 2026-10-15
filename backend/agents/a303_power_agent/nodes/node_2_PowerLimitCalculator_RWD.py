# @Time    : 2026
# @Author  : 李涛
# @File    : node_2_PowerLimitCalculator_RWD.py
# @Desc    : 轮端功率限制计算节点（RWD 后驱模式）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# 轮端功率限制计算节点（RWD 后驱模式）
# 计算折合到轮端（半轴输出端）的三电系统综合硬件最大功率限制

from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class PowerLimitCalculator_RWD(CalculationNode):
    """轮端功率限制计算节点（RWD 后驱模式）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def numerical_solve(self, memory_db=None):
        """
        数值求解：计算三电系统折算到轮端的最大允许功率
        """
        # 从内存数据库获取输入参数
        # 后电驱参数
        edu_spd_max_r = self.ssts_values.get("edu_spd_max_r", 1358.0)  # 后电驱最高转速，rpm
        axle_eff = self.ssts_values.get("axle_eff", 0.99)  # 半轴效率（RWD模式使用后轴效率）
        edu_tmax_r = self.ssts_values.get("edu_tmax_r", 2923.5)  # 后电驱最大扭矩，Nm
        edu_pmax_r = self.ssts_values.get("edu_pmax_r", 151.2)  # 后电驱峰值功率，kW
        edu_30m_pmax_r = self.ssts_values.get("edu_30m_pmax_r", 83.0)  # 后电驱持续功率，kW
        edu_pow_gain_r = self.ssts_values.get("edu_pow_gain_r", 0.9)  # 后电驱功率衰减系数
        
        # 电池参数
        bat_pmax = self.ssts_values.get("bat_pmax", 163.0)  # 电池峰值功率，kW
        bat_30m_pmax = self.ssts_values.get("bat_30m_pmax", 129.0)  # 电池持续功率，kW
        bat_300s_pmax = self.ssts_values.get("bat_300s_pmax", 140.0)  # 电池300s持续功率，kW
        mot_pow_eff = self.ssts_values.get("mot_pow_eff", 0.881)  # 电驱驱动平均效率
        power_lp = self.ssts_values.get("power_lp", 0.0)  # 动力性校核低压功率，W
        
        # ========== 计算功率折算相关变量 ==========
        
        # 1. 电驱综合最高转速（RWD 模式只使用后电驱）
        edu_spd_max = edu_spd_max_r
        
        # 2. 电池轮端功率计算（扣除低压功率并考虑传动效率）
        bat_max = (bat_pmax - power_lp / 1000.0) * mot_pow_eff * axle_eff
        bat_30m_max = (bat_30m_pmax - power_lp / 1000.0) * mot_pow_eff * axle_eff
        bat_300s_max = (bat_300s_pmax - power_lp / 1000.0) * mot_pow_eff * axle_eff
        
        # 3. 三电系统轮端持续功率@30min（RWD 模式只考虑后电驱）
        pow_30m_max = min(bat_30m_max, edu_30m_pmax_r)
        
        # 4. 三电系统轮端持续功率@300s（RWD 模式只考虑后电驱）
       #pow_300s_max = min(bat_300s_max, edu_30m_pmax_r)
        pow_300s_max = bat_300s_max
        
        # 5. 三电系统轮端峰值功率（取电池和电驱的较小值）
        edp_pmax = min(bat_max, edu_pmax_r)
        
        # ========== 保存计算结果到中间变量 ==========
        # 改名原则：撞名的 intermediate output 加后缀区分
        # - _wheel: 轮端等效值（与 SSTS input 原始电池功率区分）
        # - _final: 综合值（与 SSTS input 原始参数区分）
        # - _raw: 原始值透传（与 SSTS input 同名但语义上是透传副本）
        
        # 综合值（不撞名，但统一加后缀清晰化）
        self.intermediate_output_values["edu_spd_max_final"] = edu_spd_max
        self.intermediate_output_values["axle_eff_final"] = axle_eff  # 撞名！input 有 axle_eff (ssts_vts)
        
        # 电池轮端功率（撞名！input 有同名 ssts_vts）
        self.intermediate_output_values["bat_pmax_wheel"] = bat_max
        self.intermediate_output_values["bat_30m_pmax_wheel"] = bat_30m_max
        self.intermediate_output_values["bat_300s_pmax_wheel"] = bat_300s_max
        
        # 三电系统综合轮端功率（不撞名，加 _wheel 后缀统一风格）
        self.intermediate_output_values["edp_30m_pmax_wheel"] = pow_30m_max
        self.intermediate_output_values["edp_300s_pmax_wheel"] = pow_300s_max
        self.intermediate_output_values["edp_pmax_wheel"] = edp_pmax
        
        # 电驱原始参数透传（全部撞名！input 有同名 ssts_vts）
        self.intermediate_output_values["edu_tmax_r_raw"] = edu_tmax_r
        self.intermediate_output_values["edu_pmax_r_raw"] = edu_pmax_r
        self.intermediate_output_values["edu_30m_pmax_r_raw"] = edu_30m_pmax_r
        self.intermediate_output_values["edu_spd_max_r_raw"] = edu_spd_max_r
        self.intermediate_output_values["edu_pow_gain_r_raw"] = edu_pow_gain_r
        
        return True
    
    def semantic_solve(self) -> str:
        """语义求解器：生成轮端功率限制计算的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 轮端功率限制计算的自然语言报告（中文格式）
        """
        edu_spd_max = self.intermediate_output_values.get("edu_spd_max_final", 0.0)
        axle_eff = self.intermediate_output_values.get("axle_eff_final", 0.99)
        bat_pmax = self.intermediate_output_values.get("bat_pmax_wheel", 0.0)
        bat_30m_pmax = self.intermediate_output_values.get("bat_30m_pmax_wheel", 0.0)
        bat_300s_pmax = self.intermediate_output_values.get("bat_300s_pmax_wheel", 0.0)
        edu_pmax_r = self.intermediate_output_values.get("edu_pmax_r_raw", 0.0)
        edu_30m_pmax_r = self.intermediate_output_values.get("edu_30m_pmax_r_raw", 0.0)
        edp_30m_pmax = self.intermediate_output_values.get("edp_30m_pmax_wheel", 0.0)
        edp_300s_pmax = self.intermediate_output_values.get("edp_300s_pmax_wheel", 0.0)
        edp_pmax = self.intermediate_output_values.get("edp_pmax_wheel", 0.0)

        report = f"""### node_2_PowerLimitCalculator_RWD（功率限制计算）计算节点分析报告

#### 计算结果摘要

##### 基本参数
- 电驱综合最高转速：{edu_spd_max:.1f} rpm
- 半轴传动效率：{axle_eff:.3f}

##### 电池轮端功率
- 电池轮端峰值功率：{bat_pmax:.2f} kW
- 电池轮端300s持续功率：{bat_300s_pmax:.2f} kW
- 电池轮端持续功率：{bat_30m_pmax:.2f} kW

##### 电驱轮端功率
- 电驱轮端峰值功率：{edu_pmax_r:.2f} kW
- 电驱轮端持续功率：{edu_30m_pmax_r:.2f} kW

##### 三电系统轮端功率限制
- 三电系统轮端峰值功率：{edp_pmax:.2f} kW
- 三电系统轮端最大持续功率@30min：{edp_30m_pmax:.2f} kW
- 三电系统轮端最大持续功率@300s：{edp_300s_pmax:.2f} kW

#### 计算逻辑说明

- 输入：后电驱参数（最高转速、最大扭矩、峰值功率、持续功率、功率衰减系数），电池参数（峰值功率、30min持续功率、300s持续功率），传动效率，低压功率（均来自SSTS参数）
- 计算方法：
  * 电池轮端功率 = (电池功率 - 低压功率/1000) × 电驱驱动平均效率 × 半轴效率
  * 三电系统30min持续功率 = min(电池30min轮端功率, 电驱30min功率)
  * 三电系统300s持续功率 = 电池300s轮端功率
  * 三电系统峰值功率 = min(电池轮端峰值功率, 电驱峰值功率)
- 输出：电驱综合最高转速、半轴效率、电池轮端功率（峰值/30min/300s）、电驱轮端功率、三电系统轮端功率限制

#### 参数计算关系

- 电池轮端峰值功率: bat_pmax = (bat_pmax - power_lp/1000) × mot_pow_eff × axle_eff = ({self.ssts_values.get('bat_pmax', 0):.1f} - {self.ssts_values.get('power_lp', 0):.0f}/1000) × {self.ssts_values.get('mot_pow_eff', 0):.3f} × {self.ssts_values.get('axle_eff', 0):.3f} = {bat_pmax:.2f} kW
- 电池轮端30min持续功率: bat_30m_pmax = (bat_30m_pmax - power_lp/1000) × mot_pow_eff × axle_eff = ({self.ssts_values.get('bat_30m_pmax', 0):.1f} - {self.ssts_values.get('power_lp', 0):.0f}/1000) × {self.ssts_values.get('mot_pow_eff', 0):.3f} × {self.ssts_values.get('axle_eff', 0):.3f} = {bat_30m_pmax:.2f} kW
- 电池轮端300s持续功率: bat_300s_pmax = (bat_300s_pmax - power_lp/1000) × mot_pow_eff × axle_eff = ({self.ssts_values.get('bat_300s_pmax', 0):.1f} - {self.ssts_values.get('power_lp', 0):.0f}/1000) × {self.ssts_values.get('mot_pow_eff', 0):.3f} × {self.ssts_values.get('axle_eff', 0):.3f} = {bat_300s_pmax:.2f} kW
- 三电系统30min持续功率: edp_30m_pmax = min(bat_30m_pmax, edu_30m_pmax_r) = min({bat_30m_pmax:.2f}, {edu_30m_pmax_r:.2f}) = {edp_30m_pmax:.2f} kW
- 三电系统300s持续功率: edp_300s_pmax = bat_300s_pmax = {bat_300s_pmax:.2f} kW
- 三电系统峰值功率: edp_pmax = min(bat_pmax, edu_pmax_r) = min({bat_pmax:.2f}, {edu_pmax_r:.2f}) = {edp_pmax:.2f} kW

#### 可调参数清单（用于 DOE 分析）

- edu_spd_max_r: 后电驱最高转速, 单位: rpm, 当前值: {self.ssts_values.get('edu_spd_max_r', 0):.1f}
- edu_tmax_r: 后电驱最大扭矩, 单位: Nm, 当前值: {self.ssts_values.get('edu_tmax_r', 0):.1f}
- edu_pmax_r: 后电驱峰值功率, 单位: kW, 当前值: {self.ssts_values.get('edu_pmax_r', 0):.1f}
- edu_30m_pmax_r: 后电驱持续功率, 单位: kW, 当前值: {self.ssts_values.get('edu_30m_pmax_r', 0):.1f}
- edu_pow_gain_r: 后电驱功率衰减系数, 单位: 无量纲, 当前值: {self.ssts_values.get('edu_pow_gain_r', 0):.2f}
- bat_pmax: 电池峰值功率, 单位: kW, 当前值: {self.ssts_values.get('bat_pmax', 0):.1f}
- bat_30m_pmax: 电池持续功率, 单位: kW, 当前值: {self.ssts_values.get('bat_30m_pmax', 0):.1f}
- bat_300s_pmax: 电池300s持续功率, 单位: kW, 当前值: {self.ssts_values.get('bat_300s_pmax', 0):.1f}
- axle_eff: 半轴效率, 单位: 无量纲, 当前值: {self.ssts_values.get('axle_eff', 0):.3f}
- mot_pow_eff: 电驱驱动平均效率, 单位: 无量纲, 当前值: {self.ssts_values.get('mot_pow_eff', 0):.3f}
- power_lp: 动力性校核低压功率, 单位: W, 当前值: {self.ssts_values.get('power_lp', 0):.0f}

#### 输出参数清单（用于 DOE 的 output_vars）

- edu_spd_max: 电驱综合最高转速, 单位: rpm
- axle_eff: 半轴效率, 单位: 无量纲
- bat_pmax: 电池轮端峰值功率, 单位: kW
- bat_30m_pmax: 电池轮端30min持续功率, 单位: kW
- bat_300s_pmax: 电池轮端300s持续功率, 单位: kW
- edp_30m_pmax: 三电系统轮端30min持续功率, 单位: kW
- edp_300s_pmax: 三电系统轮端300s持续功率, 单位: kW
- edp_pmax: 三电系统轮端峰值功率, 单位: kW
- edu_tmax_r: 后电驱最大扭矩, 单位: Nm
- edu_pmax_r: 后电驱峰值功率, 单位: kW
- edu_30m_pmax_r: 后电驱持续功率, 单位: kW
- edu_spd_max_r: 后电驱最高转速, 单位: rpm
- edu_pow_gain_r: 后电驱功率衰减系数, 单位: 无量纲"""

        self.intermediate_output_values["semantic_summary"] = report

        return report