# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : time_series_class.py
# @Desc    : 通用时间序列数据类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
通用时间序列数据类

【重要约定】
- time 字段：单位固定为秒(s)，时间轴必须单调递增
- value 字段：单位不固定，取决于具体物理量（m/s, km/h, N, W 等）
- 计算结果的单位会自动推导（如积分从 m/s 变为 m）

【混合架构】
- 数值计算层：基于 pandas（稳定、性能优化）
- 语义存储层：自研（name/unit/desc 独立存储）
- 语义传播层：自研（OP_SYMBOLS/_build_name/_build_desc）

【核心原则】
- 默认保持时间序列长度不变（提升通用性）
- 提供 keep_length 参数，允许用户选择是否保持长度
- 提供便捷方法/属性用于物理区间计算（N-1 长度）
"""

from dataclasses import dataclass
from typing import Callable, Optional, Union
import numpy as np
import pandas as pd


@dataclass
class TimeSeries:
    """
    详见文件头部的详细文档说明。
    """

    time: np.ndarray
    value: np.ndarray
    name: str = ""
    unit: str = ""
    desc: str = ""

    # ============================================
    # 【1】初始化与验证
    # ============================================
    def __post_init__(self):
        if len(self.time) != len(self.value):
            raise ValueError("时间轴与数值序列长度不匹配")

        if len(self.time) > 1 and not np.all(np.diff(self.time) >= 0):
            raise ValueError("时间序列非单调递增，非法时序")

        self._series = pd.Series(self.value, index=pd.Index(self.time, name="time"))

    # ============================================
    # 【2】核心属性（只读）
    # ============================================
    @property
    def series(self) -> pd.Series:
        """返回 pandas Series 对象"""
        return self._series
    
    @property
    def dt(self) -> np.ndarray:
        """时间步长数组（N-1 长度），供物理区间计算使用"""
        return np.diff(self.time)

    @property
    def max(self) -> float:
        """最大值"""
        return float(self._series.max())

    @property
    def min(self) -> float:
        """最小值"""
        return float(self._series.min())

    @property
    def weighted_mean(self) -> float:
        """时间加权平均值（跳过零值）"""
        dt = np.diff(self.time, prepend=self.time[0])
        mask = self._series.values != 0
        if not np.any(mask):
            return 0.0
        sum_val = np.sum(self._series.values[mask] * dt[mask])
        sum_dt = np.sum(dt[mask])
        return float(sum_val / sum_dt) if sum_dt > 0 else 0.0

    @property
    def mean(self) -> float:
        """算术平均值"""
        return float(self._series.mean())

    @property
    def total_time(self) -> float:
        """总时长"""
        return float(self.time[-1] - self.time[0]) if len(self.time) > 0 else 0.0

    @property
    def point_count(self) -> int:
        """数据点数量"""
        return len(self.time)

    @property
    def sum(self) -> float:
        """数值求和"""
        return float(self._series.sum())

    # ============================================
    # 【3】语义构建工具（内部方法）
    # ============================================
    
    OP_SYMBOLS = {
        "diff": "Δ", # 区间差分
        "diff_center": "Δc", # 中心差分
        "squared": "²", # 平方
        "abs": "‖", # 绝对值
        "integrate": "∫", # 积分
        "integrate_cum": "∫Σ", # 累积积分
        "rolling_mean": "avg", # 区间滑动平均
        "clip": "clamp", # 截断
        "sign": "sgn", # 符号函数
        "neg": "-", # 负号
        "multiply": "×", # 乘法
        "divide": "÷", # 除法
        "power": "^", # 幂
        "add": "+", # 加法
        "sub": "-", # 减法
    }
    
    def _build_name(self, op: str) -> str:
        """构建操作后的变量名"""
        symbol = self.OP_SYMBOLS.get(op, op)
        return f"{symbol}{self.name}" if self.name else f"{symbol}_ts"

    def _build_desc(self, op: str, original_desc: str = None) -> str:
        """构建操作后的描述"""
        desc = original_desc or self.desc
        op_texts = {
            "diff": "差分",
            "diff_center": "中心差分",
            "squared": "平方",
            "abs": "绝对值",
            "integrate": "积分",
            "integrate_cum": "累积积分",
            "rolling_mean": f"滑动平均",
            "clip": "限幅",
            "sign": "符号",
            "neg": "相反数",
        }
        op_text = op_texts.get(op, op)
        return f"{desc}的{op_text}" if desc else f"{op_text}"

    # ============================================
    # 【4】数值计算方法（返回 TimeSeries）
    # ============================================
    def diff(self, keep_length: bool = True) -> "TimeSeries":
        """
        差分计算
        
        Args:
            keep_length: 是否保持长度不变（默认 True）
                         - True: 返回 N 长度（末尾复制最后一个有效值）
                         - False: 返回 N-1 长度（严格物理意义）
        
        Returns:
            TimeSeries: 差分结果
        """
        result = self._series.diff().dropna()  # N-1 长度
        
        if keep_length:
            # 末尾复制最后一个有效值，保持长度
            last_val = result.iloc[-1] if len(result) > 0 else 0.0
            result = pd.concat([result, pd.Series([last_val], index=[self.time[-1]])])
        
        return TimeSeries(
            time=self.time if keep_length else self.time[:-1],
            value=result.values,
            name=self._build_name("diff"),
            unit=self.unit,
            desc=self._build_desc("diff")
        )
    
    def diff_interval(self) -> "TimeSeries":
        """区间差分，返回 N-1 长度（物理意义明确，用于区间计算）"""
        return self.diff(keep_length=False)

    def rolling_mean(self, window: int, keep_length: bool = True) -> "TimeSeries":
        """
        滑动平均
        
        Args:
            window: 滑动窗口大小
            keep_length: 是否保持长度不变（默认 True）
        
        Returns:
            TimeSeries: 滑动平均结果
        """
        if window < 1:
            raise ValueError("window must be >= 1")
        if window == 1:
            return TimeSeries(
                time=self.time,
                value=self.value.copy(),
                name=self.name,
                unit=self.unit,
                desc=self.desc
            )
        
        result = self._series.rolling(window, center=True, min_periods=1).mean()
        
        if keep_length:
            # 前后填充边缘值，保持长度
            result = result.ffill().bfill()
            return TimeSeries(
                time=self.time,
                value=result.values,
                name=self._build_name("rolling_mean"),
                unit=self.unit,
                desc=self._build_desc("rolling_mean")
            )
        else:
            # 返回 N-window+1 长度（有效窗口）
            result = result.dropna()
            return TimeSeries(
                time=self.time[(window-1)//2 : len(self.time) - window//2],
                value=result.values,
                name=self._build_name("rolling_mean"),
                unit=self.unit,
                desc=self._build_desc("rolling_mean")
            )
    
    def rolling_mean_interval(self, window: int = 2) -> "TimeSeries":
        """区间滑动平均，返回 N-1 长度（用于区间计算）"""
        if window != 2:
            raise ValueError("rolling_mean_interval 仅支持 window=2")
        
        # 手动计算两点平均，返回 N-1 长度
        values = (self.value[:-1] + self.value[1:]) / 2
        return TimeSeries(
            time=self.time[:-1],
            value=values,
            name=self._build_name("rolling_mean"),
            unit=self.unit,
            desc=self._build_desc("rolling_mean")
        )

    def squared(self) -> "TimeSeries":
        """平方运算"""
        return TimeSeries(
            time=self.time,
            value=(self._series ** 2).values,
            name=self._build_name("squared"),
            unit=f"{self.unit}²" if self.unit else "",
            desc=self._build_desc("squared")
        )

    def abs(self) -> "TimeSeries":
        """绝对值"""
        return TimeSeries(
            time=self.time,
            value=np.abs(self._series.values),
            name=self._build_name("abs"),
            unit=self.unit,
            desc=self._build_desc("abs")
        )

    def clip(self, min_val: Optional[float] = None, max_val: Optional[float] = None) -> "TimeSeries":
        """
        限幅
        
        Args:
            min_val: 最小值限制
            max_val: 最大值限制
        
        Returns:
            TimeSeries: 限幅结果
        """
        result = self._series.clip(lower=min_val, upper=max_val)
        return TimeSeries(
            time=self.time,
            value=result.values,
            name=self._build_name("clip"),
            unit=self.unit,
            desc=f"{self.desc}({min_val}~{max_val})"
        )

    def sign(self) -> "TimeSeries":
        """符号函数，返回 1、-1 或 0（根据值的正负）（物理意义明确，用于区间计算）"""
        return TimeSeries(
            time=self.time,
            value=np.sign(self._series.values),
            name=self._build_name("sign"),
            unit="",
            desc=self._build_desc("sign")
        )

    def integrate(self) -> "TimeSeries":
        """累积积分"""
        dt = np.diff(self.time, prepend=self.time[0])
        integrated = np.cumsum(self._series.values * dt)
        return TimeSeries(
            time=self.time,
            value=integrated,
            name=self._build_name("integrate_cum"),
            unit=f"{self.unit}·s" if self.unit else "s",
            desc=self._build_desc("integrate_cum")
        )

    def interp_time(self, t_target: Union[np.ndarray, list]) -> "TimeSeries":
        """
        时间插值
        
        Args:
            t_target: 目标时间点数组
        
        Returns:
            TimeSeries: 插值结果
        """
        t_target = np.asarray(t_target)
        value_interp = np.interp(t_target, self.time, self.value)
        return TimeSeries(
            time=t_target,
            value=value_interp,
            name=self.name,
            unit=self.unit,
            desc=f"{self.desc}(插值到{len(t_target)}点)"
        )

    # ============================================
    # 【5】聚合计算方法（返回标量或数组）
    # ============================================
    def trapezoid(self) -> float:
        """梯形积分（返回标量）"""
        return float(np.trapezoid(self.value, self.time))

    def time_step(self, keep_length: bool = True) -> np.ndarray:
        """
        时间步长数组
        
        Args:
            keep_length: 是否保持长度不变（默认 True）
        
        Returns:
            np.ndarray: 时间步长数组
        """
        dt = np.diff(self.time)  # N-1 长度
        
        if keep_length:
            # 末尾复制最后一个时间步长
            return np.append(dt, dt[-1]) if len(dt) > 0 else dt
        
        return dt

    # ============================================
    # 【6】条件筛选方法，例如筛选出所有大于 0 的值
    # ============================================
    def where(self, condition: Callable[[np.ndarray], np.ndarray], fill_value: float = 0.0) -> "TimeSeries":
        """
        条件筛选
        
        Args:
            condition: 条件函数，返回布尔数组
            fill_value: 不满足条件时填充的值（默认 0.0）
        
        Returns:
            TimeSeries: 筛选结果
        """
        mask = condition(self.value)
        result_value = np.where(mask, self.value, fill_value)
        return TimeSeries(
            time=self.time,
            value=result_value,
            name=self.name,
            unit=self.unit,
            desc=f"{self.desc}(条件筛选)"
        )

    # ============================================
    # 【7】运算符重载，支持 TimeSeries 之间的加减乘除操作；预留方法，后续可删除或者添加更多运算符
    # ============================================
    def __add__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(self._series + other).values,
                name=self.name,
                unit=self.unit,
                desc=self.desc
            )
        elif isinstance(other, TimeSeries):
            return TimeSeries(
                time=self.time,
                value=(self._series + other._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{self.desc}+{other.desc}"
            )
        return NotImplemented

    def __sub__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(self._series - other).values,
                name=self.name,
                unit=self.unit,
                desc=self.desc
            )
        elif isinstance(other, TimeSeries):
            return TimeSeries(
                time=self.time,
                value=(self._series - other._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{self.desc}-{other.desc}"
            )
        return NotImplemented

    def __mul__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(self._series * other).values,
                name=self.name,
                unit=self.unit,
                desc=self.desc
            )
        elif isinstance(other, TimeSeries):
            return TimeSeries(
                time=self.time,
                value=(self._series * other._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{self.desc}×{other.desc}"
            )
        return NotImplemented

    def __truediv__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            if other == 0:
                raise ValueError("Division by zero")
            return TimeSeries(
                time=self.time,
                value=(self._series / other).values,
                name=self.name,
                unit=self.unit,
                desc=self.desc
            )
        elif isinstance(other, TimeSeries):
            return TimeSeries(
                time=self.time,
                value=(self._series / other._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{self.desc}÷{other.desc}"
            )
        return NotImplemented

    def __pow__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(self._series ** other).values,
                name=self._build_name("power"),
                unit=self.unit,
                desc=f"{self.desc}的{other}次幂"
            )
        return NotImplemented

    def __neg__(self) -> "TimeSeries":
        return TimeSeries(
            time=self.time,
            value=(-self._series).values,
            name=self._build_name("neg"),
            unit=self.unit,
            desc=self._build_desc("neg")
        )

    def __pos__(self) -> "TimeSeries":
        return TimeSeries(
            time=self.time,
            value=(+self._series).values,
            name=self.name,
            unit=self.unit,
            desc=self.desc
        )

    def __radd__(self, other) -> "TimeSeries":
        return self.__add__(other)

    def __rsub__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(other - self._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{other}-{self.desc}"
            )
        return NotImplemented

    def __rmul__(self, other) -> "TimeSeries":
        return self.__mul__(other)

    def __rtruediv__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(other / self._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{other}÷{self.desc}"
            )
        return NotImplemented

    def __rpow__(self, other) -> "TimeSeries":
        if isinstance(other, (int, float)):
            return TimeSeries(
                time=self.time,
                value=(other ** self._series).values,
                name=self.name,
                unit=self.unit,
                desc=f"{other}^{self.desc}"
            )
        return NotImplemented

    # ============================================
    # 【8】序列化方法，将 TimeSeries 转换为可序列化字典格式，用于存储或传输
    # ============================================
    def to_serializable(self) -> dict:
        """转换为可序列化字典"""
        return {
            "name": self.name,
            "unit": self.unit,
            "desc": self.desc,
            "data": {
                "time": self.time.tolist(),
                "value": self.value.tolist(),
            }
        }