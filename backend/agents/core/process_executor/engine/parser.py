# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : parser.py
# @Desc    : 流程解析器 - 解析 process.yaml 生成流程定义
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
流程解析器

职责：
1. 解析 process.yaml 配置文件
2. 生成 ProcessDefinition 流程定义对象
3. 将流程定义转换为 ProcessController 所需的 StepDefinition 列表
"""

from __future__ import annotations

import yaml
from typing import Any, Dict, List, Tuple

from ..data_structures import StepDefinition, ProcessDefinition


class ProcessParser:
    """流程解析器 - 解析 process.yaml 生成流程定义"""

    @staticmethod
    def parse(yaml_path: str) -> ProcessDefinition:
        """解析 YAML 文件

        Args:
            yaml_path: process.yaml 文件路径

        Returns:
            ProcessDefinition: 流程定义对象
        """
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"流程配置文件为空: {yaml_path}")

        if "steps" not in data:
            raise ValueError(f"流程配置缺少 steps 定义: {yaml_path}")

        return ProcessDefinition(data)

    @staticmethod
    def to_step_definitions(workflow: ProcessDefinition) -> List[StepDefinition]:
        """将流程定义转换为步骤定义列表

        属性模式：创建扁平的步骤列表，顶层步骤和循环内步骤都在同一层级。
        循环组作为特殊的 "loop" 类型状态存在，包含循环内步骤作为子状态。

        Args:
            workflow: 流程定义对象

        Returns:
            List[StepDefinition]: 步骤定义列表
        """
        return ProcessParser._build_attribute_step_definitions(workflow)

    @staticmethod
    def _build_attribute_step_definitions(workflow: ProcessDefinition) -> List[StepDefinition]:
        """构建属性模式的步骤定义列表

        属性模式下：
        1. 顶层步骤按 next_step 顺序排列
        2. 循环组作为特殊的 "loop" 类型步骤，包含其内部步骤作为子状态
        3. 循环内步骤按 next_step 顺序排列在对应循环组下
        4. 循环组插入到触发它的顶层步骤之后，保持正确的视觉顺序

        这样 controller 的状态树可以正确反映流程结构，
        而引擎通过 next_step 图控制实际执行顺序。
        """
        result = []
        added_step_ids = set()  # 已添加的步骤ID
        added_loop_names = set()  # 已添加的循环名

        # 构建循环组映射: loop_name -> loop_def
        loop_defs = {}
        for loop_name in workflow.get_all_loop_names():
            loop_steps = workflow.get_loop_steps(loop_name)
            loop_node_config = workflow.get_loop_node_config(loop_name)

            # 构建循环内的子步骤
            sub_steps = []
            for step_data in loop_steps:
                sub_def = ProcessParser._parse_step(step_data)
                sub_steps.append(sub_def)

            # 获取循环项配置
            loop_items = []
            if loop_node_config:
                source_config = loop_node_config.get("source", {})
                if source_config:
                    source_type = source_config.get("type", "")
                    if source_type == "function":
                        pass

            # 构建 metadata
            metadata = {
                "loop_type": loop_node_config.get("loop_type", "parallel") if loop_node_config else "parallel",
                "item_arg": loop_node_config.get("item_arg", "loop_item") if loop_node_config else "loop_item",
                "source": loop_node_config.get("source", {}) if loop_node_config else {},
                "attribute_mode": True,
            }

            # 创建循环组的 StepDefinition
            loop_def = StepDefinition(
                step_id=loop_name,
                step_name=loop_name,
                step_type="loop",
                sub_steps=sub_steps,
                loop_items=loop_items,
                metadata=metadata,
                loop_type="parallel",
            )
            loop_defs[loop_name] = loop_def

        # 按 next_step 链顺序构建结果列表
        # 从起始步骤开始遍历，遇到循环组时插入
        start_step_id = workflow._start_step_id
        current_id = start_step_id

        while current_id:
            step_data = workflow._step_id_map.get(current_id)
            if not step_data:
                break

            step_level = step_data.get("step_level", "top_level")
            loop_name = step_data.get("loop_name", "")
            step_id = step_data.get("step_id", "")

            if step_level == "top_level":
                # 添加顶层步骤
                if step_id not in added_step_ids:
                    step_def = ProcessParser._parse_step(step_data)
                    result.append(step_def)
                    added_step_ids.add(step_id)

                # 检查 next_step 是否指向循环内步骤
                next_id = step_data.get("next_step", "")
                if next_id:
                    next_data = workflow._step_id_map.get(next_id)
                    if next_data:
                        next_level = next_data.get("step_level", "top_level")
                        next_loop = next_data.get("loop_name", "")
                        if next_level == "loop_level" and next_loop:
                            # 插入循环组
                            if next_loop not in added_loop_names and next_loop in loop_defs:
                                result.append(loop_defs[next_loop])
                                added_loop_names.add(next_loop)
                            # 跳过循环内步骤，直接到循环出口
                            current_id = workflow._find_next_step_after_loop(next_loop)
                            if current_id:
                                continue
                            else:
                                break
                        else:
                            current_id = next_id
                            continue
                    else:
                        break
                else:
                    # 没有 next_step，流程结束
                    break

            elif step_level == "loop_level":
                # 找到对应循环组，确保已插入
                if loop_name and loop_name not in added_loop_names and loop_name in loop_defs:
                    result.append(loop_defs[loop_name])
                    added_loop_names.add(loop_name)
                # 找到循环的出口点
                if loop_name:
                    current_id = workflow._find_next_step_after_loop(loop_name)
                    if current_id:
                        continue
                break
            else:
                break

        # 添加未在链中的顶层步骤（如孤立的步骤）
        # 注意：_top_level_steps 里包含 synthetic loop step（由 data_structures.py
        # _build_attribute_navigation 注入的导航辅助标记），它的 step_id = loop_name。
        # 主循环已经通过 added_loop_names 插入了真正的 loop StepDefinition（带 sub_states），
        # 这里不能再把 synthetic 空壳加一遍——否则 states_tree 会出现重复 loop 节点。
        top_steps = workflow.get_top_level_steps_ordered()
        for step_data in top_steps:
            step_id = step_data.get("step_id", "")
            # synthetic loop step 检查 added_loop_names，普通 step 检查 added_step_ids
            if step_id in added_loop_names or step_id in added_step_ids:
                continue
            step_def = ProcessParser._parse_step(step_data)
            result.append(step_def)
            added_step_ids.add(step_id)

        # 添加未插入的循环组
        for loop_name, loop_def in loop_defs.items():
            if loop_name not in added_loop_names:
                result.append(loop_def)
                added_loop_names.add(loop_name)

        return result

    @staticmethod
    def _parse_step(step_data: Dict[str, Any]) -> StepDefinition:
        """递归解析单个步骤定义（属性模式）

        Args:
            step_data: YAML 中的步骤数据

        Returns:
            StepDefinition: 步骤定义对象
        """
        step_id = step_data.get("step_id", "")
        step_name = step_data.get("step_name", step_id)
        step_type = step_data.get("type", "step")

        metadata = {}
        for key in ["config_file", "agent_id",
                     "query_mode", "description", "iterate_over",
                     "check_step", "check_condition"]:
            if key in step_data:
                metadata[key] = step_data[key]

        sub_steps = []
        if "inner_steps" in step_data:
            for inner_data in step_data["inner_steps"]:
                inner_def = ProcessParser._parse_step(inner_data)
                sub_steps.append(inner_def)

        # 解析循环类型
        loop_type = step_data.get("loop_type", "parallel")

        # 解析条件分支字段
        condition_expr = step_data.get("condition", "")
        check_step = step_data.get("check_step", "")
        check_condition = step_data.get("check_condition", "")

        # 属性模式字段
        step_level = step_data.get("step_level", "top_level")
        loop_name = step_data.get("loop_name", "")
        next_step = step_data.get("next_step", "")
        next_step_on_fail = step_data.get("next_step_on_fail", "")

        return StepDefinition(
            step_id=step_id,
            step_name=step_name,
            step_type=step_type,
            sub_steps=sub_steps,
            loop_items=[],
            metadata=metadata,
            loop_type=loop_type,
            condition=condition_expr,
            check_step=check_step,
            check_condition=check_condition,
            step_level=step_level,
            loop_name=loop_name,
            next_step=next_step,
            next_step_on_fail=next_step_on_fail,
        )
