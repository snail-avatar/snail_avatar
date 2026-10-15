# @Time    : 2026
# @Author  : 李涛
# @File    : node_3_AccelTopSpeedCalculator_RWD.py
# @Desc    : 加速时间与最高车速计算节点（RWD 后驱模式）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# 加速时间与最高车速计算节点（RWD 后驱模式）
# 计算后驱配置下的加速时间和最高车速（包括1km最高车速和30min最高车速）

from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class AccelTopSpeedCalculator_RWD(CalculationNode):
    """加速时间与最高车速计算节点（RWD 后驱模式）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.g = 9.81  # 重力加速度，N/kg
        self.pi = 3.141593  # 圆周率

    def calculate_motor_torque_rwd(self, edu_spd, params):
        """
        计算后驱模式下电驱扭矩外特性
        
        Args:
            edu_spd: 当前电驱转速，rpm
            params: SSTS/VTS 参数字典
        
        Returns:
            edu_spd_tor_r: 后电驱扭矩，Nm
        """
        # 后电驱基准转速
        if params.get('edu_tmax_r', 0) > 0:
            edu_spd_base_r = 9550 * params.get('edu_pmax_r', 0) / params.get('edu_tmax_r', 1)
        else:
            edu_spd_base_r = 0
        
        # 后电驱扭矩外特性
        if edu_spd <= edu_spd_base_r:
            edu_spd_tor_r = params.get('edu_tmax_r', 0)
        else:
            edu_spd_tor_r = 9550 * params.get('edu_pmax_r', 0) / edu_spd * (
                1 - (edu_spd - edu_spd_base_r) / 
                (params.get('edu_spd_max_r', 1) - edu_spd_base_r) * 
                (1 - params.get('edu_pow_gain_r', 0.9))
            )
        
        return edu_spd_tor_r
    
    def calculate_acceleration_rwd(self, params, mass_half, mass_half_equ, f_half_r, edu_spd_max, bat_max, axle_eff, rad, drg_tor):
        """
        后驱模式加速时间计算
        
        Args:
            params: SSTS/VTS 参数字典
            mass_half: 半载质量
            mass_half_equ: 加速等效质量
            f_half_r: 后轮附着力
            edu_spd_max: 电驱最高转速
            bat_max: 电池轮端峰值功率
            axle_eff: 半轴效率
            rad: 轮胎滚动半径
            drg_tor: 拖滞力矩
        
        Returns:
            acceleration_result: 包含时间、速度、加速度的字典
        """
        # 初始化变量
        t_list = [0.0]      # 时间列表
        v_list = [0.0]      # 速度列表(m/s)
        a_list = [0.0]      # 加速度列表
        
        t_current = 0.0     # 当前时间
        v_current = 0.0     # 当前速度
        h_fixed = 0.1       # 固定步长0.1s
        t_max = 100.0       # 最大计算时间100s
        a_threshold = 0.01  # 加速度阈值
        step_count = 0
        max_steps = int(t_max / h_fixed) + 1
        
        while t_current < t_max and step_count < max_steps:
            step_count += 1
            
            # 计算当前电驱转速
            if v_current < 1e-6:
                edu_spd = 0.0
            else:
                edu_spd = (v_current * 60) / (2 * self.pi * rad)
            edu_spd = max(0.0, min(edu_spd, edu_spd_max))
            
            # 计算电驱外特性（RWD模式只考虑后电驱）
            edu_spd_tor_r = self.calculate_motor_torque_rwd(edu_spd, params)
            
            # 计算轮端驱动力（RWD模式只考虑后轮）
            f_wel_spd_r = min(
                f_half_r,
                (edu_spd_tor_r * axle_eff / rad)
            )
            f_wel_spd = f_wel_spd_r
            
            # 计算车速
            v = edu_spd * 2 * self.pi * rad / 60
            
            # 计算各种阻力
            drag_f = drg_tor / rad  # 拖滞阻力
            tire_f = mass_half * self.g * params.get('rr_part', 6.5) / 1000 * params.get('rr_gain', 1.2)  # 滚阻
            air_f = 0.5 * params.get('dst', 1.225) * (v ** 2) * params.get('cd_wt', 0.28) * params.get('cd_gain', 1.15) * params.get('aero', 2.45)  # 风阻
            
            # 电池功率限制的综合轮端驱动力
            # bat_max 已是轮端等效功率（node_2中已乘过mot_pow_eff和axle_eff），无需再乘axle_eff
            if v > 0:
                f_wel_spd_bat = min(
                    f_wel_spd,
                    1000 * bat_max / v
                )
            else:
                f_wel_spd_bat = f_wel_spd
            
            # 计算加速度
            a = (f_wel_spd_bat - tire_f - air_f - drag_f) / mass_half_equ
            a = max(0.0, a)  # 确保加速度不为负
            
            # 欧拉法积分
            v_new = v_current + a * h_fixed
            t_current += h_fixed
            
            # 更新状态
            v_current = v_new
            
            # 保存结果
            t_list.append(round(t_current, 6))
            v_list.append(round(v_current, 6))
            a_list.append(round(a, 6))
            
            # 检查停止条件
            if a <= a_threshold:
                break
        
        return {
            'time': t_list,
            'velocity_mps': v_list,
            'velocity_kmh': [v * 3.6 for v in v_list],
            'acceleration': a_list
        }
    
    def extract_acceleration_indicators(self, acceleration_result):
        """
        从加速计算结果中提取关键性能指标
        
        Args:
            acceleration_result: 加速计算结果字典
        
        Returns:
            indicators: 性能指标字典，包含各区间加速时间和最高速度
        """
        v_kmh_list = acceleration_result['velocity_kmh']
        t_list = acceleration_result['time']
        
        # 查找各速度点的时间索引
        speed_targets = [50, 80, 100, 120]
        time_indicators = {}
        
        for target_speed in speed_targets:
            idx = next((i for i, v in enumerate(v_kmh_list) if v >= target_speed), None)
            if idx is not None:
                time_indicators[f't_{target_speed}'] = t_list[idx]
            else:
                time_indicators[f't_{target_speed}'] = None
        
        # 计算区间加速时间
        indicators = {}
        indicators['t_0_50'] = time_indicators['t_50']
        indicators['t_0_80'] = time_indicators['t_80']
        indicators['t_0_100'] = time_indicators['t_100']
        indicators['t_0_120'] = time_indicators['t_120']
        
        if time_indicators['t_50'] is not None and time_indicators['t_80'] is not None:
            indicators['t_50_80'] = time_indicators['t_80'] - time_indicators['t_50']
        else:
            indicators['t_50_80'] = None
            
        if time_indicators['t_80'] is not None and time_indicators['t_120'] is not None:
            indicators['t_80_120'] = time_indicators['t_120'] - time_indicators['t_80']
        else:
            indicators['t_80_120'] = None
        
        # 最高速度（加速计算得出的最高速度）
        indicators['v_max_acc'] = max(v_kmh_list) if v_kmh_list else 0
        
        return indicators
    
    def calculate_cubic_root(self, x):
        """计算实数立方根（支持负数）"""
        if x >= 0:
            return x ** (1/3)
        else:
            return -((-x) ** (1/3))
    
    def calculate_max_speed_rwd(self, params, edu_spd_max, edp_30m_pmax, mass_half, drg_tor, acceleration_indicators=None):
        """
        后驱模式最高车速计算（包括1km最高车速和30min最高车速）
        
        Args:
            params: SSTS/VTS 参数字典
            edu_spd_max: 电驱最高转速
            edp_30m_pmax: 三电系统轮端持续功率
            mass_half: 半载质量
            drg_tor: 拖滞力矩
            acceleration_indicators: 加速性能指标（可选）
        
        Returns:
            max_speed_result: 最高车速计算结果字典
        """
        # 1. 电驱最大转速对应的最高车速
        v_max_edu = edu_spd_max * 2 * self.pi * params.get('rad', 0.359) / 60
        
        # 2. 阻力二次系数
        c = 0.5 * params.get('dst', 1.225) * params.get('cd_wt', 0.28) * params.get('cd_gain', 1.15) * params.get('aero', 2.45)
        
        # 3. 水平路面阻力常数
        drag_f = drg_tor / params.get('rad', 0.359)
        tire_f = mass_half * self.g * params.get('rr_part', 6.5) / 1000 * params.get('rr_gain', 1.2)
        b_0 = drag_f + tire_f
        
        # 4. 30min功率限制最高车速计算
        p = edp_30m_pmax
        b = b_0
        
        # 使用立方根公式计算
        term1 = 500 * p / c if c > 0 else 0
        term2 = ((500 * p / c) ** 2 + (b / (3 * c)) ** 3) ** 0.5 if c > 0 else 0
        
        # 计算两个立方根项
        cube_root1 = self.calculate_cubic_root(term1 + term2)
        cube_root2 = self.calculate_cubic_root(term1 - term2)
        
        v_max_30min_p = cube_root1 + cube_root2
        
        # 5. 1km最高车速（基于扭矩限制）
        if acceleration_indicators is not None:
            v_max_tor_kmh = acceleration_indicators['v_max_acc']
            v_max_tor = v_max_tor_kmh / 3.6  # 转换为m/s
        else:
            v_max_tor = v_max_edu  # 如果没有加速计算结果，使用电驱限制速度
        
        # 1km最高车速（电驱转速限制和扭矩限制的最小值）
        v_max_1km = 3.6 * min(v_max_edu, v_max_tor)
        
        # 6. 30min最高车速（1km最高车速和功率限制的最小值）
        v_max_30min = min(v_max_1km, (3.6 * v_max_30min_p))
        
        return {
            'v_max_1km': v_max_1km,           # 1km最高车速(km/h)
            'v_max_30min': v_max_30min        # 30min最高车速(km/h)
        }
    
    def numerical_solve(self, memory_db=None):
        """
        数值求解：计算后驱配置下的加速时间和最高车速
        """
        # =============================================================
        # 读取输入（变量名与YAML完全对应）
        # =============================================================
        # 从 SSTS 参数读取
        params = self.ssts_values
        axle_eff = params.get('axle_eff', 0.99)
        rad = params.get('rad', 0.359)
        f_brake_res = params.get('f_brake_res', 1.5)
        r_brake_res = params.get('r_brake_res', 1.5)
        f_bearing_res = params.get('f_bearing_res', 0.8)
        r_bearing_res = params.get('r_bearing_res', 0.8)
        
        # 从上游节点读取中间变量
        mass_half = self.intermediate_input_values.get('mass_half_load')
        mass_half_equ = self.intermediate_input_values.get('mass_half_load_equ')
        f_half_r = self.intermediate_input_values.get('f_half_r')
        edu_spd_max = self.intermediate_input_values.get('edu_spd_max')
        bat_max = self.intermediate_input_values.get('bat_pmax')
        edp_30m_pmax = self.intermediate_input_values.get('edp_30m_pmax')

        # 计算拖滞力矩
        drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) * 2
        
        # =============================================================
        # 执行计算
        # =============================================================
        # 步骤1：计算加速性能
        acceleration_result = self.calculate_acceleration_rwd(params, mass_half, mass_half_equ, f_half_r, edu_spd_max, bat_max, axle_eff, rad, drg_tor)
        
        # 步骤2：提取加速性能指标（原始值）
        acceleration_indicators = self.extract_acceleration_indicators(acceleration_result)
        
        # 步骤3：加速时间修正
        acc_0_50_delta = params.get('acc_0_50_delta', 0.0)
        acc_0_100_delta = params.get('acc_0_100_delta', 0.0)
        acc_50_80_delta = params.get('acc_50_80_delta', 0.0)
        acc_80_120_delta = params.get('acc_80_120_delta', 0.0)

        # 保存原始加速时间值（供语义报告使用）
        t_0_50_raw = acceleration_indicators['t_0_50']
        t_0_100_raw = acceleration_indicators['t_0_100']
        t_50_80_raw = acceleration_indicators['t_50_80']
        t_80_120_raw = acceleration_indicators['t_80_120']
        self.intermediate_output_values["t_0_50_raw"] = t_0_50_raw
        self.intermediate_output_values["t_0_100_raw"] = t_0_100_raw
        self.intermediate_output_values["t_50_80_raw"] = t_50_80_raw
        self.intermediate_output_values["t_80_120_raw"] = t_80_120_raw

        # 修正后加速时间 = 原始值 + 修正值
        t_0_50_corr = (t_0_50_raw + acc_0_50_delta) if t_0_50_raw is not None else None
        t_0_100_corr = (t_0_100_raw + acc_0_100_delta) if t_0_100_raw is not None else None
        t_50_80_corr = (t_50_80_raw + acc_50_80_delta) if t_50_80_raw is not None else None
        t_80_120_corr = (t_80_120_raw + acc_80_120_delta) if t_80_120_raw is not None else None

        # 保存修正后加速时间
        self.intermediate_output_values["t_0_50"] = t_0_50_corr
        self.intermediate_output_values["t_0_100"] = t_0_100_corr
        self.intermediate_output_values["t_50_80"] = t_50_80_corr
        self.intermediate_output_values["t_80_120"] = t_80_120_corr
        self.intermediate_output_values["v_max_acc"] = acceleration_indicators['v_max_acc']

        # 核心加速时间指标（输出到 VTS）
        self._sync_ssts_vts_output(memory_db, "t_0_50", float(t_0_50_corr) if t_0_50_corr is not None else 0.0)
        self._sync_ssts_vts_output(memory_db, "t_0_100", float(t_0_100_corr) if t_0_100_corr is not None else 0.0)
        self._sync_ssts_vts_output(memory_db, "t_50_80", float(t_50_80_corr) if t_50_80_corr is not None else 0.0)
        self._sync_ssts_vts_output(memory_db, "t_80_120", float(t_80_120_corr) if t_80_120_corr is not None else 0.0)
        
        # 步骤4：计算最高车速
        max_speed_result = self.calculate_max_speed_rwd(params, edu_spd_max, edp_30m_pmax, mass_half, drg_tor, acceleration_indicators)
        
        # 读取最高车速修正参数
        v_max_1km_delta = params.get('v_max_1km_delta', 0.0)
        v_max_30min_delta = params.get('v_max_30min_delta', 0.0)
        
        # 保存最高车速原始值
        v_max_1km_raw = max_speed_result['v_max_1km']
        v_max_30min_raw = max_speed_result['v_max_30min']
        self.intermediate_output_values["v_max_1km_raw"] = v_max_1km_raw
        self.intermediate_output_values["v_max_30min_raw"] = v_max_30min_raw
        
        # 修正后最高车速 = 原始值 + 修正值
        v_max_1km_corr = v_max_1km_raw + v_max_1km_delta
        v_max_30min_corr = v_max_30min_raw + v_max_30min_delta
        
        # 保存修正后最高车速
        self.intermediate_output_values["v_max_1km"] = v_max_1km_corr
        self.intermediate_output_values["v_max_30min"] = v_max_30min_corr

        # 核心最高车速指标（输出到 VTS）
        self._sync_ssts_vts_output(memory_db, "v_max_1km", float(v_max_1km_corr))
        self._sync_ssts_vts_output(memory_db, "v_max_30min", float(v_max_30min_corr))
        
        # 注意：中间变量已通过 intermediate_output_values 保存，
        # 会自动同步到内存数据库的 INTER 存储供下游节点使用。
        # 不需要再写入 ssts_values，因为这些不是 SSTS/VTS 参数。
        # 如果需要将某些变量保存为 SSTS/VTS 参数，请在 YAML 配置文件中定义
        # 并使用 self.set_ssts_value() 方法。
        
        return True
    
    def semantic_solve(self) -> str:
        """语义求解器：生成动力性能计算的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 动力性能计算的自然语言报告（中文格式）
        """
        # 获取计算结果（修正后）
        t_0_50 = self.intermediate_output_values.get("t_0_50", None)
        t_0_100 = self.intermediate_output_values.get("t_0_100", None)
        t_50_80 = self.intermediate_output_values.get("t_50_80", None)
        t_80_120 = self.intermediate_output_values.get("t_80_120", None)
        v_max_acc = self.intermediate_output_values.get("v_max_acc", 0.0)
        v_max_1km = self.intermediate_output_values.get("v_max_1km", 0.0)
        v_max_30min = self.intermediate_output_values.get("v_max_30min", 0.0)

        # 获取原始加速时间值
        t_0_50_raw = self.intermediate_output_values.get("t_0_50_raw", None)
        t_0_100_raw = self.intermediate_output_values.get("t_0_100_raw", None)
        t_50_80_raw = self.intermediate_output_values.get("t_50_80_raw", None)
        t_80_120_raw = self.intermediate_output_values.get("t_80_120_raw", None)

        # 获取原始最高车速值
        v_max_1km_raw = self.intermediate_output_values.get("v_max_1km_raw", None)
        v_max_30min_raw = self.intermediate_output_values.get("v_max_30min_raw", None)

        acc_time_lines = []
        if t_0_50 is not None:
            raw_str = f"（原始{t_0_50_raw:.2f}s）" if t_0_50_raw is not None and abs(t_0_50 - t_0_50_raw) > 0.001 else ""
            acc_time_lines.append(f"- 0-50km/h：{t_0_50:.2f} s{raw_str}")
        if t_0_100 is not None:
            raw_str = f"（原始{t_0_100_raw:.2f}s）" if t_0_100_raw is not None and abs(t_0_100 - t_0_100_raw) > 0.001 else ""
            acc_time_lines.append(f"- 0-100km/h：{t_0_100:.2f} s{raw_str}")
        if t_50_80 is not None:
            raw_str = f"（原始{t_50_80_raw:.2f}s）" if t_50_80_raw is not None and abs(t_50_80 - t_50_80_raw) > 0.001 else ""
            acc_time_lines.append(f"- 50-80km/h：{t_50_80:.2f} s{raw_str}")
        if t_80_120 is not None:
            raw_str = f"（原始{t_80_120_raw:.2f}s）" if t_80_120_raw is not None and abs(t_80_120 - t_80_120_raw) > 0.001 else ""
            acc_time_lines.append(f"- 80-120km/h：{t_80_120:.2f} s{raw_str}")

        if v_max_1km_raw is not None and abs(v_max_1km - v_max_1km_raw) > 0.01:
            v_max_1km_raw_str = f"（原始{v_max_1km_raw:.1f}km/h）"
        else:
            v_max_1km_raw_str = ""
        if v_max_30min_raw is not None and abs(v_max_30min - v_max_30min_raw) > 0.01:
            v_max_30min_raw_str = f"（原始{v_max_30min_raw:.1f}km/h）"
        else:
            v_max_30min_raw_str = ""

        report = f"""### node_3_AccelTopSpeedCalculator_RWD（加速最高车速）计算节点分析报告

#### 计算结果摘要

##### 加速时间
{chr(10).join(acc_time_lines)}

##### 最高车速
- 外特征最高速度：{v_max_acc:.1f} km/h
- 1km最高车速（基于扭矩和转速限制）：{v_max_1km:.1f} km/h{v_max_1km_raw_str}
- 30min最高车速（基于1km最高车速和30min持续限制）：{v_max_30min:.1f} km/h{v_max_30min_raw_str}

#### 计算逻辑说明

- 输入：半载质量、加速等效质量、后轮附着力（来自node_1A），电驱转速限制、电池轮端功率、三电系统30min持续功率（来自node_2），阻力参数（来自SSTS参数）
- 加速时间计算方法（欧拉法积分，步长0.1s）：
  * 电驱转速 = v × 60 / (2π × rad)
  * 电驱扭矩外特性：基速以下恒扭矩，基速以上按功率计算并考虑功率衰减系数
  * 轮端驱动力 = min(附着力, 电驱扭矩×传动效率/轮胎半径)
  * 电池功率限制驱动力 = 1000 × 电池轮端峰值功率 / 车速
  * 阻力 = 拖滞阻力 + 滚阻 + 风阻
  * 加速度 = (驱动力 - 阻力) / 加速等效质量
  * 速度更新：v_new = v_current + a × 步长
- 最高车速计算方法：
  * 电驱转速限制：v_max_edu = edu_spd_max × 2π × rad / 60
  * 30min功率限制（立方根公式）：v_max_30min_p = cube_root(500P/C + sqrt((500P/C)² + (B/3C)³)) + cube_root(500P/C - sqrt((500P/C)² + (B/3C)³))
  * 1km最高车速 = min(电驱转速限制, 加速计算最高速度)
  * 30min最高车速 = min(1km最高车速, 30min功率限制车速)
- 输出：各区间加速时间（0-50/0-100/50-80/80-120）、外特征最高速度、1km最高车速、30min最高车速

#### 修正方法

- acc_0_50_delta：{self.ssts_values.get('acc_0_50_delta', 0):.3f} s，0-50km/h加速时间修正值
- acc_0_100_delta：{self.ssts_values.get('acc_0_100_delta', 0):.3f} s，0-100km/h加速时间修正值
- acc_50_80_delta：{self.ssts_values.get('acc_50_80_delta', 0):.3f} s，50-80km/h加速时间修正值
- acc_80_120_delta：{self.ssts_values.get('acc_80_120_delta', 0):.3f} s，80-120km/h加速时间修正值
- v_max_1km_delta：{self.ssts_values.get('v_max_1km_delta', 0):.2f} km/h，1km最高车速修正值
- v_max_30min_delta：{self.ssts_values.get('v_max_30min_delta', 0):.2f} km/h，30min最高车速修正值
- 修正后值 = 原始计算值 + 修正值

#### 参数计算关系

- 拖滞力矩: drg_tor = (f_brake_res + r_brake_res + f_bearing_res + r_bearing_res) × 2 = ({self.ssts_values.get('f_brake_res', 0):.1f} + {self.ssts_values.get('r_brake_res', 0):.1f} + {self.ssts_values.get('f_bearing_res', 0):.1f} + {self.ssts_values.get('r_bearing_res', 0):.1f}) × 2 = {(self.ssts_values.get('f_brake_res', 0) + self.ssts_values.get('r_brake_res', 0) + self.ssts_values.get('f_bearing_res', 0) + self.ssts_values.get('r_bearing_res', 0)) * 2:.1f} N·m
- 拖滞阻力: drag_f = drg_tor / rad = {(self.ssts_values.get('f_brake_res', 0) + self.ssts_values.get('r_brake_res', 0) + self.ssts_values.get('f_bearing_res', 0) + self.ssts_values.get('r_bearing_res', 0)) * 2:.1f} / {self.ssts_values.get('rad', 0):.3f} = {(self.ssts_values.get('f_brake_res', 0) + self.ssts_values.get('r_brake_res', 0) + self.ssts_values.get('f_bearing_res', 0) + self.ssts_values.get('r_bearing_res', 0)) * 2 / self.ssts_values.get('rad', 0):.1f} N
- 风阻二次系数: C = 0.5 × dst × cd_wt × cd_gain × aero = 0.5 × {self.ssts_values.get('dst', 0):.3f} × {self.ssts_values.get('cd_wt', 0):.3f} × {self.ssts_values.get('cd_gain', 0):.2f} × {self.ssts_values.get('aero', 0):.2f} = {0.5 * self.ssts_values.get('dst', 0) * self.ssts_values.get('cd_wt', 0) * self.ssts_values.get('cd_gain', 0) * self.ssts_values.get('aero', 0):.6f}
- 修正后加速时间: t_0_50 = t_0_50_raw + acc_0_50_delta, t_0_100 = t_0_100_raw + acc_0_100_delta
- 修正后最高车速: v_max_1km = v_max_1km_raw + v_max_1km_delta, v_max_30min = v_max_30min_raw + v_max_30min_delta

#### 可调参数清单（用于 DOE 分析）

- rad: 轮胎滚动半径, 单位: m, 当前值: {self.ssts_values.get('rad', 0):.3f}
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
- acc_0_50_delta: 0-50km/h加速时间修正值, 单位: s, 当前值: {self.ssts_values.get('acc_0_50_delta', 0):.3f}
- acc_0_100_delta: 0-100km/h加速时间修正值, 单位: s, 当前值: {self.ssts_values.get('acc_0_100_delta', 0):.3f}
- acc_50_80_delta: 50-80km/h加速时间修正值, 单位: s, 当前值: {self.ssts_values.get('acc_50_80_delta', 0):.3f}
- acc_80_120_delta: 80-120km/h加速时间修正值, 单位: s, 当前值: {self.ssts_values.get('acc_80_120_delta', 0):.3f}
- v_max_1km_delta: 1km最高车速修正值, 单位: km/h, 当前值: {self.ssts_values.get('v_max_1km_delta', 0):.2f}
- v_max_30min_delta: 30min最高车速修正值, 单位: km/h, 当前值: {self.ssts_values.get('v_max_30min_delta', 0):.2f}

#### 输出参数清单（用于 DOE 的 output_vars）

- t_0_50: 0-50km/h加速时间, 单位: s
- t_0_100: 0-100km/h加速时间, 单位: s
- t_50_80: 50-80km/h加速时间, 单位: s
- t_80_120: 80-120km/h加速时间, 单位: s
- v_max_acc: 外特征最高速度, 单位: km/h
- v_max_1km: 1km最高车速, 单位: km/h
- v_max_30min: 30min最高车速, 单位: km/h
- t_0_50_raw: 0-50km/h原始加速时间, 单位: s
- t_0_100_raw: 0-100km/h原始加速时间, 单位: s
- t_50_80_raw: 50-80km/h原始加速时间, 单位: s
- t_80_120_raw: 80-120km/h原始加速时间, 单位: s
- v_max_1km_raw: 1km原始最高车速, 单位: km/h
- v_max_30min_raw: 30min原始最高车速, 单位: km/h"""

        self.intermediate_output_values["semantic_summary"] = report

        return report