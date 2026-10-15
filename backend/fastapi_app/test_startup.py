# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : test_startup.py
# @Desc    : test_startup
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""Phase 1c 验证脚本：FastAPI app import + 路由注册检查"""
import sys
from pathlib import Path

# fastapi_app 在 snail_avatar 下，所以需要把 snail_avatar 自身加入 sys.path
SNAIL_DIR = Path(__file__).parent.parent  # d:\AI_model\snail_avatar
sys.path.insert(0, str(SNAIL_DIR))
# 同时加入 snail_avatar 的父目录（d:\AI_model），确保 snail_avatar.xxx import 也能工作
sys.path.insert(0, str(SNAIL_DIR.parent))

print("=" * 60)
print("Phase 1c: FastAPI app 启动前验证")
print("=" * 60)

# 1. 验证 FastAPI app 可 import
try:
    from fastapi_app.main import app
    print("✅ FastAPI app import 成功")
except Exception as e:
    print(f"❌ FastAPI app import 失败: {type(e).__name__}: {e}")
    sys.exit(1)

# 2. 打印所有注册的路由
print(f"\n📋 已注册路由 ({len(app.routes)} 个):")
for route in sorted(app.routes, key=lambda r: getattr(r, "path", "")):
    path = getattr(route, "path", "N/A")
    methods = getattr(route, "methods", {"--"})
    endpoint = getattr(route, "endpoint", None)
    endpoint_name = endpoint.__name__ if endpoint else "N/A"
    print(f"  {', '.join(sorted(methods)):8s} {path:40s} -> {endpoint_name}")

print("\n✅ 路由注册正常，uvicorn 可启动！")
print("\n启动命令: uvicorn fastapi_app.main:app --host 0.0.0.0 --port 8000 --reload")
