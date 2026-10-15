# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : a101_step1_save_mapping.py
# @Desc    : Public Function (a101 step1): 映射关系保存 - 兼容别名
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function (a101 step1): 映射关系保存 - 兼容别名

此文件已废弃，仅作为向后兼容的别名。
实际功能已迁移到：
1. 框架自动处理：通过 YAML 的 loop_config 配置（推荐）
2. 通用函数：204_pubfn_loop_config.py 中的 set_loop_config

迁移说明：
- 新项目：使用 loop_config 配置
- 旧代码：如需手动调用，请使用 set_loop_config 函数
"""

from __future__ import annotations

from snail_avatar.backend.agents.core.public_functions.204_pubfn_loop_config import PubfnLoopConfig


# 兼容别名：保持旧的函数名称
class A101Step1SaveMapping(PubfnLoopConfig):
    """映射关系保存 Public Function（兼容别名）

    已迁移到 PubfnLoopConfig（set_loop_config）。
    保留此类仅为向后兼容，新代码请使用 loop_config 配置。
    """

    # 保持旧的函数名称
    name: str = "save_mapping_to_controller"


# 注册到函数注册表（保持向后兼容）
__all__ = ["A101Step1SaveMapping"]