# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_base.py
# @Desc    : 工作流基类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
单workflow内全量重算架构的计算流程编排核心工具集。设计原则：配置驱动，全量重算

实现通用的计算流程编排能力，支持所有计算领域（经济性、动力性、热管理等）复用。

核心设计原则：
- 100% 通用：与具体计算业务完全解耦，只关心拓扑编排
- 零代码复用：新增计算领域只需要写 YAML，不需要修改此文件
- 三层严格抽象：
    - WorkflowNode: 单个节点的流程信息（位置、依赖、开关）
    - WorkflowGraph: DAG 有向无环图、拓扑排序、循环检测
    - WorkflowExecutor: 灵活执行策略（单节点/部分/全部）

与LLM集成设计：
    所有计算领域共享一套 function calling 接口
    def run_calculation(engine_type, workflow_id, node_ids=None)
"""

from enum import Enum
import datetime
import os
import yaml
import glob
import importlib
import inspect
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple, Set, Callable
from collections import deque

from .calc_nodes_base import CalculationNode
from snail_avatar.backend.core.memory.memory_database import MemoryDatabase
from snail_avatar.backend.core.work_log import WorkLogger

# =========================================================================
# 计算流程节点包装器
# =========================================================================

class WorkflowNode:
    """
    计算流程节点包装器
    
    对 CalculationNode 的增强，增加了流程层面的元数据。
    
    为什么不直接用 CalculationNode？
    1. 同一个节点类型可以在流程中实例化多次
    2. 节点需要知道自己在流程中的依赖关系
    3. 节点需要知道自己在UI画布上的位置
    4. 节点可以被用户灵活启用/禁用
    
    设计原则：此类只加元数据，不侵入 CalculationNode 的计算逻辑
    """
    
    def __init__(
        self,
        node_id: str,
        node_instance: CalculationNode,
        upstream_node_ids: Optional[List[str]] = None,
        ui_position: Optional[Tuple[int, int]] = None,
        is_enabled: bool = True
    ):
        """
        初始化流程节点（全量重算架构）
        
        Args:
            node_id: 流程内唯一节点ID（注意不是节点类型）
            node_instance: 实际的计算节点实例（CalculationNode子类）
            upstream_node_ids: 上游依赖节点ID列表
            ui_position: UI画布位置(x, y)
            is_enabled: 是否参与计算
        """
        # 核心标识
        self.node_id = node_id
        self.node_instance = node_instance
        
        # 拓扑关系
        self.upstream_node_ids = upstream_node_ids or []
        
        # UI 渲染
        self.ui_position = ui_position or (0, 0)
        
        # 计算控制
        self.is_enabled = is_enabled
        
    def enable(self):
        """启用节点，参与计算"""
        self.is_enabled = True
    
    def disable(self):
        """禁用节点，不参与计算（下游也会受影响）"""
        self.is_enabled = False
    
    def can_execute(self, completed_ids: Set[str]) -> bool:
        """
        检查节点是否可以执行（全量重算架构：只检查上游依赖）
        
        Args:
            completed_ids: 已完成的节点ID集合
            
        Returns:
            bool: 是否可以执行
        """
        if not self.is_enabled:
            return False
        
        # 全量重算架构：节点是否可执行只取决于上游节点是否完成
        return all(dep_id in completed_ids for dep_id in self.upstream_node_ids)

# =========================================================================
# 计算流程有向无环图(DAG)类器
# =========================================================================

class WorkflowGraph:
    """
    计算流程有向无环图(DAG) - 极简版本
    
    核心职责：
    1. 节点管理
    2. 构建依赖关系
    3. 拓扑排序获取执行顺序
    
    设计原则：配置驱动，假设配置正确无误（无循环依赖）
    """
    
    def __init__(self, workflow_id: str, workflow_name: str, description: str = ""):
        """
        初始化计算流程图（全量重算架构）
        
        Args:
            workflow_id: 流程唯一标识，对应YAML文件名
            workflow_name: UI显示名称
            description: 流程功能说明
        """
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.description = description
        
        # 节点字典
        self.nodes: Dict[str, WorkflowNode] = {}
        
        # 邻接表: {node_id: [direct_downstream_ids]}
        self.adjacency_list: Dict[str, List[str]] = {}
        
        # 入度表（拓扑排序用）
        self.in_degree: Dict[str, int] = {}
    
    def add_node(self, node: WorkflowNode) -> None:
        """
        添加节点到流程
        
        Args:
            node: WorkflowNode实例
        """
        if node.node_id in self.nodes:
            raise ValueError(f"节点ID已存在: {node.node_id}")
        
        self.nodes[node.node_id] = node
        self.adjacency_list[node.node_id] = []
        self.in_degree[node.node_id] = 0
    
    def build_edges(self) -> None:
        """
        根据节点的 upstream_node_ids 构建邻接表和入度表
        
        必须在所有节点添加完成后调用一次
        """
        # 重置
        for node_id in self.adjacency_list:
            self.adjacency_list[node_id] = []
            self.in_degree[node_id] = 0
        
        # 构建边
        for node_id, node in self.nodes.items():
            for upstream_id in node.upstream_node_ids:
                if upstream_id not in self.nodes:
                    raise ValueError(f"节点 {node_id} 依赖不存在的上游节点: {upstream_id}")
                
                # 添加边: upstream_id → node_id
                self.adjacency_list[upstream_id].append(node_id)
                self.in_degree[node_id] += 1
    
    def get_execution_order(self) -> List[str]:
        """
        获取执行顺序（全流程）
        
        Returns:
            按拓扑顺序排列的节点ID列表
        """
        in_degree_copy = self.in_degree.copy()
        queue = deque()
        
        # 入度为0的节点入队
        for node_id, degree in in_degree_copy.items():
            if degree == 0:
                queue.append(node_id)
        
        result = []
        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            
            for downstream_id in self.adjacency_list[node_id]:
                in_degree_copy[downstream_id] -= 1
                if in_degree_copy[downstream_id] == 0:
                    queue.append(downstream_id)
        
        return result

# =========================================================================
# 计算流程执行器类
# =========================================================================

class WorkflowExecutor:
    """计算流程执行器 - 极致简化版"""
    
    def __init__(self, workflow_graph, vehicle_suffix="", stop_on_error=True, memory_db=None):
        self.graph = workflow_graph
        self.vehicle_suffix = vehicle_suffix
        self.stop_on_error = stop_on_error
        self.memory_db = memory_db  # 新增：内存数据库引用，传递给节点用于读写 SSTS/VTS 参数
        self.completed = set()
        self.errors = set()

        WorkLogger.info(f"工作流执行器初始化完成，车型后缀: {vehicle_suffix}")

        node_count = 0
        for node_id, node in workflow_graph.nodes.items():
            node_count += 1
            # 注入 vehicle_suffix 属性
            if hasattr(node.node_instance, 'vehicle_suffix'):
                node.node_instance.vehicle_suffix = vehicle_suffix
            else:
                WorkLogger.warn(f"节点 {node_id} 没有 vehicle_suffix 属性")
            # 注入 memory_db 属性（节点 run() 中会使用）
            if hasattr(node.node_instance, 'memory_db'):
                node.node_instance.memory_db = memory_db
    
    def execute(self, reset_first: bool = False) -> Dict[str, Any]:
        """全流程执行

        Args:
            reset_first: 是否先重置所有节点状态
        """
        WorkLogger.info("=" * 40)
        WorkLogger.info("开始全流程执行")

        # 如果需要先重置所有节点
        if reset_first:
            WorkLogger.info(f"重置所有节点: {len(self.graph.nodes)} 个")
            for node_id, node in self.graph.nodes.items():
                if hasattr(node.node_instance, 'reset'):
                    node.node_instance.reset()
            self.completed = set()
            self.errors = set()

            # 清除中间变量数据库（确保从源头重新计算）
            # 修复：只清当前 workflow_id 对应层，跨 workflow 数据互不踩
            # （之前按 vehicle_suffix 整层清，会清掉其他 agent 的 inter_data）
            if self.memory_db and hasattr(self.memory_db, 'inter_data'):
                veh_name = self.vehicle_suffix
                wid_to_clear = self.graph.workflow_id if hasattr(self.graph, 'workflow_id') else "default"
                if veh_name in self.memory_db.inter_data:
                    self.memory_db.inter_data[veh_name][wid_to_clear] = {}
                    WorkLogger.info(f"已清除中间变量数据库，车型: {veh_name}, workflow_id: {wid_to_clear}")

        exec_count = 0
        for node_id in self.graph.get_execution_order():
            node = self.graph.nodes.get(node_id)
            if not node or not node.is_enabled or not node.can_execute(self.completed):
                continue

            exec_count += 1
            WorkLogger.info(f"执行节点: {node_id}")

            try:
                # 关键修复：将 memory_db 传递给节点的 run() 方法
                result = node.node_instance.run(self.memory_db)
                if result:
                    self.completed.add(node_id)
                    WorkLogger.info(f"节点 {node_id} 执行成功")
                else:
                    self.errors.add(node_id)
                    WorkLogger.warn(f"节点 {node_id} 执行失败")
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.errors.add(node_id)
                WorkLogger.error(f"节点 {node_id} 执行出错: {type(e).__name__}: {str(e)}")

            if self.errors and self.stop_on_error:
                break

        WorkLogger.info(f"全流程执行完成：完成 {len(self.completed)} 个，失败 {len(self.errors)} 个")
        WorkLogger.info("=" * 40)

        return {"completed": len(self.completed), "errors": len(self.errors)}


# =========================================================================
# SSTS 工作流执行器（Phase 1：基础框架，无业务逻辑）
# =========================================================================

class SSTSWorkflowExecutor(WorkflowExecutor):
    """
    SSTS 工作流执行器

    在 WorkflowExecutor 基础上增加：
    1. 将 sandbox 注入到所有 SSTSCalculationNode
    2. 执行结束后收集 generate_visualization() 结果
    3. 可选自动 commit 回写全局 MemoryDatabase

    继承 WorkflowExecutor 的所有能力（vehicle_suffix 注入、memory_db 注入、
    拓扑排序执行等），SSTSSandbox 作为额外属性叠加。
    """

    def __init__(self, workflow_graph, vehicle_suffix="", stop_on_error=True,
                 memory_db=None, sandbox=None, auto_commit=False):
        """
        初始化 SSTS 工作流执行器

        Args:
            workflow_graph: DAG 工作流图
            vehicle_suffix: 车型后缀
            stop_on_error: 遇到错误是否停止
            memory_db: 全局 MemoryDatabase 实例
            sandbox: SSTSSandbox 实例（可选）
            auto_commit: 执行结束后是否自动 commit 回写
        """
        # 调用父类初始化（注入 vehicle_suffix / memory_db 到节点）
        super().__init__(workflow_graph, vehicle_suffix, stop_on_error, memory_db)

        # SSTS 专属属性
        self.sandbox = sandbox
        self.auto_commit = auto_commit
        self.visualization_results: Dict[str, dict] = {}

        # 额外注入 sandbox 到 SSTSCalculationNode
        if sandbox is not None:
            from .calc_nodes_base import SSTSCalculationNode
            for node_id, node in workflow_graph.nodes.items():
                if isinstance(node.node_instance, SSTSCalculationNode):
                    if hasattr(node.node_instance, 'sandbox'):
                        node.node_instance.sandbox = sandbox

            WorkLogger.info(
                f"[SSTSWorkflowExecutor] 已向 SSTSCalculationNode 注入 sandbox, "
                f"vehicle_suffix={vehicle_suffix}"
            )

    def execute(self, reset_first: bool = False) -> Dict[str, Any]:
        """
        全流程执行（覆写父类）

        步骤：
        1. 复用父类 execute() 执行所有节点（拓扑排序 + stop_on_error 等）
        2. 收集 generate_visualization() 结果
        3. 可选自动 commit
        """
        result = super().execute(reset_first=reset_first)

        # Step 2: 收集可视化结果
        #   优先级：节点类 generate_visualization() → 基类 _auto_infer_visualization_from_yaml() 兜底
        self.visualization_results.clear()
        for node_id, wf_node in self.graph.nodes.items():
            node = wf_node.node_instance
            viz = None

            # 路径 A：命令式 — 节点类自己实现 generate_visualization()
            if hasattr(node, 'generate_visualization'):
                try:
                    viz = node.generate_visualization()
                except Exception as e:
                    WorkLogger.warn(f"[SSTSWorkflowExecutor] 节点 {node_id} generate_visualization 异常: {e}")
                    viz = None

            # 路径 B：声明式兜底 — 根据 YAML outputs 的 type 字段自动推断
            if viz is None and hasattr(node, '_auto_infer_visualization_from_yaml'):
                try:
                    viz = node._auto_infer_visualization_from_yaml()
                except Exception as e:
                    WorkLogger.warn(f"[SSTSWorkflowExecutor] 节点 {node_id} 自动推断可视化失败: {e}")
                    viz = None

            if viz is not None:
                self.visualization_results[node_id] = viz

        # Step 3: 可选自动 commit
        if self.auto_commit and self.sandbox is not None:
            try:
                commit_count = self.sandbox.commit()
                if commit_count > 0:
                    WorkLogger.info(
                        f"[SSTSWorkflowExecutor] auto_commit 完成: {commit_count} 个参数回写"
                    )
            except Exception as e:
                WorkLogger.warn(f"[SSTSWorkflowExecutor] auto_commit 失败: {e}")

        return result


# =========================================================================
# 简化工厂函数（方便快速使用）
# =========================================================================

def create_simple_workflow(
    workflow_id: str,
    workflow_name: str,
    node_configs: List[Dict[str, Any]],
    memory_db: MemoryDatabase,
    vehicle_suffix: str = "default"
) -> Tuple[WorkflowGraph, WorkflowExecutor]:
    """
    快速创建简单计算流程的工厂函数
    
    Args:
        workflow_id: 流程ID
        workflow_name: 显示名称
        node_configs: 节点配置列表，每个包含:
            - node_id: 节点ID
            - node_class: 节点类
            - upstream: 上游ID列表
            - position: UI位置
        memory_db: 内存数据库实例
        vehicle_suffix: 车型后缀
        
    Returns:
        (流程图, 执行器)
    """
    graph = WorkflowGraph(workflow_id, workflow_name)
    
    for config in node_configs:
        node_instance = config["node_class"](node_name=config["node_id"])
        node = WorkflowNode(
            node_id=config["node_id"],
            node_instance=node_instance,
            upstream_node_ids=config.get("upstream", []),
            ui_position=config.get("position", (0, 0))
        )
        graph.add_node(node)
    
    graph.build_edges()
    executor = WorkflowExecutor(graph, vehicle_suffix=vehicle_suffix, memory_db=memory_db)
    
    return graph, executor


# =========================================================================
# 通用工作流构建工厂函数（消除经济性/动力性 Agent 中的重复代码）
# =========================================================================

def build_workflow_from_yaml(
    agent_dir: str,
    nodes_pkg_path: str,
    memory_db: Any,
    vehicle_suffix: str = "",
    vehicle_info_field: str = "能源形式",
    vehicle_info_default: str = "ev",
    yaml_pattern: str = "workflow_*.yaml",
    yaml_match_fn: Optional[Callable[[Dict[str, Any], str], bool]] = None,
    default_yaml_filename: str = "workflow_ev_ECO.yaml",
    node_id_from_yaml_fn: Optional[Callable[[str], str]] = None,
    node_id_from_module_fn: Optional[Callable[[str], str]] = None,
    node_id_from_topology_fn: Optional[Callable[[str], str]] = None,
    use_yaml_position: bool = True,
    vehicle_lower: bool = False,
    key_results_fn: Optional[Callable[[Dict[str, Any], Any], List[Dict[str, Any]]]] = None,
    # --- SSTS 扩展参数（Phase 1：默认值保持 VTS 行为完全不变）---
    sandbox=None,
    auto_commit: bool = False,
    use_ssts_executor: bool = False,
) -> SimpleNamespace:
    """
    通用工作流构建工厂函数 - 从 YAML 配置文件构建完整的计算工作流

    【设计思路】
    通过参数化差异点，将经济性和动力性 Agent 中重复的 workflow 构建逻辑统一抽象。
    调用方只需传入不同的参数即可获得符合自身业务规则的工作流实例。

    Args:
        agent_dir: Agent 所在目录的绝对路径（含 config/ 和 nodes/ 子目录）
        nodes_pkg_path: 节点类的 Python 包路径（如 "snail_avatar.backend.agents.a302_economy_agent.nodes"）
        memory_db: 内存数据库实例
        vehicle_suffix: 车型后缀，如 "evLTO"、"reevLTO"
        vehicle_info_field: 车型信息字段名（从 vehsuffix 中提取），如 "能源形式" / "驱动形式"
        vehicle_info_default: 车型信息默认值
        yaml_pattern: workflow YAML 文件 glob 匹配模式
        yaml_match_fn: YAML 内容匹配函数 (config, vehicle_value) -> bool
        default_yaml_filename: 无匹配时使用的默认 YAML 文件名
        node_id_from_yaml_fn: YAML 文件名 → cache_key 解析函数
        node_id_from_module_fn: Python 模块名 → cache_key 解析函数
        node_id_from_topology_fn: topology中节点名 → cache_key 解析函数
        use_yaml_position: 是否使用 YAML topology 中的 position 字段
        vehicle_lower: 车型信息值是否需要转小写（如 fwd/FWD → fwd）
        key_results_fn: 关键结果提取函数 (topology_config, graph) -> List[Dict]

    Returns:
        SimpleNamespace 工作流实例，包含：
            - topology_config: 原始 YAML 配置字典
            - graph: WorkflowGraph 实例
            - executor: WorkflowExecutor 实例
            - all_nodes: 所有节点字典（同 graph.nodes）
            - get_node(node_id): 获取指定节点
            - get_key_results(): 获取关键结果（若提供 key_results_fn）
            - run_all(reset_first=True): 执行全流程计算
    """
    config_dir = os.path.join(agent_dir, "config")
    nodes_dir = os.path.join(agent_dir, "nodes")

    # ---- 步骤1: 从 memory_db 提取车型信息 ----
    vehicle_info = None
    if hasattr(memory_db, "vehsuffix"):
        for vehicle in memory_db.vehsuffix:
            if vehicle.get("车型后缀") == vehicle_suffix:
                vehicle_info = vehicle
                break

    vehicle_value = vehicle_info.get(vehicle_info_field, vehicle_info_default) if vehicle_info else vehicle_info_default
    if vehicle_lower and isinstance(vehicle_value, str):
        vehicle_value = vehicle_value.lower()

    # ---- 步骤2: 自动发现并选择 workflow YAML ----
    workflow_configs = []
    for file_path in glob.glob(os.path.join(config_dir, yaml_pattern)):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if yaml_match_fn is None or yaml_match_fn(config, vehicle_value):
                workflow_configs.append(file_path)
        except Exception as e:
            print(f"[WARNING] 加载工作流配置文件失败: {file_path}, 错误: {e}")

    if not workflow_configs:
        workflow_configs = [os.path.join(config_dir, default_yaml_filename)]

    workflow_yaml_path = workflow_configs[0]

    # ---- 步骤3: 加载拓扑配置 ----
    with open(workflow_yaml_path, "r", encoding="utf-8") as f:
        topology_config = yaml.safe_load(f)

    # ---- 步骤4: 自动发现节点元数据 ----
    node_meta_cache: Dict[str, Dict[str, Any]] = {}
    for yaml_file in glob.glob(os.path.join(config_dir, "node_*.yaml")):
        filename = os.path.basename(yaml_file)
        if node_id_from_yaml_fn is not None:
            cache_key = node_id_from_yaml_fn(filename)
        else:
            cache_key = os.path.splitext(filename)[0]
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                meta = yaml.safe_load(f)
            node_meta_cache[cache_key] = meta
        except Exception as e:
            print(f"[WARNING] 加载节点元数据失败: {yaml_file}, 错误: {e}")

    # ---- 步骤5: 自动发现节点类 ----
    node_class_cache: Dict[str, type] = {}
    for py_file in glob.glob(os.path.join(nodes_dir, "node_*.py")):
        filename = os.path.basename(py_file)
        module_name = filename.replace(".py", "")
        if node_id_from_module_fn is not None:
            cache_key = node_id_from_module_fn(module_name)
        else:
            cache_key = module_name

        try:
            module = importlib.import_module(f"{nodes_pkg_path}.{module_name}")
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, CalculationNode) and obj is not CalculationNode:
                    node_class_cache[cache_key] = obj
                    break
        except Exception as e:
            print(f"[WARNING] 加载节点类失败: {module_name}, 错误: {e}")

    # ---- 步骤6: 构建 WorkflowGraph ----
    graph = WorkflowGraph(
        workflow_id=topology_config.get("workflow_id", "unknown"),
        workflow_name=topology_config.get("workflow_name", "未命名工作流"),
        description=topology_config.get("description", "")
    )

    # ---- 步骤7: 实例化所有节点 ----
    node_index = 0
    for node_id, topology_info in topology_config.get("nodes", {}).items():
        upstream = topology_info.get("upstream", [])

        if node_id_from_topology_fn is not None:
            cache_key = node_id_from_topology_fn(node_id)
        else:
            cache_key = node_id

        node_meta = node_meta_cache.get(cache_key, {})
        node_class = node_class_cache.get(cache_key)

        if not node_class:
            node_index += 1
            continue

        # 确定 UI 位置
        if use_yaml_position:
            position = tuple(topology_info.get("position", (0, 0)))
        else:
            row = node_index // 2
            col = node_index % 2
            position = (col * 300 + 50, row * 200 + 50)

        # 实例化计算节点
        node_instance = node_class(node_name=node_meta.get("node_display_name", node_id))

        # 注入元数据
        node_instance.node_type_id = node_meta.get("node_type_id", node_id)
        node_instance.node_display_name = node_meta.get("node_display_name", node_id)
        node_instance.node_category = node_meta.get("node_category", "")
        node_instance.node_description = node_meta.get("node_description", "")

        # 自动设置 Schema（输入/输出变量）
        inputs_def = node_meta.get("inputs", {})
        outputs_def = node_meta.get("outputs", {})

        for var_name, var_meta in inputs_def.items():
            node_instance.ssts_vts_schema[var_name] = {
                "db_key": f"{var_name}_result_{getattr(node_instance, 'vehicle_suffix', '')}",
                "type": object,
                "unit": var_meta.get("unit", ""),
                "description": var_meta.get("name", var_name),
                "default": var_meta.get("default", None),
                "direction": "input"
            }
            node_instance.ssts_values[var_name] = var_meta.get("default", None)

        for var_name, var_meta in outputs_def.items():
            node_instance.intermediate_output_schema[var_name] = {
                "type": object,
                "unit": var_meta.get("unit", ""),
                "description": var_meta.get("name", var_name)
            }

        # 包装为 WorkflowNode 加入图
        workflow_node = WorkflowNode(
            node_id=node_id,
            node_instance=node_instance,
            upstream_node_ids=upstream,
            ui_position=position,
            is_enabled=True
        )
        graph.add_node(workflow_node)
        node_index += 1

    # ---- 步骤8: 构建边 ----
    graph.build_edges()

    # ---- 步骤9: 创建 WorkflowExecutor（SSTS 扩展支持）----
    stop_on_error = topology_config.get("execution", {}).get("stop_on_error", True)
    if use_ssts_executor and sandbox is not None:
        executor = SSTSWorkflowExecutor(
            graph, vehicle_suffix, stop_on_error, memory_db,
            sandbox=sandbox, auto_commit=auto_commit,
        )
    else:
        executor = WorkflowExecutor(graph, vehicle_suffix, stop_on_error, memory_db)

    # ---- 步骤10: 返回 SimpleNamespace 包装的工作流 ----
    ns_dict = {
        "topology_config": topology_config,
        "graph": graph,
        "executor": executor,
        "all_nodes": graph.nodes,
        "get_node": lambda nid: graph.nodes.get(nid),
        "run_all": lambda reset_first=True: executor.execute(reset_first=reset_first),
    }
    if key_results_fn is not None:
        ns_dict["get_key_results"] = lambda: key_results_fn(topology_config, graph)
    # SSTS 扩展：额外暴露 visualization_results 和 sandbox
    if use_ssts_executor:
        ns_dict["visualization_results"] = getattr(executor, 'visualization_results', {})
        ns_dict["sandbox"] = sandbox
    return SimpleNamespace(**ns_dict)
