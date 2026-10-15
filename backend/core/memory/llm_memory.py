# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : llm_memory.py
# @Desc    : LLM推理专用内存
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
LLMMemory - LLM推理专用内存

【核心职责】
- 从memorycore压缩生成LLM友好格式
- 供LLM推理使用
- 自行决定同步时机，不依赖事件通知
"""

import json
from typing import Dict


class LLMMemory:
    """
    LLM推理专用内存
    
    设计原则：
    - 主动获取模式：自行决定何时从MemoryDatabase同步
    - 单向依赖：只依赖memorycore数据结构，不依赖具体类
    - 数据格式：自然语言友好，便于LLM理解
    """

    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.current = {}

    def _log(self, message: str):
        """日志记录"""
        print(message)
        if self.log_callback:
            self.log_callback(message)

    def _clean_llm_key(self, key: str, level: int) -> str:
        """
        【LLM压缩工具】清洗技术前缀，只保留核心语义
        
        移除规则：level 0 只保留第一个下划线前的部分
                 level 1+ 移除 ["base", "target", "memorycore", "curve", "ecocycle"]
        
        目的：给LLM看的key要干净，去掉工程师技术前缀
        """
        if "_" not in key:
            return key
        
        parts = key.split("_")
        
        if level == 0:
            return parts[0]
        else:
            result = []
            for p in parts:
                if p in ["base", "target", "memorycore", "curve", "ecocycle"]:
                    continue
                result.append(p)
            return "_".join(result) if result else key

    def _compress_param_item(self, item: dict) -> list:
        """
        【LLM压缩工具】参数项压缩
        
        优化策略：
        1. "值"和"单位"合并成单一字符串："100 km"
        2. 去掉所有空单位（"Null"也视为空）
        3. 多类型参数展开为独立条目
        4. 输出格式: [{"参数名": "值 单位"}, ...]
        
        目的：LLM读起来更自然，不需要理解嵌套结构
        """
        if "参数值" in item:
            name = item.get("名称", "")
            result = []
            for pv in item["参数值"]:
                sub_name = pv.get("名称", "")
                full_name = f"{name}_{sub_name}" if name else sub_name
                val = str(pv.get("值", ""))
                unit = item.get("单位", "")
                if unit and unit != "Null":
                    result.append({full_name: f"{val} {unit}"})
                else:
                    result.append({full_name: val})
            return result
        else:
            name = item.get("名称", "")
            unit = item.get("单位", "")
            if unit and unit != "Null":
                unit_suffix = f" {unit}"
            else:
                unit_suffix = ""
            
            val = str(item.get("值", ""))
            return [{name: f"{val}{unit_suffix}"}]

    def compress(self, source_data: Dict) -> Dict:
        """
        压缩转换（递归遍历整个memorycore）
        
        压缩流程：
        1. Key清洗：移除所有工程师技术前缀
        2. Value压缩：参数值与单位合并
        3. 扁平化：消除工程师友好的嵌套层级
        
        设计目标：
        - 尽可能接近人类自然语言表达方式
        - 去掉所有只有工程师懂的命名约定
        - LLM可以直接用做推理上下文（token也更少）
        """
        def compress_node(node, level=0):
            if isinstance(node, dict):
                result = {}
                for raw_key, value in node.items():
                    clean_key = self._clean_llm_key(raw_key, level)
                    result[clean_key] = compress_node(value, level + 1)
                return result
            
            elif isinstance(node, list):
                result = []
                for item in node:
                    if isinstance(item, dict):
                        compressed_list = self._compress_param_item(item)
                        result.extend(compressed_list)
                    else:
                        result.append(item)
                return result
            
            else:
                return node
        
        return compress_node(source_data)

    def sync_from_memorycore(self, memorycore: Dict):
        """
        从MemoryCore同步数据
        
        LLMMemory自行决定何时调用此方法同步数据
        不依赖MemoryDatabase的事件通知
        
        Args:
            memorycore (Dict): MemoryDatabase的memorycore数据
        """
        self.current = self.compress(memorycore)
        self._log("  [OK] LLMMemory 已从MemoryCore同步数据")

    def format_to_str(self) -> str:
        """LLMMemory 转 JSON 可视化字符串"""
        return json.dumps(self.current, indent=4, ensure_ascii=False)