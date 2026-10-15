# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_1_IBuilder.py
# @Desc    : I 曲线构建节点
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
I 曲线（理想制动力分配）构建节点

对应计算方法文档 §3：
  Fμ1^I(φ) = φ · G/L · (b + φ·hg)
  Fμ2^I(φ) = φ·G - Fμ1^I(φ)
  Z = φ（I 曲线上制动强度 = 路面附着系数）
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class IBuilderNode(CalculationNode):
    """I 曲线构建"""

    def numerical_solve(self, memory_db=None):
        G = self.intermediate_input_values.get("G", 0.0)
        L = self.intermediate_input_values.get("L_m", 1.0)
        b = self.intermediate_input_values.get("b", 0.0)
        hg = self.intermediate_input_values.get("hg", 0.0)

        # φ ∈ [0, 1.0] 均匀采样，步长 0.001
        phi = np.linspace(0.0, 1.0, 1001)

        # 文档 §3 公式：Fμ1^I(φ) = φ · G/L · (b + φ·hg)
        F_mu1_I = phi * G / L * (b + phi * hg)
        F_mu2_I = phi * G - F_mu1_I

        self.intermediate_output_values["phi_array"] = phi
        self.intermediate_output_values["F_mu1_I"] = F_mu1_I
        self.intermediate_output_values["F_mu2_I"] = F_mu2_I
        self.intermediate_output_values["Z_array"] = phi   # I 曲线 Z = φ

        return True

    def semantic_solve(self) -> str:
        """I 曲线摘要"""
        phi = self.intermediate_output_values.get("phi_array", np.array([]))
        F_mu1_I = self.intermediate_output_values.get("F_mu1_I", np.array([]))

        if len(phi) == 0:
            return "### IBuilder 计算节点分析报告\n\n数据为空。"

        # 关键采样点（Z=0.3/0.6/0.8）
        sample_Z = [0.3, 0.6, 0.8]
        samples = []
        for z in sample_Z:
            idx = int(z / 0.001)
            if idx < len(F_mu1_I):
                f1 = F_mu1_I[idx]
                samples.append(f"  - Z={z:.1f}: 前轴 Fμ1^I = {f1:.1f} N")

        return (
            f"### IBuilder（I 曲线构建）计算节点分析报告\n"
            f"\n#### 计算结果摘要\n"
            f"- φ ∈ [0, 1.0]，共 {len(phi)} 个采样点\n"
            f"- I 曲线：理想制动力分配（前后轮同时抱死）\n"
            f"- 关键采样点：\n"
            f"{'\\n'.join(samples)}\n"
        )

    def generate_visualization(self):
        """返回 I 曲线可视化数据"""
        phi = self.intermediate_output_values.get("phi_array", np.array([]))
        F_mu1_I = self.intermediate_output_values.get("F_mu1_I", np.array([]))
        F_mu2_I = self.intermediate_output_values.get("F_mu2_I", np.array([]))

        if len(phi) == 0:
            return None

        return {
            "chart_type": "line",
            "title": "I 曲线（理想制动力分配）",
            "x_label": "Fμ1 (N)",
            "y_label": "Fμ2 (N)",
            "series": [
                {
                    "name": "I 曲线",
                    "x": F_mu1_I.tolist(),
                    "y": F_mu2_I.tolist(),
                },
            ],
        }
