# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : test_memory_db.py
# @Desc    : test_memory_db
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""Phase 2 验证：MemoryDatabase API 测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # d:\AI_model
sys.path.insert(0, str(Path(__file__).parent.parent))  # d:\AI_model\snail_avatar

from snail_avatar.backend.core.memory.memory_database import MemoryDatabase

db = MemoryDatabase()

# 1. 测试 get_vehsuffix
print("=== get_vehsuffix ===")
vehs = db.get_vehsuffix()
print(f"返回类型: {type(vehs)}")
print(f"内容: {vehs[:2] if vehs else '(空)'}...")

# 2. 测试 memorycore 结构
print("\n=== memorycore 结构 ===")
print(f"memorycore keys (前5): {list(db.memorycore.keys())[:5]}")
if db.memorycore:
    first_key = list(db.memorycore.keys())[0]
    first_val = db.memorycore[first_key]
    print(f"  [{first_key}] type: {type(first_val).__name__}")
    if isinstance(first_val, dict):
        print(f"  keys (前3): {list(first_val.keys())[:3]}")

# 3. 测试是否有数据
print("\n=== 数据加载状态 ===")
print(f"data 非空: {bool(db.data)}")
print(f"memorycore 非空: {bool(db.memorycore)}")
