# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_3_StrategyLine.py
# @Desc    : 最优制动力分配策略线节点（三链路并行：FWD/RWD/AWD 全算）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
最优回收制动力分配策略线节点

设计原则：本节点是通用理论分析模块，同时计算前驱/后驱/四驱三种
         驱动形式的最优回收制动力分配曲线，输出 dict 结构供下游融合。

对应计算方法文档 §5（前驱）、§6（后驱）。AWD 为补充逻辑。
  FWD：4 段分段（纯前轴 → M 曲线 → M→I 过渡 → I 曲线）
  RWD：3 段分段（纯后轴 → 后轴→I 过渡 → I 曲线）
  AWD：沿 I 曲线（前后天然满足法规）

输出结构（风格 A：dict 嵌套 ndarray）：
  strategy_curves = {
      "fwd": {"F_drive": ndarray, "F_front": ndarray, "F_rear": ndarray,
              "segment_id": ndarray, "valid": True},
      "rwd": {...},
      "awd": {...},
  }
"""

import numpy as np
from snail_avatar.backend.agents.core.workflow_base.calc_nodes_base import CalculationNode


class StrategyLineNode(CalculationNode):
    """最优制动力分配策略线（三链路并行）"""

    # =========================================================================
    # 辅助函数：I/M 曲线反查（文档 §3/§4）
    # =========================================================================

    @staticmethod
    def F_M1_I(Z, G, L, b, hg):
        """I 曲线反查前轴制动力（文档 §3）"""
        return Z * G / L * (b + Z * hg)

    @staticmethod
    def F_M1_M(Z, G, L, b, hg):
        """M 曲线反查前轴制动力（文档 §4）
        仅在 C(φ)<0 区间有效。
        """
        phi_M = (Z - 0.1) / 0.85 + 0.2
        return phi_M * G / L * (b + phi_M * hg)

    # =========================================================================
    # 策略线函数（已独立，无需改）
    # =========================================================================

    @classmethod
    def FWD_strategy(cls, Z_arr, G, L, b, hg, Z_B1, Z_C1=0.4, Z_D1=0.7):
        """前驱 4 段最优回收制动力线（文档 §5）"""
        F_mu1_req = np.zeros_like(Z_arr, dtype=float)
        segment_id = np.zeros_like(Z_arr, dtype=int)

        for i, Z in enumerate(Z_arr):
            if Z <= Z_B1:
                # 段①：纯前轴制动
                F_mu1_req[i] = G * Z
                segment_id[i] = 1
            elif Z <= Z_C1:
                # 段②：沿 M 曲线
                F_mu1_req[i] = cls.F_M1_M(Z, G, L, b, hg)
                segment_id[i] = 2
            elif Z <= Z_D1:
                # 段③：M→I 线性过渡
                F_M1_at_C1 = cls.F_M1_M(Z_C1, G, L, b, hg)
                F_M1_at_D1 = cls.F_M1_I(Z_D1, G, L, b, hg)
                F_mu1_req[i] = F_M1_at_C1 + (F_M1_at_D1 - F_M1_at_C1) / (Z_D1 - Z_C1) * (Z - Z_C1)
                segment_id[i] = 3
            else:
                # 段④：沿 I 曲线
                F_mu1_req[i] = cls.F_M1_I(Z, G, L, b, hg)
                segment_id[i] = 4

        F_mu2_req = G * Z_arr - F_mu1_req
        return F_mu1_req, F_mu2_req, segment_id

    @classmethod
    def RWD_strategy(cls, Z_arr, G, L, b, hg, Z_B2=0.1, Z_C2=0.15):
        """后驱 3 段最优回收制动力线（文档 §6）"""
        F_mu1_req = np.zeros_like(Z_arr, dtype=float)
        segment_id = np.zeros_like(Z_arr, dtype=int)

        for i, Z in enumerate(Z_arr):
            if Z <= Z_B2:
                # 段①：纯后轴制动
                F_mu1_req[i] = 0.0
                segment_id[i] = 1
            elif Z <= Z_C2:
                # 段②：纯后轴→I 曲线过渡
                F_M1_at_C2 = cls.F_M1_I(Z_C2, G, L, b, hg)
                F_mu1_req[i] = F_M1_at_C2 * (Z - Z_B2) / (Z_C2 - Z_B2)
                segment_id[i] = 2
            else:
                # 段③：沿 I 曲线
                F_mu1_req[i] = cls.F_M1_I(Z, G, L, b, hg)
                segment_id[i] = 3

        F_mu2_req = G * Z_arr - F_mu1_req
        return F_mu1_req, F_mu2_req, segment_id

    @classmethod
    def AWD_strategy(cls, Z_arr, G, L, b, hg):
        """四驱最优回收制动力线（补充：沿 I 曲线）"""
        F_mu1_req = cls.F_M1_I(Z_arr, G, L, b, hg)   # 直接向量化
        F_mu2_req = G * Z_arr - F_mu1_req
        segment_id = np.ones_like(Z_arr, dtype=int)   # 全部段①
        return F_mu1_req, F_mu2_req, segment_id

    # =========================================================================
    # 主流程（三链路并行，无 drive_type 依赖）
    # =========================================================================

    def numerical_solve(self, memory_db=None):
        G = self.intermediate_input_values.get("G", 0.0)
        L = self.intermediate_input_values.get("L_m", 1.0)
        b = self.intermediate_input_values.get("b", 0.0)
        hg = self.intermediate_input_values.get("hg", 0.0)
        Z_B1 = self.intermediate_input_values.get("Z_B1", 0.0)

        Z_C1 = self.ssts_values.get("Z_C1", 0.4)
        Z_D1 = self.ssts_values.get("Z_D1", 0.7)
        Z_B2 = self.ssts_values.get("Z_B2", 0.1)
        Z_C2 = self.ssts_values.get("Z_C2", 0.15)

        # Z 扫描数组：[0, 0.8]，步长 0.01
        Z_arr = np.round(np.arange(0.0, 0.801, 0.01), 3)

        # --- 三条策略线全并行计算（无 drive_type 分支）---
        sc = {}

        # FWD
        F_mu1_fwd, F_mu2_fwd, seg_fwd = self.FWD_strategy(Z_arr, G, L, b, hg, Z_B1, Z_C1, Z_D1)
        sc["fwd"] = {
            "F_drive": F_mu1_fwd,          # 电驱需求 = 前轴制动力（FWD 只有前轴电驱）
            "F_front": F_mu1_fwd,
            "F_rear": np.zeros_like(Z_arr),
            "segment_id": seg_fwd,
            "valid": True,
        }

        # RWD
        F_mu1_rwd, F_mu2_rwd, seg_rwd = self.RWD_strategy(Z_arr, G, L, b, hg, Z_B2, Z_C2)
        sc["rwd"] = {
            "F_drive": F_mu2_rwd,          # 电驱需求 = 后轴制动力
            "F_front": np.zeros_like(Z_arr),
            "F_rear": F_mu2_rwd,
            "segment_id": seg_rwd,
            "valid": True,
        }

        # AWD
        F_mu1_awd, F_mu2_awd, seg_awd = self.AWD_strategy(Z_arr, G, L, b, hg)
        sc["awd"] = {
            "F_drive": F_mu1_awd + F_mu2_awd,  # 电驱需求 = 前后合计
            "F_front": F_mu1_awd,
            "F_rear": F_mu2_awd,
            "segment_id": seg_awd,
            "valid": True,
        }

        self.intermediate_output_values["Z_array"] = Z_arr
        self.intermediate_output_values["strategy_curves"] = sc

        return True

    def semantic_solve(self) -> str:
        sc = self.intermediate_output_values.get("strategy_curves", {})
        Z = self.intermediate_output_values.get("Z_array", np.array([]))

        if not sc:
            return "### StrategyLine\n\n数据为空。"

        seg_desc = {
            "fwd": {1: "纯前轴", 2: "沿 M 曲线", 3: "M→I 过渡", 4: "沿 I 曲线"},
            "rwd": {1: "纯后轴", 2: "后轴→I 过渡", 3: "沿 I 曲线"},
            "awd": {1: "沿 I 曲线（双轴联合）"},
        }

        lines = [
            "### StrategyLine（最优制动力分配策略线）计算节点分析报告",
            "",
            "#### 计算结果摘要",
            f"- 制动强度扫描区间 Z ∈ [0, 0.8]，共 {len(Z)} 点",
            f"- 同时计算三种驱动形式的策略曲线（理论对比）",
            "",
            "#### 三种驱动形式分段对比",
        ]

        for drive in ["fwd", "rwd", "awd"]:
            entry = sc.get(drive, {})
            seg = entry.get("segment_id", np.array([]))
            valid = entry.get("valid", False)
            tag = "✓" if valid else "✗ invalid"
            lines.append(f"")
            lines.append(f"**{drive.upper()}** {tag}")
            if len(seg) > 0:
                unique_segs = sorted(set(seg.tolist()))
                for s in unique_segs:
                    desc = seg_desc.get(drive, {}).get(s, "?")
                    lines.append(f"  - 段{s}: {desc}")

        return "\n".join(lines)

    def generate_visualization(self):
        """返回策略线可视化数据：三条驱动形式的需求合计 + 分轴"""
        Z = self.intermediate_output_values.get("Z_array", np.array([]))
        sc = self.intermediate_output_values.get("strategy_curves", {})

        if len(Z) == 0 or not sc:
            return None

        series = []
        colors = {"fwd": "#e74c3c", "rwd": "#3498db", "awd": "#2ecc71"}

        for drive in ["fwd", "rwd", "awd"]:
            entry = sc.get(drive, {})
            if not entry.get("valid"):
                continue
            F = entry.get("F_drive", np.array([]))
            if len(F) > 0:
                series.append({
                    "name": f"{drive.upper()} 电驱需求合计",
                    "x": Z.tolist(), "y": F.tolist(),
                    "color": colors.get(drive),
                })

        return {
            "chart_type": "line",
            "title": "最优回收制动力分配策略线（FWD vs RWD vs AWD）",
            "x_label": "制动强度 Z",
            "y_label": "需求制动力 (N)",
            "series": series,
        }
