# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : components_reader.py
# @Desc    : 通用零部件参数文件读取器（纯工具，零业务耦合）
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
通用零部件参数文件读取器

职责：给定任意 .xlsx / .json / .yaml / .yml / .csv 文件，
自动识别其结构并返回统一格式的数据字典。

设计原则：
  - 零业务耦合：不认识 Motor / Brake / Battery 任何具体领域
  - 自动识别：通过行列特征 + 表头关键词判断数据类型
  - 可配置覆盖：rules dict 允许上层覆盖默认识别行为

统一数据格式（三种）：
  curve_1d:  {"type": "curve_1d", "x_label": str, "y_label": str,
              "x": List[float], "y": List[float], "y_abs": List[float] | None}
  map_2d:    {"type": "map_2d",   "x_label": str, "y_label": str, "z_label": str,
              "x": List[float], "y": List[float], "z": List[List[float]]}
  scalar:    {"type": "scalar",   "value": Any}

文件级返回：{sheet_name_or_top_key: 统一格式 dict}
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Optional, Tuple


class ComponentsReader:
    """通用零部件参数读取器（纯静态工具类）"""

    # ========= 表头关键词字典（用于猜 x_label / y_label / z_label）=========
    HEADER_KEYWORDS: Dict[str, List[str]] = {
        "rpm":        ["rpm", "转速", "speed", "n_"],   # 去掉单字母 "n"——会误匹配 "nm" 等子串
        "nm":         ["nm", "扭矩", "torque", "t_"],
        "efficiency": ["eff", "效率", "效率map", "efficiency"],
        "generation": ["generation", "regen", "回收", "发电"],
        "drive":      ["drive", "驱动", "行驶"],
        "soc":        ["soc", "荷电", "state_of_charge"],
        "power":      ["power", "功率", "p_"],
        "current":    ["current", "电流", "i_"],
        "voltage":    ["voltage", "电压", "v_"],
    }

    # =========================================================================
    # 主入口
    # =========================================================================

    @staticmethod
    def read_file(file_path: str, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        读取任意参数文件，返回统一格式字典

        Args:
            file_path: 绝对路径
            rules: 可选，上层覆盖规则（预留给未来扩展）

        Returns:
            dict: {
                "<sheet_name_or_top_key>": {
                    "type": "curve_1d" | "map_2d" | "scalar",
                    ...统一格式字段...
                }
            }
            读取失败返回空 dict
        """
        if not file_path or not os.path.isfile(file_path):
            return {}

        ext = os.path.splitext(file_path)[1].lower()

        if ext in (".xlsx", ".xls"):
            return ComponentsReader._read_xlsx(file_path, rules)
        elif ext in (".json",):
            return ComponentsReader._read_json(file_path)
        elif ext in (".yaml", ".yml"):
            return ComponentsReader._read_yaml(file_path)
        elif ext in (".csv",):
            return ComponentsReader._read_csv(file_path, rules)
        else:
            return {}

    # =========================================================================
    # xlsx 读取
    # =========================================================================

    @staticmethod
    def _read_xlsx(file_path: str, rules: Optional[Dict] = None) -> Dict[str, Any]:
        """读取 xlsx 文件，逐 sheet 识别类型并解析"""
        try:
            import openpyxl
        except ImportError:
            return {}

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
        except Exception:
            return {}

        result: Dict[str, Any] = {}
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            if ws.max_row < 1 or ws.max_column < 1:
                continue

            data = ComponentsReader._parse_worksheet(ws, rules)
            if data is not None:
                result[sheet_name] = data

        return result

    @staticmethod
    def _parse_worksheet(ws, rules: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        根据行列特征自动识别并解析 worksheet

        类型判定规则（按优先级）：
          1. 4 列曲线 + 含 "generation" 关键词 → 双列曲线（drive/generation）
          2. 行≥3 且 列≥3 且 第一行/第一列均为数值序列 → map_2d
          3. 列数 == 2 → 简单 XY 曲线（curve_1d）
          4. 列数 == 4 → 双列曲线（简化版，无 generation 关键词时）
          5. 其他 → curve_1d（取前两列）
        """
        n_rows = ws.max_row
        n_cols = ws.max_column

        # 读原始所有行
        rows: List[List[Any]] = []
        for row in ws.iter_rows(min_row=1, max_row=n_rows, max_col=n_cols, values_only=True):
            rows.append(list(row))

        # 空表
        if n_rows == 0 or n_cols == 0:
            return None

        # ---- 规则 0（前置）: 2 行 header + N 列数值表 → scalar_dict ----
        # 几何判定：恰好 2 行、≥2 列；第一行含字符串表头、第二行全数值
        # 典型用途：Motor 的 reducer sheet（gear_radio + efficiency）、
        #           Battery 的 soc_limits / battery_specs 等单值参数组
        # 这条规则必须在曲线/地图之前，否则会被规则 3 误判成 curve_1d
        if n_rows == 2 and n_cols >= 2:
            first_row_has_str = any(
                isinstance(c, str) and c.strip() != ""
                for c in rows[0] if c is not None
            )
            second_row_all_num = all(
                ComponentsReader._to_float(c) is not None
                for c in rows[1] if c is not None
            )
            if first_row_has_str and second_row_all_num:
                result_dict = {}
                for col_idx in range(min(len(rows[0]), len(rows[1]))):
                    key = str(rows[0][col_idx]).strip()
                    val = ComponentsReader._to_float(rows[1][col_idx])
                    if val is not None:
                        result_dict[key] = val
                return {"type": "scalar_dict", "data": result_dict}

        # ---- 规则 1 & 4: 4 列特殊表 ----
        if n_cols == 4 and n_rows >= 3:
            # 检测第 0 行或第 1 行是否含 generation / drive 关键词
            has_gen, has_drv = ComponentsReader._detect_gen_drive(rows)
            if has_gen or has_drv:
                return ComponentsReader._parse_4col_curve(rows, has_gen, has_drv)

        # ---- 规则 2: 2D MAP ----
        if n_rows >= 3 and n_cols >= 3:
            first_row_numeric = ComponentsReader._is_numeric_row(rows[0])
            first_col_numeric = ComponentsReader._is_numeric_col(rows)
            if first_row_numeric and first_col_numeric:
                return ComponentsReader._parse_map_2d(rows)

            # 检查去掉 A1 后：后续行首列是数值、后续列首行是数值
            # （A1 是混合标签如 rpm 斜杠 Nm 的情况）
            if n_rows >= 3 and n_cols >= 3:
                header_row = rows[0][1:]   # 去掉 A1 后的第一行
                header_col = [r[0] for r in rows[1:]]   # 去掉 A1 后的第一列
                if (ComponentsReader._all_floatable(header_row)
                        and ComponentsReader._all_floatable(header_col)):
                    return ComponentsReader._parse_map_2d(rows)

        # ---- 规则 3: 简单 2 列曲线 ----
        if n_cols == 2 and n_rows >= 2:
            return ComponentsReader._parse_simple_curve(rows)

        # ---- 规则 5: 通用兜底 ----
        if n_cols >= 2 and n_rows >= 2:
            return ComponentsReader._parse_simple_curve(rows)

        # 标量 / 单行
        return {"type": "scalar", "value": rows}

    # =========================================================================
    # sheet 解析器
    # =========================================================================

    @staticmethod
    def _parse_simple_curve(rows: List[List[Any]]) -> Dict[str, Any]:
        """解析简单 2 列（或多列取前 2 列）XY 曲线"""
        x, y = [], []
        # 跳过可能的表头行（非数值）
        for row in rows:
            if len(row) < 2:
                continue
            xi = ComponentsReader._to_float(row[0])
            yi = ComponentsReader._to_float(row[1])
            if xi is None or yi is None:
                continue
            x.append(xi)
            y.append(yi)

        labels = ComponentsReader._guess_labels(rows, 2)
        return {
            "type": "curve_1d",
            "x_label": labels[0],
            "y_label": labels[1],
            "x": x,
            "y": y,
            "y_abs": [abs(v) for v in y],
        }

    @staticmethod
    def _parse_4col_curve(rows: List[List[Any]], has_gen: bool,
                          has_drv: bool) -> Dict[str, Any]:
        """
        解析 4 列双曲线表

        典型结构：
          row0: ['drive', None, 'generation', None]   ← 顶层标题
          row1: ['rpm', 'Nm', 'rpm', 'Nm']            ← 列头
          row2+: [rpm, Nm, rpm, Nm]                   ← 数据

        策略：优先取 generation 侧（列 index 2 / 3），其次 drive 侧（0 / 1）
        """
        # 找数据起始行：跳过含字符串的行
        start_row = 0
        for i, row in enumerate(rows):
            if len(row) >= 4 and ComponentsReader._to_float(row[0]) is not None:
                start_row = i
                break

        if has_gen:
            # generation 侧：列 2 = rpm, 列 3 = Nm
            x_idx, y_idx = 2, 3
            x_label, y_label = "rpm", "Nm"
            side = "generation"
        elif has_drv:
            # drive 侧：列 0 = rpm, 列 1 = Nm
            x_idx, y_idx = 0, 1
            x_label, y_label = "rpm", "Nm"
            side = "drive"
        else:
            x_idx, y_idx = 0, 1
            x_label, y_label = "x", "y"
            side = "unknown"

        x, y = [], []
        # 同时收集 drive 侧和 generation 侧（如果都有的话）
        x_drv, y_drv = [], []
        x_gen, y_gen = [], []
        for row in rows[start_row:]:
            # generation 侧（列 2/3）
            xi = ComponentsReader._to_float(row[2]) if len(row) > 2 else None
            yi = ComponentsReader._to_float(row[3]) if len(row) > 3 else None
            if xi is not None and yi is not None:
                x_gen.append(xi); y_gen.append(yi)
            # drive 侧（列 0/1）
            xi = ComponentsReader._to_float(row[0]) if len(row) > 0 else None
            yi = ComponentsReader._to_float(row[1]) if len(row) > 1 else None
            if xi is not None and yi is not None:
                x_drv.append(xi); y_drv.append(yi)

        # 向后兼容：x/y/y_abs 字段保持 generation 侧
        x = x_gen if has_gen else x_drv
        y = y_gen if has_gen else y_drv

        # 新增：series 字段返回所有可用侧（前端可画多条线）
        series: List[Dict[str, Any]] = []
        if x_gen and y_gen:
            series.append({"name": "generation", "x": x_gen, "y": y_gen,
                           "y_abs": [abs(v) for v in y_gen]})
        if x_drv and y_drv:
            series.append({"name": "drive", "x": x_drv, "y": y_drv,
                           "y_abs": [abs(v) for v in y_drv]})

        print(f"[DEBUG _parse_4col_curve] has_gen={has_gen}, has_drv={has_drv} → n_gen={len(x_gen)}, n_drv={len(x_drv)}, series_count={len(series)}")

        return {
            "type": "curve_1d",
            "x_label": x_label,
            "y_label": y_label,
            "x": x,
            "y": y,
            "y_abs": [abs(v) for v in y],
            "series": series,   # 多系列（drive + generation）
        }

    @staticmethod
    def _parse_map_2d(rows: List[List[Any]]) -> Dict[str, Any]:
        """
        解析 2D MAP

        典型结构：
          A1 单元格是混合标签（如 rpm-Nm 或 转速-扭矩）
          第 1 行（去掉 A1）是 x 轴刻度（转速）
          第 1 列（去掉 A1）是 y 轴刻度（扭矩）
          交叉矩阵是 z 值（效率 / 损失 / 功率等）
        """
        # 判定 A1 是否混合标签
        a1 = rows[0][0] if rows[0] else None
        has_mixed_corner = isinstance(a1, str) and (
            "\\" in a1 or "/" in a1 or "\n" in a1
        )

        if has_mixed_corner:
            # 标准 MAP 布局：A1 是标签，后面是数值
            x_raw = rows[0][1:]
            y_raw = [r[0] for r in rows[1:]]
            z_raw = [r[1:] for r in rows[1:]]
        else:
            # 无混合角：整体都是数值矩阵
            x_raw = rows[0]
            y_raw = [r[0] for r in rows[1:]]
            z_raw = [r[1:] for r in rows[1:]]

        x = [ComponentsReader._to_float(v) for v in x_raw
             if ComponentsReader._to_float(v) is not None]
        y = [ComponentsReader._to_float(v) for v in y_raw
             if ComponentsReader._to_float(v) is not None]

        # z 矩阵：过滤 None，保留 shape
        z: List[List[float]] = []
        for row in z_raw:
            z_row = [ComponentsReader._to_float(v) or 0.0 for v in row[:len(x)]]
            if len(z_row) == len(x):
                z.append(z_row)

        # 猜 label
        x_label, y_label, z_label = ComponentsReader._guess_map_labels(rows, a1)

        print(f"[DEBUG _parse_map_2d] a1={a1!r} has_mixed={has_mixed_corner} → x_label={x_label!r}, y_label={y_label!r}, z_label={z_label!r}  x_len={len(x)}, y_len={len(y)}")

        return {
            "type": "map_2d",
            "x_label": x_label,
            "y_label": y_label,
            "z_label": z_label,
            "x": x,
            "y": y,
            "z": z,
        }

    # =========================================================================
    # JSON / YAML / CSV
    # =========================================================================

    @staticmethod
    def _read_json(file_path: str) -> Dict[str, Any]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ComponentsReader._dict_to_uniform(data)
        except Exception:
            return {}

    @staticmethod
    def _read_yaml(file_path: str) -> Dict[str, Any]:
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return ComponentsReader._dict_to_uniform(data)
        except Exception:
            return {}

    @staticmethod
    def _read_csv(file_path: str, rules: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = list(csv.reader(f))
            if len(reader) < 2:
                return {}
            # 把 csv 行转成 worksheet-like 结构再统一解析
            return {"csv": ComponentsReader._parse_worksheet(reader, rules)
                    or {"type": "scalar", "value": reader}}
        except Exception:
            return {}

    @staticmethod
    def _dict_to_uniform(data: Any) -> Dict[str, Any]:
        """把 json/yaml 顶层 dict 转成统一格式"""
        if not isinstance(data, dict):
            return {"_root": {"type": "scalar", "value": data}}

        result = {}
        for key, val in data.items():
            result[key] = ComponentsReader._value_to_uniform(val)
        return result

    @staticmethod
    def _value_to_uniform(val: Any) -> Dict[str, Any]:
        """识别 dict 内某个 value 的类型"""
        if isinstance(val, dict):
            # 尝试识别为 curve_1d: {x: [...], y: [...]}
            if ("x" in val and "y" in val
                    and isinstance(val["x"], list) and isinstance(val["y"], list)):
                return {
                    "type": "curve_1d",
                    "x_label": val.get("x_label", "x"),
                    "y_label": val.get("y_label", "y"),
                    "x": [float(v) for v in val["x"]],
                    "y": [float(v) for v in val["y"]],
                    "y_abs": [abs(float(v)) for v in val["y"]],
                }
            # 尝试识别为 map_2d
            if ("x" in val and "y" in val and "z" in val
                    and isinstance(val["x"], list) and isinstance(val["y"], list)
                    and isinstance(val["z"], list)):
                return {
                    "type": "map_2d",
                    "x_label": val.get("x_label", "x"),
                    "y_label": val.get("y_label", "y"),
                    "z_label": val.get("z_label", "z"),
                    "x": [float(v) for v in val["x"]],
                    "y": [float(v) for v in val["y"]],
                    "z": val["z"],
                }
            return {"type": "scalar", "value": val}
        return {"type": "scalar", "value": val}

    # =========================================================================
    # 辅助工具
    # =========================================================================

    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        """安全转 float，失败返回 None"""
        if v is None or v == "":
            return None
        try:
            f = float(v)
            if f != f:   # NaN 检查
                return None
            return f
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _all_floatable(values: List[Any]) -> bool:
        """所有值都能转 float"""
        return all(ComponentsReader._to_float(v) is not None for v in values)

    @staticmethod
    def _is_numeric_row(row: List[Any]) -> bool:
        """整行（除可能的 A1）都是数值"""
        numeric_count = sum(1 for v in row if ComponentsReader._to_float(v) is not None)
        return numeric_count >= len(row) - 1

    @staticmethod
    def _is_numeric_col(rows: List[List[Any]]) -> bool:
        """首列都是数值"""
        if not rows:
            return False
        numeric_count = sum(1 for r in rows
                            if r and ComponentsReader._to_float(r[0]) is not None)
        return numeric_count >= len(rows) - 1

    @staticmethod
    def _detect_gen_drive(rows: List[List[Any]]) -> Tuple[bool, bool]:
        """检测是否含 generation / drive 关键词"""
        joined = " ".join(
            str(cell).lower()
            for row in rows[:3]
            for cell in row
            if cell is not None
        )
        has_gen = any(k in joined for k in ComponentsReader.HEADER_KEYWORDS["generation"])
        has_drv = any(k in joined for k in ComponentsReader.HEADER_KEYWORDS["drive"])
        return has_gen, has_drv

    @staticmethod
    def _guess_labels(rows: List[List[Any]], n_cols: int) -> Tuple[str, str]:
        """从表头猜 x / y label"""
        labels = ["x", "y"]
        for row in rows[:2]:
            for ci in range(min(n_cols, len(row))):
                cell = str(row[ci]).lower() if row[ci] is not None else ""
                for canonical, keywords in ComponentsReader.HEADER_KEYWORDS.items():
                    if any(k in cell for k in keywords):
                        labels[ci] = canonical
                        break
        return labels[0], labels[1]

    @staticmethod
    def _guess_map_labels(rows: List[List[Any]], a1: Any) -> Tuple[str, str, str]:
        """猜 2D MAP 的三个轴 label"""
        a1_str = str(a1) if a1 else ""
        # 解析 A1 混合标签
        parts: List[str] = []
        for sep in ["\\", "/", "\n"]:
            if sep in a1_str:
                parts = [p.strip() for p in a1_str.split(sep) if p.strip()]
                break

        x_label = parts[0] if len(parts) >= 1 else "x"
        y_label = parts[1] if len(parts) >= 2 else "y"

        # 标准化到 canonical 名（按关键词长度降序遍历，长词先匹配，避免子串误匹配）
        def _canonicalize(label: str) -> str:
            if not label: return label
            for canonical, keywords in sorted(
                ComponentsReader.HEADER_KEYWORDS.items(),
                key=lambda kv: max(len(k) for k in kv[1]), reverse=True
            ):
                if any(k in label.lower() for k in keywords):
                    return canonical
            return label

        x_label = _canonicalize(x_label)
        y_label = _canonicalize(y_label)

        # z_label: 尝试在 A1 后面找关键词，或用 "z"
        z_label = "z"
        joined = " ".join(
            str(c).lower() for row in rows[:3] for c in row if c is not None
        )
        for canonical, keywords in ComponentsReader.HEADER_KEYWORDS.items():
            if canonical in ("efficiency", "power", "current", "voltage"):
                if any(k in joined for k in keywords):
                    z_label = canonical
                    break

        return x_label, y_label, z_label
