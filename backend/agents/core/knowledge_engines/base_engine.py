# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : base_engine.py
# @Desc    : 知识库引擎基类
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
知识库引擎基类

定义所有知识库引擎的通用接口，包括：
- 规则引擎
- 案例引擎
- 知识图谱引擎

同时提供通用的多关键词拆分和评分搜索方法，子类的 search() 可直接调用。
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple


class BaseEngine(ABC):
    """知识库引擎基类"""

    # 多关键词拆分的分隔符正则：空格、顿号、中英文逗号、中英文分号
    _SPLIT_PATTERN = re.compile(r'[\s、，,；;]+')
    # 引号对正则：匹配成对的中文/英文单双引号内容
    _QUOTE_PATTERN = re.compile(r'["\"\"\'\']([^"\"\"\'\']+)["\"\"\'\']')
    # 最小关键词长度（过滤过短的噪声词）
    _MIN_KEYWORD_LEN = 2

    @abstractmethod
    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """关键词搜索"""
        pass

    @abstractmethod
    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有条目"""
        pass

    @abstractmethod
    def export_to_excel(self, file_path: str) -> bool:
        """导出到Excel"""
        pass

    @abstractmethod
    def import_from_excel(self, file_path: str) -> bool:
        """从Excel导入"""
        pass

    @abstractmethod
    def save(self) -> None:
        """保存到持久化存储"""
        pass

    # ------------------------------------------------------------------
    # 通用多关键词搜索方法（子类可调用）
    # ------------------------------------------------------------------

    def _split_keywords(self, query: str) -> List[str]:
        """将查询字符串拆分为多个关键词

        拆分规则：
        1. 先提取引号（单双引号、中英文）内的完整内容作为独立关键词
        2. 去除引号后，剩余文本按空格、顿号、逗号、分号等分隔符拆分
        3. 过滤空字符串和过短词（<2字符）

        Args:
            query: 用户输入的查询字符串

        Returns:
            拆分后的关键词列表
        """
        keywords: List[str] = []

        # 步骤1: 提取引号内的内容作为独立关键词
        quoted_matches = self._QUOTE_PATTERN.findall(query)
        keywords.extend(quoted_matches)

        # 步骤2: 去除引号内容后，按分隔符拆分剩余文本
        text_without_quotes = self._QUOTE_PATTERN.sub(' ', query)
        parts = self._SPLIT_PATTERN.split(text_without_quotes)

        for part in parts:
            part = part.strip()
            if len(part) >= self._MIN_KEYWORD_LEN:
                keywords.append(part)

        # 去重并保持顺序
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords

    def _multi_keyword_search(
        self,
        items: List[Dict[str, Any]],
        get_search_text: Callable[[Dict[str, Any]], Tuple[str, str]],
        query: str,
    ) -> List[Dict[str, Any]]:
        """通用多关键词评分搜索

        对每个条目计算匹配评分：每命中一个关键词 +1，如果命中的是 name 字段再额外 +1。
        至少命中一个关键词的条目才会被返回，按评分从高到低排序。

        Args:
            items: 待搜索的条目列表
            get_search_text: 回调函数，接收一个条目，返回 (name_text, full_search_text)
                             name_text 用于加权匹配，full_search_text 用于普通匹配
            query: 用户输入的查询字符串

        Returns:
            按评分排序的匹配结果列表
        """
        keywords = self._split_keywords(query)

        # 如果拆分后只有0或1个关键词，退化为整串子串匹配（保持向后兼容）
        if len(keywords) <= 1:
            keyword_lower = query.lower().strip()
            if not keyword_lower:
                return []
            results = []
            for item in items:
                _, full_text = get_search_text(item)
                if keyword_lower in full_text.lower():
                    results.append(item)
            return results

        # 多关键词评分匹配
        scored_items: List[Tuple[int, Dict[str, Any]]] = []
        for item in items:
            name_text, full_text = get_search_text(item)
            name_lower = name_text.lower()
            full_lower = full_text.lower()

            score = 0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in full_lower:
                    score += 1
                    # 名称字段命中额外加权
                    if kw_lower in name_lower:
                        score += 1

            if score > 0:
                scored_items.append((score, item))

        # 按评分从高到低排序
        scored_items.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_items]
