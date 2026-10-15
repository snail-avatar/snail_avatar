# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : process_context.py
# @Desc    : 流程执行上下文 - 配置驱动的轻量级流程执行器
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程执行上下文

轻量级流程执行器，不继承 LLMConversationAgent。
通过 process.yaml 配置驱动，提供 ProcessEngine 需要的所有回调和公共接口。

职责：
1. 加载 process.yaml 并初始化 ProcessEngine
2. 管理多实例状态隔离（_controllers / _execution_states / _snapshots）
3. 提供 ProcessEngine 需要的回调方法
4. 提供公共接口供 UI 层调用

使用方式：
    ctx = ProcessContext(agent_dir="/path/to/agent", memory_db=db)
    result = ctx.run_flow(instance_key="reevlto", mode="ALL")
"""

from __future__ import annotations

import os
import copy
from typing import Any, Dict, Type, List, Tuple, Optional, Callable

from snail_avatar.backend.agents.core.process_executor import ProcessEngine, ProcessController
from snail_avatar.backend.agents.core.process_executor.utils.context_provider import YamlContextProvider


class ProcessContext:
    """流程执行上下文 — 配置驱动的轻量级流程执行器

    不继承 LLMConversationAgent，仅提供 ProcessEngine 需要的回调和公共接口。
    LLM 调用由 LLMStep 通过 LLMDeploy 自行创建，不需要本类提供 chat() 方法。

    实例缓存：按 agent_dir + memory_db 唯一标识缓存实例，同一 agent 目录和
    同一 memory_db 组合只会创建一次 ProcessContext。panel 和 function 调用
    会共享同一个实例，从而共享 _controllers / _execution_states / _step_results。
    """

    # 流程定义文件名（位于 agent 目录下的 config/ 子目录）
    PROCESS_YAML_FILENAME = "process.yaml"

    # 类级别实例缓存：key = "{agent_dir}#{id(memory_db)}"
    _context_cache: Dict[str, "ProcessContext"] = {}

    # 类级别全局回调集合：instance_key="" 时注册的 callback
    # 会在每次 _get_controller 创建新 controller 时自动同步进去
    # 解决问题：Panel 在 function_run_flow 创建 controller 之前就注册了全局 callback，
    # 但 add_progress_callback 只遍历现有 controller，导致新建的 controller 没有这个 callback。
    _global_callbacks: set = set()

    def __new__(cls, agent_dir: str, memory_db=None):
        # 缓存 key 只用 agent_dir
        # 注意：memory_db 不参与缓存 key——ProcessContext 的核心职责是加载
        # process.yaml 和管理 controllers/execution_states，而 memory_db 只是
        # 存储在 self._memory_db 供后续 step 使用。不同入口（panel vs function）
        # 可能通过不同方式获取到不同的 memory_db 对象 id，但它们指向同一份数据。
        # 如果把 memory_db id 纳入缓存 key，会导致 panel 创建的 ctx 和 function
        # 创建的 ctx 不共享，从而 function 执行后 panel 看不到结果。
        key = agent_dir

        # 命中缓存直接返回已有实例（__init__ 会被跳过，见下方逻辑）
        if key in cls._context_cache:
            return cls._context_cache[key]

        # 未命中：创建新实例并预注册到缓存
        instance = super().__new__(cls)
        cls._context_cache[key] = instance
        return instance

    def __init__(self, agent_dir: str, memory_db=None):
        """初始化流程执行上下文

        注意：__new__ 可能返回缓存中的已有实例，此时 __init__ 仍会被 Python 调用。
        已初始化的实例会跳过 process.yaml / workflow_engine 等重型初始化，
        但会更新 memory_db（以防新传入的 memory_db 更完整）。

        Args:
            agent_dir: Agent 所在目录（包含 config/process.yaml）
            memory_db: MemoryCore 数据库实例
        """
        # 如果是缓存命中的已有实例（_agent_dir 已在之前 __init__ 中设置过），
        # 跳过重型初始化，只更新 memory_db（如果新值有意义）
        if hasattr(self, '_agent_dir'):
            if memory_db is not None and self._memory_db is None:
                self._memory_db = memory_db
            return

        self._agent_dir = agent_dir
        self._memory_db = memory_db

        # 多实例状态隔离容器
        self._controllers: Dict[str, ProcessController] = {}
        self._execution_states: Dict[str, Dict[str, Any]] = {}
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        # 上下文提供者（从 process.yaml 的 context_vars 配置加载）
        self._context_provider: Optional[YamlContextProvider] = None

        # 加载 process.yaml 并初始化流程引擎
        process_yaml_path = os.path.join(agent_dir, "config", self.PROCESS_YAML_FILENAME)
        self._workflow_engine: ProcessEngine = ProcessEngine(process_yaml_path)

        # 读取参数构建配置（args_config 段，业务参数名映射）
        self._args_config: Dict[str, Any] = self._workflow_engine.workflow.raw.get('args_config', {})

        # 缓存外层和内层步骤列表
        self._outer_steps_cache: List[Tuple[str, str]] = self._workflow_engine.get_outer_steps()
        self._inner_steps_cache: List[Tuple[str, str]] = self._workflow_engine.get_inner_steps()

        # 加载上下文词汇表
        self._init_context_provider()

    # ==================================================================
    # 步骤属性访问器
    # ==================================================================

    @property
    def OUTER_STEPS(self) -> List[Tuple[str, str]]:
        """外层步骤列表"""
        return self._outer_steps_cache

    @property
    def INNER_STEPS(self) -> List[Tuple[str, str]]:
        """内层步骤列表"""
        return self._inner_steps_cache

    @property
    def LOOP_STEP_IDS(self) -> List[str]:
        """所有循环步骤ID列表"""
        return self._workflow_engine.get_all_loop_ids()

    @property
    def CONDITIONAL_OPTIONAL_MAP(self) -> Dict[str, str]:
        """条件可选步骤映射: step_id -> 依赖的 condition step_id

        条件可选步骤只在对应 condition 的 condition_result=False 时才执行。
        UI 层可据此根据条件结果动态隐藏/显示进度条中的步骤。
        """
        return self._workflow_engine.get_conditional_optional_map()

    @property
    def workflow_engine(self) -> ProcessEngine:
        """流程引擎实例"""
        return self._workflow_engine

    def is_stopped(self) -> bool:
        """检查流程是否已停止（用于重试逻辑中的停止命令响应）"""
        return self._workflow_engine.is_stopped()

    # ==================================================================
    # 执行状态管理
    # ==================================================================

    def _create_initial_execution_state(self) -> Dict[str, Any]:
        """创建初始执行状态

        支持多循环节点串行排列，每个循环节点独立管理状态。
        """
        return {
            "stage": "INIT",
            "mode": "ALL",
            "instance_attrs": {},
            "condition_results": {},
            # 各循环节点的状态
            "loop_nodes": {
                # "loop_categories": {
                #     "items": ["V_BSG", "V_EPS", ...],
                #     "current_index": 0,
                #     "completed": False,
                #     "results": [...]
                # }
            },
            # 当前活动的循环节点ID
            "current_loop_node": None,
        }

    def _get_execution_state(self, instance_key: str) -> Dict[str, Any]:
        """获取指定实例的执行状态（不存在则创建初始状态）"""
        if instance_key not in self._execution_states:
            self._execution_states[instance_key] = self._create_initial_execution_state()
        return self._execution_states[instance_key]

    def get_execution_state(self, instance_key: str) -> Dict[str, Any]:
        """获取指定实例的执行状态（对外接口）"""
        return self._get_execution_state(instance_key)

    def reset_execution_state(self, instance_key: str) -> None:
        """重置指定实例的执行状态（从头开始执行，清空沙箱）"""
        self._execution_states[instance_key] = self._create_initial_execution_state()
        # 同时重置控制器的状态和沙箱
        if instance_key in self._controllers:
            controller = self._controllers[instance_key]
            if hasattr(controller, 'reset'):
                controller.reset()

    # ==================================================================
    # 循环节点状态管理
    # ==================================================================

    def _get_loop_node_state(self, instance_key: str, node_id: str) -> Dict[str, Any]:
        """获取循环节点状态（不存在则创建）"""
        state = self._get_execution_state(instance_key)
        if node_id not in state["loop_nodes"]:
            state["loop_nodes"][node_id] = {
                "items": [],
                "current_index": 0,
                "completed": False,
                "results": []
            }
        return state["loop_nodes"][node_id]

    def set_loop_items(self, instance_key: str, node_id: str, items: List[Any]) -> None:
        """设置循环项列表"""
        node_state = self._get_loop_node_state(instance_key, node_id)
        node_state["items"] = items
        node_state["current_index"] = 0
        node_state["completed"] = False

    def get_current_loop_item(self, instance_key: str, node_id: str) -> Any:
        """获取当前循环项"""
        node_state = self._get_loop_node_state(instance_key, node_id)
        if node_state["current_index"] < len(node_state["items"]):
            return node_state["items"][node_state["current_index"]]
        return None

    def advance_loop(self, instance_key: str, node_id: str) -> bool:
        """推进循环索引

        Returns:
            bool: True 表示还有下一项，False 表示循环已完成
        """
        node_state = self._get_loop_node_state(instance_key, node_id)
        node_state["current_index"] += 1
        if node_state["current_index"] >= len(node_state["items"]):
            node_state["completed"] = True
            return False
        return True

    def is_loop_completed(self, instance_key: str, node_id: str) -> bool:
        """检查循环是否完成"""
        node_state = self._get_loop_node_state(instance_key, node_id)
        return node_state["completed"]

    def get_loop_progress(self, instance_key: str, node_id: str) -> Dict[str, Any]:
        """获取循环进度"""
        node_state = self._get_loop_node_state(instance_key, node_id)
        total = len(node_state["items"])
        current = node_state["current_index"]
        return {
            "node_id": node_id,
            "total": total,
            "current": current,
            "progress": f"{current}/{total}" if total > 0 else "0/0",
            "is_completed": node_state["completed"]
        }

    # ==================================================================
    # ProcessController 管理
    # ==================================================================

    def _init_context_provider(self) -> None:
        """从 process.yaml 加载 context_vars 并初始化上下文提供者"""
        try:
            vocab_config = self._workflow_engine.workflow.raw.get('context_vars', {})
            if vocab_config:
                self._context_provider = YamlContextProvider(vocab_config, self)
        except Exception:
            self._context_provider = None

    def _get_controller(self, instance_key: str) -> ProcessController:
        """获取指定实例的 ProcessController（不存在则创建并配置）"""
        if instance_key not in self._controllers:
            controller = ProcessController(context_provider=self._context_provider)
            self._workflow_engine.configure_controller(controller)
            # 把所有已注册的全局 callbacks 同步进去
            # （Panel 在 function_run_flow 创建 controller 之前可能就已注册了全局 callback）
            for cb in self._global_callbacks:
                controller.add_callback(cb)
            self._controllers[instance_key] = controller
        return self._controllers[instance_key]

    # ==================================================================
    # 快照机制
    # ==================================================================

    def _save_snapshot(self, instance_key: str) -> None:
        """保存当前执行状态快照（步骤执行前调用）"""
        state = self._execution_states.get(instance_key)
        controller = self._controllers.get(instance_key)
        if not state or not controller:
            return
        self._snapshots[instance_key] = copy.deepcopy(state)
        controller.save_snapshot()

    def _restore_snapshot(self, instance_key: str) -> bool:
        """恢复到上一次保存的快照状态"""
        if instance_key not in self._snapshots:
            return False
        controller = self._controllers.get(instance_key)
        if not controller:
            return False
        self._execution_states[instance_key] = self._snapshots[instance_key]
        controller.restore_snapshot()
        del self._snapshots[instance_key]
        return True

    def has_snapshot(self, instance_key: str) -> bool:
        """检查是否存在可恢复的快照"""
        return instance_key in self._snapshots

    # ==================================================================
    # 进度回调与状态查询
    # ==================================================================

    def add_progress_callback(self, callback: Callable[[Dict[str, Any]], None], instance_key: str = "") -> None:
        """添加进度回调函数

        instance_key 为空时注册为全局 callback：
        - 会加到当前所有已存在的 controller 上
        - 会保存到类级 _global_callbacks，之后新建 controller 时自动同步
        - 这样 Panel 在 function_run_flow 创建 controller 之前注册的 callback 也能生效
        """
        if instance_key:
            self._get_controller(instance_key).add_callback(callback)
        else:
            # 先加到所有现有 controller
            for controller in self._controllers.values():
                controller.add_callback(callback)
            # 再保存到全局集合（类级，跨实例共享）
            cls = type(self)
            cls._global_callbacks.add(callback)

    def get_workflow_state(self, instance_key: str = "") -> Dict[str, Any]:
        """获取当前工作流状态"""
        if instance_key:
            return self._get_controller(instance_key).get_state()
        return {
            suffix: controller.get_state()
            for suffix, controller in self._controllers.items()
        }

    def get_step_results(self, instance_key: str = "") -> Dict[str, Any]:
        """获取步骤执行结果（供 UI 层调用）"""
        if instance_key:
            controller = self._get_controller(instance_key)
            return controller.get_step_results() if controller else {}
        return {
            suffix: controller.get_step_results()
            for suffix, controller in self._controllers.items()
        }

    def get_sandbox_data(self, instance_key: str = "") -> Dict[str, Any]:
        """获取沙箱数据（供 UI 层调用）"""
        controller = self._get_controller(instance_key) if instance_key else None
        if controller is None and self._controllers:
            controller = next(iter(self._controllers.values()))
        if controller is None:
            return {}
        sandbox = controller.get_sandbox()
        return sandbox.get_all_data() if sandbox else {}

    # ==================================================================
    # Step 注册表
    # ==================================================================

    def _get_step_registry(self) -> Dict[str, Type]:
        """获取 step_id → StepClass 的注册表

        通过 StepFactory 扫描 agent 目录下的 config/steps/*.yaml，
        并从 process.yaml 中加载步骤配置作为补充。
        """
        from snail_avatar.backend.agents.core.process_executor import StepFactory
        return StepFactory.scan_configs(self._agent_dir, workflow=self._workflow_engine.workflow)

    def _get_inner_step_registry(self) -> Dict[str, Type]:
        """获取内层循环步骤的注册表（过滤掉所有外层步骤）"""
        all_steps = self._get_step_registry()
        outer_ids = set(self._workflow_engine.workflow.get_outer_step_ids())
        return {k: v for k, v in all_steps.items() if k not in outer_ids}

    def _get_detect_step_id(self) -> str:
        """检测阶段 step_id（配置驱动，通过 role 查找）"""
        return self._workflow_engine.workflow.get_step_id_by_role("detect")

    def _get_final_summary_step_id(self) -> str:
        """最终总结阶段 step_id（配置驱动，通过 role 查找）"""
        return self._workflow_engine.workflow.get_step_id_by_role("final")

    # ==================================================================
    # 流程执行（委托给 ProcessEngine）
    # ==================================================================

    def run_flow(self, instance_key: str, mode: str = "ALL", target_category: str = "") -> Dict[str, Any]:
        """批量执行完整流程

        Args:
            instance_key: 实例标识（如 instance_key）
            mode: "ALL"（全部）或 "SINGLE"（单项）
            target_category: 单项模式下的目标项名称

        Returns:
            dict: 包含状态、步骤结果和汇总信息的字典
        """
        return self._workflow_engine.run_flow(
            ctx=self,
            instance_key=instance_key,
            mode=mode,
            target_item=target_category,
        )

    def run_single_step(self, instance_key: str, mode: str = "ALL", target_category: str = "") -> Dict[str, Any]:
        """单步执行流程

        Args:
            instance_key: 实例标识
            mode: "ALL" 或 "SINGLE"
            target_category: 目标项名称

        Returns:
            dict: 执行结果
        """
        return self._workflow_engine.run_single_step(
            ctx=self,
            instance_key=instance_key,
            mode=mode,
            target_item=target_category,
        )

    def repeat_last_step(self, instance_key: str, mode: str = "ALL", target_category: str = "") -> Dict[str, Any]:
        """重复执行上一步（从快照恢复后重新执行）"""
        if not self.has_snapshot(instance_key):
            return {
                "status": "error",
                "message": "无可重复的步骤，请先执行单步操作",
            }

        self._restore_snapshot(instance_key)
        return self.run_single_step(instance_key, mode, target_category)

    # ==================================================================
    # 通用步骤执行方法
    # ==================================================================

    def _execute_step(
        self,
        step_class: Type,
        args: Dict[str, Any],
        context=None,
        step_id: str = None,
        step_name: str = None,
    ) -> Dict[str, Any]:
        """执行步骤并处理结果

        Args:
            step_class: 步骤类
            args: 步骤参数
            context: 上下文对象（通常为 self）
            step_id: 步骤 ID（可选，用于错误处理）
            step_name: 步骤名称（可选，用于错误处理）

        Returns:
            dict: 包含步骤 ID、名称和执行结果的字典
        """
        try:
            result = step_class.execute(args, context=context)
            return {
                "step_id": step_class.step_id,
                "step_name": step_class.step_name,
                "result": result,
            }
        except Exception as e:
            return {
                "step_id": step_id or getattr(step_class, "step_id", "unknown"),
                "step_name": step_name or getattr(step_class, "step_name", "未知步骤"),
                "result": {"type": "text", "content": f"执行失败: {e}"},
                "error": str(e),
            }
