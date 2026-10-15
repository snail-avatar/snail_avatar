# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : excel_operator.py
# @Desc    : Excel文件操作工具
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Excel 操作类 - 程序与物理文件的唯一边界

【单一职责】只做文件IO，不做业务解析
1. 自动扫描所有Sheet，按前缀分类处理
2. base_ 前缀Sheet：多级表头基础数据表解析
3. curve_ 前缀Sheet：离散点曲线数据解析
4. 写入单元格数值（不改变布局/格式/公式）
"""

import pandas as pd
import numpy as np
import openpyxl
import re
import json
from typing import Dict, List, Any


class ExcelOperator:
    """
    Excel 操作算子 - 纯IO层，可扩展架构
    
    设计原则：
    - 自动发现所有Sheet，不写死名称
    - 按Sheet名称前缀分类，不同类型不同解析方法
    - 新增类型只需加新方法，符合开闭原则
    - 输出统一为：{Sheet名: [字典1, 字典2, ...]} 纯Python结构
    """
    
    SHEET_TYPE_PREFIX = {
        "simple_": "简单列表",
        "base_": "基础数据表",
        "target_": "目标值数据表",
        "curve_": "曲线数据表",
    }
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
    
    def _log(self, message: str):
        print(message)
        if self.log_callback:
            self.log_callback(message)
    
    def _build_key_name(self, parts: List[str]) -> str:
        """
        【工具】多级标题单元格合并为键名
        只做合并，不做清洗，原封不动保留所有字符（包括中文）
        """
        unique_parts = []
        seen = set()
        for part in parts:
            part_str = str(part).strip()
            if part_str and part_str != 'nan' and part_str not in seen:
                unique_parts.append(part_str)
                seen.add(part_str)
        return ",".join(unique_parts)
    
    def _clean_column_name(self, name: str) -> str:
        """
        【精准清洗】只清洗包含base_key的列名
        
        规则：
        1. 英文字母转小写
        2. 删除所有空格（前中后）
        3. 保留中文、逗号、下划线
        4. 删除其他特殊字符
        """
        s = str(name)
        
        s = s.lower()
        s = s.replace(" ", "")
        s = re.sub(r'[^\u4e00-\u9fa5a-z0-9_,]', '', s)
        
        return s
    
    def _clean_sheet_name(self, name: str) -> str:
        """
        Sheet名称统一清洗
        
        四原则完全一致：
        1. 所有大写字母改成小写
        2. 去除字符串前、中、后的所有空格
        3. 去除除了"_"和","外的所有特殊字符
        4. 中文字符不处理
        """
        s = str(name)
        
        s = s.lower()
        s = s.replace(" ", "")
        s = re.sub(r'[^\u4e00-\u9fa5a-z0-9_,]', '', s)
        
        return s
    
    def _clean_base_key(self, key: str) -> str:
        """
        base_key 格式统一清洗（base_ 和 target_ 类通用）
        
        四原则完全一致：
        1. 所有大写字母改成小写
        2. 去除字符串前、中、后的所有空格
        3. 去除除了"_"和","外的所有特殊字符
        4. 中文字符原封不动
        """
        if pd.isna(key) or key is None:
            return key
        
        s = str(key)
        
        s = s.lower()
        s = s.replace(" ", "")
        s = re.sub(r'[^\u4e00-\u9fa5a-z0-9_,]', '', s)
        
        return s
    
    def scan_and_classify_sheets(self, file_path: str) -> Dict[str, List[str]]:
        """
        【自动分类】扫描Excel所有Sheet，按前缀分类
        
        输出: {
            "base": ["base_产品定义_proddef", "base_VTS_v1"],
            "curve": ["curve_经济性测试循环_ecocycle"],
            "unknown": ["其他Sheet名"]
        }
        """
        excel_file = pd.ExcelFile(file_path)
        all_sheets = excel_file.sheet_names
        
        result = {
            "base": [],
            "target": [],
            "curve": [],
            "simple": [],
            "unknown": [],
        }
        
        for original_name in all_sheets:
            clean_name = self._clean_sheet_name(original_name)
            
            if clean_name.startswith("base_"):
                result["base"].append(clean_name)
            elif clean_name.startswith("target_"):
                result["target"].append(clean_name)
            elif clean_name.startswith("curve_"):
                result["curve"].append(clean_name)
            elif clean_name.startswith("simple_"):
                result["simple"].append(clean_name)
            else:
                result["unknown"].append(clean_name)
        
        self._log(f"\n=== ExcelOperator: Sheet扫描分类完成 ===")
        self._log(f"  base类: {result['base']}")
        self._log(f"  curve类: {result['curve']}")
        self._log(f"  target类: {result['target']}")
        self._log(f"  simple类: {result['simple']}")
        self._log(f"  其他: {result['unknown']}")
        
        return result
    
    def read_base_sheet(self, file_path: str, sheet_name: str) -> List[Dict]:
        """
        【base类Sheet解析器】
        
        算法：
        1. 全量无表头读取，跳过第1列序号
        2. 扫描找到含"base_key"的行作为分界点
        3. 在标题行范围内找到值为"名称"的列作为标题列边界
        4. 生成填充掩码: 行<=base_key_row OR 列<name_col
        5. 只在掩码范围内执行纵向/横向向前填充
        6. 分界点以上为标题区，合并生成列名
        7. 统计base_key的数量N
        8. 数据区的每一行拆分为N条数据（N个base_key）
        """
        self._log(f"\n=== 解析 base Sheet: {sheet_name} ===")
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        
        # ===== 第一步：先找边界，不先填充！用纯原始数据找 =====
        self._log(f"  [OK] 第一步：扫描确定边界")
        
        base_key_row = -1
        for i, row in df.iterrows():
            row_str = str(row.values).lower()
            if "base_key" in row_str:
                base_key_row = i
                self._log(f"       标题行底部边界: 第{base_key_row}行")
                break
        
        if base_key_row == -1:
            raise ValueError(f"Sheet [{sheet_name}] 未找到包含base_key的分界行！")
        
        name_col = -1
        for col_idx in range(len(df.columns)):
            col_values = df.iloc[0:base_key_row + 1, col_idx].values
            for val in col_values:
                if str(val).strip() == "名称":
                    name_col = col_idx
                    self._log(f"       标题列右侧边界: 第{name_col}列")
                    break
            if name_col != -1:
                break
        
        if name_col == -1:
            name_col = 1
            self._log(f"       未找到名称列，默认标题列边界: 第{name_col}列")
        
        if hasattr(self, 'sheet_header_info'):
            clean_name = self._clean_sheet_name(sheet_name)
            self.sheet_header_info[clean_name] = {
                'base_key_row': base_key_row,
                'name_col': name_col
            }
            self._log(f"       保存表头信息: clean_name={clean_name}, base_key_row={base_key_row}, name_col={name_col}")
        
        # ===== 第二步：生成 OR 掩码（只在这个范围内才填充）=====
        self._log(f"  [OK] 第二步：生成填充掩码 [行<={base_key_row} OR 列<{name_col}]")
        
        rows, cols = df.shape
        mask = np.zeros((rows, cols), dtype=bool)
        
        for r in range(rows):
            for c in range(cols):
                if r <= base_key_row or c < name_col:
                    mask[r][c] = True
        
        # ===== 第三步：只在掩码范围内填充 =====
        self._log(f"  [OK] 第三步：只在掩码范围内执行双向填充")
        self._log(f"       掩码范围外的单元格（数据区）保持原始值")
        
        df_orig = df.copy()
        df = df.ffill(axis=0)
        df = df.where(mask, df_orig)
        
        df_orig = df.copy()
        df = df.ffill(axis=1)
        df = df.where(mask, df_orig)
        
        self._log(f"  [OK] 精准范围填充完成，数据区空值已保留！")
        
        col_names = []
        for col_idx in range(1, len(df.columns)):
            title_cells = df.iloc[0:base_key_row + 1, col_idx].tolist()
            col_name = self._build_key_name(title_cells)
            col_names.append(col_name)
        
        for idx, name in enumerate(col_names):
            if name.startswith("车型,"):
                col_names[idx] = self._clean_column_name(name)
        
        self._log(f"  [OK] 生成列名: {col_names[:5]}...")
        self._log(f"       所有车型开头的列已做规范化清洗")
        
        column_positions = {}
        for idx, name in enumerate(col_names):
            excel_col = idx + 2  # idx从0开始，数据区从列1开始，Excel从1开始 → idx+1+1=idx+2
            column_positions[name] = excel_col
        
        if hasattr(self, 'sheet_header_info'):
            clean_name = self._clean_sheet_name(sheet_name)
            info = self.sheet_header_info.get(clean_name, {})
            info['column_positions'] = column_positions
            self.sheet_header_info[clean_name] = info
            self._log(f"       列位置映射: {column_positions}")
        
        base_key_positions = []
        for idx, name in enumerate(col_names):
            if "base_key" in name.lower():
                base_key_positions.append(idx)
        
        value_positions = [i + 1 for i in base_key_positions]
        
        N = len(base_key_positions)
        self._log(f"  [OK] base_key数量: {N}个，每行拆{N}条数据")
        self._log(f"       base_key列位置: {base_key_positions}")
        self._log(f"       对应数值列位置: {value_positions}")
        
        result = []
        data_rows = df.iloc[base_key_row + 1:, 1:].values
        
        for row_values in data_rows:
            if pd.isna(row_values).all():
                continue
            
            common_fields = {}
            for idx in range(len(col_names)):
                if idx not in base_key_positions and idx not in value_positions:
                    key = col_names[idx]
                    val = row_values[idx]
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    common_fields[key] = val
            
            for bk_idx in base_key_positions:
                bk_value = row_values[bk_idx]
                
                if pd.isna(bk_value) or str(bk_value).strip() == "" or str(bk_value).strip().lower() == "nan":
                    continue
                
                bk_value = self._clean_base_key(bk_value)
                
                item = common_fields.copy()
                
                bk_col_name = col_names[bk_idx]
                if isinstance(bk_value, float) and bk_value.is_integer():
                    bk_value = int(bk_value)
                item[bk_col_name] = bk_value
                
                val_idx = bk_idx + 1
                if val_idx < len(row_values):
                    val_col_name = col_names[val_idx]
                    val = row_values[val_idx]
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    item[val_col_name] = val
                
                result.append(item)
        
        self._log(f"  [OK] 解析完成: 原始{len(data_rows)}行 → {len(result)}条数据")
        return result
    
    def read_target_sheet(self, file_path: str, sheet_name: str) -> List[Dict]:
        """
        【target类Sheet解析器】
        
        两步算法：
        1. 先用base类的规则拆分，按base_key数量拆成多行
        2. 按参数+车型进行合并，同一参数同一车型的所有状态字段合并到一条
        
        效果：6行 → 2行（每车型一行，一行包含当前值/目标值/达标标识）
        """
        self._log(f"\n=== 解析 target Sheet: {sheet_name} ===")
        self._log(f"  [STEP 1] 调用base类算法，按base_key拆分")
        
        raw_split = self.read_base_sheet(file_path, sheet_name)
        
        self._log(f"  [STEP 2] 按参数+车型合并，同车型多状态字段归并")
        
        groups = {}
        
        for item in raw_split:
            common_keys = []
            veh_keys = []
            
            for k in item.keys():
                if k.startswith("车型,"):
                    veh_keys.append(k)
                else:
                    common_keys.append(k)
            
            if not veh_keys:
                continue
            
            first_veh_key = veh_keys[0]
            parts = first_veh_key.split(",")
            if len(parts) >= 2:
                veh_name = parts[1]
            else:
                veh_name = "unknown"
            
            common_values = tuple(str(item.get(k)) for k in common_keys)
            group_key = (common_values, veh_name)
            
            if group_key not in groups:
                groups[group_key] = {}
                
                for k in common_keys:
                    groups[group_key][k] = item.get(k)
            
            for k in veh_keys:
                groups[group_key][k] = item.get(k)
        
        result = list(groups.values())
        
        self._log(f"       拆分后 {len(raw_split)} 行 → 合并后 {len(result)} 行")
        self._log(f"  [OK] target类合并完成")
        
        return result
    
    def read_simple_sheet(self, file_path: str, sheet_name: str) -> List[Dict]:
        """
        【simple类Sheet解析器】
        
        极简读取算法：
        1. 第一行直接作为列名 header=0
        2. 没有合并单元格，不需要任何填充
        3. 直接转成扁平字典列表
        """
        self._log(f"\n=== 解析 simple Sheet: {sheet_name} ===")
        self._log(f"  [INFO] 简单列表类型，直接读取，不做填充")
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
        
        result = df.where(pd.notnull(df), None).to_dict('records')
        
        for item in result:
            for key, value in item.items():
                if isinstance(value, float) and value.is_integer():
                    item[key] = int(value)
        
        self._log(f"  [OK] 解析完成: {len(result)} 条数据")
        
        return result
    
    def read_curve_sheet(self, file_path: str, sheet_name: str) -> List[Dict]:
        """
        【curve类Sheet解析器】
        
        算法：
        1. 全量无表头读取
        2. 纵向向前填充(ffill)处理纵向合并单元格
        3. 横向向前填充(ffill)处理横向合并单元格
        4. 找到第一个纯数字行作为正文起始
        5. 以上为标题区，每两列为一组
        6. 每两列生成一个 {曲线名: {时间列表名: [], 数值列表名: []}}
        7. 曲线名：两列所有标题去重，左→右、上→下用","连接
        """
        self._log(f"\n=== 解析 curve Sheet: {sheet_name} ===")
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        
        self._log(f"  [OK] 第一步：用纯原始数据扫描所有行，不做任何填充！")
        self._log(f"       【重要】先找边界，后填充，避免数据被污染")
        title_rows = []
        
        for i, row in df.iterrows():
            has_non_numeric = False
            for v in row.values:
                if not pd.isna(v):
                    try:
                        float(v)
                    except ValueError:
                        has_non_numeric = True
                        break
            
            if has_non_numeric:
                title_rows.append(i)
        
        self._log(f"       识别出标题行: {title_rows}")
        
        data_start_row = title_rows[-1] + 1
        self._log(f"       最终确定数值起始行: 第{data_start_row}行（前面都是标题行）")
        self._log(f"       0~{data_start_row-1}行 = 标题区，执行填充")
        self._log(f"       {data_start_row}行及以后 = 数值区，不做任何填充！")
        
        self._log(f"")
        self._log(f"  [OK] 第二步：只在标题行范围内执行填充（纵向+横向）")
        self._log(f"       数值行不做任何填充！空值就是曲线结束的标志！")
        
        df_title = df.iloc[0:data_start_row, :].copy()
        df_title = df_title.ffill(axis=0)
        df_title = df_title.ffill(axis=1)
        df.iloc[0:data_start_row, :] = df_title
        
        if data_start_row >= len(df):
            raise ValueError(f"Sheet [{sheet_name}] 未找到数值起始行！")
        
        total_cols = len(df.columns)
        self._log(f"  [OK] 总列数: {total_cols} 列，按每2列一组解析")
        
        result = []
        
        for start_col in range(0, total_cols, 2):
            if start_col + 1 >= total_cols:
                self._log(f"  [WARN] 列{start_col+1}超出范围，跳过第{start_col//2 + 1}组")
                continue
            
            name_parts = []
            seen = set()
            
            for row_idx in range(data_start_row - 1):
                for col_idx in [start_col, start_col + 1]:
                    val = df.iloc[row_idx, col_idx]
                    val_str = str(val).strip()
                    if val_str and val_str != 'nan' and val_str not in seen:
                        name_parts.append(val_str)
                        seen.add(val_str)
            
            curve_name = ",".join(name_parts) if name_parts else f"curve_{start_col//2}"
            
            list_name_x = str(df.iloc[data_start_row - 1, start_col]).strip()
            list_name_y = str(df.iloc[data_start_row - 1, start_col + 1]).strip()
            
            if list_name_x == 'nan':
                list_name_x = "x"
            if list_name_y == 'nan':
                list_name_y = "y"
            
            data_x = []
            data_y = []
            
            for row_idx in range(data_start_row, len(df)):
                val_x = df.iloc[row_idx, start_col]
                val_y = df.iloc[row_idx, start_col + 1]
                
                if pd.isna(val_x) and pd.isna(val_y):
                    break
                
                if pd.isna(val_x) or pd.isna(val_y):
                    break
                
                try:
                    data_x.append(float(val_x))
                    data_y.append(float(val_y))
                except ValueError:
                    break
            
            if len(data_x) > 0:
                result.append({
                    curve_name: {
                        list_name_x: data_x,
                        list_name_y: data_y
                    }
                })
                self._log(f"  [OK] {curve_name}: {len(data_x)} 个点")
            else:
                self._log(f"  [WARN] 第{start_col//2 + 1}组有效点数为0，跳过")
        
        self._log(f"  [OK] 解析完成: 共{len(result)}条曲线")
        return result
    
    def read_all_sheets(self, file_path: str) -> Dict[str, List[Dict]]:
        """
        【调度入口】自动识别类型，分派到对应解析器
        
        输出格式: {
            "base_产品定义": [{k1:v1, k2:v2}, ...],
            "base_VTS": [{k1:v1, k2:v2}, ...],
            "curve_循环": [{曲线名: {time:[], value:[]}}, ...],
        }
        
        同时保存原始名称和清洗后名称的映射到 self.sheet_name_mapping
        """
        self._log(f"\n{'='*60}")
        self._log(f"ExcelOperator: 开始自动扫描+解析所有Sheet")
        self._log(f"{'='*60}")
        
        excel_file = pd.ExcelFile(file_path)
        all_sheets = excel_file.sheet_names
        
        self._log(f"\n[OK] 按Excel原始从左到右顺序解析: {all_sheets}")
        
        result = {}
        self.sheet_name_mapping = {}
        self.sheet_header_info = {}
        
        for original_name in all_sheets:
            clean_name = self._clean_sheet_name(original_name)
            self.sheet_name_mapping[clean_name] = original_name
            
            if clean_name.startswith("base_"):
                result[clean_name] = self.read_base_sheet(file_path, original_name)
            
            elif clean_name.startswith("target_"):
                result[clean_name] = self.read_target_sheet(file_path, original_name)
            
            elif clean_name.startswith("curve_"):
                result[clean_name] = self.read_curve_sheet(file_path, original_name)
            
            elif clean_name.startswith("simple_"):
                result[clean_name] = self.read_simple_sheet(file_path, original_name)
            
            else:
                self._log(f"\n  [SKIP] 未知类型，跳过: {original_name} -> {clean_name}")
        
        self._log(f"\n{'='*60}")
        self._log(f"解析完成: 共{len(result)}个Sheet")
        self._log(f"{'='*60}")
        
        return result
    
    def _open_workbook(self, file_path: str):
        """
        打开 Excel 工作簿（内部方法）
        
        Args:
            file_path: 文件路径
        
        Returns:
            openpyxl.Workbook: 工作簿对象
        """
        return openpyxl.load_workbook(file_path)
    
    def _write_cell_to_workbook(self, wb, sheet_name: str, 
                                base_key: str, veh_suffix: str, type_suffix: str, value: Any) -> bool:
        """
        写入单个单元格数值到已打开的工作簿（内部方法，批量写入使用）
        
        使用读取阶段已经构建好的 sheet_header_info['column_positions'] 映射进行写回，
        避免重新扫描原始 Excel（合并单元格仍为空白）导致的定位困难。
        
        写回逻辑：
        1. 根据 sheet_name 获取清洗后的名称，查找对应的 column_positions 映射
        2. 遍历 column_positions，找到匹配 veh_suffix 和 type_suffix 的值列
        3. 获取对应的 base_key 列位置（值列左侧一列）
        4. 使用 sheet_header_info['base_key_row'] 确定数据起始行
        5. 在 base_key 列的数据行中查找匹配的 base_key，确定目标行
        6. 写入值到目标单元格
        
        Args:
            wb: 已打开的工作簿对象
            sheet_name: 可以是清洗后的名称或原始名称，支持 _memorycore 后缀
            base_key: 基础键名（如 f_brake_res）
            veh_suffix: 车型后缀（如 reevlto）
            type_suffix: 类型后缀（如 result、target、pass）
            value: 要写入的值
        
        Returns:
            bool: 是否写入成功
        """
        clean_name = self._clean_sheet_name(sheet_name)
        
        if not hasattr(self, 'sheet_header_info') or clean_name not in self.sheet_header_info:
            return False
        
        header_info = self.sheet_header_info[clean_name]
        column_positions = header_info.get('column_positions', {})
        base_key_row = header_info.get('base_key_row', 0)
        
        original_name = sheet_name
        if hasattr(self, 'sheet_name_mapping'):
            if sheet_name in self.sheet_name_mapping:
                original_name = self.sheet_name_mapping[sheet_name]
            elif sheet_name.endswith('_memorycore'):
                lookup_name_no_suffix = sheet_name[:-len('_memorycore')]
                if lookup_name_no_suffix in self.sheet_name_mapping:
                    original_name = self.sheet_name_mapping[lookup_name_no_suffix]
        
        if original_name not in wb.sheetnames:
            return False
        
        ws = wb[original_name]
        
        target_col = None
        base_key_col = None
        
        for col_name, col_num in column_positions.items():
            if col_name.endswith(',值'):
                col_lower = col_name.lower()
                veh_lower = veh_suffix.lower()
                
                veh_matched = False
                for part in col_lower.split(','):
                    parts = part.split('_')
                    if veh_lower in parts:
                        veh_matched = True
                        break
                
                if veh_matched:
                    if not type_suffix or type_suffix.lower() in col_lower:
                        target_col = col_num
                        base_key_col_name = col_name[:-1] + 'base_key'
                        if base_key_col_name in column_positions:
                            base_key_col = column_positions[base_key_col_name]
                        else:
                            base_key_col = col_num - 1
                        break
        
        if target_col is None or base_key_col is None:
            return False
        
        target_row = None
        for row in range(base_key_row + 1, ws.max_row + 1):
            cell_value = ws.cell(row=row, column=base_key_col).value
            if cell_value and str(cell_value).lower() == base_key.lower():
                target_row = row
                break
        
        if target_row is None:
            return False
        
        for merged_range in ws.merged_cells.ranges:
            if merged_range.min_row <= target_row <= merged_range.max_row and \
               merged_range.min_col <= target_col <= merged_range.max_col:
                target_row = merged_range.min_row
                target_col = merged_range.min_col
                break
        
        ws.cell(row=target_row, column=target_col, value=value)
        return True
    
    def write_cell_value(self, file_path: str, sheet_name: str, 
                         row: int, col: int, value: Any):
        """
        写入单个单元格数值（单条写入模式，已废弃，保留兼容）
        
        Args:
            sheet_name: 可以是清洗后的名称或原始名称，支持 _memorycore 后缀
            row: 数据行索引（0-based，不含表头）
            col: 数据列索引（0-based，不含序号列）
            value: 要写入的值
        """
        pass
    
    def write_column_values(self, file_path: str, sheet_name: str, 
                            start_row: int, col: int, values: List[Any]):
        """
        批量写入一列数值
        """
        wb = openpyxl.load_workbook(file_path)
        ws = wb[sheet_name]
        for i, value in enumerate(values):
            ws.cell(row=start_row + i, column=col, value=value)
        wb.save(file_path)
        self._log(f"ExcelOperator: 批量写入 {sheet_name} 第{col}列: {len(values)} 个值")
    
    # JSON格式化渲染器
    def format_all_sheets_to_str(self, data: dict) -> str:
        """
        所有Sheet数据格式化渲染器
        
        与 MemoryDatabase 架构风格保持统一
        """
        return json.dumps(data, indent=4, ensure_ascii=False)