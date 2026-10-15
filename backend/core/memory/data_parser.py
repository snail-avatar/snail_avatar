# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : data_parser.py
# @Desc    : 数据解析核心引擎
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
数据解析类 - DataFrame ↔ StructuredData 双向转换器

【单一职责】只做格式转换，不碰文件，不存状态
输入：ExcelOperator吐出的原始DataFrame
输出：MemoryDatabase能接收的结构化字典
"""

import pandas as pd
from typing import Dict, List, Any, Tuple


class DataParser:
    """
    数据解析器 - 纯函数转换层
    
    设计原则：
    - 无状态，纯函数
    - 输入输出都是标准数据结构
    - 不碰文件IO，不做数据持久
    """
    
    VEHICLE_TYPES = ["增程", "纯电"]
    DATA_TYPES = ["目标值", "仿真值", "达标标识"]
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
    
    def _log(self, message: str):
        print(message)
        if self.log_callback:
            self.log_callback(message)
    
    def _extract_value(self, row, col) -> str:
        """从行中提取值，处理多级标题元组"""
        if isinstance(col, tuple) and len(col) > 1:
            value = row[col]
        else:
            value = row[col]
        
        value_str = str(value)
        value_str = value_str.replace('\n', ' ').replace('\r', ' ')
        return value_str.strip()
    
    def _convert_value_type(self, value) -> Any:
        """自动转换数值类型：int → float → str"""
        try:
            return int(value)
        except (ValueError, TypeError):
            try:
                return float(value)
            except (ValueError, TypeError):
                return str(value)
    
    def match_columns(self, df: pd.DataFrame, sheet_name: str) -> Dict[str, Any]:
        """
        【核心】自动匹配DataFrame列名
        原逻辑完整移植，算法不变
        """
        self._log(f"\n=== DataParser: 匹配 {sheet_name} 列名 ===")
        
        column_keywords = {
            "中文名称": ["中文名称", "名称", "产品名称", "项目名称"],
            "单位": ["单位", "计量单位", "量纲"],
            "类别一级": ["类别", "一级"],
            "类别二级": ["类别", "二级"],
        }
        
        for vehicle_type in self.VEHICLE_TYPES:
            column_keywords[f"{vehicle_type}代号"] = [
                f"{vehicle_type}代号", f"{vehicle_type}编码", f"{vehicle_type}编号"
            ]
            column_keywords[f"{vehicle_type}数值"] = [
                f"{vehicle_type}数值", f"{vehicle_type}值", f"{vehicle_type}仿真值"
            ]
            for data_type in self.DATA_TYPES:
                column_keywords[f"{vehicle_type}{data_type}"] = [f"{vehicle_type}{data_type}"]
        
        column_mapping = {}
        
        for field, keywords in column_keywords.items():
            for col in df.columns:
                if isinstance(col, tuple) and len(col) > 1:
                    if 'Unnamed' in str(col[1]) or str(col[1]).strip() == '':
                        col_str = str(col[0])
                    else:
                        col_str = str(col[1])
                else:
                    col_str = str(col)
                
                if any(keyword in col_str for keyword in keywords):
                    column_mapping[field] = col
                    self._log(f"  [OK] {field}: {col}")
                    break
        
        return column_mapping
    
    def ffill_merge_cells(self, df: pd.DataFrame, column: str) -> pd.Series:
        """合并单元格自动向下填充"""
        if column in df.columns:
            return df[column].ffill()
        return pd.Series(dtype=object)
    
    def auto_detect_vehicle_types(self, dfs: Dict[str, pd.DataFrame]) -> List[str]:
        """自动识别Excel中的车型列表"""
        vehicle_types = set()
        
        for sheet_name, df in dfs.items():
            for col in df.columns:
                if isinstance(col, tuple) and len(col) >= 2:
                    col_first = str(col[0])
                    if "车型" in col_first:
                        vehicle_type = str(col[1]).strip()
                        if (vehicle_type and 
                            vehicle_type != 'nan' and 
                            'Unnamed' not in vehicle_type):
                            vehicle_types.add(vehicle_type)
        
        result = sorted(list(vehicle_types)) if vehicle_types else self.VEHICLE_TYPES
        self._log(f"\n=== DataParser: 自动识别车型 ===")
        self._log(f"  {result}")
        return result
    
    def parse_vts_sheet(self, df: pd.DataFrame, column_mapping: Dict) -> Dict[str, List]:
        """
        VTS Sheet 结构化解析
        输出: {key: [{名称, 单位, 代号, 数值}, ...]}
        """
        self._log(f"\n=== DataParser: 解析 VTS Sheet ===")
        
        level1_col = column_mapping.get("类别一级")
        level2_col = column_mapping.get("类别二级")
        
        if level1_col and level1_col in df.columns:
            df[level1_col] = df[level1_col].ffill()
        if level2_col and level2_col in df.columns:
            df[level2_col] = df[level2_col].ffill()
        
        result = {}
        
        for index, row in df.iterrows():
            level1_value = self._extract_value(row, level1_col) if level1_col else "未知"
            level2_value = self._extract_value(row, level2_col) if level2_col else "未知"
            
            level1_key = str(level1_value).strip() if level1_value != 'nan' else "未知一级分类"
            level2_key = str(level2_value).strip() if level2_value != 'nan' else "未知二级分类"
            
            for vehicle_type in self.VEHICLE_TYPES:
                for data_type in self.DATA_TYPES:
                    code_col = column_mapping.get(f"{vehicle_type}{data_type}代号", 
                                                column_mapping.get(f"{vehicle_type}代号"))
                    if not code_col:
                        continue
                    
                    code = self._extract_value(row, code_col)
                    if not code or code.strip() == '' or code == 'nan':
                        continue
                    
                    value_col = column_mapping.get(f"{vehicle_type}{data_type}数值", 
                                                  column_mapping.get(f"{vehicle_type}数值"))
                    value = self._convert_value_type(self._extract_value(row, value_col))
                    
                    data = {
                        "名称": self._extract_value(row, column_mapping["中文名称"]),
                        "单位": self._extract_value(row, column_mapping["单位"]),
                        "代号": code,
                        "数值": value
                    }
                    
                    key = f"{vehicle_type}_{level1_key}_{level2_key}_{data_type}"
                    
                    if key not in result:
                        result[key] = []
                    result[key].append(data)
        
        self._log(f"  [OK] 生成 {len(result)} 个分组")
        return result
    
    def parse_standard_sheet(self, df: pd.DataFrame, column_mapping: Dict, 
                            sheet_name: str) -> Dict[str, List]:
        """
        产品定义/SSTS/计算条件 通用解析器
        """
        self._log(f"\n=== DataParser: 解析 {sheet_name} Sheet ===")
        
        result = {}
        for vehicle_type in self.VEHICLE_TYPES:
            result[vehicle_type] = []
        
        for index, row in df.iterrows():
            for vehicle_type in self.VEHICLE_TYPES:
                code_col = column_mapping.get(f"{vehicle_type}代号")
                if not code_col:
                    continue
                
                code = self._extract_value(row, code_col)
                if not code or code.strip() == '' or code == 'nan':
                    continue
                
                value_col = column_mapping.get(f"{vehicle_type}数值")
                value = self._convert_value_type(self._extract_value(row, value_col))
                
                data = {
                    "名称": self._extract_value(row, column_mapping["中文名称"]),
                    "单位": self._extract_value(row, column_mapping["单位"]),
                    "代号": code,
                    "数值": value
                }
                result[vehicle_type].append(data)
        
        for vt in self.VEHICLE_TYPES:
            self._log(f"  [OK] {vt}: {len(result[vt])} 条参数")
        
        return result
    
    def parse_drive_cycle(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """
        驾驶循环曲线解析
        输出: {循环名: {time_s: [], velocity_m_s: []}}
        """
        self._log(f"\n=== DataParser: 解析驾驶循环 ===")
        
        result = {}
        cycle_names = set()
        
        for col in df.columns:
            if isinstance(col, tuple) and len(col) >= 1:
                cycle_name = str(col[0])
                if cycle_name and cycle_name != 'nan' and 'Unnamed' not in cycle_name:
                    cycle_names.add(cycle_name)
        
        for cycle_name in sorted(cycle_names):
            time_col, velocity_col = None, None
            
            for col in df.columns:
                if isinstance(col, tuple) and len(col) >= 2:
                    col_first = str(col[0])
                    col_second = str(col[1]).lower()
                    
                    if col_first == cycle_name:
                        if 'time' in col_second:
                            time_col = col
                        elif 'velocity' in col_second:
                            velocity_col = col
            
            if time_col is not None and velocity_col is not None:
                time_data = df[time_col].dropna().tolist()
                velocity_data = df[velocity_col].dropna().tolist()
                
                min_len = min(len(time_data), len(velocity_data))
                result[cycle_name] = {
                    "time_s": time_data[:min_len],
                    "velocity_m_s": velocity_data[:min_len]
                }
                self._log(f"  [OK] {cycle_name}: {min_len} 个数据点")
        
        return result
    
    def extract_performance_categories(self, df: pd.DataFrame, 
                                       column_mapping: Dict) -> Dict:
        """
        提取性能分类层级关系（第0部分元数据）
        """
        level1_col = column_mapping.get("类别一级")
        level2_col = column_mapping.get("类别二级")
        
        result = {
            "一级分类": [],
            "二级分类": [],
            "层级关系": {}
        }
        
        if level1_col in df.columns:
            df[level1_col] = df[level1_col].ffill()
            level1_unique = sorted(df[level1_col].dropna().unique().tolist())
            result["一级分类"] = [str(c).strip() for c in level1_unique if str(c) != 'nan']
        
        if level2_col in df.columns:
            df[level2_col] = df[level2_col].ffill()
            level2_unique = sorted(df[level2_col].dropna().unique().tolist())
            result["二级分类"] = [str(c).strip() for c in level2_unique if str(c) != 'nan']
        
        if level1_col in df.columns and level2_col in df.columns:
            level_map = {}
            for _, row in df.iterrows():
                l1 = str(row.get(level1_col, "")).strip()
                l2 = str(row.get(level2_col, "")).strip()
                if l1 and l1 != 'nan' and l2 and l2 != 'nan':
                    if l1 not in level_map:
                        level_map[l1] = set()
                    level_map[l1].add(l2)
            result["层级关系"] = {k: sorted(list(v)) for k, v in level_map.items()}
        
        self._log(f"\n=== DataParser: 性能分类层级 ===")
        self._log(f"  [OK] 一级分类: {len(result['一级分类'])} 个")
        self._log(f"  [OK] 二级分类: {len(result['二级分类'])} 个")
        
        return result
