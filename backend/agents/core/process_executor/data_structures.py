# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : data_structures.py
# @Desc    : 流程控制器数据结构定义
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepDefinition:
    """步骤定义 - 从 YAML 解析的结构化步骤描述（属性模式）
    
    属性模式特性：
    - next_step 显式指定下一步跳转
    - step_level/loop_name 定义步骤层级和循环归属
    
    支持的步骤类型:
    - step: 普通步骤
    - loop: 循环步骤
    - condition: 条件分支步骤
    """
    step_id: str
    step_name: str
    step_type: str = "step"  # step, loop, condition
    sub_steps: List[StepDefinition] = field(default_factory=list)
    loop_items: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 循环类型: "parallel"（并行）
    loop_type: str = "parallel"
    
    # 条件分支相关字段
    condition: str = ""
    check_step: str = ""
    check_condition: str = ""
    
    # 属性模式字段
    # 步骤层级: "top_level"（顶层）或 "loop_level"（循环内）
    step_level: str = "top_level"
    # 循环组名称（仅 loop_level 步骤需要，标识所属循环）
    loop_name: str = ""
    # 正常流程的下一步骤 ID
    next_step: str = ""
    # 条件节点失败分支的目标步骤 ID（仅 condition 类型使用）
    next_step_on_fail: str = ""
    
    # 其他字段
    next_step_id: str = ""
    depends_on: List[str] = field(default_factory=list)
    retry_count: int = 0

    def has_loop(self) -> bool:
        return self.step_type == "loop" and len(self.loop_items) > 0


@dataclass
class StepState:
    """步骤状态 - 运行时步骤的状态跟踪"""
    step_id: str
    step_name: str
    step_type: str = "step"
    status: str = "pending"
    current_index: int = 0
    loop_items: List[str] = field(default_factory=list)
    current_loop_item: str = ""
    completed_loop_items: List[str] = field(default_factory=list)
    step_result: Dict[str, Any] = field(default_factory=dict)
    sub_states: List[StepState] = field(default_factory=list)
    timestamp_start: Optional[datetime.datetime] = None
    timestamp_end: Optional[datetime.datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    error_message: str = ""
    retry_attempts: int = 0
    
    # 动态条件结果缓存
    condition_result: Optional[bool] = None

    def is_completed(self) -> bool:
        if self.step_type == "loop":
            return len(self.completed_loop_items) >= len(self.loop_items)
        return self.status == "completed"

    def is_running(self) -> bool:
        return self.status == "running"

    def start(self) -> None:
        self.status = "running"
        self.timestamp_start = datetime.datetime.now()

    def complete(self, step_result: Dict[str, Any] = None) -> None:
        self.status = "completed"
        self.step_result = step_result or {}
        self.timestamp_end = datetime.datetime.now()

    def reset(self) -> None:
        self.status = "pending"
        self.current_index = 0
        self.current_loop_item = ""
        self.completed_loop_items = []
        self.step_result = {}
        self.timestamp_start = None
        self.timestamp_end = None
        self.skipped = False
        self.error_message = ""
        self.retry_attempts = 0
        self.condition_result = None
        for sub in self.sub_states:
            sub.reset()


class ProcessDefinition:
    """流程定义 - 从 YAML 解析的结构化流程描述（属性模式）

    属性模式特性：
    - steps 使用 step_level/loop_name/next_step 属性定义流程
    - 提供对 process.yaml 配置的只读访问，包括：
    - 步骤查找（按 step_id / role）
    - 步骤类型/配置文件/Agent 来源查询
    - 条件节点配置解析
    - 循环节点配置获取
    - 属性模式下的流程导航（next_step 跳转、循环组识别）
    """

    def __init__(self, data: Dict[str, Any]):
        self.raw = data
        self.name = data.get("workflow", {}).get("name", "")
        self.version = data.get("workflow", {}).get("version", "")
        self.description = data.get("workflow", {}).get("description", "")
        self.global_config: Dict[str, Any] = data.get("global_config", {})
        
        # 属性模式：使用 steps 列表
        self.steps: List[Dict[str, Any]] = data.get("steps", [])
        
        # 属性模式的步骤查找映射
        self._step_id_map: Dict[str, Dict[str, Any]] = {}  # step_id -> step config
        self._top_level_steps: List[Dict[str, Any]] = []  # 顶层步骤（按 next_step 顺序）
        self._loop_groups: Dict[str, List[Dict[str, Any]]] = {}  # loop_name -> 步骤列表
        self._start_step_id: str = ""  # 流程起始步骤 ID
        self._ordered_step_ids: List[str] = []  # 有序步骤 ID 列表（用于查找上一个步骤）
        # 条件可选步骤映射: step_id -> 依赖的 condition step_id
        # 条件可选步骤只在 condition_result=False（条件不通过）时才执行
        self._conditional_optional_map: Dict[str, str] = {}

        # 构建属性模式导航映射
        self._build_attribute_navigation()
    
    def _build_attribute_navigation(self) -> None:
        """构建属性模式的导航映射"""
        # 构建 step_id -> step config 映射
        self._step_id_map = {}
        for step in self.steps:
            step_id = step.get("step_id", "")
            if step_id:
                self._step_id_map[step_id] = step
        
        # 分离顶层步骤和循环步骤
        top_level = []
        loop_level = {}  # loop_name -> [steps]
        
        # ===== DEBUG =====
        print(f"[DEBUG][Workflow] raw steps: count={len(self.steps)}")
        for s in self.steps:
            print(f"  step_id={s.get('step_id','')!r} step_level={s.get('step_level','')!r} step_type={s.get('step_type','')!r} next_step={s.get('next_step','')!r}")

        for step in self.steps:
            step_level = step.get("step_level", "top_level")
            step_id = step.get("step_id", "")
            
            if step_level == "top_level":
                top_level.append(step)
            elif step_level == "loop_level":
                loop_name = step.get("loop_name", "")
                if loop_name not in loop_level:
                    loop_level[loop_name] = []
                loop_level[loop_name].append(step)
        
        # 顶层步骤按 next_step 顺序排列
        self._top_level_steps = self._order_steps_by_next(top_level)

        # ===== DEBUG =====
        print(f"[DEBUG][Workflow] _top_level_steps (before loop-insert): {[s.get('step_id','') for s in self._top_level_steps]}")
        print(f"[DEBUG][Workflow] loop_level keys: {list(loop_level.keys())}")
        
        # ---- 关键修复：注入 synthetic loop step 到 _top_level_steps ----
        # controller._states 里有 synthetic loop step（step_id=loop_name, step_type="loop"）
        # 但 YAML 里没有这个 step，ProcessDefinition.steps 里也没有
        # 所以 _order_steps_by_next 找不到它，必须手动插入
        #
        # 插入逻辑：找到 top_level 中 step 的 next_step 指向 loop 内部 step 的那个 top step，
        # 在它后面插入 synthetic loop step（step_id=loop_name）
        if loop_level:
            expanded = []
            inserted_loops = set()
            for tstep in self._top_level_steps:
                expanded.append(tstep)
                next_id = tstep.get("next_step", "")
                if next_id:
                    next_data = self._step_id_map.get(next_id)
                    if next_data and next_data.get("step_level") == "loop_level":
                        loop_name = next_data.get("loop_name", "")
                        if loop_name and loop_name not in inserted_loops:
                            # 构造 synthetic loop step 字典
                            synthetic = {
                                "step_id": loop_name,
                                "step_name": loop_name,
                                "step_type": "loop",
                                "step_level": "top_level",
                            }
                            expanded.append(synthetic)
                            inserted_loops.add(loop_name)
                            # 也加入 _step_id_map，让 get_step_by_id() 能查到
                            self._step_id_map[loop_name] = synthetic
                            print(f"[DEBUG][Workflow] inserted synthetic loop step {loop_name!r} after {tstep.get('step_id','')!r}")
            self._top_level_steps = expanded
        
        # ===== DEBUG =====
        print(f"[DEBUG][Workflow] _top_level_steps (final): {[s.get('step_id','') for s in self._top_level_steps]}")
        
        # 循环组步骤按 next_step 顺序排列
        self._loop_groups = {}
        for loop_name, steps in loop_level.items():
            self._loop_groups[loop_name] = self._order_steps_by_next(steps)
        
        # 查找起始步骤（第一个顶层步骤）
        if self._top_level_steps:
            self._start_step_id = self._top_level_steps[0].get("step_id", "")
        
        # 构建有序步骤 ID 列表（用于查找上一个步骤）
        # 格式: 顶层步骤 ID + 循环组标记 + 循环内步骤 ID
        self._ordered_step_ids = []
        
        for step in self._top_level_steps:
            step_id = step.get("step_id", "")
            self._ordered_step_ids.append(step_id)
            
        # 添加循环组内的步骤（按循环组顺序）
        for loop_name, loop_steps in self._loop_groups.items():
            for step in loop_steps:
                step_id = step.get("step_id", "")
                self._ordered_step_ids.append(step_id)
    
    def _order_steps_by_next(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 next_step 顺序排列步骤（含条件分支展开）

        使用拓扑排序，从没有被其他步骤 next_step 指向的步骤开始，
        沿着 next_step 链排列。遇到条件节点时，将 next_step_on_fail
        路径上的步骤插入到条件节点之后，使步骤列表包含所有可能执行的步骤。

        同时记录 _conditional_optional_map（step_id -> condition step_id），
        供 UI 层根据条件结果动态隐藏/显示条件可选步骤。
        """
        if not steps:
            return []

        # 构建允许的 step_id 集合（只有这些步骤可以被包含）
        allowed_ids = set(s.get("step_id", "") for s in steps)

        # 构建 next_step 映射（只包含允许的步骤）
        next_map = {}
        step_ids = set()
        # 收集条件分支步骤ID（仅作为 next_step_on_fail 目标的步骤）
        conditional_branch_ids = set()
        for step in steps:
            step_id = step.get("step_id", "")
            step_ids.add(step_id)
            next_map[step_id] = step.get("next_step", "")
            # 如果是条件节点，记录其失败分支步骤
            if step.get("type") == "condition":
                on_fail = step.get("next_step_on_fail", "")
                if on_fail:
                    conditional_branch_ids.add(on_fail)

        # 查找起始步骤（没有被其他步骤指向的）
        # 注意：也要包含 next_step_on_fail 的值，因为条件分支步骤只被 next_step_on_fail 指向
        pointed_to = set(next_map.values()) - {""}
        # 添加条件分支步骤的目标到 pointed_to，防止它们被当作起始步骤
        for step in steps:
            if step.get("type") == "condition":
                on_fail = step.get("next_step_on_fail", "")
                if on_fail:
                    pointed_to.add(on_fail)
        start_candidates = [s for s in steps
                           if s.get("step_id", "") not in pointed_to]

        if not start_candidates:
            return steps

        # 从起始步骤开始，沿 next_step 链排列
        result = []
        visited = set()

        for start_step in start_candidates:
            current_id = start_step.get("step_id", "")
            while current_id and current_id not in visited:
                if current_id not in self._step_id_map:
                    break
                if current_id not in allowed_ids:
                    break

                visited.add(current_id)
                current_step = self._step_id_map[current_id]
                result.append(current_step)

                # 遇到条件节点时，将 next_step_on_fail 路径上的步骤插入到 condition 之后
                if current_step.get("type") == "condition":
                    condition_step_id = current_id
                    next_on_fail = current_step.get("next_step_on_fail", "")

                    # 收集 fail 分支上所有需要插入的步骤（直到与主路径汇合）
                    fail_steps_to_insert = []
                    fail_visited = set()
                    fail_id = next_on_fail
                    main_next = current_step.get("next_step", "")

                    while fail_id and fail_id != main_next:
                        if fail_id in self._step_id_map and fail_id in allowed_ids:
                            if fail_id not in fail_visited:
                                fail_steps_to_insert.append(self._step_id_map[fail_id])
                                fail_visited.add(fail_id)
                                # 记录条件可选映射
                                self._conditional_optional_map[fail_id] = condition_step_id
                        # 继续沿 fail 分支走
                        fail_step = self._step_id_map.get(fail_id, {})
                        fail_id = fail_step.get("next_step", "")

                    # 把 fail 分支步骤插入到 result 中（condition 之后）
                    result.extend(fail_steps_to_insert)
                    # 同步标记到 visited，防止最后的兜底循环重复追加
                    visited.update(fail_visited)

                # 继续沿主路径的 next_step 走
                current_id = current_step.get("next_step", "")

        # 添加未访问的步骤（兜底，防止遗漏）
        for step in steps:
            step_id = step.get("step_id", "")
            if step_id not in visited:
                result.append(step)
                visited.add(step_id)

        return result
    
    # ===== 属性模式导航方法 =====
    
    def is_attribute_mode(self) -> bool:
        """是否使用属性模式（始终返回 True）"""
        return True
    
    @property
    def conditional_optional_map(self) -> Dict[str, str]:
        """条件可选步骤映射: step_id -> 依赖的 condition step_id

        条件可选步骤只在对应 condition 的 condition_result=False 时才执行。
        UI 层可据此根据条件结果动态隐藏/显示进度条中的步骤。
        """
        return self._conditional_optional_map

    def get_start_step(self) -> Optional[Dict[str, Any]]:
        """获取流程起始步骤"""
        if self._start_step_id and self._start_step_id in self._step_id_map:
            return self._step_id_map[self._start_step_id]
        return None
    
    def get_next_step_config(self, step_id: str, 
                              condition_result: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        """获取下一步骤的配置（属性模式）
        
        Args:
            step_id: 当前步骤 ID
            condition_result: 条件评估结果（仅 condition 类型需要）
                - True: 条件满足（YES/pass）
                - False: 条件不满足（NO/fail）
                - None: 非条件节点或不需要条件评估
        
        Returns:
            下一步骤的配置字典，如果没有下一步返回 None
        """
        step = self._step_id_map.get(step_id)
        if not step:
            return None
        
        step_type = step.get("type", "")
        
        if step_type == "condition" and condition_result is not None:
            # 条件节点：根据条件结果选择分支
            if condition_result:
                next_id = step.get("next_step", "")
            else:
                next_id = step.get("next_step_on_fail", "")
        else:
            # 普通步骤：使用 next_step
            next_id = step.get("next_step", "")
        
        if not next_id:
            return None
        
        return self._step_id_map.get(next_id)
    
    def get_loop_steps(self, loop_name: str) -> List[Dict[str, Any]]:
        """获取指定循环组内的所有步骤（按 next_step 顺序）"""
        return self._loop_groups.get(loop_name, [])
    
    def _find_next_step_after_loop(self, loop_name: str) -> str:
        """查找循环组执行完成后的下一步骤 ID
        
        遍历循环组中的所有步骤，找到 next_step 指向循环外的步骤。
        如果没有找到，返回空字符串。
        """
        loop_steps = self._loop_groups.get(loop_name, [])
        for step in loop_steps:
            next_id = step.get("next_step", "")
            if next_id:
                next_step = self._step_id_map.get(next_id)
                if next_step:
                    next_level = next_step.get("step_level", "top_level")
                    next_loop = next_step.get("loop_name", "")
                    # 如果下一步是顶层步骤或属于不同循环组
                    if next_level == "top_level" or next_loop != loop_name:
                        return next_id
        return ""
    
    def get_all_loop_names(self) -> List[str]:
        """获取所有循环组名称"""
        return list(self._loop_groups.keys())
    
    def get_loop_name_for_step(self, step_id: str) -> str:
        """获取步骤所属的循环组名称"""
        step = self._step_id_map.get(step_id)
        if not step:
            return ""
        return step.get("loop_name", "")
    
    def get_step_level(self, step_id: str) -> str:
        """获取步骤的层级"""
        step = self._step_id_map.get(step_id)
        if not step:
            return "top_level"
        return step.get("step_level", "top_level")
    
    def is_step_in_loop_group(self, step_id: str, loop_name: str) -> bool:
        """检查步骤是否属于指定循环组"""
        step = self._step_id_map.get(step_id)
        if not step:
            return False
        return step.get("loop_name", "") == loop_name
    
    def get_top_level_steps_ordered(self) -> List[Dict[str, Any]]:
        """获取按 next_step 顺序排列的顶层步骤列表"""
        return self._top_level_steps
    
    def get_inner_steps_ordered(self, loop_name: str) -> List[Dict[str, Any]]:
        """获取按 next_step 顺序排列的循环内步骤列表"""
        return self._loop_groups.get(loop_name, [])
    
    def get_display_inner_steps(self, loop_name: str) -> List[Dict[str, Any]]:
        """获取用于显示的循环内步骤列表（含条件分支展开）
        
        在主路径步骤的基础上，当遇到条件节点时，将条件分支步骤
        （next_step_on_fail 路径上的步骤）插入到条件节点的位置。
        这样可以在 UI 中正确显示条件分支的所有步骤。
        """
        loop_steps = self._loop_groups.get(loop_name, [])
        result = []
        added_ids = set()  # 记录已添加的步骤 ID，防止重复
        
        for step in loop_steps:
            step_id = step.get("step_id", "")
            step_type = step.get("type", "")
            
            if step_type == "condition":
                # 条件节点：添加条件分支步骤（next_step_on_fail 路径上的步骤）
                next_on_fail = step.get("next_step_on_fail", "")
                
                # 添加失败分支的起始步骤
                if next_on_fail and next_on_fail in self._step_id_map:
                    if next_on_fail not in added_ids:
                        fail_step = self._step_id_map[next_on_fail]
                        result.append(fail_step)
                        added_ids.add(next_on_fail)
                    
                    # 继续沿失败分支的 next_step 走，直到与主路径汇合
                    fail_next = fail_step.get("next_step", "")
                    main_next = step.get("next_step", "")
                    while fail_next and fail_next != main_next:
                        if fail_next in self._step_id_map and fail_next not in added_ids:
                            result.append(self._step_id_map[fail_next])
                            added_ids.add(fail_next)
                        # 继续沿失败分支走
                        fail_next_step = self._step_id_map.get(fail_next, {})
                        fail_next = fail_next_step.get("next_step", "")
            else:
                # 非条件步骤：直接添加
                if step_id not in added_ids:
                    result.append(step)
                    added_ids.add(step_id)
        
        return result
    
    def get_all_step_configs_flat(self) -> List[Dict[str, Any]]:
        """获取所有步骤的扁平列表（属性模式专用）"""
        return list(self._step_id_map.values())

    def get_flow_steps(self) -> List[Dict[str, Any]]:
        """获取流程步骤列表"""
        return self.steps

    def get_loop_node_config(self, node_id: str) -> Optional[Dict[str, Any]]:
        """获取循环节点的配置
        
        从 args_config.loop_nodes 中查找指定 node_id 的配置
        """
        loop_nodes = self.raw.get("args_config", {}).get("loop_nodes", [])
        for loop_config in loop_nodes:
            if loop_config.get("node_id") == node_id:
                return loop_config
        return None

    def get_step_by_id(self, step_id: str) -> Optional[Dict[str, Any]]:
        """查找步骤定义"""
        return self._step_id_map.get(step_id)

    def get_step_by_role(self, role: str) -> Optional[Dict[str, Any]]:
        """通过 role 查找步骤定义"""
        for step in self.steps:
            if step.get("role") == role:
                return step
        return None

    def get_step_id_by_role(self, role: str) -> str:
        """获取指定角色的 step_id"""
        step = self.get_step_by_role(role)
        return step.get("step_id", "") if step else ""

    def get_all_step_configs(self) -> List[Dict[str, Any]]:
        """获取所有步骤配置列表"""
        return [s for s in self.steps if "step_id" in s]

    def get_all_step_ids(self) -> List[str]:
        """获取所有步骤 ID 列表"""
        return [s.get("step_id", "") for s in self.get_all_step_configs()]

    def get_outer_step_ids(self) -> List[str]:
        """获取所有外层步骤的 step_id"""
        return [s.get("step_id", "") for s in self._top_level_steps]

    def get_inner_step_ids(self) -> List[str]:
        """获取所有内层步骤的 step_id（所有循环内的步骤）"""
        inner_ids = []
        for loop_name, steps in self._loop_groups.items():
            for step in steps:
                step_id = step.get("step_id", "")
                if step_id:
                    inner_ids.append(step_id)
        return inner_ids

    def get_all_loop_step_ids(self) -> List[str]:
        """获取所有循环步骤的 ID 列表"""
        return self.get_all_loop_names()

    def get_inner_steps_for_loop(self, loop_step_id: str) -> List[Dict[str, Any]]:
        """获取循环步骤的内层步骤定义（供显示层使用，条件节点已被展开）"""
        loop_name = loop_step_id
        # 先尝试直接匹配 loop_name
        if loop_name in self._loop_groups:
            return self.get_display_inner_steps(loop_name)
        # 从 loop_nodes 配置中获取 node_id
        loop_node_config = self.get_loop_node_config(loop_step_id)
        if loop_node_config:
            node_id = loop_node_config.get("node_id", loop_step_id)
            if node_id in self._loop_groups:
                return self.get_display_inner_steps(node_id)
        return []

    def get_raw_inner_steps_for_loop(self, loop_step_id: str) -> List[Dict[str, Any]]:
        """获取循环步骤的原始内层步骤定义（供逻辑层使用，保留条件节点）"""
        loop_name = loop_step_id
        loop_node_config = self.get_loop_node_config(loop_step_id)
        if loop_node_config:
            node_id = loop_node_config.get("node_id", loop_step_id)
            if node_id in self._loop_groups:
                return self._loop_groups[node_id]
        if loop_name in self._loop_groups:
            return self._loop_groups[loop_name]
        return []

    def get_condition_config(self, step_id: str) -> Dict[str, Any]:
        """获取条件节点的配置"""
        step = self.get_step_by_id(step_id)
        if step and step.get("type") == "condition":
            return {
                "check_step": step.get("check_step", ""),
                "check_condition": step.get("check_condition", ""),
                "condition_expression": step.get("condition", ""),
                "evaluate_by": step.get("evaluate_by", ""),
                "yes_value": step.get("yes_value", "pass"),
                "no_value": step.get("no_value", "fail"),
                "next_step": step.get("next_step", ""),
                "next_step_on_fail": step.get("next_step_on_fail", ""),
            }
        return {}
