# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_2A_MotorWorkpoint.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""电驱工作点计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_2A_MotorWorkpoint.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base import CalculationNode
from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries


class MotorWorkpointNode(CalculationNode):
    """电驱工作点计算器节点类
    
    最小物理过程2A：电驱机械端工作点计算
    职责：纵向动力学方程求解，计算电驱动力、扭矩、转速
    """
    
    def numerical_solve(self, memory_db=None):
        """数值求解器：执行电驱工作点计算
        
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
            f_road_load = self.intermediate_input_values.get("f_road_load")
            f_inert = self.intermediate_input_values.get("f_inert")
            
            # 从 SSTS 参数读取
            rad = self.ssts_values.get("rad")
            
            # =============================================================
            # 纯算法逻辑
            # =============================================================
            
            # 电驱总力 = 道路阻力 + 惯性力（两者都是 N-1 长度）
            f_motor = f_road_load.value + f_inert.value
            
            # 电驱总扭矩 = 力 × 车轮半径
            t_motor = f_motor * rad
            
            # 计算驱动扭矩和制动扭矩
            t_drive = np.where(t_motor > 0, t_motor, 0)
            t_brake = np.where(t_motor < 0, -t_motor, 0) # 修正为正数
            
            # =============================================================
            # 创建 TimeSeries 输出
            # =============================================================
            # 使用 f_road_load 的时间轴（N-1 长度）
            time = f_road_load.time
            
            t_motor_ts = TimeSeries(
                time=time,
                value=t_motor,
                name="t_motor",
                unit="Nm",
                desc="电驱工作扭矩"
            )
            
            t_drive_ts = TimeSeries(
                time=time,
                value=t_drive,
                name="t_drive",
                unit="Nm",
                desc="驱动扭矩"
            )
            
            t_brake_ts = TimeSeries(
                time=time,
                value=t_brake,
                name="t_brake",
                unit="Nm",
                desc="制动扭矩"
            )
            
            # =============================================================
            # 计算统计特征参数
            # =============================================================
            motor_torque_stats = {
                "t_motor_mean_Nm": float(np.mean(t_motor)),
                "t_motor_max_Nm": float(np.max(t_motor)),
                "t_motor_min_Nm": float(np.min(t_motor)),
                "t_drive_mean_Nm": float(np.mean(t_drive)),
                "t_brake_mean_Nm": float(np.mean(t_brake)),
                "drive_ratio_pct": float(np.sum(t_drive > 0) / len(t_drive) * 100), # 驱动工况占比
                "brake_ratio_pct": float(np.sum(t_brake > 0) / len(t_brake) * 100), # 制动工况占比
            }
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            # 时间序列输出（TimeSeries 对象）
            self.intermediate_output_values["t_motor"] = t_motor_ts
            self.intermediate_output_values["t_drive"] = t_drive_ts
            self.intermediate_output_values["t_brake"] = t_brake_ts
            
            # 统计特征输出
            self.intermediate_output_values["motor_torque_stats"] = motor_torque_stats
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False
    
    def semantic_solve(self) -> str:
        """语义求解器：生成电驱工作点分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 电驱工作点分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("motor_torque_stats", {})
        
        report = f"""### node_2A_MotorWorkpoint（电驱工作点）计算节点分析报告

#### 计算结果摘要

##### 扭矩特征
- 平均工作扭矩：{stats.get('t_motor_mean_Nm', 0):.2f} Nm
- 最大工作扭矩：{stats.get('t_motor_max_Nm', 0):.2f} Nm
- 最小工作扭矩：{stats.get('t_motor_min_Nm', 0):.2f} Nm

##### 驱动/制动分布
- 平均驱动扭矩：{stats.get('t_drive_mean_Nm', 0):.2f} Nm
- 平均制动扭矩：{stats.get('t_brake_mean_Nm', 0):.2f} Nm
- 驱动工况占比：{stats.get('drive_ratio_pct', 0):.1f}%
- 制动工况占比：{stats.get('brake_ratio_pct', 0):.1f}%

#### 计算逻辑说明

- 输入：道路阻力、惯性力（来自阻力计算节点），车轮半径（SSTS参数）
- 计算方法：
  * 电驱总力：F_motor = F_road_load + F_inert
  * 电驱总扭矩：T_motor = F_motor × rad
  * 驱动扭矩：T_drive = max(T_motor, 0)
  * 制动扭矩：T_brake = max(-T_motor, 0)
- 输出：电驱工作扭矩、驱动扭矩、制动扭矩时间序列，扭矩统计参数

#### 可调参数清单（用于 DOE 分析）

- rad: 车轮半径, 单位: m, 当前值: {self.ssts_values.get('rad', 0):.3f}（直接影响扭矩转换比例）

#### 输出参数清单（用于 DOE 的 output_vars）

- t_motor: 电驱工作扭矩时间序列, 单位: Nm
- t_drive: 驱动扭矩时间序列, 单位: Nm
- t_brake: 制动扭矩时间序列, 单位: Nm"""
        
        # 将语义摘要写入输出，供下游节点使用    
        self.intermediate_output_values["semantic_summary"] = report
        
        return report
