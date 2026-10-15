# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : process_sandbox.py
# @Desc    : 流程沙箱 - 私域内存数据存储
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程沙箱 (ProcessSandbox)

用于存储流程执行过程中的私域数据，与公共 memory_db 隔离。
沙箱数据分为两类：

1. step_results - 步骤执行结果
   - 按 step_id 存储每个步骤的执行结果
   - 用于步骤间的数据传递，后续步骤可读取之前步骤的结果
   - 数据格式遵循 StepResultData / StepErrorData 约定

2. process_data - 业务流程数据
   - 按业务逻辑名称存储流程整体可见的数据
   - 包含两类 key：
     a) 步骤派生数据：{step_id}_structured / {step_id}_reasoning
        （通过 set_step_structured / set_step_reasoning 类型化方法访问）
     b) 业务自由命名数据：如 vts_category_data
        （通过 set_process_data / get_process_data 通用方法访问）

设计原则：
- 私域隔离：每个 ProcessController 实例独占一个沙箱，互不干扰
- 格式约定：通过 TypedDict 声明数据格式，通过类型化方法统一访问规则
- 兼容保留：保留原始 set_step_result / get_step_result 等接口，现有调用方无需修改
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# =============================================================================
# 数据格式约定（TypedDict，仅类型提示，运行时不强制）
# =============================================================================

class StepResultData(TypedDict):
    """步骤正常结果数据格式

    由 steps/base.py 的 _save_to_sandbox 写入，
    读取方通过 get_step_result 获取后访问 structured_data / reasoning_logic 字段。
    """
    structured_data: Dict[str, Any]   # 结构化数据
    reasoning_logic: str              # 推理逻辑文本


class StepErrorData(TypedDict):
    """步骤错误结果数据格式

    由 steps/base.py 的 _save_to_sandbox 在异常分支写入。
    """
    error: str                        # 错误信息
    is_error: bool                    # 错误标记，固定为 True


# =============================================================================
# 流程沙箱
# =============================================================================

class ProcessSandbox:
    """流程沙箱 - 存储流程执行过程中的私域数据

    沙箱由 ProcessControllerBase 持有（controllers/base.py），
    每个 controller 实例对应一个独立的沙箱，实现私域数据隔离。

    数据存储结构：
        _step_results: {step_id: StepResultData | StepErrorData | Dict}
        _process_data: {business_key: Any}
            - 业务 key 包括：
              "{step_id}_structured"  -> Dict（步骤结构化数据）
              "{step_id}_reasoning"   -> str（步骤推理逻辑）
              自由命名 key            -> Any（业务数据，如 "vts_category_data"）
    """

    def __init__(self):
        # 步骤执行结果：按 step_id 存储步骤的执行结果
        self._step_results: Dict[str, Dict[str, Any]] = {}

        # 业务流程数据：按业务逻辑名称存储
        self._process_data: Dict[str, Any] = {}

        # Agent 类型映射：{agent_type: {loop_item: agent_id}}
        # 用于存储 calculator 和 expert 两种类型的 agent 映射，支持按 agent_type 查询
        self._agent_type_mappings: Dict[str, Dict[str, str]] = {}

    # ==========================================================================
    # 步骤结果读写（兼容接口，保留原始 dict 格式）
    # ==========================================================================

    def set_step_result(self, step_id: str, data: Dict) -> None:
        """设置步骤执行结果

        Args:
            step_id: 步骤ID（可含循环项前缀，如 "ANALYZE_PRODUCT_EV"）
            data: 步骤执行结果，格式遵循 StepResultData 或 StepErrorData
        """
        self._step_results[step_id] = data

    def get_step_result(self, step_id: str) -> Optional[Dict[str, Any]]:
        """获取步骤执行结果

        Args:
            step_id: 步骤ID

        Returns:
            Optional[Dict]: 步骤执行结果，不存在返回 None
        """
        return self._step_results.get(step_id)

    # ==========================================================================
    # 步骤结果类型化访问（新增，统一 key 命名规则）
    # ==========================================================================

    def set_step_structured(self, step_id: str, data: Dict[str, Any]) -> None:
        """写入步骤的结构化数据到 process_data

        统一 key 命名规则：{step_id}_structured
        替代散落在子类中的 set_process_data(f"{step_id}_structured", data) 调用。

        Args:
            step_id: 步骤ID
            data: 结构化数据字典
        """
        self._process_data[f"{step_id}_structured"] = data

    def get_step_structured(self, step_id: str) -> Dict[str, Any]:
        """读取步骤的结构化数据

        对应 set_step_structured 的读取。

        Args:
            step_id: 步骤ID

        Returns:
            Dict: 结构化数据，不存在返回空 dict
        """
        return self._process_data.get(f"{step_id}_structured", {}) or {}

    def set_step_reasoning(self, step_id: str, text: str) -> None:
        """写入步骤的推理逻辑到 process_data

        统一 key 命名规则：{step_id}_reasoning
        替代散落在子类中的 set_process_data(f"{step_id}_reasoning", text) 调用。

        Args:
            step_id: 步骤ID
            text: 推理逻辑文本
        """
        self._process_data[f"{step_id}_reasoning"] = text

    def get_step_reasoning(self, step_id: str) -> str:
        """读取步骤的推理逻辑

        对应 set_step_reasoning 的读取。

        Args:
            step_id: 步骤ID

        Returns:
            str: 推理逻辑文本，不存在返回空字符串
        """
        return self._process_data.get(f"{step_id}_reasoning", "") or ""

    def set_step_error(self, step_id: str, error_msg: str) -> None:
        """写入步骤错误结果到 step_results

        遵循 StepErrorData 格式约定，替代手动构造
        set_step_result(step_id, {"error": msg, "is_error": True})。

        Args:
            step_id: 步骤ID
            error_msg: 错误信息
        """
        self._step_results[step_id] = {"error": error_msg, "is_error": True}

    def is_step_error(self, step_id: str) -> bool:
        """判断步骤是否执行出错

        Args:
            step_id: 步骤ID

        Returns:
            bool: 步骤结果为错误格式且 is_error=True 时返回 True，否则 False
        """
        result = self._step_results.get(step_id)
        if not result or not isinstance(result, dict):
            return False
        return bool(result.get("is_error", False))

    # ==========================================================================
    # 业务流程数据读写（通用接口，支持自由命名 key）
    # ==========================================================================

    def set_process_data(self, key: str, value: Any) -> None:
        """设置业务流程数据

        用于存储业务特定的数据（如 "vts_category_data"），
        key 由调用方自由命名。

        Args:
            key: 业务数据名称
            value: 业务数据内容
        """
        self._process_data[key] = value

    def get_process_data(self, key: str = None) -> Any:
        """获取业务流程数据

        Args:
            key: 业务数据名称，为 None 时返回所有业务流程数据

        Returns:
            Any: 业务数据内容，key 不存在返回 None
        """
        if key is None:
            return self._process_data
        return self._process_data.get(key)

    # ==========================================================================
    # 整体数据访问与重置
    # ==========================================================================

    def get_all_data(self) -> Dict[str, Any]:
        """获取沙箱中所有数据的副本

        返回格式与历史版本保持一致，供 UI 层（process_context.get_sandbox_data）使用。

        Returns:
            Dict: {"step_results": {...}, "process_data": {...}, "agent_type_mappings": {...}}
        """
        return {
            "step_results": self._step_results,
            "process_data": self._process_data,
            "agent_type_mappings": self._agent_type_mappings,
        }

    def clear(self) -> None:
        """清空沙箱中的所有数据

        由 controllers/progress.py 的 reset 方法调用。
        """
        self._step_results = {}
        self._process_data = {}
        self._agent_type_mappings = {}

    # ==========================================================================
    # Agent 类型映射管理
    # ==========================================================================

    def set_agent_type_mapping(self, agent_type: str, mapping: Dict[str, str]) -> None:
        """设置指定 agent_type 的映射

        Args:
            agent_type: Agent 类型（"calculator" 或 "expert"）
            mapping: {loop_item: agent_id} 映射字典
        """
        if agent_type not in self._agent_type_mappings:
            self._agent_type_mappings[agent_type] = {}
        self._agent_type_mappings[agent_type].update(mapping)

    def get_agent_id_by_type(self, agent_type: str, loop_item: str = "") -> str:
        """获取指定 agent_type 在特定循环项下的 Agent ID

        查找顺序：
        1. 按 agent_type + loop_item 精确匹配
        2. 按 agent_type + "__default__" 默认值
        3. 按 agent_type 获取任意值

        Args:
            agent_type: Agent 类型（"calculator" 或 "expert"）
            loop_item: 循环项名称（可选）

        Returns:
            str: Agent ID，未找到返回空字符串
        """
        mapping = self._agent_type_mappings.get(agent_type, {})
        if not mapping:
            return ""

        # 1. 精确匹配 loop_item
        if loop_item and loop_item in mapping:
            return mapping[loop_item]

        # 2. 查找 __default__
        if "__default__" in mapping:
            return mapping["__default__"]

        # 3. 返回第一个值
        return next(iter(mapping.values()), "")

    def get_all_agent_type_mappings(self) -> Dict[str, Dict[str, str]]:
        """获取所有 agent_type 的映射

        Returns:
            Dict: {agent_type: {loop_item: agent_id}}
        """
        return self._agent_type_mappings.copy()
