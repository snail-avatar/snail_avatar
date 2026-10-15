# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_builder.py
# @Desc    : 共享工作流构建器（UI 面板和 function 工具共用同一套构建逻辑）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
共享工作流构建器

【设计目标】
- 统一 UI 面板（BaseWorkflowTab）与 function 工具（EconomyAgent）的工作流构建逻辑
- 节点 ID 规则：使用完整文件名 / 节点名（如 node_5_EVEnergyConsumption），不做任何截断
- schema_type 规则：严格区分 ssts_vts 与 intermediate，避免 VTS 输出被误存为中间变量

【使用方式】
    # UI 面板：
    from snail_avatar.backend.agents.core.workflow_base.workflow_builder import build_workflow_from_yaml_file
    workflow = build_workflow_from_yaml_file(
        yaml_path=workflow_yaml_path,
        vehicle_suffix=vehicle_suffix,
        memory_db=memory_db,
    )

    # function 工具：
    from snail_avatar.backend.agents.core.workflow_base.workflow_builder import build_workflow_from_yaml_file
    workflow = build_workflow_from_yaml_file(
        yaml_path=workflow_yaml_path,
        vehicle_suffix=vehicle_suffix,
        memory_db=memory_db,
    )

【关键属性注入】
每个计算节点实例会被注入以下属性，与 BaseWorkflowTab._load_initial_data() 保持一致：
- vehicle_suffix: 车型后缀（中间变量存储键名）
- vehicle_type: 与 vehicle_suffix 相同（部分节点用 vehicle_type）
- memory_db: 数据库引用
- workflow_id: 工作流 ID（中间变量分层存储）
- node_name: 节点 ID（中间变量存储键名）
- node_type_id: 节点类型 ID
- node_display_name: 节点显示名称
- node_category: 节点分类
- node_description: 节点描述
- load_initial_ssts(memory_db): 预加载 SSTS 数据
"""

import os
import yaml
import glob
import importlib
import inspect
from typing import Dict, List, Any, Optional
from types import SimpleNamespace

from snail_avatar.backend.agents.core.workflow_base import (
    WorkflowNode,
    WorkflowGraph,
    WorkflowExecutor,
    CalculationNode,
)


# =============================================================================
# 节点元数据发现
# =============================================================================

def discover_node_metadata(config_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    自动发现所有节点元数据 YAML 文件

    节点 ID 规则：使用完整文件名（不含 .yaml 后缀）作为 key，不做任何截断
    例如：node_5_EVEnergyConsumption.yaml → key 为 "node_5_EVEnergyConsumption"

    Args:
        config_dir: 配置目录路径（包含 node_*.yaml 文件）

    Returns:
        Dict: {节点ID: 元数据字典}
    """
    meta_cache = {}
    pattern = os.path.join(config_dir, "node_*.yaml")

    for yaml_file in glob.glob(pattern):
        filename = os.path.basename(yaml_file)
        # 提取节点ID：node_1_DriveCycleAnalyzer.yaml → node_1_DriveCycleAnalyzer
        node_id = os.path.splitext(filename)[0]

        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                meta = yaml.safe_load(f)
            meta_cache[node_id] = meta
        except Exception as e:
            print(f"[workflow_builder] 加载节点元数据失败: {yaml_file}, 错误: {e}")

    return meta_cache


# =============================================================================
# 节点类发现
# =============================================================================

def discover_node_classes(nodes_dir: str, nodes_pkg_path: str) -> Dict[str, type]:
    """
    自动发现所有 Python 节点类

    节点 ID 规则：使用完整模块名（不含 .py 后缀）作为 key，不做任何截断
    例如：node_1_DriveCycleAnalyzer.py → key 为 "node_1_DriveCycleAnalyzer"

    Args:
        nodes_dir: 节点 Python 文件所在目录
        nodes_pkg_path: 节点类的 Python 包路径，如 "snail_avatar.backend.agents.a302_economy_agent.nodes"

    Returns:
        Dict: {节点ID: 节点类}
    """
    class_cache = {}
    pattern = os.path.join(nodes_dir, "node_*.py")

    for py_file in glob.glob(pattern):
        filename = os.path.basename(py_file)
        module_name = filename.replace(".py", "")
        node_id = module_name

        try:
            module = importlib.import_module(f"{nodes_pkg_path}.{module_name}")

            for name, obj in inspect.getmembers(module):
                # 只选择本模块定义的 CalculationNode 子类（排除从其他模块 import 进来的基类）
                # __module__ 过滤是关键：SSTSCalculationNode.__module__ = "calc_nodes_base" ≠ "node_0_VehicleParam"
                if (inspect.isclass(obj)
                        and issubclass(obj, CalculationNode)
                        and obj is not CalculationNode
                        and obj.__module__ == module.__name__):
                    class_cache[node_id] = obj
                    break
        except Exception as e:
            print(f"[workflow_builder] {module_name} 导入失败: {e}")

    return class_cache


# =============================================================================
# 输入输出变量注册（支持 schema_type 区分）
# =============================================================================

def auto_register_io(node_instance: Any, inputs_def: Dict, outputs_def: Dict,
                      vehicle_suffix: str = "") -> None:
    """
    从元数据自动注册输入输出变量（支持 schema_type 字段）

    与 BaseWorkflowTab._auto_register_io() 保持完全一致的逻辑：

    - schema_type == "ssts_vts": 变量存入 ssts_vts_schema，direction="input" 或 "output"
    - schema_type == "intermediate"（输入）: 变量存入 intermediate_input_schema，记录 source_node/source_var
    - schema_type == "intermediate"（输出）: 变量存入 intermediate_output_schema
    - 未指定 schema_type 时：输入默认 ssts_vts，输出默认 intermediate

    Args:
        node_instance: 节点实例
        inputs_def: 输入变量定义（从 YAML meta 中读取）
        outputs_def: 输出变量定义（从 YAML meta 中读取）
        vehicle_suffix: 车型后缀（用于构建 db_key）
    """
    # ----- 输入变量 -----
    for var_name, var_meta in inputs_def.items():
        schema_type = var_meta.get("schema_type", "ssts_vts")

        if schema_type == "ssts_vts":
            # SSTS 输入 → 存入 ssts_vts_schema，direction="input"
            db_key = f"{var_name}_result_{vehicle_suffix}"
            node_instance.ssts_vts_schema[var_name] = {
                "db_key": db_key,
                "type": var_meta.get("type", "object"),
                "unit": var_meta.get("unit", ""),
                "description": var_meta.get("name", var_name),
                "default": var_meta.get("default", None),
                "direction": "input",
            }
            node_instance.ssts_values[var_name] = var_meta.get("default", None)
        elif schema_type == "intermediate":
            # 中间变量输入 → 存入 intermediate_input_schema，记录 source_node/source_var
            node_instance.intermediate_input_schema[var_name] = {
                "source_node": var_meta.get("source_node", ""),
                "source_var": var_meta.get("source_var", var_name),
                "type": var_meta.get("type", "object"),
                "unit": var_meta.get("unit", ""),
                "description": var_meta.get("name", var_name),
            }

    # ----- 输出变量 -----
    for var_name, var_meta in outputs_def.items():
        schema_type = var_meta.get("schema_type", "intermediate")

        if schema_type == "intermediate":
            # 中间变量输出 → 存入 intermediate_output_schema
            node_instance.intermediate_output_schema[var_name] = {
                "type": var_meta.get("type", "object"),
                "unit": var_meta.get("unit", ""),
                "description": var_meta.get("name", var_name),
            }
        elif schema_type == "ssts_vts":
            # VTS 输出 → 存入 ssts_vts_schema，direction="output"
            db_key = f"{var_name}_result_{vehicle_suffix}"
            node_instance.ssts_vts_schema[var_name] = {
                "db_key": db_key,
                "type": var_meta.get("type", "object"),
                "unit": var_meta.get("unit", ""),
                "description": var_meta.get("name", var_name),
                "direction": "output",
                "schema_type": "ssts_vts",
            }


# =============================================================================
# 构建 WorkflowGraph
# =============================================================================

def build_graph_from_config(topology_config: Dict,
                              node_meta_cache: Dict[str, Dict[str, Any]],
                              node_class_cache: Dict[str, type],
                              vehicle_suffix: str = "") -> WorkflowGraph:
    """
    从拓扑配置构建 WorkflowGraph

    节点 ID 规则：使用完整节点名匹配元数据和类缓存，不做任何截断

    Args:
        topology_config: 工作流 YAML 配置字典
        node_meta_cache: discover_node_metadata() 的结果
        node_class_cache: discover_node_classes() 的结果
        vehicle_suffix: 车型后缀

    Returns:
        WorkflowGraph: 构建完成的有向无环图
    """
    graph = WorkflowGraph(
        workflow_id=topology_config["workflow_id"],
        workflow_name=topology_config["workflow_name"],
        description=topology_config.get("description", ""),
    )

    # 实例化所有节点
    for node_id, topology_info in topology_config["nodes"].items():
        # 合并拓扑信息和节点元数据
        upstream = topology_info["upstream"]

        # 用完整 node_id 查找 meta 和 class（不截断）
        node_meta = node_meta_cache.get(node_id, {})

        if node_meta:
            node_type_id = node_meta.get("node_type_id", node_id)
            display_name = node_meta.get("node_display_name", node_id)
            inputs_def = node_meta.get("inputs", {})
            outputs_def = node_meta.get("outputs", {})
        else:
            node_type_id = node_id
            display_name = node_id
            inputs_def = {}
            outputs_def = {}

        # 获取节点类并实例化（用完整 node_id 查找）
        node_class = node_class_cache.get(node_id)

        if node_class is None:
            raise ValueError(f"按约定未自动发现对应节点类: {node_id}")

        # 实例化计算节点
        node_instance = node_class(node_name=display_name)

        # 注入 vehicle_suffix（关键！）
        node_instance.vehicle_suffix = vehicle_suffix

        # 自动注册输入输出变量（区分 schema_type）
        auto_register_io(node_instance, inputs_def, outputs_def, vehicle_suffix)

        # 注入元数据
        node_instance.node_type_id = node_type_id
        node_instance.node_display_name = display_name
        node_instance.node_category = node_meta.get("node_category", "")
        node_instance.node_description = node_meta.get("node_description", "")
        # SSTS 节点白名单：本节点在沙箱中只读哪些零部件
        node_instance.sandbox_components = node_meta.get("sandbox_components", [])
        # 注入节点名称（工作流中的节点ID，如 "node_5_EVEnergyConsumption"）
        node_instance.node_name = node_id

        # 包装为 WorkflowNode 加入图
        workflow_node = WorkflowNode(
            node_id=node_id,
            node_instance=node_instance,
            upstream_node_ids=upstream,
            is_enabled=True,
        )

        graph.add_node(workflow_node)

    return graph


# =============================================================================
# 主入口：从 YAML 文件构建工作流
# =============================================================================

def build_workflow_from_yaml_file(yaml_path: str,
                                    vehicle_suffix: str = "",
                                    memory_db: Any = None,
                                    nodes_pkg_path: Optional[str] = None,
                                    config_dir: Optional[str] = None,
                                    nodes_dir: Optional[str] = None,
                                    # --- SSTS 扩展可选参数（默认值保持 VTS 行为完全不变）---
                                    sandbox: Any = None,
                                    auto_commit: bool = False) -> SimpleNamespace:
    """
    从 YAML 文件构建工作流（无头模式，与 BaseWorkflowTab._build_workflow() 逻辑一致）

    【关键特性】
    - 节点 ID 使用完整文件名/节点名，不做任何截断
    - schema_type 严格区分 ssts_vts / intermediate
    - 注入 node_name、workflow_id、vehicle_suffix 等关键属性
    - 预加载 SSTS 数据

    Args:
        yaml_path: 工作流 YAML 文件绝对路径（如 workflow_ev_ECO.yaml）
        vehicle_suffix: 车型后缀，如 "evLTO"、"reevLTO"
        memory_db: 数据库引用（用于节点注入和 SSTS 预加载）
        nodes_pkg_path: 可选：节点类的 Python 包路径，如 "snail_avatar.backend.agents.a302_economy_agent.nodes"
                        未指定时从 yaml_path 自动推导
        config_dir: 可选：节点元数据 YAML 目录，未指定时使用 yaml_path 所在目录
        nodes_dir: 可选：节点 Python 文件目录，未指定时从 yaml_path 自动推导

    Returns:
        SimpleNamespace 工作流实例，包含：
            - workflow_id: 工作流 ID
            - topology_config: 原始 YAML 配置字典
            - graph: WorkflowGraph 实例
            - executor: WorkflowExecutor 实例
            - all_nodes: 所有节点字典（同 graph.nodes）
            - get_node(node_id): 获取指定节点
            - run_all(reset_first=True): 执行全流程计算
    """
    # 1. 加载 YAML 配置
    with open(yaml_path, 'r', encoding='utf-8') as f:
        topology_config = yaml.safe_load(f)

    # 2. 确定目录路径
    if config_dir is None:
        config_dir = os.path.dirname(yaml_path)

    # 规范化路径
    normalized_yaml_path = os.path.normpath(yaml_path)

    # 构建正确的 nodes_dir 和 nodes_pkg_path
    agent_dir = os.path.basename(os.path.dirname(os.path.dirname(normalized_yaml_path)))
    if nodes_dir is None:
        nodes_dir = os.path.join(os.path.dirname(os.path.dirname(normalized_yaml_path)), "nodes")
    if nodes_pkg_path is None:
        nodes_pkg_path = f"snail_avatar.backend.agents.{agent_dir}.nodes"

    # 3. 自动发现节点元数据
    node_meta_cache = discover_node_metadata(config_dir)

    # 4. 自动发现节点类
    node_class_cache = discover_node_classes(nodes_dir, nodes_pkg_path)

    # 5. 构建 WorkflowGraph
    graph = build_graph_from_config(topology_config, node_meta_cache, node_class_cache, vehicle_suffix)
    graph.build_edges()

    # 6. 注入关键属性（同 BaseWorkflowTab._load_initial_data() 逻辑）
    workflow_id = topology_config.get("workflow_id", "unknown")
    for node_id, node in graph.nodes.items():
        node_instance = node.node_instance

        for attr, value in [
            ("vehicle_suffix", vehicle_suffix),
            ("vehicle_type", vehicle_suffix),
            ("memory_db", memory_db),
            ("workflow_id", workflow_id),
        ]:
            if hasattr(node_instance, attr):
                setattr(node_instance, attr, value)

        # 加载初始 SSTS 数据
        if hasattr(node_instance, "load_initial_ssts") and memory_db is not None:
            try:
                node_instance.load_initial_ssts(memory_db)
            except Exception as e:
                print(f"[workflow_builder] {node_id} 加载 SSTS 失败: {e}")

    # 7. 创建执行器（SSTS 扩展：有 sandbox 时用 SSTSWorkflowExecutor 自动注入节点）
    stop_on_error = topology_config.get("execution", {}).get("stop_on_error", True)
    if sandbox is not None:
        from snail_avatar.backend.agents.core.workflow_base.workflow_base import SSTSWorkflowExecutor
        executor = SSTSWorkflowExecutor(
            graph, vehicle_suffix, stop_on_error, memory_db,
            sandbox=sandbox, auto_commit=auto_commit,
        )
    else:
        executor = WorkflowExecutor(graph, vehicle_suffix, stop_on_error, memory_db)

    # 8. 返回工作流实例（结构同 BaseWorkflowTab._build_workflow()）
    def debug_run_all(reset_first: bool = False):
        result = executor.execute(reset_first=reset_first)
        return result

    workflow = SimpleNamespace(
        workflow_id=workflow_id,
        topology_config=topology_config,
        graph=graph,
        executor=executor,
        all_nodes=graph.nodes,
        get_node=lambda node_id: graph.nodes.get(node_id),
        run_all=debug_run_all,
    )

    return workflow


# =============================================================================
# 便捷函数：根据车型后缀选择对应 YAML
# =============================================================================

def select_workflow_yaml_for_vehicle(config_dir: str, vehicle_suffix: str = "",
                                       calculation_type: str = "economy") -> Optional[str]:
    """
    根据车型后缀选择对应工作流 YAML 文件

    规则：
    - 车型后缀包含 "reev"（不区分大小写）→ 使用 REEV 工作流
    - 默认使用 EV 工作流

    Args:
        config_dir: 配置目录
        vehicle_suffix: 车型后缀
        calculation_type: 计算类型（如 "economy"）

    Returns:
        str: 匹配的 YAML 文件绝对路径，未找到时返回 None
    """
    suffix_lower = vehicle_suffix.lower() if vehicle_suffix else "ev"

    # 先尝试按 energy_type 精确匹配
    if "reev" in suffix_lower:
        target_energy_type = "reev"
    else:
        target_energy_type = "ev"

    for yaml_path in glob.glob(os.path.join(config_dir, "workflow_*.yaml")):
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if (config.get("calculation_type") == calculation_type
                    and config.get("energy_type", "").lower() == target_energy_type):
                return yaml_path
        except Exception:
            continue

    # 退而求其次：只匹配 calculation_type
    for yaml_path in glob.glob(os.path.join(config_dir, "workflow_*.yaml")):
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if config.get("calculation_type") == calculation_type:
                return yaml_path
        except Exception:
            continue

    return None
