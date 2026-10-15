# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : vts_compute_agent.py
# @Desc    : VTS 计算注册 + 计算契约基类（继承 LLMConversationAgent）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
VTS 计算注册 + 计算契约基类

继承关系：VTSComputeAgent → LLMConversationAgent

提供标准化的执行接口契约：
  - run_full_calculation(): 执行完整计算流程
  - get_calculation_results(): 获取计算结果摘要

【VTS 计算自动注册机制】
子类只需设置以下类属性，即可被 VTS 计算协调器自动发现和调用：
  - is_vts_agent = True        （声明参与 VTS 计算）
  - vts_category = "动力性"      （计算类别，用于 UI 显示）
  - vts_priority = 10           （执行优先级，数字小的先执行）
"""

from typing import Any

from .llm_conversation_agent import LLMConversationAgent


class VTSComputeAgent(LLMConversationAgent):
    """
    VTS 计算注册 + 计算契约基类（继承 LLMConversationAgent）

    提供标准化的执行接口契约：
    - run_full_calculation(): 执行完整计算流程
    - get_calculation_results(): 获取计算结果摘要

    【VTS 计算自动注册机制】
    子类只需设置以下类属性，即可被 VTS 计算协调器自动发现和调用：
    - is_vts_agent = True        （声明参与 VTS 计算）
    - vts_category = "动力性"      （计算类别，用于 UI 显示）
    - vts_priority = 10           （执行优先级，数字小的先执行）
    """

    # =========================================================================
    # VTS Agent 注册表（类属性，所有子类共享）
    # =========================================================================

    _vts_agent_registry: dict = {}          # key: (priority, category), value: agent_class

    # 子类覆写以下属性以声明为 VTS 计算参与者
    is_vts_agent: bool = False              # 是否参与 VTS 统一计算
    vts_category: str = ""                   # 计算类别，如 "动力性" / "经济性"
    vts_priority: int = 100                  # 执行顺序，数字越小越先执行

    # 计算型 Agent 每次调用前清空历史，确保计算任务独立
    CLEAR_HISTORY_ON_CALL = True

    # =========================================================================
    # 自动注册：子类定义时自动加入注册表
    # =========================================================================

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "is_vts_agent", False):
            key = (cls.vts_priority, cls.vts_category)
            if key not in VTSComputeAgent._vts_agent_registry:
                VTSComputeAgent._vts_agent_registry[key] = cls

    # =========================================================================
    # VTS Agent 发现接口（类方法）
    # =========================================================================

    @classmethod
    def get_vts_agents(cls):
        """
        返回所有已注册的 VTS Agent，按 priority 排序

        Returns:
            List[Tuple[Tuple[int, str], type]]: [((priority, category), agent_class), ...]
        """
        return sorted(cls._vts_agent_registry.items(), key=lambda x: x[0])

    @classmethod
    def clear_vts_registry(cls):
        """清空注册表（主要用于测试）"""
        cls._vts_agent_registry.clear()

    # =========================================================================
    # 计算执行接口（子类必须实现）
    # =========================================================================

    def run_full_calculation(self):
        """执行完整计算流程（子类必须实现）"""
        raise NotImplementedError

    def get_calculation_results(self):
        """获取计算结果摘要（子类必须实现）"""
        raise NotImplementedError
