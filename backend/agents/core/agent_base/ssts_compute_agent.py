# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : ssts_compute_agent.py
# @Desc    : SSTS 计算 Agent 基类（重写原残留桩类，Phase 1 基础框架）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
SSTS 计算 Agent 基类（重写原残留桩类）

继承关系：SSTSWorkflowAgentBase → WorkflowAgentBase → VTSComputeAgent → LLMConversationAgent

在 WorkflowAgentBase 基础上叠加 SSTS 能力：
1. SSTSSandbox — 局部沙箱（隔离 + 只读桥接 + commit 回写）
2. 文件夹参数自动识别与加载 — 根据 memory_db.file_path 自动关联项目文件夹
3. 可视化结果收集 — 从节点 generate_visualization() 收集图表数据

自动注册机制（镜像 VTSComputeAgent）：
  - is_ssts_agent = True
  - ssts_category = "能量回收"
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from snail_avatar.backend.core.work_log import WorkLogger
from snail_avatar.backend.agents.core.workflow_base.ssts_sandbox import SSTSSandbox
from snail_avatar.backend.agents.core.agent_base.workflow_agent_base import WorkflowAgentBase


class SSTSWorkflowAgentBase(WorkflowAgentBase):
    """SSTS 计算 Agent 基类（重写原残留桩类）

    在 WorkflowAgentBase 基础上叠加 3 项 SSTS 能力：
    1. SSTSSandbox — 局部沙箱（隔离 + 只读桥接 + commit 回写）
    2. 文件夹参数读取 — load_from_folder()
    3. 可视化结果收集 — visualization_results
    """

    # =========================================================================
    # SSTS 自动注册（镜像 VTSComputeAgent 的 __init_subclass__ 模式）
    # =========================================================================

    _ssts_agent_registry: Dict[str, type] = {}     # key: ssts_category, value: agent_class

    # 子类覆写以下属性以声明为 SSTS 计算参与者
    is_ssts_agent: bool = False                     # 是否参与 SSTS 计算
    ssts_category: str = ""                         # SSTS 类别，如 "能量回收"
    is_vts_agent: bool = False                      # 默认不参与 VTS 统一计算（可选覆写）

    # SSTS 专属配置（子类覆写或从 YAML 读取）
    sandbox_config: Dict[str, Any] = {
        "load_paths": [],                            # 文件夹加载路径过滤（glob patterns）
        "auto_detect": True,                         # 是否自动检测项目文件夹
    }

    # =========================================================================
    # __init_subclass__ 自动注册
    # =========================================================================

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "is_ssts_agent", False):
            key = cls.ssts_category
            if key and key not in SSTSWorkflowAgentBase._ssts_agent_registry:
                SSTSWorkflowAgentBase._ssts_agent_registry[key] = cls

    # =========================================================================
    # SSTS Agent 发现接口（类方法）
    # =========================================================================

    @classmethod
    def get_ssts_agents(cls):
        """返回所有已注册的 SSTS Agent"""
        return list(cls._ssts_agent_registry.items())

    @classmethod
    def clear_ssts_registry(cls):
        """清空注册表（主要用于测试）"""
        cls._ssts_agent_registry.clear()

    # =========================================================================
    # 初始化覆写
    # =========================================================================

    def _extra_init(self) -> None:
        """
        SSTS Agent 专属初始化

        执行顺序：
        1. super()._extra_init() → WorkflowAgentBase 创建 _workflow_cache
        2. 创建 SSTSSandbox(global_db=self._memory_db) 实例
        3. 调用 _auto_detect_project_folder() → 自动识别项目文件夹 + 加载零部件参数
        4. 记录已关联的 file_path，后续调用时若 memory_db.file_path 变化则自动重建 sandbox
        """
        # Step 1: 调用父类
        super()._extra_init()

        # Step 2: 创建沙箱实例
        self.sandbox = SSTSSandbox(global_db=self._memory_db)
        self._last_associated_file_path: Optional[str] = None  # 上次关联的 Excel 文件路径

        # Step 3: 尝试自动检测并加载
        if self.sandbox_config.get("auto_detect", True):
            self._try_auto_load_sandbox()

        WorkLogger.info(
            f"[SSTSWorkflowAgentBase] {self.__class__.__name__} 初始化完成, "
            f"is_ready={self.is_ready()}"
        )

    # =========================================================================
    # 公开接口
    # =========================================================================

    def get_sandbox(self) -> SSTSSandbox:
        """获取沙箱实例"""
        return self.sandbox

    def reload_sandbox(self, folder_path: Optional[str] = None) -> int:
        """
        重新加载文件夹参数

        Args:
            folder_path: 指定文件夹路径（None 时自动重新识别）

        Returns:
            成功加载的文件数
        """
        self.sandbox.clear()
        if folder_path:
            self.sandbox.project_folder = folder_path
        else:
            folder_path = self._auto_detect_project_folder(self._memory_db)
            if folder_path:
                self._match_vehicle_subfolder_and_load(folder_path)
                return self.sandbox.loaded_file_count
            else:
                WorkLogger.warn(f"[SSTSWorkflowAgentBase] reload_sandbox: 未找到项目文件夹")
                return 0

        # 手动指定路径
        filter_patterns = self.sandbox_config.get("load_paths") or None
        count = self.sandbox.load_from_folder(folder_path, filter_patterns)
        return count

    def commit_sandbox_to_global(self, param_type: str = "result") -> int:
        """
        将沙箱中标记的参数写回全局 MemoryDatabase

        Args:
            param_type: db_key 的 type 段（默认 "result"）

        Returns:
            成功写回的参数数量
        """
        return self.sandbox.commit(param_type=param_type)

    def get_visualization_results(self) -> Dict[str, Any]:
        """
        获取最新计算的可视化结果

        从最近一次 WorkflowExecutor 执行的结果中收集。
        首次调用或尚未执行计算时返回空字典。
        """
        return getattr(self, "_visualization_results_cache", {})

    def is_ready(self) -> bool:
        """
        SSTS agent 是否已准备好工作

        判断条件：
        1. memory_db 存在（通过 self._memory_db 或 get_memory_db() 检查）
        2. sandbox 已关联项目文件夹（或加载了参数）
        """
        # 检查 memory_db
        memory_db = self._memory_db
        if memory_db is None:
            try:
                from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
                memory_db = get_memory_db()
            except Exception:
                pass
        if memory_db is None:
            return False

        # 检查沙箱（允许空沙箱工作，只要 memory_db 就绪）
        return True

    def get_project_info(self) -> Dict[str, Any]:
        """返回当前关联的项目信息"""
        return self.sandbox.snapshot()

    # =========================================================================
    # 自动检测 + 加载（薄封装：核心逻辑已下沉到 SSTSSandbox.auto_load_for_agent）
    # =========================================================================

    def _try_auto_load_sandbox(self) -> None:
        """
        尝试自动加载项目文件夹到沙箱

        懒加载策略：检查 memory_db 是否就绪 + file_path 是否有变化
        核心索引逻辑全在 sandbox.auto_load_for_agent（agent 路径和 HTTP 路径共用）
        """
        memory_db = self._memory_db
        if memory_db is None:
            try:
                from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
                memory_db = get_memory_db()
            except Exception:
                pass

        if memory_db is None:
            return

        current_file_path = getattr(memory_db, "file_path", None)
        if current_file_path and current_file_path != self._last_associated_file_path:
            # 核心逻辑：sandbox.auto_load_for_agent 内部做项目根检测 + 后缀匹配 + 逐个加载
            self.sandbox.auto_load_for_agent(self.sandbox_config, memory_db)
            self._last_associated_file_path = current_file_path

    def get_sandbox_snapshot(self) -> dict:
        """返回沙箱当前状态的快照（UI / LLM 工具调用）"""
        return self.sandbox.snapshot()
