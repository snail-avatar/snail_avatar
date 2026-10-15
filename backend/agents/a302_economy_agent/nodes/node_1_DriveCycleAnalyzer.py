# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_1_DriveCycleAnalyzer.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
驾驶循环分析器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_1_DriveCycleAnalyzer.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 calculate() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class DriveCycleAnalyzerNode(CalculationNode):
    """驾驶循环分析器节点类

    最小物理过程1：驾驶循环运动学分析
    职责：纯运动学分析，计算时间间隔、速度、加速度、行驶距离等基础数组
    """

    def _load_drive_cycle(self, memory_db=None) -> TimeSeries:
        """根据驾驶循环名称加载驾驶循环曲线数据

        Args:
            memory_db: 内存数据库引用（可选，如果已注入则使用注入的）

        Returns:
            TimeSeries: 驾驶循环时间序列数据

        Raises:
            ValueError: 无法获取驾驶循环数据时抛出
        """
        drive_cycle_name = self.ssts_values.get("drive_cycle")
        if not drive_cycle_name:
            raise ValueError("驾驶循环名称(drive_cycle)未设置")

        if memory_db is None:
            memory_db = getattr(self, 'memory_db', None)

        if memory_db:
            return memory_db.get_ecocycle_curve(drive_cycle_name)
        else:
            time = self.intermediate_input_values.get("time")
            value = self.intermediate_input_values.get("value")
            if time is None or value is None:
                raise ValueError("无法获取驾驶循环数据，请确保 memory_db 已注入")
            return TimeSeries(time=time, value=value)

    def numerical_solve(self, memory_db=None):
        """执行驾驶循环分析计算

        【约定优于配置架构】
        - 输入：self.ssts_values["drive_cycle"] 获取驾驶循环名称
        - 数据：从 memory_db.get_ecocycle_curve() 获取时间序列数据
        - 输出：写入 self.intermediate_output_values

        Args:
            memory_db: 内存数据库引用（可选，如果需要从数据库获取驾驶循环数据）

        Returns:
            bool: 计算是否成功
        """
        try:
            # =============================================================
            # 读取输入：使用抽象的驾驶循环数据读取方法
            # =============================================================
            cycle_ts = self._load_drive_cycle(memory_db)

            time = cycle_ts.time
            value = cycle_ts.value

            # =============================================================
            # 纯算法逻辑（使用 TimeSeries 链式方法）
            # =============================================================

            # 1. 获取时间步长（N-1长度）
            dt = cycle_ts.dt

            # 2. 计算速度变化（使用区间差分，N-1长度）
            dv_ts = cycle_ts.diff_interval()
            dv = dv_ts.value

            # 3. 计算加速度 a = dv / dt（两者都是 N-1 长度，匹配）
            a = dv / dt
            
            # 创建加速度 TimeSeries
            a_ts = TimeSeries(
                time=dv_ts.time,
                value=a,
                name="a",
                unit="m/s²",
                desc="加速度"
            )

            # 4. 计算区间平均速度（使用区间滑动平均，N-1长度）
            vel_ave_ts = cycle_ts.rolling_mean_interval()
            vel_ave = vel_ave_ts.value

            # 5. 计算行驶距离 lth = vel_ave * dt（两者都是 N-1 长度，匹配）
            lth = vel_ave * dt
            
            # 创建行驶距离 TimeSeries
            lth_ts = TimeSeries(
                time=vel_ave_ts.time,
                value=lth,
                name="lth",
                unit="m",
                desc="行驶距离"
            )

            # 6. 计算循环特征参数（复用 TimeSeries 属性）
            total_distance = float(np.sum(lth) / 1000)
            cycle_duration = cycle_ts.total_time
            v_mean = cycle_ts.mean * 3.6
            v_max = cycle_ts.max * 3.6

            # 加速度相关参数
            a_accel_mask = a > 0.05
            a_decel_mask = a < -0.05
            a_accel_mean = float(np.mean(a[a_accel_mask])) if np.any(a_accel_mask) else 0.0
            a_decel_mean = float(np.mean(np.abs(a[a_decel_mask]))) if np.any(a_decel_mask) else 0.0
            a_max = a_ts.max
            a_decel_max = abs(a_ts.min)

            # 各工况时间占比（基于时间间隔，兼容不均匀采样）
            # 使用区间平均速度进行工况判断，与 node_3_WheelEnergy 保持一致
            dt = np.diff(time)  # 时间间隔数组，长度 N-1
            total_time = np.sum(dt) if len(dt) > 0 else 0.0
            
            idle_vel_threshold = 0.1    # 怠速速度阈值（m/s），约 0.36 km/h
            acc_threshold = 0.001       # 加速度阈值（m/s²）
            
            # 工况分段（优先级：怠速 > 加速/减速 > 巡航）
            idle_mask = vel_ave < idle_vel_threshold                   # 怠速段：速度接近零
            acc_mask = (a > acc_threshold) & ~idle_mask               # 加速段：排除怠速
            dec_mask = (a < -acc_threshold) & ~idle_mask              # 减速段：排除怠速
            const_mask = ~idle_mask & ~acc_mask & ~dec_mask            # 恒速段：排除其他
            
            idle_time = np.sum(dt[idle_mask]) if np.any(idle_mask) else 0.0
            acc_time = np.sum(dt[acc_mask]) if np.any(acc_mask) else 0.0
            dec_time = np.sum(dt[dec_mask]) if np.any(dec_mask) else 0.0
            cruise_time = total_time - idle_time - acc_time - dec_time
            
            idle_ratio_time = idle_time / total_time * 100 if total_time > 0 else 0.0
            acc_ratio_time = acc_time / total_time * 100 if total_time > 0 else 0.0
            dec_ratio_time = dec_time / total_time * 100 if total_time > 0 else 0.0
            cruise_ratio_time = cruise_time / total_time * 100 if total_time > 0 else 0.0

            # 循环特征参数（基于时间的工况占比，兼容不均匀采样）
            cycle_stats = {
                "duration_s": cycle_duration,
                "distance_km": total_distance,
                "v_mean_kmh": v_mean,
                "v_max_kmh": v_max,
                "a_accel_mean": a_accel_mean,
                "a_decel_mean": a_decel_mean,
                "a_max": a_max,
                "a_decel_max": a_decel_max,
                "idle_ratio_pct": float(idle_ratio_time),
                "accel_ratio_pct": float(acc_ratio_time),
                "decel_ratio_pct": float(dec_ratio_time),
                "cruise_ratio_pct": float(cruise_ratio_time)
            }

            # =============================================================
            # 存储输出（按配置文件精简为5个变量）
            # =============================================================

            # vel：原始速度时间序列（N长度）
            self.intermediate_output_values["vel"] = cycle_ts

            # vel_ave：平均速度时间序列（N-1长度）
            self.intermediate_output_values["vel_ave"] = vel_ave_ts

            # a：加速度时间序列（N-1长度）
            self.intermediate_output_values["a"] = a_ts

            # lth：行驶距离时间序列（N-1长度）
            self.intermediate_output_values["lth"] = lth_ts

            # cycle_distance：循环总里程（独立输出，便于下游节点使用）
            self.intermediate_output_values["cycle_distance"] = total_distance

            # cycle_time：循环总时长（独立输出，便于下游节点使用）
            self.intermediate_output_values["cycle_time"] = cycle_duration

            # 工况掩码输出（供下游节点使用，避免重复计算）
            self.intermediate_output_values["idle_mask"] = idle_mask
            self.intermediate_output_values["acc_mask"] = acc_mask
            self.intermediate_output_values["dec_mask"] = dec_mask
            self.intermediate_output_values["const_mask"] = const_mask

            # cycle_stats：循环特征参数
            self.intermediate_output_values["cycle_stats"] = cycle_stats

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False

    def semantic_solve(self) -> str:
        """语义求解器：生成驾驶循环分析的自然语言描述

        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。

        Returns:
            str: 驾驶循环分析的自然语言报告（中文格式）
        """
        cycle_stats = self.intermediate_output_values.get("cycle_stats", {})
        total_distance = cycle_stats.get("distance_km", 0)
        cycle_duration = cycle_stats.get("duration_s", 0)
        cycle_name = self.ssts_values.get("drive_cycle", "未知")
        ssts = self.ssts_values

        report = f"""### node_1_DriveCycleAnalyzer（驾驶循环分析）计算节点分析报告

#### 计算结果摘要

##### 基本信息
- 驾驶循环名称：{cycle_name}
- 循环总里程：{total_distance:.2f} km
- 循环总时长：{cycle_duration:.0f} 秒

##### 速度特征
- 平均速度：{cycle_stats.get('v_mean_kmh', 0):.1f} km/h
- 最高速度：{cycle_stats.get('v_max_kmh', 0):.1f} km/h

##### 加速度特征
- 平均加速度：{cycle_stats.get('a_accel_mean', 0):.2f} m/s²
- 最大加速度：{cycle_stats.get('a_max', 0):.2f} m/s²
- 平均减速度：{cycle_stats.get('a_decel_mean', 0):.2f} m/s²
- 最大减速度：{cycle_stats.get('a_decel_max', 0):.2f} m/s²

##### 工况时间占比
- 怠速工况：{cycle_stats.get('idle_ratio_pct', 0):.1f}%
- 加速工况：{cycle_stats.get('accel_ratio_pct', 0):.1f}%
- 巡航工况：{cycle_stats.get('cruise_ratio_pct', 0):.1f}%
- 减速工况：{cycle_stats.get('decel_ratio_pct', 0):.1f}%

#### 计算逻辑说明

- 输入：驾驶循环名称（SSTS参数 drive_cycle），从memory_db获取时间序列数据
- 计算方法：
  * 加速度：a = dv / dt（使用区间差分）
  * 平均速度：区间滑动平均
  * 行驶距离：lth = vel_ave × dt（逐段累加）
  * 工况识别：基于速度和加速度阈值分段（优先级：怠速 > 加速/减速 > 巡航）
- 输出：速度、加速度、行驶距离时间序列，工况掩码，循环统计特征参数

#### 可调参数清单（用于 DOE 分析）

- drive_cycle: 驾驶循环名称, 当前值: {ssts.get('drive_cycle', '未知')}（此参数选择数据源，非敏感性分析对象）

#### 输出参数清单（用于 DOE 的 output_vars）

- vel: 原始速度时间序列, 单位: m/s
- vel_ave: 平均速度时间序列, 单位: m/s
- lth: 行驶距离时间序列, 单位: m
- a: 加速度时间序列, 单位: m/s²
- cycle_distance: 循环总里程, 单位: km
- cycle_time: 循环总时长, 单位: s
- cycle_stats: 循环特征参数字典"""

        self.intermediate_output_values["semantic_summary"] = report

        return report
