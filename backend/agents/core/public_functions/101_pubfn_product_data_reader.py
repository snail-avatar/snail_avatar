# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 101_pubfn_product_data_reader.py
# @Desc    : Public Function: 产品定义数据读取
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 101: 产品定义数据读取

提供产品定义数据的读取功能，包括：
- 获取产品定义数据（JSON 格式）
- 获取所有产品定义参数项（包含 db_key）
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


class PubfnProductDataReader(AtomicFunction):
    """产品定义数据读取 Public Function"""

    name: str = "product_data_reader"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """返回工具的 function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "产品定义数据读取工具。提供以下操作：\n"
                    "  - get_product_data: 获取产品定义数据（JSON 格式）\n"
                    "  - get_all_product_items: 获取所有产品定义参数项（包含 db_key）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": (
                                "操作类型，可选值：\n"
                                "  get_product_data / get_all_product_items"
                            ),
                        },
                    },
                    "required": ["operation"],
                },
            },
            "metadata": {
                "type": "data_read",
                "pubfn_index": "101",
            },
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Any:
        """执行产品定义数据读取原子操作"""
        operation = args.get("operation", "")
        if not operation:
            return {"type": "text", "content": "错误：必须提供 operation 参数"}

        try:
            if operation == "get_product_data":
                return cls.get_product_data(args)

            elif operation == "get_all_product_items":
                return cls.get_all_product_items(args)

            else:
                return {"type": "text", "content": f"错误：未知的操作类型 '{operation}'"}

        except Exception as e:
            return {"type": "text", "content": f"执行失败：{str(e)}"}

    # ==================================================================
    # 内部工具方法
    # ==================================================================

    @classmethod
    def _extract_items_from_dict(cls, data: Dict[str, Any]) -> List[Any]:
        """递归从嵌套字典中提取所有参数项（包含 db_key 或 名称 的字典）

        Args:
            data: get_sheet_data 返回的嵌套字典

        Returns:
            List[Any]: 所有参数项列表
        """
        items = []
        for value in data.values():
            if isinstance(value, dict):
                if "db_key" in value or "名称" in value:
                    items.append(value)
                else:
                    items.extend(cls._extract_items_from_dict(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        if "db_key" in item or "名称" in item:
                            items.append(item)
                        else:
                            items.extend(cls._extract_items_from_dict(item))
        return items

    # ==================================================================
    # 数据读取方法
    # ==================================================================

    @classmethod
    def get_product_data(cls, args: Dict[str, Any]) -> str:
        """获取产品定义数据并格式化为 JSON 字符串

        Args:
            args: 参数字典，需包含 memory_db, instance_key, vehicle_suffix

        Returns:
            str: JSON 格式的产品数据字符串
        """
        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import (
            collect_vehicles,
            get_sheet_data,
        )
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import (
            PRODUCT_DEF_SHEET_KEY,
        )

        if db is None:
            return json.dumps({"error": "当前未加载数据（memory_db 为空）"}, ensure_ascii=False)

        if instance_key:
            vehicle_names = [vehicle_suffix]
            name_to_instance_key = {vehicle_suffix: instance_key}
        else:
            vehicle_names, name_to_instance_key = collect_vehicles(db)

        if not vehicle_names:
            return json.dumps({"error": "未找到任何车型数据。"}, ensure_ascii=False)

        all_data = []

        for vehicle_name in vehicle_names:
            key = name_to_instance_key.get(vehicle_name, vehicle_name)

            sheet_data = get_sheet_data(db, key, PRODUCT_DEF_SHEET_KEY)

            if not sheet_data:
                all_data.append({
                    "车型": vehicle_name,
                    "状态": "未找到产品定义数据",
                })
                continue

            items = cls._extract_items_from_dict(sheet_data) if isinstance(sheet_data, dict) else (sheet_data if isinstance(sheet_data, list) else [])

            product_info = []
            for item in items:
                if isinstance(item, dict):
                    product_info.append({
                        "名称": item.get("名称", ""),
                        "值": item.get("值"),
                        "单位": item.get("单位", ""),
                        "db_key": item.get("db_key", ""),
                    })

            all_data.append({
                "车型": vehicle_name,
                "参数": product_info,
            })

        return json.dumps(all_data, ensure_ascii=False, indent=2)

    @classmethod
    def get_all_product_items(cls, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取所有产品定义参数项（包含 db_key）

        Args:
            args: 参数字典，需包含 memory_db, instance_key, vehicle_suffix

        Returns:
            List[Dict[str, Any]]: 所有参数项列表，每项包含 名称、值、单位、db_key
        """
        db = args.get("memory_db")
        instance_key = args.get("instance_key", "")
        vehicle_suffix = args.get("vehicle_suffix", "")

        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import (
            collect_vehicles,
            get_sheet_data,
        )
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import (
            PRODUCT_DEF_SHEET_KEY,
        )

        if db is None:
            return []

        if instance_key:
            vehicle_names = [vehicle_suffix]
            name_to_instance_key = {vehicle_suffix: instance_key}
        else:
            vehicle_names, name_to_instance_key = collect_vehicles(db)

        all_items = []

        for vehicle_name in vehicle_names:
            key = name_to_instance_key.get(vehicle_name, vehicle_name)
            sheet_data = get_sheet_data(db, key, PRODUCT_DEF_SHEET_KEY)

            if not sheet_data:
                continue

            items = cls._extract_items_from_dict(sheet_data) if isinstance(sheet_data, dict) else (sheet_data if isinstance(sheet_data, list) else [])

            for item in items:
                if isinstance(item, dict) and "db_key" in item:
                    all_items.append({
                        "名称": item.get("名称", ""),
                        "值": item.get("值"),
                        "单位": item.get("单位", ""),
                        "db_key": item.get("db_key", ""),
                    })

        return all_items
