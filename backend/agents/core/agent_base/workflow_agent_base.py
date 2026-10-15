# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_agent_base.py
# @Desc    : 工作流计算型 Agent 基类（统一经济性、动力性等基于工作流的 Agent）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
工作流计算型 Agent 基类

统一所有基于工作流（workflow）引擎的计算型 Agent（经济性、动力性、操稳性等）。

继承关系：
    WorkflowAgentBase  ->  VTSComputeAgent  ->  LLMConversationAgent

子类只需做 3 件事：
    1. 设置类属性（vts_category, vts_priority, AGENT_DISPLAY_NAME 等）
    2. 实现 get_workflow_config() 方法，返回工作流构建所需的参数
    3. 在同目录下创建 functions/ 目录（工具自动扫描注册）

典型用法示例（经济性 Agent）：

    class EconomyAgent(WorkflowAgentBase):
        is_vts_agent = True
        vts_category = "经济性"
        vts_priority = 20
        AGENT_DISPLAY_NAME = "经济性计算与分析专家"

        def get_workflow_config(self):
            return {
                "nodes_pkg_path": "snail_avatar.backend.agents.a302_economy_agent.nodes",
                "vehicle_info_field": "能源形式",
                "vehicle_info_default": "ev",
                "yaml_pattern": "workflow_*.yaml",
                "yaml_match_fn": lambda cfg, v: (
                    cfg.get("calculation_type") == "economy"
                    and cfg.get("energy_type") == v
                ),
                "default_yaml_filename": "workflow_ev_ECO.yaml",
                "node_id_from_yaml_fn": (
                    lambda fn: "_".join(os.path.splitext(fn)[0].split("_")[:2])
                ),
                "node_id_from_topology_fn": (
                    lambda nid: "_".join(nid.split("_")[:2])
                ),
                "use_yaml_position": True,
            }
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from snail_avatar.backend.agents.core.agent_base.vts_compute_agent import VTSComputeAgent
from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger


class WorkflowAgentBase(VTSComputeAgent):
    """工作流计算型 Agent 基类

    统一管理：
    1. VTS 计算自动注册（is_vts_agent, vts_category, vts_priority）
    2. 工作流懒加载与缓存
    3. 计算接口标准化（run_full_calculation, get_calculation_results）
    4. memory_db 懒注入
    5. send_message 标准实现（function calling 循环）
    """

    # ================================================================
    # 子类必须覆盖的类属性（VTS 计算自动注册）
    # ================================================================

    # 是否参与 VTS 统一计算（默认为 True，所有工作流型 Agent 都应参与）
    is_vts_agent: bool = True

    # 计算类别名称（用于 UI 显示，如 "经济性"、"动力性"）
    vts_category: str = ""

    # 执行优先级（数字越小越先执行，如 10-动力性, 20-经济性）
    vts_priority: int = 100

    # 【核心】面板标识，用于 workflow_registry 匹配 registry 条目
    # 可以是 workflow_id（EV_ECO_CALC）、category（economy）或 panel_id（eco）
    panel_id: str = ""

    # function calling 循环的最大轮数
    MAX_TOOL_ROUNDS: int = 8

    # 是否需要 memory_db（工作流型 Agent 都需要）
    NEEDS_MEMORY_DB: bool = True

    # ================================================================
    # 子类必须实现的方法
    # ================================================================

    def get_workflow_config(self) -> Dict[str, Any]:
        """返回工作流构建所需的配置参数

        返回的字典将传递给 build_workflow_from_yaml() 函数。
        必须包含以下键：
            - nodes_pkg_path: 节点 Python 包路径（如 "snail_avatar.backend.agents.a302_economy_agent.nodes"）
            - vehicle_info_field: 车型信息字段名（如 "能源形式"、"驱动形式"）
            - vehicle_info_default: 车型信息默认值（如 "ev"、"rwd"）
            - yaml_pattern: 工作流 YAML 文件匹配模式（如 "workflow_*.yaml"）
            - yaml_match_fn: 工作流匹配函数（lambda config, value -> bool）
            - default_yaml_filename: 默认工作流 YAML 文件名
            - node_id_from_yaml_fn: 从 YAML 文件名解析 node_id 的函数
            - node_id_from_topology_fn: 从拓扑节点 ID 解析 node_id 的函数
            - use_yaml_position: 是否使用 YAML 中的 position 信息排序节点

        可选键：
            - node_id_from_module_fn: 从模块名解析 node_id 的函数（如 power_agent 需要）
            - vehicle_lower: 是否将车型信息转为小写（默认 False）
            - agent_display_name: 对话中显示的名称（优先于类属性 AGENT_DISPLAY_NAME）
        """
        raise NotImplementedError("子类必须实现 get_workflow_config() 方法")

    # ================================================================
    # 初始化
    # ================================================================

    def __init__(
        self,
        memory_db: Optional[Any] = None,
        vehicle_suffix: str = "",
        agent_dir: Optional[str] = None,
        yaml_filename: Optional[str] = None,
        create_registry_fn: Optional[Callable] = None,
    ) -> None:
        """初始化工作流计算型 Agent

        Args:
            memory_db: MemoryDatabase 实例（可选，后续懒注入）
            vehicle_suffix: 车型后缀（可选，用于指定工作流）
            agent_dir: Agent目录路径（可选，配置驱动时传入）
            yaml_filename: YAML配置文件名（可选，配置驱动时传入）
            create_registry_fn: 工具注册函数（可选，配置驱动时传入）
        """
        # 获取工作流配置（用于确定 agent 目录和 YAML 文件名）
        self._wf_config = self.get_workflow_config()

        # 确定 agent 目录（优先使用传入参数，否则基于当前子类文件所在目录）
        if agent_dir is not None:
            agent_dir = agent_dir
        else:
            import inspect
            try:
                agent_dir = os.path.dirname(os.path.abspath(inspect.getfile(self.__class__)))
            except Exception:
                agent_dir = os.path.dirname(os.path.abspath(__file__))

        # 确定 YAML 文件名（优先使用传入参数，否则从配置或默认）
        if yaml_filename is not None:
            yaml_filename = yaml_filename
        else:
            yaml_filename = self._wf_config.get(
                "yaml_filename",
                f"{self.vts_category}_agent.yaml" if self.vts_category else "agent.yaml",
            )

        # 使用传入的 create_registry_fn，或动态导入 functions 模块
        if create_registry_fn is not None:
            _create_registry_fn = create_registry_fn
        else:
            # 动态导入 functions 模块并调用 create_default_registry() 生成注册中心实例。
            # LLMConversationAgent.__init__ 会将 create_registry_fn 作为参数传入，
            # 并在内部调用 create_registry_fn() 获取 FunctionRegistry 实例。
            def _create_registry_fn() -> Any:
                try:
                    import importlib
                    # 从类的完整模块路径中去掉最后一级（文件名），取父包路径
                    # 例如："snail_avatar.backend.agents.a302_economy_agent.economy_analyse_agent"
                    #   → "snail_avatar.backend.agents.a302_economy_agent"
                    module_parts = self.__class__.__module__.split(".")
                    if len(module_parts) > 1:
                        package_path = ".".join(module_parts[:-1])
                    else:
                        # 特殊情况：模块名没有点（如直接在顶层运行）
                        package_path = self.__class__.__module__
                    mod_name = f"{package_path}.functions"
                    mod = importlib.import_module(mod_name)
                    create_fn = getattr(mod, "create_default_registry")
                    # 调用 create_default_registry() 返回 FunctionRegistry 实例
                    return create_fn()
                except Exception as e:
                    AgentMessageLogger.log(
                        "system", "workflow_agent",
                        f"[{self.__class__.__name__}] 无法导入 functions 模块: {e}"
                    )
                    # 兜底：返回一个空的 FunctionRegistry 实例
                    from snail_avatar.backend.agents.core.public_functions_core.function_base import FunctionRegistry
                    return FunctionRegistry()

        # 调用基类初始化
        super().__init__(
            agent_dir=agent_dir,
            yaml_filename=yaml_filename,
            create_registry_fn=_create_registry_fn,
            memory_db=memory_db,
            vehicle_suffix=vehicle_suffix,
        )

    # ================================================================
    # _extra_init: 工作流懒加载初始化（覆写 LLMConversationAgent._extra_init）
    # ================================================================

    def _extra_init(self) -> None:
        """Agent 专属初始化：设置工作流懒加载状态"""
        self._workflow: Optional[Any] = None
        self._workflow_cache: Dict[str, Any] = {}

    # ================================================================
    # 工作流懒加载与缓存
    # ================================================================

    @property
    def workflow(self) -> Any:
        """使用通用工厂函数懒加载工作流

        优先使用当前 vehicle_suffix 的工作流。
        """
        return self.get_workflow_for_vehicle(self._vehicle_suffix)

    def get_workflow_for_vehicle(self, vehicle_suffix: str = "") -> Any:
        """
        从共享层 workflow_registry 构建工作流实例

        【设计原则】
        1. **统一来源**：所有路径（agent / FastAPI / flet）都走 workflow_registry.build_workflow()
        2. **本地缓存**：构建成功后缓存到 self._workflow_cache，避免重复解析 YAML
        3. **无 flet 依赖**：纯 YAML + memory_db → build_workflow_from_yaml_file

        【调用流程】
        Step 1: 检查 self._workflow_cache 缓存 → 命中直接返回
        Step 2: 验证 self.panel_id 已设置 → 未设置返回 None
        Step 3: workflow_registry.build_workflow(panel_id, suffix, db)
        Step 4: 缓存并返回

        Args:
            vehicle_suffix: 车型后缀（如 "evlto"、"reevlto"）

        Returns:
            workflow 实例 | None: 无法获取时返回 None（调用方应处理此情况并提示）
        """
        cache_key = vehicle_suffix or "default"

        # === Step 1: 已有缓存，直接返回 ===
        if cache_key in self._workflow_cache:
            return self._workflow_cache[cache_key]

        # === Step 2: 验证 panel_id 设置 ===
        if not self.panel_id:
            print(f"[ERROR][WorkflowAgentBase] {self.__class__.__name__} 未设置 panel_id，无法获取工作流")
            return None

        # === Step 3: 从共享层 workflow_registry 构建 ===
        try:
            from snail_avatar.backend.agents.core.workflow_base.workflow_registry import build_workflow
        except Exception as e:
            print(f"[WorkflowAgentBase] workflow_registry.build_workflow 导入失败: {e}")
            return None

        db = getattr(self, "_memory_db", None)
        if db is None:
            try:
                from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
                db = get_memory_db()
            except Exception:
                pass
        if db is None:
            print("[WorkflowAgentBase] memory_db 为空，无法构建 workflow")
            return None

        wf = build_workflow(self.panel_id, vehicle_suffix, db)
        if wf is not None:
            self._workflow_cache[cache_key] = wf
            print(f"[WorkflowAgentBase] 构建工作流成功: panel={self.panel_id}, suffix={vehicle_suffix}")
        else:
            print(f"[ERROR][WorkflowAgentBase] 构建工作流失败: panel={self.panel_id}, suffix={vehicle_suffix}")
        return wf

    def clear_workflow_cache(self) -> None:
        """清空工作流缓存（当数据库或车型信息变化时调用）"""
        self._workflow_cache.clear()
        self._workflow = None

    # ================================================================
    # 关键计算结果提取（子类可覆写）
    # ================================================================

    def _get_key_results(self, topology_config: Any, graph: Any) -> List[Dict[str, Any]]:
        """从工作流拓扑配置中提取关键计算结果

        默认实现：从 topology_config 的 key_results 字段提取。
        子类可根据需要覆写以自定义提取逻辑。

        Args:
            topology_config: 工作流 YAML 配置
            graph: 工作流图对象

        Returns:
            关键计算结果列表，每个元素包含 variable、node_id、value 等信息
        """
        results: List[Dict[str, Any]] = []

        key_results_config = topology_config.get("key_results", []) if isinstance(topology_config, dict) else []

        for result_config in key_results_config:
            node_id = result_config.get("node_id", "")
            variable = result_config.get("variable", "")

            value = None
            if graph is not None and hasattr(graph, "nodes"):
                node = graph.nodes.get(node_id)
                if node and hasattr(node, "node_instance"):
                    output_values = getattr(node.node_instance, "output_values", None)
                    if output_values is not None:
                        value = output_values.get(variable)

            result_item: Dict[str, Any] = {**result_config, "value": value}
            results.append(result_item)

        return results

    # ================================================================
    # VTS 计算接口
    # ================================================================

    def run_full_calculation(self) -> Dict[str, Any]:
        """执行完整计算流程

        Returns:
            计算结果字典，包含 success、result、message 等字段
        """
        try:
            wf = self.workflow
            if wf is None:
                return {
                    "success": False,
                    "error": "无法加载工作流实例",
                    "message": f"{self.vts_category}计算失败：无法加载工作流",
                }

            result = wf.run_all()
            return {
                "success": True,
                "result": result,
                "message": f"{self.vts_category}计算完成",
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "message": f"{self.vts_category}计算失败: {e}",
            }

    def get_calculation_results(self) -> Dict[str, Any]:
        """获取计算结果摘要

        Returns:
            计算结果摘要字典
        """
        try:
            wf = self.workflow
            if wf is not None and hasattr(wf, "get_key_results"):
                key_results = wf.get_key_results()
                indicators = {}
                for result in key_results:
                    var_name = result.get("variable")
                    value = result.get("value")
                    if var_name is not None:
                        indicators[var_name] = value

                return {
                    "status": "completed",
                    "message": f"{self.vts_category}计算完成",
                    "key_results": key_results,
                    "indicators": indicators,
                }

            return {
                "status": "completed",
                "message": "计算结果获取功能待实现",
            }
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": f"获取计算结果失败: {e}",
                "traceback": traceback.format_exc(),
            }

    # ================================================================
    # 快捷方法（与旧接口保持兼容）
    # ================================================================

    def run_all(self) -> Dict[str, Any]:
        """快捷方法：直接执行全流程计算"""
        return self.run_full_calculation()

    def get_summary(self) -> Dict[str, Any]:
        """快捷方法：获取计算结果摘要"""
        return self.get_calculation_results()

    # ================================================================
    # UI 面板创建（子类可覆写，从同目录 ui/ 子目录加载）
    # ================================================================

    def create_panel(self) -> Optional[Any]:
        """创建诊断 UI 面板

        默认实现：尝试从同目录下的 ui/ 子目录加载 panel 模块。
        模块文件名和类名由子类决定，默认查找 ui/{category}_panel.py

        Returns:
            UI 面板实例，或 None（如果未找到面板）
        """
        try:
            import os
            import importlib
            import inspect

            agent_dir = os.path.dirname(os.path.abspath(inspect.getfile(self.__class__)))
            ui_dir = os.path.join(agent_dir, "ui")

            # 尝试查找面板文件：优先从 get_workflow_config 的 panel_filename
            cfg = getattr(self, "_wf_config", {})
            panel_filename = cfg.get("panel_filename")

            if panel_filename is None:
                # 根据 vts_category 推断面板文件名
                category_lower = self.vts_category.lower() if self.vts_category else ""
                if "经济" in category_lower:
                    panel_filename = "eco_panel.py"
                elif "动力" in category_lower:
                    panel_filename = "power_panel.py"
                else:
                    panel_filename = f"{category_lower}_panel.py"

            panel_path = os.path.join(ui_dir, panel_filename)

            if not os.path.exists(panel_path):
                return None

            # 动态导入面板模块
            mod_name = f"{self.__class__.__module__}.ui.{os.path.splitext(panel_filename)[0]}"
            try:
                ui_mod = importlib.import_module(mod_name)
            except ImportError:
                # 尝试用 spec 导入
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    f"_panel_{id(self)}", panel_path
                )
                if spec is None or spec.loader is None:
                    return None
                ui_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ui_mod)

            # 查找 Panel 类（常见命名模式）
            class_names_to_try = [
                "Panel",
                f"{self.vts_category}Panel",
                f"{self.__class__.__name__.replace('Agent', 'Panel')}",
            ]

            for cls_name in class_names_to_try:
                if hasattr(ui_mod, cls_name):
                    panel_cls = getattr(ui_mod, cls_name)
                    if isinstance(panel_cls, type):
                        return panel_cls()

            # 兜底：尝试创建模块中第一个类的实例
            for name in dir(ui_mod):
                item = getattr(ui_mod, name)
                if isinstance(item, type) and not name.startswith("_"):
                    try:
                        return item()
                    except Exception:
                        continue

            return None

        except Exception as e:
            AgentMessageLogger.log(
                "system", "workflow_agent",
                f"[{self.__class__.__name__}] 创建面板失败: {e}"
            )
            return None
