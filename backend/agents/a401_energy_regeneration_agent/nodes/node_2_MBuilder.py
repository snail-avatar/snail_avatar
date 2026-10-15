# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_2_MBuilder.py
# @Desc    : M 曲线构建节点（ECE R13 法规下限）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
M 曲线构建节点

对应计算方法文档 §4：
  C(φ) = hg/L·φ² + (b/L - 0.85)·φ + 0.07
  Fμ1^M(φ) = φ · G/L · (b + φ·hg)   （前轴可独立提供，与 I 曲线相同）
  Fμ2^M(φ) = 0                      （当 C(φ) ≥ 0，前轴独立满足法规）
             G·[0.1 + 0.85(φ-0.2)] - Fμ1^M(φ)  （当 C(φ) < 0）

  求解 Z_B1（段①段②分界）：
    解 C(φ)=0 的二次方程，取 [0.2, 0.8] 内的根 φ_B1
    Z_B1 = φ_B1 · (b + φ_B1·hg) / L
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class MBuilderNode(CalculationNode):
    """M 曲线构建（ECE R13 法规下限）"""

    @staticmethod
    def _C(phi, hg, L, b):
        """C(φ) 判断函数（文档 §4）"""
        return hg / L * phi**2 + (b / L - 0.85) * phi + 0.07

    @staticmethod
    def _solve_Z_B1(hg, L, b):
        """解 C(φ)=0 二次方程，返回落在 [0.2, 0.8] 内的根对应的 Z_B1"""
        A = hg / L
        B = b / L - 0.85
        C_coef = 0.07

        disc = B**2 - 4 * A * C_coef
        if disc < 0 or A == 0:
            return 0.0, 0.0

        sqrt_disc = np.sqrt(disc)
        roots = [(-B + sqrt_disc) / (2 * A), (-B - sqrt_disc) / (2 * A)]

        for phi_root in roots:
            if 0.2 <= phi_root <= 0.8:
                Z_B1 = phi_root * (b + phi_root * hg) / L
                return Z_B1, phi_root

        return 0.0, 0.0  # fallback

    def numerical_solve(self, memory_db=None):
        G = self.intermediate_input_values.get("G", 0.0)
        L = self.intermediate_input_values.get("L_m", 1.0)
        b = self.intermediate_input_values.get("b", 0.0)
        hg = self.intermediate_input_values.get("hg", 0.0)

        # 解 C(φ)=0
        Z_B1, phi_B1 = self._solve_Z_B1(hg, L, b)

        # M 曲线构建：φ ∈ [0.2, 0.8]（法规区间）
        phi = np.linspace(0.2, 0.8, 601)

        # C(φ) 数组
        C_array = self._C(phi, hg, L, b)

        # Fμ1^M(φ) = φ · G/L · (b + φ·hg)（前轴与 I 曲线同）
        F_mu1_M = phi * G / L * (b + phi * hg)

        # Fμ2^M(φ)：C≥0 时 0；C<0 时 G·[0.1 + 0.85(φ-0.2)] - Fμ1
        F_mu2_M = np.zeros_like(phi)
        mask = C_array < 0
        F_mu2_M[mask] = G * (0.1 + 0.85 * (phi[mask] - 0.2)) - F_mu1_M[mask]

        self.intermediate_output_values["phi_array"] = phi
        self.intermediate_output_values["F_mu1_M"] = F_mu1_M
        self.intermediate_output_values["F_mu2_M"] = F_mu2_M
        self.intermediate_output_values["C_array"] = C_array
        self.intermediate_output_values["Z_B1"] = Z_B1
        self.intermediate_output_values["phi_B1"] = phi_B1

        return True

    def semantic_solve(self) -> str:
        Z_B1 = self.intermediate_output_values.get("Z_B1", 0.0)
        phi_B1 = self.intermediate_output_values.get("phi_B1", 0.0)

        return (
            f"### MBuilder（M 曲线构建）计算节点分析报告\n"
            f"\n#### 计算结果摘要\n"
            f"- C(φ)=0 的有效根 φ_B1 = {phi_B1:.4f}（落在 [0.2, 0.8] 内）\n"
            f"- 对应制动强度 Z_B1 = {Z_B1:.4f}（前驱段①上限）\n"
            f"- M 曲线：法规 ECE R13 下限边界\n"
            f"  - C(φ) ≥ 0 区间：前轴可独立满足法规，Fμ2^M = 0\n"
            f"  - C(φ) < 0 区间：后轴补足 Fμ2^M 以满足法规\n"
        )

    def generate_visualization(self):
        """返回 M 曲线可视化数据（叠加在 I 曲线上）"""
        phi = self.intermediate_output_values.get("phi_array", np.array([]))
        F_mu1_M = self.intermediate_output_values.get("F_mu1_M", np.array([]))
        F_mu2_M = self.intermediate_output_values.get("F_mu2_M", np.array([]))

        if len(phi) == 0:
            return None

        return {
            "chart_type": "line",
            "title": "M 曲线（ECE R13 法规下限）",
            "x_label": "Fμ1 (N)",
            "y_label": "Fμ2 (N)",
            "series": [
                {"name": "Fμ1^M(φ)", "x": phi.tolist(), "y": F_mu1_M.tolist()},
                {"name": "Fμ2^M(φ)", "x": phi.tolist(), "y": F_mu2_M.tolist()},
            ],
        }
