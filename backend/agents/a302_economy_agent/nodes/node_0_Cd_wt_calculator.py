# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : node_0_Cd_wt_calculator.py
# @Desc    : 风阻系数综合计算器节点
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""风阻系数综合计算器节点

【约定优于配置架构】
此文件只写纯算法逻辑！

- inputs/outputs 定义：node_0_Cd_wt_calculator.yaml （单一真相源）
- 变量自动注册：workflow_ev_ECO.py 在初始化时完成
- 本文件职责：只实现 numerical_solve() 和 semantic_solve() 方法

计算公式：cd_wt = cd_style + cd_cool_air + cd_under_body
"""

from snail_avatar.backend.agents.core.workflow_base import CalculationNode


class CdWtCalculatorNode(CalculationNode):
    """风阻系数综合计算器节点类
    
    最小物理过程0：风阻系数综合计算
    职责：根据造型风阻系数、冷却风阻系数、下车体风阻系数计算风洞测试风阻系数
    """

    def numerical_solve(self, memory_db=None):
        """数值求解器：计算风洞测试风阻系数
        
        计算公式：cd_wt = cd_style + cd_cool_air + cd_under_body
        
        Args:
            memory_db: 内存数据库引用（用于同步 ssts_vts 类型输出到 MemoryCore）
            
        Returns:
            bool: 计算是否成功
        """
        try:
            # =============================================================
            # 读取输入（变量名与YAML完全对应）
            # =============================================================
            cd_style = self.ssts_values.get("cd_style", 0)
            cd_cool_air = self.ssts_values.get("cd_cool_air", 0)
            cd_under_body = self.ssts_values.get("cd_under_body", 0)
            
            # =============================================================
            # 纯算法逻辑
            # =============================================================
            cd_wt = cd_style + cd_cool_air + cd_under_body
            
            # 计算各分量占比
            total = cd_wt if cd_wt != 0 else 1
            cd_wt_stats = {
                "cd_style": float(cd_style),
                "cd_cool_air": float(cd_cool_air),
                "cd_under_body": float(cd_under_body),
                "cd_wt": float(cd_wt),
                "style_ratio_pct": float(cd_style / total * 100),
                "cool_ratio_pct": float(cd_cool_air / total * 100),
                "under_body_ratio_pct": float(cd_under_body / total * 100),
            }
            
            # =============================================================
            # 存储输出（与YAML配置完全对应）
            # =============================================================
            # ssts_vts 类型输出：必须同步写入 MemoryCore，供下游节点读取
            self._sync_ssts_vts_output(memory_db, "cd_wt", float(cd_wt))
            
            # intermediate 类型输出：写入本地缓存
            self.intermediate_output_values["cd_wt"] = cd_wt
            self.intermediate_output_values["cd_wt_stats"] = cd_wt_stats
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status = "error"
            self.error_info = {"type": type(e).__name__, "message": str(e)}
            return False

    def semantic_solve(self) -> str:
        """语义求解器：生成风阻系数分析的自然语言描述
        
        将计算结果转换为自然语言报告，用于 LLM 模型的推理输入。
        
        Returns:
            str: 风阻系数分析的自然语言报告（中文格式）
        """
        stats = self.intermediate_output_values.get("cd_wt_stats", {})
        ssts = self.ssts_values
        
        report = f"""### node_0_Cd_wt_calculator（风阻系数综合计算）计算节点分析报告

#### 计算结果摘要

##### 风阻系数分量
- 造型风阻系数 cd_style：{stats.get('cd_style', 0):.4f}
- 冷却风阻系数 cd_cool_air：{stats.get('cd_cool_air', 0):.4f}
- 下车体风阻系数 cd_under_body：{stats.get('cd_under_body', 0):.4f}

##### 风洞测试风阻系数
- cd_wt：{stats.get('cd_wt', 0):.4f}

##### 分量占比
- 造型风阻占比：{stats.get('style_ratio_pct', 0):.1f}%
- 冷却风阻占比：{stats.get('cool_ratio_pct', 0):.1f}%
- 下车体风阻占比：{stats.get('under_body_ratio_pct', 0):.1f}%

#### 计算逻辑说明

- 输入：cd_style、cd_cool_air、cd_under_body（三个SSTS参数）
- 计算公式：cd_wt = cd_style + cd_cool_air + cd_under_body = {stats.get('cd_style', 0):.4f} + {stats.get('cd_cool_air', 0):.4f} + {stats.get('cd_under_body', 0):.4f} = {stats.get('cd_wt', 0):.4f}
- 输出：cd_wt（VTS参数，写入MemoryCore）

#### 可调参数清单（用于 DOE 分析）

- cd_style: 造型风阻系数, 单位: 无量纲, 当前值: {ssts.get('cd_style', 0):.4f}
- cd_cool_air: 冷却风阻系数, 单位: 无量纲, 当前值: {ssts.get('cd_cool_air', 0):.4f}
- cd_under_body: 下车体风阻系数, 单位: 无量纲, 当前值: {ssts.get('cd_under_body', 0):.4f}

#### 输出参数清单（用于 DOE 的 output_vars）

- cd_wt: 风洞测试风阻系数, 单位: 无量纲, schema_type: ssts_vts"""
        
        self.intermediate_output_values["semantic_summary"] = report
        return report