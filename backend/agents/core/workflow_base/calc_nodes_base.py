# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : calc_nodes_base.py
# @Desc    : 计算节点基类 - 极简版
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
计算节点基类 - 极简版

【约定优于配置架构】
- 节点元数据：node_X_xxx.yaml（单一真相源）
- 节点类：node_X_xxx.py（纯算法逻辑）
- 自动注册：Workflow 在初始化时完成

此基类提供：
1. 统一的生命周期管理（PENDING -> RUNNING -> COMPLETED/ERROR）
2. 变量读写接口（SSTS/VTS/INTER）
3. 进度追踪和日志记录
4. 调试和监控钩子

设计原则：
- 子类只实现 numerical_solve() 方法
- 所有 I/O 通过 Memory Database 完成
- 状态机驱动，便于可视化监控
"""

import uuid
import datetime
from typing import Dict, Any, Optional
from enum import Enum

from snail_avatar.backend.core.work_log import WorkLogger


class NodeState(Enum):
    """节点状态枚举"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 执行成功
    ERROR = "error"          # 执行失败


class CalculationNode:
    """
    计算节点基类 - 极简版
    
    【架构说明】
    - 每个节点实例有唯一的 instance_id（区分同类型的多个实例）
    - 节点类型通过 node_type_id 标识（如 "node_1_DriveCycleAnalyzer"）
    - 所有输入输出变量通过 Schema 定义，运行时从 Memory Database 读写
    
    【使用方式】
    1. 子类继承此类
    2. 实现 calculate() 方法
    3. 在 node_X_xxx.yaml 中定义输入输出
    4. Workflow 自动完成注册和调度
    """
    
    # 节点类型标识（子类覆写，如 "node_1_DriveCycleAnalyzer"）
    node_type_id: str = "base_node"
    
    # 节点显示名称（子类覆写，用于UI展示）
    node_display_name: str = "基础节点"
    
    # 节点版本
    version: str = "1.0.0"
    
    # 节点描述
    description: str = "基础计算节点"
    
    # 节点分类（用于UI分组）
    category: str = "general"
    
    # SSTS/VTS 参数定义（从 YAML 加载后填充，实例属性）
    # 格式: {var_name: {"db_key": str, "type": type, "unit": str, "description": str, "default": any}}
    
    # 中间变量输入定义（从上游节点获取，实例属性）
    # 格式: {var_name: {"source_node": str, "source_var": str, "type": type, "unit": str}}
    
    # 中间变量输出定义（供下游节点使用，实例属性）
    # 格式: {var_name: {"type": type, "unit": str, "description": str}}
    
    def __init__(self, instance_id: str = None, **kwargs):
        """
        初始化计算节点
        
        【重要】子类必须调用 super().__init__() 来确保状态正确初始化
        
        Args:
            instance_id: 节点实例唯一标识（可选，默认生成 UUID）
            **kwargs: 覆盖默认参数值
        """
        # 节点实例唯一标识（区分同类型的多个实例）
        self.instance_id: str = instance_id or str(uuid.uuid4())
        
        # 车型类型（用于显示）
        self.vehicle_type: str = "default"
        
        # 车型后缀（用于构建 db_key，如 "reevLTO"）
        self.vehicle_suffix: str = ""
        
        # 内存数据库引用（由 WorkflowExecutor 注入）
        self.memory_db: Any = None
        
        # 工作流ID（由 WorkflowExecutor 注入，用于中间变量分层存储）
        self.workflow_id: str = ""
        
        # 节点名称（工作流配置中的节点ID，如 "node_1"，用于 INTER 存储）
        self.node_name: str = ""
        
        # 核心状态机
        self.state: NodeState = NodeState.PENDING
        self.progress: float = 0.0  # 计算进度 0.0 - 1.0
        
        # ⚠️ 关键：为每个实例创建独立的 schema 副本（避免类属性共享问题）
        # 类属性 ssts_vts_schema 是共享的，必须创建实例副本
        self.ssts_vts_schema: Dict[str, Dict] = {}
        self.intermediate_input_schema: Dict[str, Dict] = {}
        self.intermediate_output_schema: Dict[str, Dict] = {}
        
        # 三类变量值缓存
        # 使用私有属性存储，通过属性包装器控制写入
        self._ssts_values: Dict[str, Any] = {}
        self.intermediate_input_values: Dict[str, Any] = {}
        self.intermediate_output_values: Dict[str, Any] = {}
        
        # 执行元数据
        self.start_time: Optional[datetime.datetime] = None
        self.end_time: Optional[datetime.datetime] = None
        self.execution_duration: float = 0.0
        
        # 错误信息
        self.error_info: Optional[Dict[str, Any]] = None
        
        # 内存数据库引用（用于 output_values 属性）
        self.memory_db: Any = None
        
        # 日志记录
        self.logs: list = []
        
        # 应用 kwargs 覆盖
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        self._log("INFO", f"节点初始化完成: {self.node_display_name}")
    
    @property
    def ssts_values(self) -> Dict[str, Any]:
        """
        获取 SSTS/VTS 变量值字典（只读属性）
        
        为了确保数据一致性，禁止直接写入 ssts_values。
        如需写入 SSTS/VTS 变量，请使用 set_ssts_value() 方法。
        
        Returns:
            Dict[str, Any]: SSTS/VTS 变量值字典（只读）
        """
        return self._ssts_values
    
    @property
    def output_values(self) -> Dict[str, Any]:
        """
        获取节点输出值（统一接口）
        
        根据 schema_type 从不同位置读取，实现"唯一真相源"原则：
        - ssts_vts: 从 MemoryCore 读取（唯一真相源）
        - intermediate: 从 intermediate_output_values 读取
        
        Returns:
            Dict[str, Any]: 所有输出变量及其值
        """
        result = {}
        
        # 处理 intermediate 类型的输出（从 intermediate_output_values 读取）
        for var_name, value in self.intermediate_output_values.items():
            result[var_name] = value
        
        # 处理 ssts_vts 类型的输出（从 MemoryCore 读取，唯一真相源）
        # 使用 ssts_vts_schema 而不是 output_schema（output_schema 不存在）
        if self.memory_db and self.ssts_vts_schema:
            for var_name, schema in self.ssts_vts_schema.items():
                # 只处理输出变量（direction="output"）
                if schema.get('direction') == 'output':
                    # 从 schema 中获取已构建好的 db_key
                    db_key = schema.get('db_key')
                    if db_key and hasattr(self.memory_db, 'get_ssts_vts_param'):
                        value = self.memory_db.get_ssts_vts_param(db_key)
                        if value is not None:
                            result[var_name] = value
        
        return result
    
    # =========================================================================
    # 第一层：核心计算接口（子类必须实现）
    # =========================================================================
    
    def numerical_solve(self, memory_db: Any = None) -> Any:
        """
        【子类必须实现】数值求解器

        【重要约定】
        1. 所有输入通过 self.ssts_values 和 self.intermediate_input_values 获取
        2. 所有输出写入 self.intermediate_output_values
        3. 不要直接操作文件或数据库，只使用提供的接口
        4. 返回 True 表示成功，False 或抛出异常表示失败

        Args:
            memory_db: 内存数据库引用（可选，如果已注入则使用注入的）

        Returns:
            bool: 是否计算成功
        """
        raise NotImplementedError(f"节点 {self.node_type_id} 必须实现 numerical_solve() 方法")
    
    def semantic_solve(self) -> str:
        """
        【子类可选实现】语义求解器
        
        将节点内的计算结果拼接成一段有意义的自然语言总结字符串（中文格式）。
        这个字符串将作为本节点输出的一部分，用于 LLM 模型的推理输入。
        
        Returns:
            str: 计算结果的自然语言描述（中文格式），默认为空字符串
        """
        return ""
    
    # =========================================================================
    # 第二层：统一执行接口（模板方法模式）
    # =========================================================================
    
    def run(self, memory_db: Any = None) -> bool:
        """
        [FINAL] 执行计算流程
        
        模板方法模式：定义计算骨架，子类实现 calculate()
        
        Returns:
            bool: 计算是否成功
        """
        try:
            db = memory_db if memory_db is not None else getattr(self, 'memory_db', None)
            self.memory_db = db

            if self.state == NodeState.COMPLETED:
                WorkLogger.info(f"节点 [{self.node_display_name}] 已完成，跳过")
                return True

            if self.state == NodeState.RUNNING:
                WorkLogger.warn(f"节点 [{self.node_display_name}] 正在运行中，重复调用")
                return False

            self.state = NodeState.RUNNING
            self.progress = 0.0
            self.start_time = datetime.datetime.now()
            WorkLogger.info(f"开始计算节点 [{self.node_display_name}]")

            self.progress = 0.1
            self._load_and_check_ssts_vts(db)

            self.progress = 0.2
            self._load_and_check_intermediate(db)

            self.progress = 0.5
            WorkLogger.info(f"节点 [{self.node_display_name}] 执行计算核心逻辑")

            success = self.numerical_solve(db)
            if not success:
                raise RuntimeError(f"节点计算失败：{self.error_info}")

            self.progress = 0.8
            semantic_result = self.semantic_solve()
            if semantic_result:
                self.intermediate_output_values["semantic_summary"] = semantic_result
            self._sync_intermediate_outputs(db)

            self.progress = 1.0
            self.state = NodeState.COMPLETED
            self.end_time = datetime.datetime.now()
            self.execution_duration = (self.end_time - self.start_time).total_seconds()

            WorkLogger.info(f"节点 [{self.node_display_name}] 计算完成，耗时 {self.execution_duration:.3f} 秒")

            return True

        except Exception as e:
            self.state = NodeState.ERROR
            self.error_info = {
                "type": type(e).__name__,
                "message": str(e),
            }
            WorkLogger.error(f"节点 [{self.node_display_name}] 计算失败: {type(e).__name__}: {str(e)}")
            self._log("ERROR", f"计算失败: {type(e).__name__}: {str(e)}")
            return False
    
    def reset(self) -> None:
        """
        [FINAL] 重置节点状态到 PENDING
        
        用于用户手动重新计算。
        清理所有运行时状态，保留元数据。
        """
        self.state = NodeState.PENDING
        self.progress = 0.0
        self.ssts_values.clear()
        self.intermediate_input_values.clear()
        self.intermediate_output_values.clear()
        self.error_info = None
        self.logs.clear()
        self.start_time = None
        self.end_time = None
        self.execution_duration = 0.0
        self._log("INFO", "节点状态已重置")
    
    # =========================================================================
    # 第三层：变量读写接口
    # =========================================================================
    # 加载输入参数到节点本地缓存（内部方法）
    def _load_ssts_input_param(self, var_name: str, value: Any) -> None:
        """
        加载输入参数到节点本地缓存（内部方法）
        
        此方法用于从内存数据库读取参数后，将其缓存到节点本地，
        供后续计算使用。不进行输出类型检查，因为这是输入参数的加载。
        
        Args:
            var_name: 变量名（必须在 ssts_vts_schema 中定义）
            value: 变量值
        """
        # 检查变量是否在 schema 中定义（确保配置正确）
        if var_name not in self.ssts_vts_schema:
            WorkLogger.warn(f"节点 [{self.node_display_name}] 加载未定义的 SSTS/VTS 输入参数: {var_name}")
        
        # 直接写入缓存（不检查 direction，因为这是输入参数加载）
        self._ssts_values[var_name] = value
    
    def _load_and_check_ssts_vts(self, memory_db: Any) -> None:
        """
        [FINAL] 从内存数据库加载 SSTS/VTS 参数
        
        遍历 ssts_vts_schema 中标记为 direction="input" 的变量，
        使用 memory_db.get_ssts_vts_param() 读取参数值。
        
        db_key 格式：{var_name}_result_{vehicle_suffix}
        与 _sync_ssts_vts_output 和 load_initial_ssts 保持一致
        
        Args:
            memory_db: 内存数据库引用
        """
        if not memory_db or not self.ssts_vts_schema:
            return
        
        for var_name, schema in self.ssts_vts_schema.items():
            # 只处理输入变量
            if schema.get("direction") != "input":
                continue
            
            # 构建 db_key：使用 var_name 作为 base_key
            # 格式：{var_name}_result_{vehicle_suffix}
            if self.vehicle_suffix:
                db_key = f"{var_name}_result_{self.vehicle_suffix}"
            else:
                WorkLogger.warn(f"节点 [{self.node_display_name}] 变量 {var_name} 无法构建 db_key (vehicle_suffix 为空)")
                continue
            
            # 从内存数据库读取
            try:
                if hasattr(memory_db, 'get_ssts_vts_param'):
                    value = memory_db.get_ssts_vts_param(db_key)
                    if value is not None:
                        # 根据 schema 中的 type 字段，尝试将文本格式的数值转换为浮点数
                        param_type = schema.get("type", "")
                        if param_type in ("float", "int") and isinstance(value, str):
                            try:
                                value = float(value)
                            except (ValueError, TypeError):
                                pass
                        self._load_ssts_input_param(var_name, value)
                    else:
                        # 使用默认值
                        default_value = schema.get("default")
                        self._load_ssts_input_param(var_name, default_value)
                        WorkLogger.warn(f"节点 [{self.node_display_name}] 使用默认值: {var_name} = {default_value} ！！！！！！！！！！！！")
                else:
                    WorkLogger.warn(f"节点 [{self.node_display_name}] memory_db 没有 get_ssts_vts_param 方法")
            except Exception as e:
                WorkLogger.warn(f"节点 [{self.node_display_name}] 读取 SSTS 参数失败: {var_name}, 错误: {e} ！！！！！！！！！！！！")
                # 使用默认值
                default_value = schema.get("default")
                self._load_ssts_input_param(var_name, default_value)
                WorkLogger.warn(f"节点 [{self.node_display_name}] 使用默认值: {var_name} = {default_value} ！！！！！！！！！！！！")
    
    def _load_and_check_intermediate(self, memory_db: Any) -> None:
        """
        [FINAL] 从内存数据库加载中间变量输入
        
        遍历 intermediate_input_schema，
        使用 memory_db.get_inter_data() 读取上游节点的输出。
        
        Args:
            memory_db: 内存数据库引用
        """
        if not memory_db or not self.intermediate_input_schema:
            return
        
        # 获取车型名称和工作流ID
        veh_name = self.vehicle_suffix
        workflow_id = self.workflow_id if hasattr(self, 'workflow_id') else "default"
        
        for var_name, schema in self.intermediate_input_schema.items():
            source_node = schema.get("source_node")
            source_var = schema.get("source_var", var_name)
            
            # 从内存数据库读取
            try:
                if hasattr(memory_db, 'get_inter_data'):
                    value = memory_db.get_inter_data(veh_name, workflow_id, source_node, source_var)
                    if value is not None:
                        self.intermediate_input_values[var_name] = value
                    else:
                        WorkLogger.warn(f"节点 [{self.node_display_name}] 中间变量 {var_name} 不存在")
                else:
                    WorkLogger.warn(f"节点 [{self.node_display_name}] memory_db 没有 get_inter_data 方法")
            except Exception as e:
                WorkLogger.warn(f"节点 [{self.node_display_name}] 读取中间变量失败: {var_name}, 错误: {e}")
    
    def _sync_intermediate_outputs(self, memory_db: Any) -> None:
        """
        [FINAL] 将中间变量输出同步到内存数据库
        
        将 self.intermediate_output_values 中的所有变量写入 INTER 中间变量数据库，
        供下游节点读取使用。
        
        Args:
            memory_db: 内存数据库引用
        """
        if not memory_db or not self.intermediate_output_values:
            return
        
        # 获取车型名称、工作流ID和节点名称
        veh_name = self.vehicle_suffix
        workflow_id = self.workflow_id if hasattr(self, 'workflow_id') else "default"
        node_id = self.node_name if hasattr(self, 'node_name') and self.node_name else self.instance_id
        
        for var_name, value in self.intermediate_output_values.items():
            try:
                if hasattr(memory_db, 'set_inter_data'):
                    memory_db.set_inter_data(veh_name, workflow_id, node_id, var_name, value)
                else:
                    WorkLogger.warn(f"节点 [{self.node_display_name}] memory_db 没有 set_inter_data 方法")
            except Exception as e:
                WorkLogger.warn(f"节点 [{self.node_display_name}] 写入中间变量失败: {var_name}, 错误: {e}")
    # 写入 SSTS/VTS 参数
    # 用于将计算结果写入 MemoryCore 的 VTS 参数存储，
    # 供其他功能使用。
    def _sync_ssts_vts_output(self, memory_db: Any, var_name: str, value: Any) -> None:
        """
        [FINAL] 将变量写入 SSTS/VTS 参数

        将计算结果写入 MemoryCore 的 VTS 参数存储，供其他节点或 UI 使用。
        db_key 格式：{var_name}_result_{vehicle_suffix}

        Args:
            memory_db: 内存数据库引用
            var_name: 变量名（如 "e_dc", "e_ac", "mile_ev"）
            value: 变量值
        """
        if not memory_db:
            return

        # 构建完整的 db_key（变量名_result_车型后缀）
        # 与 load_initial_ssts 和 _load_and_check_ssts_vts 保持一致
        db_key = f"{var_name}_result_{self.vehicle_suffix}"

        try:
            if hasattr(memory_db, 'set_ssts_vts_param'):
                success = memory_db.set_ssts_vts_param(db_key, value)

                # 同时更新 ssts_vts_schema 中的 current_value（供 UI 显示）
                if success and var_name in self.ssts_vts_schema:
                    self.ssts_vts_schema[var_name]['current_value'] = value
            else:
                WorkLogger.warn(f"节点 [{self.node_display_name}] memory_db 没有 set_ssts_vts_param 方法")
        except Exception as e:
            WorkLogger.warn(f"节点 [{self.node_display_name}] 写入 SSTS/VTS 参数失败: {var_name}, 错误: {e}")
    # 安全地设置 SSTS/VTS 变量值
    # 检查变量是否在 ssts_vts_schema 中定义，
    # 防止写入未定义的变量导致数据不一致。
    # 如果变量未在 schema 中定义且 allow_undefined=False，
    # 则抛出 ValueError 异常。
    def set_ssts_value(self, var_name: str, value: Any, allow_undefined: bool = False) -> bool:
        """
        安全地设置 SSTS/VTS 变量值
        
        此方法会检查变量是否在 ssts_vts_schema 中定义，
        防止写入未定义的变量导致数据不一致。
        
        Args:
            var_name: 变量名
            value: 变量值
            allow_undefined: 是否允许写入未定义的变量（默认禁止）
        
        Returns:
            bool: 是否设置成功
        
        Raises:
            ValueError: 如果变量未在 schema 中定义且 allow_undefined=False
        """
        # 检查变量是否在 schema 中定义
        if var_name not in self.ssts_vts_schema:
            if not allow_undefined:
                WorkLogger.error(f"节点 [{self.node_display_name}] 尝试写入未定义的 SSTS/VTS 变量: {var_name}")
                raise ValueError(f"SSTS/VTS 变量 '{var_name}' 未在 schema 中定义，节点: {self.node_display_name}")
            else:
                # 允许写入未定义变量，但记录警告
                WorkLogger.warn(f"节点 [{self.node_display_name}] 写入未定义的 SSTS/VTS 变量: {var_name}")
        
        # 检查变量是否为输出类型
        schema = self.ssts_vts_schema.get(var_name)
        if schema and schema.get('direction') != 'output':
            WorkLogger.warn(f"节点 [{self.node_display_name}] 尝试写入非输出类型的 SSTS/VTS 变量: {var_name}")
        
        # 执行写入
        self._ssts_values[var_name] = value
        return True
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        [FINAL] 获取节点状态摘要
        
        给调度器和UI提供统一的状态查询接口。
        """
        return {
            "instance_id": self.instance_id,
            "node_type_id": self.node_type_id,
            "node_display_name": self.node_display_name,
            "state": self.state.value,
            "progress": self.progress,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution_duration": self.execution_duration,
            "has_error": self.error_info is not None,
            "error_info": self.error_info,
        }
    
    ## 初始化阶段预加载 SSTS 参数（不执行计算）
    def load_initial_ssts(self, memory_db: Any) -> None:
        """
        [FINAL] 在初始化阶段预加载 SSTS 参数（不执行计算）
        
        Args:
            memory_db: 内存数据库引用
        """
        if not self.ssts_vts_schema:
            return
        
        for var_name, schema in self.ssts_vts_schema.items():
            # 构建 db_key：变量名_result_车型后缀
            # 例如: var_name = "mass", vehicle_suffix = "reevlto" → "mass_result_reevlto"
            if self.vehicle_suffix:
                full_db_key = f"{var_name}_result_{self.vehicle_suffix}"
            else:
                raise ValueError(f"[load_initial_ssts] 车型后缀(vehicle_suffix)不能为空！节点: {self.node_display_name}, 变量: {var_name}")
            
            # 尝试从 memory database 读取（使用拼接后的完整 db_key）
            try:
                if hasattr(memory_db, 'get_ssts_vts_param'):
                    value = memory_db.get_ssts_vts_param(full_db_key)
                    if value is not None:
                        # 根据 schema 中的 type 字段，尝试将文本格式的数值转换为浮点数
                        param_type = schema.get("type", "")
                        if param_type in ("float", "int") and isinstance(value, str):
                            try:
                                value = float(value)
                            except (ValueError, TypeError):
                                pass
                        self.ssts_values[var_name] = value
                        schema["current_value"] = value
                    else:
                        default_value = schema.get("default", "N/A")
                        schema["current_value"] = default_value
                        WorkLogger.warn(f"节点 [{self.node_display_name}] 预加载 SSTS 参数使用默认值: {var_name} = {default_value} ！！！！！！！！！！！！")
                else:
                    default_value = schema.get("default", "N/A")
                    schema["current_value"] = default_value
                    WorkLogger.warn(f"节点 [{self.node_display_name}] 预加载 SSTS 参数使用默认值: {var_name} = {default_value} ！！！！！！！！！！！！")
            except Exception as e:
                default_value = schema.get("default", "N/A")
                schema["current_value"] = default_value
                WorkLogger.warn(f"节点 [{self.node_display_name}] 预加载 SSTS 参数失败: {var_name}, 错误: {e}")
                WorkLogger.warn(f"节点 [{self.node_display_name}] 预加载 SSTS 参数使用默认值: {var_name} = {default_value} ！！！！！！！！！！！！")    
    
    def _log(self, level: str, message: str) -> None:
        """[FINAL] 记录日志"""
        timestamp = datetime.datetime.now()
        self.logs.append((timestamp, level, message))
    
    # =========================================================================
    # 第四层：钩子方法（子类实现/覆写）
    # =========================================================================
    """
    注意：以下方法是子类实现业务逻辑的唯一入口。
    """

    def generate_visualization(self) -> Optional[dict]:
        """
        【钩子】生成计算结果的图表配置

        子类可选实现；返回 None 表示不生成图表。

        返回格式（JSON 配置为主，base64 可选降级）：
        {
            "chart_type": "line" | "bar" | "scatter" | "contour" | "table",
            "title": "图表标题",
            "x_label": "X轴标签",
            "y_label": "Y轴标签",
            "series": [
                {"name": "曲线名", "x": [...], "y": [...]}
            ],
            "base64_image": "..."    // 可选：预渲染图片（降级用）
        }

        Returns:
            dict | None: 图表配置，或 None
        """
        return None

    # ---------------------------------------------------------------------
    # 【声明式兜底】根据 YAML outputs 的 type 字段自动推断可视化
    # ---------------------------------------------------------------------

    # 这些 type 会被自动转换成可视化曲线
    _AUTO_VIS_TYPES = ("TimeSeries", "ndarray", "np.ndarray")

    def _auto_infer_visualization_from_yaml(self) -> Optional[list]:
        """
        根据 YAML outputs 中的 type 字段自动组装 viz dict 列表（兜底逻辑）

        执行条件：generate_visualization() 返回 None 时才会被调用。
        规则：
        - type=TimeSeries  → 单独一张图（X=.time, Y=.value）
        - type=ndarray     → 1D ndarray 各自一张图；布尔掩码（全是0/1）自动合并
                              同组叠加（用同节点第一个 TimeSeries 的 time 做 X 轴）
        - float/int/str/dict → 跳过（单值或统计类，不曲线化）

        Returns:
            list[dict] | None: 每个元素是一张图的 viz dict，或 None
        """
        import numpy as np
        from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries

        outputs_schema = getattr(self, 'intermediate_output_schema', {})
        outputs_values = getattr(self, 'intermediate_output_values', {})
        if not outputs_schema or not outputs_values:
            return None

        def _extract_ts(var_name, var_meta):
            """从 outputs 中安全取出一个 TimeSeries，返回 (time_arr, value_arr) 或 None"""
            ts = outputs_values.get(var_name)
            if ts is None:
                return None
            if isinstance(ts, TimeSeries):
                return np.asarray(ts.time), np.asarray(ts.value)
            if hasattr(ts, 'time') and hasattr(ts, 'value'):
                return np.asarray(ts.time), np.asarray(ts.value)
            return None

        def _extract_nd(var_name, var_meta):
            """从 outputs 中安全取出 ndarray，返回 (arr, label) 或 None"""
            arr = outputs_values.get(var_name)
            if arr is None:
                return None
            arr = np.asarray(arr)
            if arr.ndim != 1:
                return None
            return arr

        viz_list = []              # 最终输出：每个元素 = 一张图的 viz dict
        first_time_axis = None     # 第一个 TimeSeries 的 time，供 ndarray 做 X 轴
        bool_mask_series = []      # 布尔掩码 ndarray 先收集，最后合并成一张图

        # 第一轮：TimeSeries → 每个变量独立一张图
        for var_name, var_meta in outputs_schema.items():
            if str(var_meta.get("type", "")).strip() != "TimeSeries":
                continue
            result = _extract_ts(var_name, var_meta)
            if result is None:
                continue
            time_arr, value_arr = result
            if first_time_axis is None and len(time_arr) > 0:
                first_time_axis = time_arr

            label = var_meta.get("name", var_name)
            unit = var_meta.get("unit", "")
            title = f"{label} ({unit})" if unit else label
            viz_list.append({
                "chart_type": "line",
                "title": title,
                "x_label": "时间 (s)",
                "y_label": unit or label,
                "series": [{
                    "name": label,
                    "x": time_arr.tolist(),
                    "y": value_arr.tolist(),
                }],
            })

        # 第二轮：ndarray → 布尔掩码先收集到 bool_mask_series，其他独立一张图
        for var_name, var_meta in outputs_schema.items():
            if str(var_meta.get("type", "")).strip() not in ("ndarray", "np.ndarray"):
                continue
            arr = _extract_nd(var_name, var_meta)
            if arr is None:
                continue

            label = var_meta.get("name", var_name)
            is_bool_mask = np.all((arr == 0) | (arr == 1))
            x_vals = (first_time_axis[:len(arr)].tolist()
                      if first_time_axis is not None and len(first_time_axis) >= len(arr)
                      else list(range(len(arr))))

            if is_bool_mask:
                bool_mask_series.append({
                    "name": label,
                    "x": x_vals,
                    "y": arr.tolist(),
                })
            else:
                unit = var_meta.get("unit", "")
                viz_list.append({
                    "chart_type": "line",
                    "title": f"{label} ({unit})" if unit else label,
                    "x_label": "时间 (s)" if first_time_axis is not None else "序号",
                    "y_label": unit or label,
                    "series": [{
                        "name": label,
                        "x": x_vals,
                        "y": arr.tolist(),
                    }],
                })

        # 布尔掩码合并成一张图
        if bool_mask_series:
            viz_list.append({
                "chart_type": "line",
                "title": "工况掩码对比",
                "x_label": "时间 (s)" if first_time_axis is not None else "序号",
                "y_label": "是否激活 (0/1)",
                "series": bool_mask_series,
            })

        return viz_list if viz_list else None


# =========================================================================
# SSTS 计算节点基类（Phase 1：基础框架，无业务逻辑）
# =========================================================================

class SSTSCalculationNode(CalculationNode):
    """
    SSTS 计算节点基类

    在 CalculationNode 之上增加 1 项 SSTS 能力：
    1. self.sandbox — 局部沙箱（由 SSTSWorkflowExecutor 注入）

    图表相关方法（generate_visualization / _auto_infer_visualization_from_yaml）
    已上移到 CalculationNode 基类，所有节点类型共享。

    interface 保持与 CalculationNode 一致：
      - numerical_solve(memory_db): 子类实现
      - semantic_solve(): 子类可选实现

    访问沙箱参数（方案 A：沙箱顶层按车型后缀分割）：
      self.sandbox.get("mot_reg_eff", vehicle_suffix=self.vehicle_suffix)

    访问全局 MemoryDatabase 参数（继承父类逻辑，零修改）：
      self.ssts_values["mot_reg_eff"]
      # 父类 _load_and_check_ssts_vts() 自动拼 db_key = "mot_reg_eff_result_reevlto"
    """

    def __init__(self, instance_id: str = None, **kwargs):
        super().__init__(instance_id=instance_id, **kwargs)
        # 局部沙箱引用（Phase 1: None，由 SSTSWorkflowExecutor 在运行时注入）
        self.sandbox: Optional[Any] = None


