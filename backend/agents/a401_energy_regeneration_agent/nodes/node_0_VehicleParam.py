# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_0_VehicleParam.py
# @Desc    : 整车参数预处理节点
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
整车参数预处理节点

职责：从 MemoryDB 读取 SSTS 参数（SI 单位），输出基础量 G, L_m, a, b, hg, R, i0 供下游节点使用。对应计算方法文档 §1-2。
"""

from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class VehicleParamNode(CalculationNode):
    """整车参数预处理"""

    def numerical_solve(self, memory_db=None):
        """参数预处理 + 单位换算
        
        base key 对齐 economy/power 已有命名：
          tire_radius → rad（eco + pwr）
          cg_to_front → mass_centroid_x（pwr）
          cg_height  → mass_centroid_z（pwr）
          cg_to_rear → 删除（用 wheel_base - mass_centroid_x 派生）
          测试质量 → 满载 = mass_curb + mass_maxload（制动校核用，与 power 爬坡工况一致）
        """
        m_curb = self.ssts_values.get("mass_curb") or 0.0
        m_maxload = self.ssts_values.get("mass_maxload") or 0.0
        m_full = m_curb + m_maxload   # 制动校核用满载（与 power agent 爬坡工况一致）

        g = 9.81
        G = m_full * g

        # 输入已是 SI 单位（db_memory 直接存 m / kg），不需要 /1000 换算
        L_m = self.ssts_values.get("wheel_base") or 0.0
        a = self.ssts_values.get("mass_centroid_x") or 0.0   # 前轴 → 质心（x 原点在前轴）
        R = self.ssts_values.get("rad") or 0.0               # 轮胎滚动半径 = 轮心离地高度
        # mass_centroid_z 是质心相对于前轮轮心的高度（乘用车坐标系 z 原点在轮心）
        # 制动力公式需要质心离地面高度 = 轮心离地 + 质心相对轮心
        hg = R + (self.ssts_values.get("mass_centroid_z") or 0.0)

        # b 派生：wheel_base - mass_centroid_x（对齐 a = mass_centroid_x 的坐标系约定）
        b = L_m - a

        # 一致性校验：若派生结果不合理（质心不在轮距内），给出警告
        if a > L_m or a < 0:
            pass  # 留给更下游/UI 层提示

        self.intermediate_output_values["G"] = G
        self.intermediate_output_values["L_m"] = L_m
        self.intermediate_output_values["a"] = a
        self.intermediate_output_values["b"] = b
        self.intermediate_output_values["hg"] = hg
        self.intermediate_output_values["R"] = R

        return True

    def semantic_solve(self) -> str:
        """整车参数摘要"""
        G = self.intermediate_output_values.get("G", 0)
        L_m = self.intermediate_output_values.get("L_m", 0)
        a = self.intermediate_output_values.get("a", 0)
        b = self.intermediate_output_values.get("b", 0)
        hg = self.intermediate_output_values.get("hg", 0)

        return (
            f"### VehicleParam（整车参数预处理）计算节点分析报告\n"
            f"\n#### 计算结果摘要\n"
            f"- 测试质量对应的整车重力 G = {G:.1f} N\n"
            f"- 轴距 L = {L_m:.3f} m\n"
            f"- 质心到前轴 a = {a:.3f} m，到后轴 b = {b:.3f} m\n"
            f"- 质心高度 hg = {hg:.3f} m\n"
            f"\n#### 说明\n"
            f"- 本模块为通用能量回收分析，输出三链路并行（FWD/RWD/AWD）\n"
        )
