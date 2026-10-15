# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : memory_database.py
# @Desc    : 内存数据库核心模块
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
内存数据库核心模块 - 极简过渡版

参照：内存数据库说明文档.txt 第14-36行六部分架构定义
此模块是整个系统的唯一数据真相源，实现五部分完整数据结构：

【第0部分】原始Excel数据容器 - data
【第1部分】计算标识映射 - calctypeid（按车型分组的计算参数标识）
【第2部分】车型后缀列表 - vehsuffix（车型维度枚举）
【第3部分】驾驶循环工况 - ecocycle（时间序列曲线类参数）
【第4部分】内存核心数据库 - memorycore（完整版：按Sheet/车型/分类分层）

【第5部分】LLM推理专用内存 - 已迁移至 llm_memory.py

设计原则：
- Core 层绝对干净，不碰 UI、不碰 asyncio
- 所有模块共享同一个 MemoryDatabase 实例
- 计算节点/LLM/UI 都从这里取数，唯一真相源
"""

import os
import re
import json
from typing import Dict, List, Any

from snail_avatar.backend.core.memory.excel_operator import ExcelOperator


class MemoryDatabase:
    """
    内存数据库核心类
    
    实现五部分数据结构：
    0. data - 【第0部分】原始Excel全量数据（Sheet名 -> 行数据）
    1. calctypeid - 【第1部分】计算标识映射（工程计算专用，按车型分组）
    2. vehsuffix - 【第2部分】车型后缀列表（车型维度枚举）
    3. ecocycle - 【第3部分】驾驶循环工况（表格/曲线类参数）
    4. memorycore - 【第4部分】内存核心数据库（完整版分层结构）
    
    LLM推理专用内存（第5部分）已迁移至 llm_memory.py
    LLMMemory 将自行决定何时从 memorycore 同步数据
    
    所有数据读写都通过此类，是整个系统的唯一数据真相源。
    """
    
    def __init__(self, file_path=None, log_callback=None):
        """
        初始化内存数据库
        
        Args:
            file_path (str, optional): Excel文件路径
            log_callback (callable, optional): 日志回调函数 fn(message)
        """
        self.file_path = file_path
        self.log_callback = log_callback
        
        self.excel_op = ExcelOperator(log_callback)
        
        # =====================================================================
        # 五部分数据结构（整个系统的唯一真相源）
        # =====================================================================
        
        # 第0部分: 原始Excel数据容器
        # 来源: ExcelOperator 读取的所有Sheet原始数据
        # 用途: 结构化的数据源，其他部分都从这里提取
        # 结构: {sheet_name: [{"名称", "单位", "车型,增程,值", ...}, ...]}
        self.data = {}

        # 第1部分: vehsuffix - 车型后缀列表（用于动态识别和计算循环）
        # 结构: [{"后缀", "车型", "描述", ...}, ...]
        self.vehsuffix = []
        
        # 第2部分: memorycore - 内存核心数据库
        # 来源: Excel 中 xxx_memorycore Sheet 提取并深度结构化
        # 用途: 完整版，按Sheet/车型/分类/数据类型分层
        # 结构: {veh_name: {sheet_name: {cat1: {cat2: [{"名称", "db_key", "值"}, ...]}}}}
        self.memorycore = {}
        
        # 第3部分: inter_data - 中间变量存储（永久保存）
        # 结构: {veh_name: {workflow_id: {node_id: {var_name: value, ...}, ...}, ...}, ...}
        # 第一层: 车型（从 calctypeid 自动识别）
        # 第二层: 计算内容（如 eco、power，对应 WorkflowTab）
        # 第三层: 节点名称（计算节点的实例ID）
        self.inter_data = {}

        # 第4部分: ecocycle - 驾驶循环工况
        # 来源: Excel 中 xxx_ecocycle Sheet 直接复制
        # 用途: 表格或者曲线类参数（计算工况或者零部件级参数）
        # 结构: [{"时间_s", "车速_kmh", ...}, ...]
        self.ecocycle = []
        
        self._log("\n=== MemoryDatabase 初始化完成 ===")
        self._log("  [OK] ExcelOperator - 文件读取")
        self._log("  [OK] MemoryDatabase - 五部分容器初始化完成")
        self._log("  [OK] LLMMemory - 已迁移至 llm_memory.py")
    
    def _log(self, message: str):
        """
        日志记录（与UI完全解耦，只调用回调函数）
        
        Args:
            message (str): 日志消息
        """
        print(message)
        if self.log_callback:
            self.log_callback(message)
    
    def load_from_excel(self, file_path=None):
        """
        从Excel文件加载全部数据并完成结构化
        
        执行流程：
        1. 调用 ExcelOperator 读取所有Sheet
        2. 触发 _after_load_hook 完成五部分结构化
        3. LLMMemory 将自行决定何时同步数据
        
        Args:
            file_path (str, optional): 覆盖初始化时的路径
        
        Returns:
            dict: 原始Excel全量数据
        """
        if file_path:
            self.file_path = file_path
        
        self._log(f"\n=== MemoryDatabase: 加载Excel ===")
        
        self.data = self.excel_op.read_all_sheets(self.file_path)
        
        self._log(f"\n  [OK] 加载完成: {len(self.data)} 个Sheet")
        
        self._after_load_hook()
        
        return self.data
    
    def get_sheet(self, sheet_name: str) -> List[Dict]:
        """
        获取指定Sheet的原始数据
        
        Args:
            sheet_name (str): Sheet名称
        
        Returns:
            List[Dict]: Sheet行数据列表
        """
        return self.data.get(sheet_name, [])
    
    def get_all_sheets(self) -> Dict[str, List[Dict]]:
        """
        获取所有Sheet原始数据
        
        Returns:
            Dict[str, List[Dict]]: {Sheet名: 行数据列表}
        """
        return self.data
    
    def sheet_names(self) -> List[str]:
        """
        获取所有Sheet名称列表
        
        Returns:
            List[str]: Sheet名称列表
        """
        return list(self.data.keys())

    # =========================================================================
    # 标准化标识符清洗规则，转小写等
    # =========================================================================
        
    def _clean_identifier(self, s: str) -> str:
        """
        标准化标识符清洗规则
        
        清洗步骤：
        1. 转小写
        2. 移除所有空格
        3. 只保留中文、小写字母、数字、下划线、逗号
        4. 移除所有其他特殊字符
        
        用途：
        - db_key 生成时统一命名规则
        - 车型名称标准化
        - 参数标识清洗
        
        Args:
            s (str): 原始标识符字符串
        
        Returns:
            str: 清洗后的标准标识符
        """
        if not s:
            return ""
        
        s = str(s).lower().replace(" ", "")
        s = re.sub(r'[^\u4e00-\u9fa5a-z0-9_,]', '', s)
        
        return s
    
    def _extract_common_fields(self, item: dict) -> dict:
        """
        【结构化工具】提取非车型相关的公共字段
        
        遍历item所有key，过滤掉以"车型,"开头的列，剩下的就是所有车型共享的字段
        
        Args:
            item (dict): 原始数据行
        
        Returns:
            dict: 公共字段字典
        """
        common = {}
        
        for key, value in item.items():
            if not (isinstance(key, str) and key.startswith("车型,")):
                common[key] = value
        
        return common
    
    def _extract_veh_from_item_target(self, item: dict) -> dict:
        """
        【结构化工具】从一行数据中按车型拆分目标字段
        
        Excel中一行数据可能包含多车型目标值，格式为：
        "车型,增程,目标值,type" / "车型,纯电,仿真值,calctypeid"
        
        本函数负责：
        1. 识别并提取所有以"车型,"开头的列
        2. 按车型名称分组
        3. 清洗车型名称作为分组key
        
        Args:
            item (dict): 原始数据行（包含多车型目标值）
        
        Returns:
            dict: {veh_name: {完整字段名: 值, ...}, ...}
        """
        result = {}
        
        for k, v in item.items():
            if not (isinstance(k, str) and k.startswith("车型,")):
                continue
            
            parts = k.split(",")
            if len(parts) < 2:
                continue
            
            veh_name = self._clean_identifier(parts[1])
            
            if veh_name not in result:
                result[veh_name] = {}
            
            result[veh_name][k] = v
        
        return result
    
    def _build_db_key_from_raw_fields(self, raw_fields: dict, veh_name: str) -> tuple:
        """
        【结构化工具】从原始字段构建标准 db_key
        
        db_key 命名规则（全链路一致）：
        - 三段式: {base_key}_{type_suffix}_{veh_suffix}
        - 二段式: {base_key}_{veh_suffix}
        - 一段式: {base_key}
        
        所有组成部分都经过 _clean_identifier 标准化
        
        Args:
            raw_fields (dict): 车型分组后的原始字段
            veh_name (str): 车型名称（用于提取车型后缀）
        
        Returns:
            tuple: (标准db_key, 参数值)
        """
        fields = {}
        for full_key, value in raw_fields.items():
            parts = full_key.split(",")
            if len(parts) >= 3:
                field_type = parts[-1]
                fields[field_type] = value
            if len(parts) >= 4:
                fields["type_suffix"] = parts[2]
        
        base_key = fields.get("base_key", "")
        type_suffix = fields.get("type_suffix", "")
        
        if "_" in type_suffix:
            type_suffix = type_suffix.split("_")[-1]
        
        if "_" in veh_name:
            veh_suffix = veh_name.split("_")[-1]
        else:
            veh_suffix = veh_name
        
        base_key = self._clean_identifier(base_key)
        type_suffix = self._clean_identifier(type_suffix)
        veh_suffix = self._clean_identifier(veh_suffix)
        
        if base_key and type_suffix and veh_suffix:
            db_key = f"{base_key}_{type_suffix}_{veh_suffix}"
        elif base_key and veh_suffix:
            db_key = f"{base_key}_{veh_suffix}"
        else:
            db_key = base_key
        
        return (db_key, fields.get("值"))
    
    def _build_param_values(self, raw_fields: dict, veh_name: str) -> dict:
        """
        【结构化工具】构建参数值结构（处理多类型同参情况）
        
        处理场景：
        - 单一类型场景: 直接返回 {db_key, 值}
        - 多类型场景: 如"目标值/仿真值/达标标识"，返回 {"参数值": [类型1, 类型2, ...]}
        
        Args:
            raw_fields (dict): 车型分组后的原始字段
            veh_name (str): 车型名称
        
        Returns:
            dict: 参数值结构（单一值或多类型列表）
        """
        groups = {}
        for full_key, value in raw_fields.items():
            parts = full_key.split(",")
            if len(parts) < 3:
                continue
            
            field_type = parts[-1]
            
            if len(parts) >= 4:
                type_suffix = parts[2]
                if "_" in type_suffix:
                    type_name = type_suffix.split("_")[0]
                else:
                    type_name = type_suffix
            else:
                type_suffix = ""
                type_name = "默认"
            
            key = (type_suffix, type_name)
            if key not in groups:
                groups[key] = {}
            
            groups[key][field_type] = value
        
        if len(groups) == 1:
            key = list(groups.keys())[0]
            fields = groups[key]
            db_key, _ = self._build_db_key_from_raw_fields(raw_fields, veh_name)
            return {
                "db_key": db_key,
                "值": fields.get("值")
            }
        
        else:
            param_values = []
            for (type_suffix, type_name), fields in groups.items():
                temp_fields = {}
                for full_key, value in raw_fields.items():
                    if type_suffix in full_key:
                        temp_fields[full_key] = value
                
                db_key, _ = self._build_db_key_from_raw_fields(temp_fields, veh_name)
                
                param_values.append({
                    "名称": type_name,
                    "db_key": db_key,
                    "值": fields.get("值")
                })
            
            return {
                "参数值": param_values
            }

     # =========================================================================
   
    # =========================================================================
    # 【第1部分结构化】VehSuffix 车型后缀列表 ；以及根据字段匹配值的查询方法
    # =========================================================================

    def _extract_vehsuffix(self):
        """
        【第1部分结构化】VehSuffix 车型后缀列表

        直接复制Sheet内容，不需要结构化
        用途：车型维度枚举，用于动态识别和计算循环

        注意：对所有字段值进行清洗，保持与 memorycore 中 db_key 格式一致
        """
        for sheet_name in self.sheet_names():
            if sheet_name.lower().endswith("vehsuffix"):
                raw_vehsuffix = self.get_sheet(sheet_name)
                self.vehsuffix = []
                for item in raw_vehsuffix:
                    cleaned_item = item.copy()
                    # 对所有字段值进行清洗（仅清洗字符串类型）
                    for key, value in cleaned_item.items():
                        if isinstance(value, str):
                            cleaned_item[key] = self._clean_identifier(value)
                    self.vehsuffix.append(cleaned_item)
                self._log(f"  [OK] VehSuffix 复制完成: {len(self.vehsuffix)} 条配置")
                break
    
    def get_vehsuffix(self, **kwargs) -> List[Dict]:
        """
        获取 VehSuffix 车型后缀列表，支持按字段匹配查询
        
        Args:
            **kwargs: 过滤条件，如 车型="增程车型", 车型后缀="reevlto", 能源形式="ev"
        
        Returns:
            List[Dict]: 匹配的车型列表
            
        示例:
            # 获取所有车型
            all_vehicles = memory_db.get_vehsuffix()
            
            # 根据车型名称查询
            vehicle = memory_db.get_vehsuffix(车型="增程车型")
            
            # 根据能源形式查询
            ev_vehicles = memory_db.get_vehsuffix(能源形式="ev")
            
            # 组合条件查询
            target = memory_db.get_vehsuffix(车型="纯电车型", 车型后缀="evlto")
        """
        if not kwargs:
            return self.vehsuffix
        
        result = []
        for veh in self.vehsuffix:
            match = True
            for key, value in kwargs.items():
                if veh.get(key) != value:
                    match = False
                    break
            if match:
                result.append(veh)
        
        return result
    
    # =========================================================================
    # 【第2部分结构化】MemoryCore 内存核心数据库 ；以及SSTS和VTS 参数的读写方法
    # =========================================================================

    def _extract_memorycore(self):
        """
        【第2部分结构化】MemoryCore 内存核心数据库
        
        深度结构化流程：
        1. 查找以 memorycore 结尾的所有Sheet
        2. Level 1: 按车型分组 -> {veh_name: ...}
        3. Level 2: 按Sheet分组 -> {sheet_name: ...}
        4. Level 3: 按类别一级/二级分组 -> {cat1: {cat2: ...}}
        5. Level 4: 参数项列表，每个参数项:
           - 移除原始"车型,"前缀列
           - 提取并构建参数值结构（处理多类型）
           - 生成标准化 db_key
        
        最终结构: {veh_name: {sheet_name: {cat1: {cat2: [参数项列表]}}}}
        """
        structured = {}
        
        for sheet_name in self.sheet_names():
            if sheet_name.lower().endswith("memorycore"):
                sheet_data = self.get_sheet(sheet_name)
                
                for item in sheet_data:
                    common = self._extract_common_fields(item)
                    veh_fields_raw = self._extract_veh_from_item_target(item)
                    
                    for veh_name, raw_fields in veh_fields_raw.items():
                        if veh_name not in structured:
                            structured[veh_name] = {}
                        
                        if sheet_name not in structured[veh_name]:
                            structured[veh_name][sheet_name] = []
                        
                        final_item = {**common, **raw_fields}
                        structured[veh_name][sheet_name].append(final_item)
        
        for veh_name in structured:
            for sheet_name in structured[veh_name]:
                items = structured[veh_name][sheet_name]
                
                if not items:
                    continue
                
                first_item = items[0]
                has_category = "类别,一级" in first_item or "类别,二级" in first_item
                
                if not has_category:
                    continue
                
                categorized = {}
                
                for item in items:
                    cat1 = item.get("类别,一级", "") or "未分类"
                    cat2 = item.get("类别,二级", "") or "默认"
                    
                    if cat1 not in categorized:
                        categorized[cat1] = {}
                    if cat2 not in categorized[cat1]:
                        categorized[cat1][cat2] = []
                    
                    item.pop("类别,一级", None)
                    item.pop("类别,二级", None)
                    
                    categorized[cat1][cat2].append(item)
                
                structured[veh_name][sheet_name] = categorized
        
        for veh_name in structured:
            for sheet_name in structured[veh_name]:
                items = structured[veh_name][sheet_name]
                
                if isinstance(items, dict):
                    for cat1 in items:
                        for cat2 in items[cat1]:
                            for i, item in enumerate(items[cat1][cat2]):
                                raw_fields = self._extract_veh_from_item_target(item)
                                for field_key in list(item.keys()):
                                    if field_key.startswith("车型,"):
                                        item.pop(field_key, None)
                                
                                for veh_name2, raw_fields2 in raw_fields.items():
                                    if veh_name2 == veh_name:
                                        param_result = self._build_param_values(raw_fields2, veh_name2)
                                        item.update(param_result)
                else:
                    for i, item in enumerate(items):
                        raw_fields = self._extract_veh_from_item_target(item)
                        for field_key in list(item.keys()):
                            if field_key.startswith("车型,"):
                                item.pop(field_key, None)
                        
                        for veh_name2, raw_fields2 in raw_fields.items():
                            if veh_name2 == veh_name:
                                param_result = self._build_param_values(raw_fields2, veh_name2)
                                item.update(param_result)
        
        self.memorycore = structured
        
        self._log(f"  [OK] MemoryCore 结构化完成:")
        for veh_name, sheets in structured.items():
            self._log(f"      {veh_name}: {len(sheets)} 个Sheet")

    def _after_load_hook(self):
        """
        Excel加载完成后自动执行的钩子函数
        
        顺序执行四部分结构化：
        1. vehsuffix - 车型后缀列表
        2. memorycore - 内存核心数据库（最复杂的深度结构化）
        3. inter_data - 中间变量数据库（新建结构）
        4. ecocycle - 驾驶循环工况
        
        LLMMemory 将自行决定何时从 memorycore 同步数据
        """
        self._extract_vehsuffix()
        self._extract_memorycore()
        self._creat_inter()
        self._extract_ecocycle()

    def get_ssts_vts_param(self, db_key: str) -> Any:
        """
        从 MemoryCore 读取参数（支持 SSTS 和 VTS）
        
        Args:
            db_key: 完整的数据库键名（如 "mass_curb_result_reevlto"）
        
        Returns:
            Any: 参数值，如果不存在返回 None
            
        搜索范围:
            1. target_ssts及计算条件_memorycore
            2. target_vts_memorycore
        """
        # 遍历所有车型数据
        for veh_data in self.memorycore.values():
            # 遍历车型下的所有表数据
            for sheet_data in veh_data.values():
                # 处理两种数据结构：嵌套字典或直接列表
                if isinstance(sheet_data, dict):
                    for cat1_data in sheet_data.values():
                        for cat2_data in cat1_data.values():
                            for item in cat2_data:
                                if item.get("db_key") == db_key:
                                    return item.get("值")
                                if "参数值" in item:
                                    for param_item in item["参数值"]:
                                        if param_item.get("db_key") == db_key:
                                            return param_item.get("值")
                else:
                    for item in sheet_data:
                        if item.get("db_key") == db_key:
                            return item.get("值")
                        if "参数值" in item:
                            for param_item in item["参数值"]:
                                if param_item.get("db_key") == db_key:
                                    return param_item.get("值")
        return None

    def set_ssts_vts_param(self, db_key: str, value: Any) -> bool:
        """
        向 MemoryCore 写入参数（支持 SSTS 和 VTS）

        Args:
            db_key: 完整的数据库键名（如 "e_dc_result_reevlto"）
            value: 参数值

        Returns:
            bool: 是否成功写入

        写入策略:
            1. 优先匹配已存在的 db_key 进行更新
            2. 遍历所有车型进行匹配
        """
        success = False

        # 类型转换：将纯数字字符串自动转换为浮点数，非数字字符串保持原样
        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                pass

        db_key_clean = self._clean_identifier(db_key)

        total_items_scanned = 0
        matched_keys = []

        # 遍历所有车型数据
        for veh_name, veh_data in self.memorycore.items():
            # 遍历车型下的所有表数据
            for sheet_name, sheet_data in veh_data.items():
                # 处理两种数据结构：嵌套字典或直接列表
                if isinstance(sheet_data, dict):
                    for cat1_data in sheet_data.values():
                        for cat2_data in cat1_data.values():
                            for item in cat2_data:
                                total_items_scanned += 1
                                item_db_key = self._clean_identifier(item.get("db_key", ""))
                                if item_db_key == db_key_clean:
                                    item["值"] = value
                                    success = True
                                    matched_keys.append(item.get("db_key"))
                                if "参数值" in item:
                                    for param_item in item["参数值"]:
                                        param_db_key = self._clean_identifier(param_item.get("db_key", ""))
                                        if param_db_key == db_key_clean:
                                            param_item["值"] = value
                                            success = True
                                            matched_keys.append(param_item.get("db_key"))
                else:
                    for item in sheet_data:
                        total_items_scanned += 1
                        item_db_key = self._clean_identifier(item.get("db_key", ""))
                        if item_db_key == db_key_clean:
                            item["值"] = value
                            success = True
                            matched_keys.append(item.get("db_key"))
                        if "参数值" in item:
                            for param_item in item["参数值"]:
                                param_db_key = self._clean_identifier(param_item.get("db_key", ""))
                                if param_db_key == db_key_clean:
                                    param_item["值"] = value
                                    success = True
                                    matched_keys.append(param_item.get("db_key"))

        return success

    # =========================================================================
    # 【第3部分结构化】INTER 中间变量数据库；及其读写方法
    # =========================================================================

    def _creat_inter(self):
        """
        【第3部分结构化】INTER 中间变量数据库
        
        用于存储工作流节点间传递的中间变量。
        结构: inter_data[veh_name][workflow_id][node_id][var_name] = value
        
        注意：此方法不是从Excel抽取数据，而是新建中间变量结构。
        第一层车型信息从 vehsuffix 获取。
        """
        self.inter_data = {}
        
        # 从 vehsuffix 获取车型信息，初始化第一层结构
        for veh in self.vehsuffix:
            veh_name = veh.get("车型后缀", "")
            if veh_name and veh_name not in self.inter_data:
                self.inter_data[veh_name] = {}
        
        self._log(f"  [OK] INTER 中间变量数据库结构化完成: {len(self.inter_data)} 个车型")

    def set_inter_data(self, veh_name: str, workflow_id: str, node_id: str, var_name: str, value: Any):
        """
        设置 INTER 中间变量
        
        Args:
            veh_name: 车型名称
            workflow_id: 工作流标识（如 eco、power）
            node_id: 节点ID
            var_name: 变量名称
            value: 变量值
        
        存储结构: inter_data[veh_name][workflow_id][node_id][var_name] = value
        """
        if veh_name not in self.inter_data:
            self.inter_data[veh_name] = {}
        if workflow_id not in self.inter_data[veh_name]:
            self.inter_data[veh_name][workflow_id] = {}
        if node_id not in self.inter_data[veh_name][workflow_id]:
            self.inter_data[veh_name][workflow_id][node_id] = {}
        
        self.inter_data[veh_name][workflow_id][node_id][var_name] = value
        self._log(f"  [INTER] 设置: {veh_name}.{workflow_id}.{node_id}.{var_name}")

    def get_inter_data(self, veh_name: str, workflow_id: str, node_id: str, var_name: str = None) -> Any:
        """
        获取 INTER 中间变量
        
        Args:
            veh_name: 车型名称
            workflow_id: 工作流标识
            node_id: 节点ID
            var_name: 变量名称，None表示获取该节点的所有变量
        
        Returns:
            Any: 变量值或变量字典，如果不存在返回 None
        """
        if var_name:
            return self.inter_data.get(veh_name, {}).get(workflow_id, {}).get(node_id, {}).get(var_name)
        else:
            return self.inter_data.get(veh_name, {}).get(workflow_id, {}).get(node_id)

    # =========================================================================
    # 【第4部分结构化】EcoCycle 驾驶循环工况；及其读取方法
    # =========================================================================

    def _extract_ecocycle(self):
        """
        【第4部分结构化】EcoCycle 驾驶循环工况
        
        将原始驾驶循环曲线数据转换为 TimeSeries 对象列表，列表名称为"ecocycle"；列表内每个对象对应一个驾驶循环工况。
        每个对象包含以下字段：
        - name: 工况名称（如CLTC、WLTC等）
        - unit: 单位（秒(s））
        - desc: 语义描述（如"CLTC 工况"）
        - statistics: 统计信息字典，包含点数、总时间、算术平均值、最大值、最小值、时间加权平均值等
        注意：
        1. 时间轴（秒(s））必须单调递增。
        2. 数值序列（速度）必须与时间轴长度一致。
        支持多工况（CLTC、WLTC等）
        """
        import numpy as np
        from snail_avatar.backend.core.data_classes.time_series_class import TimeSeries
        
        self.ecocycle = []  # 改为 TimeSeries 对象列表
        
        for sheet_name in self.sheet_names():
            if sheet_name.lower().endswith("ecocycle"):
                raw_data = self.get_sheet(sheet_name)
                
                for item in raw_data:
                    try:
                        # 解析原始数据项
                        cycle_name = list(item.keys())[0]
                        data = item[cycle_name]
                        
                        # 提取时间字段
                        time_key = None
                        for key in data.keys():
                            if key.startswith("time_"):
                                time_key = key
                                break
                        
                        # 提取速度字段
                        velocity_key = None
                        for key in data.keys():
                            if key.startswith("velocity_"):
                                velocity_key = key
                                break
                        
                        if not time_key or not velocity_key:
                            raise ValueError(f"Missing time or velocity data in '{cycle_name}'")
                        
                        # 提取单位（去掉前缀）
                        time_unit = time_key.replace("time_", "")
                        velocity_unit = velocity_key.replace("velocity_", "")
                        
                        # 时间单位必须是秒
                        if time_unit != "s":
                            raise ValueError(f"时间单位必须是秒(s)，当前为: {time_unit}")
                        
                        time_arr = np.array(data[time_key], dtype=np.float64)
                        value_arr = np.array(data[velocity_key], dtype=np.float64)
                        
                        # 清理工况名称（大写转小写）
                        cleaned_cycle_name = self._clean_identifier(cycle_name)
                        
                        # 创建 TimeSeries 实例
                        ts = TimeSeries(
                            time=time_arr,
                            value=value_arr,
                            name=cleaned_cycle_name,   # 使用清理后的工况名称
                            unit=velocity_unit,
                            desc=f"驾驶循环工况: {cleaned_cycle_name}"
                        )
                        self.ecocycle.append(ts)
                        
                    except Exception as e:
                        self._log(f"  [WARN] 解析驾驶循环失败: {e}")
                
                self._log(f"  [OK] EcoCycle 解析完成: {len(self.ecocycle)} 个工况")
                break

    def get_ecocycle_curve(self, cycle_name: str):
        """
        根据驾驶循环名称获取对应的曲线数据
        
        Args:
            cycle_name: 驾驶循环名称（如 "wltc_cycle", "cltc_cycle"）
        
        Returns:
            TimeSeries: 驾驶循环时间序列数据实例
        
        Raises:
            ValueError: 未找到指定的驾驶循环
        """
        import numpy as np
        
        # 将输入的 cycle_name 清理为小写进行匹配
        cleaned_cycle_name = self._clean_identifier(cycle_name)
        
        # 遍历 ecocycle 列表查找匹配的循环
        for ts in self.ecocycle:
            if hasattr(ts, 'name'):
                ts_name_cleaned = self._clean_identifier(ts.name)
                if ts_name_cleaned == cleaned_cycle_name:
                    return ts  # 直接返回 TimeSeries 实例
        
        raise ValueError(f"未找到驾驶循环: {cycle_name}")

    # =========================================================================
    # JSON 可视化字符串格式化方法
    # ========================================================================= 

    def format_vehsuffix_to_str(self) -> str:
        """VehSuffix 转 JSON 可视化字符串"""
        return json.dumps(self.vehsuffix, indent=4, ensure_ascii=False)
    
    def format_ecocycle_to_str(self) -> str:
        """EcoCycle 转 JSON 可视化字符串"""
        result = [ts.to_serializable() for ts in self.ecocycle]
        return json.dumps(result, indent=4, ensure_ascii=False)
    
    def format_memorycore_to_str(self) -> str:
        """MemoryCore 转 JSON 可视化字符串"""
        return json.dumps(self.memorycore, indent=4, ensure_ascii=False)

    def format_inter_data_to_str(self) -> str:
        """INTER 数据转 JSON 可视化字符串"""
        return json.dumps(self.inter_data, indent=4, ensure_ascii=False, default=str)

    # =========================================================================
    # 【写回功能】将 memorycore 数据写回 Excel
    # =========================================================================

    def _split_db_key(self, db_key: str) -> tuple:
        """
        反向拆分 db_key 为 base_key, type_suffix, veh_suffix

        db_key 命名规则（全链路一致）：
        - 三段式: {base_key}_{type_suffix}_{veh_suffix}  → mass_curb_result_reevlto
        - 二段式: {base_key}_{veh_suffix}                → mass_curb_reevlto
        - 一段式: {base_key}                              → mass_curb

        智能拆分策略：
        1. 从 db_key 末尾向前查找已知的 veh_suffix
        2. 如果找到，再检查前一部分是否是 type_suffix (result/target/pass)
        3. 剩余部分就是 base_key（可能包含下划线）

        Args:
            db_key: 完整的数据库键名

        Returns:
            tuple: (base_key, type_suffix, veh_suffix)
        """
        known_vehsuffixes = set()
        for item in self.vehsuffix:
            if isinstance(item, dict) and "后缀" in item:
                known_vehsuffixes.add(str(item["后缀"]))
            elif isinstance(item, str):
                known_vehsuffixes.add(item)
        
        if not known_vehsuffixes:
            known_vehsuffixes = {"reevlto", "evlto"}

        type_suffixes = {"result", "target", "pass"}

        for i in range(1, len(db_key)):
            if db_key.endswith("_" + db_key[-i:]):
                candidate_veh = db_key[-i:]
                if candidate_veh in known_vehsuffixes:
                    remaining = db_key[:-(i + 1)]

                    for j in range(1, len(remaining)):
                        if remaining.endswith("_" + remaining[-j:]):
                            candidate_type = remaining[-j:]
                            if candidate_type in type_suffixes:
                                base_key = remaining[:-(j + 1)]
                                return (base_key, candidate_type, candidate_veh)

                    return (remaining, "", candidate_veh)

        parts = db_key.split("_")
        if len(parts) >= 3:
            veh_suffix = parts[-1]
            type_suffix = parts[-2]
            base_key = "_".join(parts[:-2])
            return (base_key, type_suffix, veh_suffix)

        elif len(parts) == 2:
            veh_suffix = parts[-1]
            base_key = parts[0]
            return (base_key, "", veh_suffix)

        else:
            return (db_key, "", "")

    def _extract_memorycore_data(self) -> list:
        """
        遍历 memorycore 提取所有需要写回的数据

        Returns:
            list: [(db_key, value, sheet_name, veh_name), ...]
        """
        result = []

        for veh_name, veh_data in self.memorycore.items():
            for sheet_name, sheet_data in veh_data.items():
                if isinstance(sheet_data, dict):
                    for cat1_data in sheet_data.values():
                        for cat2_data in cat1_data.values():
                            for item in cat2_data:
                                if "db_key" in item and "值" in item:
                                    result.append((
                                        item["db_key"],
                                        item["值"],
                                        sheet_name,
                                        veh_name
                                    ))
                                if "参数值" in item:
                                    for param_item in item["参数值"]:
                                        if "db_key" in param_item and "值" in param_item:
                                            result.append((
                                                param_item["db_key"],
                                                param_item["值"],
                                                sheet_name,
                                                veh_name
                                            ))
                else:
                    for item in sheet_data:
                        if "db_key" in item and "值" in item:
                            result.append((
                                item["db_key"],
                                item["值"],
                                sheet_name,
                                veh_name
                            ))
                        if "参数值" in item:
                            for param_item in item["参数值"]:
                                if "db_key" in param_item and "值" in param_item:
                                    result.append((
                                        param_item["db_key"],
                                        param_item["值"],
                                        sheet_name,
                                        veh_name
                                    ))

        return result

    def _find_row_by_base_key(self, sheet_name: str, base_key: str, veh_name: str = None) -> int:
        """
        在原始数据中查找 base_key 所在的行索引

        搜索策略：
        1. 如果指定了车型，优先在该车型的列中查找
        2. 优先搜索列名包含 "base_key" 的列（大小写不敏感）
        3. 如果找不到，搜索所有列中值匹配 base_key 的行（大小写不敏感）

        Args:
            sheet_name: Sheet名称
            base_key: 基础键名
            veh_name: 车型名称（可选，用于精确匹配）

        Returns:
            int: 行索引，未找到返回 -1
        """
        raw_sheet = self.data.get(sheet_name, [])
        base_key_clean = self._clean_identifier(base_key).lower()

        if veh_name:
            veh_name_clean = self._clean_identifier(veh_name).lower()
            if "_" in veh_name_clean:
                veh_suffix = veh_name_clean.split("_")[-1]
            else:
                veh_suffix = veh_name_clean

            for row_idx, row_data in enumerate(raw_sheet):
                for col_key, col_value in row_data.items():
                    if col_key.lower().find("base_key") >= 0:
                        if self._clean_identifier(str(col_value)).lower() == base_key_clean:
                            veh_cols = [k for k in row_data.keys() if k.startswith("车型,")]
                            found_veh_match = False
                            for veh_col in veh_cols:
                                parts = veh_col.split(",")
                                if len(parts) >= 2:
                                    veh_part = self._clean_identifier(parts[1]).lower()
                                    if veh_part == veh_suffix or veh_part == veh_name_clean:
                                        found_veh_match = True
                                        break
                            if found_veh_match:
                                return row_idx

        for row_idx, row_data in enumerate(raw_sheet):
            for col_key, col_value in row_data.items():
                if col_key.lower().find("base_key") >= 0:
                    if self._clean_identifier(str(col_value)).lower() == base_key_clean:
                        return row_idx

        for row_idx, row_data in enumerate(raw_sheet):
            for col_key, col_value in row_data.items():
                if self._clean_identifier(str(col_value)).lower() == base_key_clean:
                    return row_idx

        return -1

    def _find_result_column(self, row_data: dict, veh_name: str, type_suffix: str) -> str:
        """
        在原始数据行中查找对应的结果列名（值列）

        Excel 列名格式:
        - base sheet（3行表头）: "车型,增程车型_reevlto,值"
        - target sheet（4行表头）: "车型,增程车型_reevlto,当前值_result,值"

        匹配逻辑:
        1. 车型名称匹配（支持完整名称和后缀两种形式）
        2. 类型后缀匹配（从第三部分提取，如 "当前值_result" 中的 "result"）
        3. 必须是值列（最后一部分为"值"），不是base_key列

        Args:
            row_data: 原始数据行字典
            veh_name: 车型名称（如 "增程车型_reevlto"）
            type_suffix: 类型后缀（如 "result"，空字符串表示匹配任何类型）

        Returns:
            str: 结果列名（值列），未找到返回 None
        """
        veh_name_clean = self._clean_identifier(veh_name)
        if "_" in veh_name_clean:
            veh_suffix = veh_name_clean.split("_")[-1]
        else:
            veh_suffix = veh_name_clean

        for col_key in row_data.keys():
            if col_key.startswith("车型,"):
                parts = col_key.split(",")
                if len(parts) >= 3:
                    veh_part = self._clean_identifier(parts[1])
                    
                    last_part = parts[-1]
                    if last_part == "base_key":
                        continue
                    
                    col_type_part = ""
                    if len(parts) >= 4:
                        col_type_part = parts[2]

                    col_type_suffix = ""
                    if "_" in col_type_part:
                        col_type_suffix = col_type_part.split("_")[-1]

                    veh_match = False
                    if veh_part == veh_suffix:
                        veh_match = True
                    elif veh_part in veh_name_clean or veh_name_clean in veh_part:
                        veh_match = True
                    elif self._clean_identifier(veh_part) == self._clean_identifier(veh_name_clean):
                        veh_match = True

                    type_match = False
                    if not type_suffix:
                        type_match = True
                    elif col_type_suffix == type_suffix:
                        type_match = True
                    elif type_suffix in col_type_part or col_type_part in type_suffix:
                        type_match = True

                    if veh_match and type_match:
                        return col_key

        return None

    def save_memorycore_to_excel(self, file_path=None) -> bool:
        """
        将 memorycore 中的数据写回 Excel 文件（批量写入模式）

        流程：
        1. 遍历 memorycore 提取所有 db_key 和值
        2. 反向拆分 db_key 为 base_key, type_suffix, veh_suffix
        3. 在原始数据中定位 base_key 所在行和结果列
        4. 收集所有待写入数据（内存操作，不涉及磁盘）
        5. 打开一次 Excel 文件，批量写入所有数据
        6. 保存一次文件

        Args:
            file_path: 输出文件路径，默认使用加载时的路径

        Returns:
            bool: 是否成功
        """
        if file_path:
            output_path = file_path
        else:
            if not self.file_path:
                self._log("[ERROR] 未指定输出文件路径")
                return False
            dir_name = os.path.dirname(self.file_path)
            base_name = os.path.basename(self.file_path)
            name_parts = os.path.splitext(base_name)
            new_base_name = f"{name_parts[0]}_更新{name_parts[1]}"
            output_path = os.path.join(dir_name, new_base_name)

        if not os.path.exists(output_path):
            if os.path.exists(self.file_path):
                import shutil
                shutil.copy2(self.file_path, output_path)
                self._log(f"  [OK] 已复制原文件到: {output_path}")
            else:
                self._log(f"  [ERROR] 原文件不存在: {self.file_path}")
                return False

        self._log(f"\n=== MemoryDatabase: 写回 Excel ===")
        self._log(f"  [OK] 输出文件: {output_path}")

        memorycore_data = self._extract_memorycore_data()
        self._log(f"  [OK] 提取到 {len(memorycore_data)} 条待写回数据")

        write_queue = []
        failed_count = 0

        for db_key, value, sheet_name, veh_name in memorycore_data:
            base_key, type_suffix, veh_suffix = self._split_db_key(db_key)

            write_queue.append({
                'sheet_name': sheet_name,
                'base_key': base_key,
                'veh_suffix': veh_suffix,
                'type_suffix': type_suffix,
                'value': value,
                'db_key': db_key
            })

        self._log(f"  [OK] 准备写入 {len(write_queue)} 条数据")

        try:
            wb = self.excel_op._open_workbook(output_path)
            
            success_count = 0
            for item in write_queue:
                sheet_name = item['sheet_name']
                base_key = item['base_key']
                veh_suffix = item['veh_suffix']
                type_suffix = item['type_suffix']
                value = item['value']
                db_key = item['db_key']
                
                success = self.excel_op._write_cell_to_workbook(wb, sheet_name, base_key, veh_suffix, type_suffix, value)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    self._log(f"  [WARN] 写入失败: {db_key}")
            
            wb.save(output_path)
            wb.close()
            
            self._log(f"  [OK] 批量写入完成")
            
        except Exception as e:
            self._log(f"  [ERROR] 批量写入失败: {e}")
            success_count = 0
            failed_count += len(write_queue)

        self._log(f"\n  [OK] 写回完成: 成功 {success_count} 条，失败 {failed_count} 条")
        return failed_count == 0