# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : 003_pubfn_open_project_file.py
# @Desc    : Public Function: 根据自然语言模糊匹配并打开 data 目录下的项目 Excel 文件
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议

"""
Public Function 003: 打开项目 Excel 文件

根据用户的自然语言描述（如 "蜗牛项目 V6.0 最新版"），
模糊匹配 data 目录根下的项目 Excel 数据文件。

三种返回状态：
  - unique_match:  唯一高分命中，直接加载到 memory_db
  - need_confirm:  多个分数接近的候选，返回列表由 LLM 追问用户
  - no_match:      没有有效匹配，列出当前所有可用文件

文件名特征（data 目录实际模式）：
  {项目名}项目-VTS_SSTS_{版本}_ini[_{后缀}].xlsx
  例：蜗牛项目-VTS_SSTS_V6.0_ini_更新.xlsx

命名规范：继承 AtomicFunction（纯数据操作，不调用其他 Agent）
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from snail_avatar.backend.agents.core.public_functions_core.function_base import AtomicFunction


# ==========================================================================
# 内部数据结构
# ==========================================================================

@dataclass
class CandidateFile:
    """候选文件"""
    file_path: str
    file_name: str
    score: float = 0.0
    # 从文件名提取的特征（调试 / 返回给 LLM 用）
    project_name: str = ""
    version: str = ""
    suffix_tags: List[str] = field(default_factory=list)


# ==========================================================================
# PubfnOpenProjectFile — 主类
# ==========================================================================

class PubfnOpenProjectFile(AtomicFunction):
    """根据自然语言模糊匹配并加载项目 Excel 文件"""

    name: str = "open_project_file"

    # 匹配判定阈值
    MIN_VALID_SCORE = 30.0       # 最低有效分（低于此视为未匹配）
    UNIQUE_GAP = 15.0            # 第一名与第二名的最小分差（高于此视为唯一命中）

    # data 目录下项目名候选（从文件名动态学习，这里先枚举已知的）
    KNOWN_PROJECT_NAMES = ["蜗牛", "越野", "峰璟"]

    # 更新 / 新版意图关键词
    UPDATE_INTENT_KEYWORDS = ["最新", "更新", "新版", "最近", "new", "latest"]

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "根据用户的自然语言描述，匹配并加载 data 目录下的项目 Excel 数据文件。\n\n"
                    "【精确文件名匹配优先】\n"
                    "如果你已经知道确切的文件名称（含 .xlsx 后缀的完整文件名，或含 -VTS_SSTS_ 模式的文件名片段），\n"
                    "直接把精确文件名作为 query 参数传入即可，本工具会快速精确匹配并直接加载。\n\n"
                    "【自然语言模糊匹配】\n"
                    "支持按项目名称（蜗牛、越野、峰璟等）、版本号（V6.0、V0.0等）、更新状态等关键词组合查询。\n"
                    "当模糊匹配结果不唯一时，会返回候选列表，由助手询问用户确认；"
                    "当没有匹配结果时，会列出当前 data 目录下所有可用文件供用户参考。\n\n"
                    "【多轮对话中的序号指代处理】\n"
                    "当用户回复序号指代（如“第三个”、“第3项”、“3号”）或模糊指代（如“初始版”、“最新那个”）时，\n"
                    "你必须先从本工具上一轮返回的候选列表中解析出精确的文件名称，\n"
                    "然后把该精确文件名（含 .xlsx 后缀）作为 query 参数传入本工具。\n"
                    "不要把序号文本（如 “3”）或简短指代（如 “第三个”）直接作为 query 传入。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "查询字符串。两种用法：\n"
                                "  1) 精确文件名：直接传完整文件名（如 '蜗牛项目-VTS_SSTS_V6.0_ini.xlsx'），工具会快速精确匹配并加载\n"
                                "  2) 自然语言：传模糊描述（如 '蜗牛项目 V6.0 最新版'），工具会做模糊打分\n"
                                "多轮对话中遇到用户序号回复时，你必须先从候选列表解析出精确文件名再传入，不要直接传序号文本。"
                            )
                        }
                    },
                    "required": ["query"]
                }
            },
            "metadata": {
                "type": "file_loader",
                "pubfn_index": "003",
            }
        }

    @classmethod
    def _execute_atomic(cls, args: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """执行匹配 + 加载（精确匹配优先，兜底模糊打分）"""
        query = (args.get("query") or "").strip()
        if not query:
            return cls._format_no_match(
                reason="查询为空，请提供项目名称或版本等描述信息"
            )

        # 1. 扫描 data 目录
        data_dir, files = cls._scan_data_dir()
        if not files:
            return cls._format_no_match(
                reason=f"data 目录（{data_dir}）下暂无可用的 .xlsx 文件"
            )

        # 2. 精确文件名匹配快速路径（LLM 传了完整文件名时，跳过模糊打分）
        exact_hits = cls._try_filename_exact_match(query, files)
        if exact_hits is not None:
            if len(exact_hits) == 1:
                # 唯一精确命中，直接加载
                exact_hits[0].score = 200.0  # 标记为精确匹配
                return cls._load_file(exact_hits[0])
            elif len(exact_hits) > 1:
                # 多个文件同时精确命中（罕见），走 need_confirm
                for h in exact_hits:
                    h.score = 200.0
                return cls._format_need_confirm(exact_hits[:3])
            # exact_hits 为空列表 → 没匹配上，继续走模糊打分

        # 3. 对每个文件模糊打分
        candidates = cls._score_candidates(query, files)

        # 4. 按分数排序
        candidates.sort(key=lambda c: c.score, reverse=True)

        # 5. 判定匹配结果并分支
        return cls._decide_and_execute(candidates, data_dir)

    # ------------------------------------------------------------------
    # Step 1: 扫描 data 目录
    # ------------------------------------------------------------------

    @classmethod
    def _scan_data_dir(cls) -> Tuple[str, List[str]]:
        """扫描 data 目录根下所有有效 .xlsx 文件

        Returns:
            tuple: (data_dir, [file_path, ...])
        """
        from snail_avatar.backend.core.path_utils import get_resource_dir

        data_dir = os.path.join(get_resource_dir(), "data")
        if not os.path.isdir(data_dir):
            return data_dir, []

        files = []
        for fname in os.listdir(data_dir):
            # 只取根目录 .xlsx；跳过 Excel 临时锁文件（~$ 开头）
            if not fname.endswith(".xlsx"):
                continue
            if fname.startswith("~$"):
                continue
            full_path = os.path.join(data_dir, fname)
            if os.path.isfile(full_path):
                files.append(full_path)

        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)  # 最新修改时间优先
        return data_dir, files

    # ------------------------------------------------------------------
    # Step 1.5: 精确文件名匹配（快速路径，跳过模糊打分）
    # ------------------------------------------------------------------

    @classmethod
    def _try_filename_exact_match(
        cls, query: str, scan_files: List[str]
    ) -> Optional[List[CandidateFile]]:
        """尝试把 query 当作精确文件名来匹配

        匹配规则（按优先级依次尝试，命中即返回）：
          1) query 以 .xlsx 结尾 → 按 file_name 精确比较（忽略大小写）
          2) query 去掉 .xlsx 后缀后等于某个文件的 stem → 命中
          3) query 足够长（≥ 15 字符）且包含文件名标志性片段（-VTS_SSTS-）
             → 做 stem 包含匹配，只返回唯一命中；多命中则视为不明确（返回 None 让模糊打分接管）

        Returns:
            - List[CandidateFile]: 匹配到的文件列表（精确命中场景）
            - None: query 看起来不是精确文件名（应该走模糊打分）
            - []: 看起来是精确文件名但一个都没匹配上（异常情况）
        """
        # 先把所有 scan_files 解析成 CandidateFile（需要 file_name 和 stem）
        candidates = [cls._parse_filename(p) for p in scan_files]

        # 预处理 query：去掉空白、统一全角符号
        q = query.strip()

        # ---- 规则 1 & 2：query 以 .xlsx 结尾 ----
        if q.lower().endswith(".xlsx"):
            # 精确 file_name 比较（忽略大小写）
            hits = [c for c in candidates if c.file_name.lower() == q.lower()]
            if hits:
                return hits
            # query 带 .xlsx 但精确没匹配上，可能是 LLM 给的文件名有偏差
            # 再试一次 stem 包含匹配
            q_stem = re.sub(r"\.xlsx$", "", q, flags=re.IGNORECASE)
            hits = [c for c in candidates if c.file_name.lower().startswith(q_stem.lower())]
            if hits:
                return hits
            # 明确 .xlsx 结尾但一个都没匹配上 → 返回空列表（不是 None）
            return []

        # ---- 规则 3：query 包含 -VTS_SSTS- 标志性片段 ----
        if "-vts_ssts-" in q.lower() and len(q) >= 15:
            # query 看起来是标准项目文件名的 stem
            hits = [c for c in candidates if q.lower() in c.file_name.lower()]
            if len(hits) == 1:
                return hits
            # 多命中 → 让模糊打分接管（query 太宽泛）
            return None

        # ---- 兜底：query 足够长（≥ 25 字符） → 尝试 stem 包含匹配 ----
        if len(q) >= 25 and ("_" in q or "-" in q):
            hits = [c for c in candidates if q.lower() in c.file_name.lower()]
            if len(hits) == 1:
                return hits
            if len(hits) > 1:
                # 多命中（少见）→ 返回让上层 need_confirm
                return hits

        # 以上都不满足 → 不是精确文件名，返回 None 让模糊打分接管
        return None

    # ------------------------------------------------------------------
    # Step 2: 解析文件名特征
    # ------------------------------------------------------------------

    @classmethod
    def _parse_filename(cls, file_path: str) -> CandidateFile:
        """从文件名中提取项目名、版本、后缀关键词"""
        file_name = os.path.basename(file_path)
        # 去掉 .xlsx 后缀
        stem = re.sub(r"\.xlsx$", "", file_name)

        candidate = CandidateFile(
            file_path=file_path,
            file_name=file_name,
        )

        # 尝试从文件名中匹配项目名（已知列表）
        for pname in cls.KNOWN_PROJECT_NAMES:
            if pname in stem:
                candidate.project_name = pname
                break

        # 尝试从文件名中提取版本号（V + 数字.数字，如 V6.0、V0.0、V1.2.3）
        ver_match = re.search(r"V(\d+(?:\.\d+)*)", stem, re.IGNORECASE)
        if ver_match:
            candidate.version = "V" + ver_match.group(1)

        # 提取后缀片段（_ 分隔的 token，排除已知固定词）
        # 模式: {项目名}项目-VTS_SSTS_{版本}_ini[_tag1_tag2...].xlsx
        # 把所有 _ 分隔的部分拿出来做 tags
        parts = re.split(r"[-_]", stem)
        known_tokens = {"VTS", "SSTS", "INI"}
        tags = []
        for part in parts:
            part_upper = part.upper()
            if part_upper in known_tokens:
                continue
            # 跳过项目名/版本号（已经单独提取）
            if part == candidate.project_name or part == candidate.version.replace("V", ""):
                continue
            if part:
                tags.append(part)
        candidate.suffix_tags = tags

        return candidate

    # ------------------------------------------------------------------
    # Step 3: 对 query 中的关键词和每个候选文件打分
    # ------------------------------------------------------------------

    @classmethod
    def _score_candidates(cls, query: str, file_paths: List[str]) -> List[CandidateFile]:
        """对所有候选文件打分"""
        # 先把所有文件解析成 CandidateFile
        candidates = [cls._parse_filename(p) for p in file_paths]

        # 从 query 中提取关键词
        query_project_names = cls._extract_project_names(query)
        query_version = cls._extract_version(query)
        has_update_intent = cls._has_update_intent(query)
        query_keywords = cls._extract_keywords(query)

        # 逐文件打分
        for c in candidates:
            score = 5.0  # 基础分：所有有效文件都有

            # --- 项目名匹配（权重最高）---
            if query_project_names:
                if c.project_name and c.project_name in query_project_names:
                    score += 50.0  # 项目名精确命中
                else:
                    score -= 10.0  # query 指定了项目名但此文件不匹配

            # --- 版本号匹配 ---
            if query_version:
                if c.version and c.version.upper() == query_version.upper():
                    score += 30.0  # 版本号精确命中
                elif c.version:
                    score -= 5.0  # 版本号不匹配

            # --- 更新/新版意图 ---
            if has_update_intent:
                # 文件名含 "更新" / "update" 则加分
                combined_tags = " ".join(c.suffix_tags).lower() + " " + c.file_name.lower()
                if any(kw in combined_tags for kw in ["更新", "update", "new"]):
                    score += 15.0
                # 最新修改时间的文件也加一点分
                mtime = os.path.getmtime(c.file_path)
                score += min(abs(mtime) % 10, 5)  # 最多额外 +5

            # --- 通用关键词子串命中 ---
            for kw in query_keywords:
                if kw in c.file_name:
                    score += 10.0

            # --- "panel" / 面板 关键词（query 含此则排除 _panel 文件）---
            if "panel" in query.lower() or "面板" in query:
                if "_panel" in c.file_name.lower():
                    score += 5.0
            else:
                if "_panel" in c.file_name.lower():
                    score -= 5.0  # 默认排除 panel 文件

            c.score = max(score, 0.0)  # 不允许负分

        return candidates

    @classmethod
    def _extract_project_names(cls, query: str) -> List[str]:
        """从 query 中提取已知项目名"""
        found = []
        for pname in cls.KNOWN_PROJECT_NAMES:
            if pname in query:
                found.append(pname)
        return found

    @classmethod
    def _extract_version(cls, query: str) -> Optional[str]:
        """从 query 中提取版本号（如 V6.0）"""
        m = re.search(r"V(\d+(?:\.\d+)*)", query, re.IGNORECASE)
        if m:
            return "V" + m.group(1)
        return None

    @classmethod
    def _has_update_intent(cls, query: str) -> bool:
        """判断 query 是否表达了 '最新/更新' 意图"""
        q_lower = query.lower()
        return any(kw in q_lower for kw in cls.UPDATE_INTENT_KEYWORDS)

    @classmethod
    def _extract_keywords(cls, query: str) -> List[str]:
        """从 query 中提取通用关键词（非停用词的短 token）"""
        # 简单策略：按常见分词标点拆，过滤停用词
        stopwords = {
            "的", "了", "请", "把", "帮", "我", "要", "打开", "文件", "项目",
            "那个", "这个", "一下", "吧", "啊", "呢", "吗", "是", "就",
            "数据", "excel", "表",
        }
        raw_tokens = re.split(r"[\s,，。.!！?？、\-_（）()【】\[\]]+", query)
        keywords = []
        for tok in raw_tokens:
            tok = tok.strip()
            if len(tok) >= 2 and tok not in stopwords:
                # 跳过纯版本号（已经单独处理）
                if re.match(r"^V\d", tok, re.IGNORECASE):
                    continue
                keywords.append(tok)
        return keywords

    # ------------------------------------------------------------------
    # Step 4: 判定 + 执行
    # ------------------------------------------------------------------

    @classmethod
    def _decide_and_execute(
        cls, candidates: List[CandidateFile], data_dir: str
    ) -> Dict[str, Any]:
        """根据打分结果决定是直接加载、返回候选列表还是报告未匹配"""
        if not candidates:
            return cls._format_no_match(reason="data 目录扫描无结果")

        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None

        # 全部低于阈值 → no_match
        if best.score < cls.MIN_VALID_SCORE:
            return cls._format_no_match(
                reason=f"未找到匹配文件（最高分 {best.score:.0f}，阈值 {cls.MIN_VALID_SCORE}）",
                all_files=candidates,
            )

        # 唯一高分：没有第二或分差足够大
        is_unique = (second is None) or (best.score - second.score >= cls.UNIQUE_GAP)

        if is_unique:
            return cls._load_file(best)

        # 需要用户确认
        top3 = candidates[:3]
        return cls._format_need_confirm(top3)

    # ------------------------------------------------------------------
    # Step 5: 加载文件（同步调用 MemoryDatabase + 写入唯一权威槽）
    # ------------------------------------------------------------------

    @classmethod
    def _load_file(cls, candidate: CandidateFile) -> Dict[str, Any]:
        """同步加载 Excel 文件到 memory_db

        注意：function calling 上下文没有 Flet page / asyncio，
        因此直接调用 Core 层的 MemoryDatabase（纯同步），不使用 UI 层的 load_excel_file。
        """
        from snail_avatar.backend.core.memory.memory_database import MemoryDatabase
        from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import set_memory_db
        from snail_avatar.backend.core.work_log import WorkLogger

        file_path = candidate.file_path
        log_messages = []

        def log_cb(msg: str):
            log_messages.append(msg)

        try:
            memory_db = MemoryDatabase(file_path=file_path, log_callback=log_cb)
            memory_db.load_from_excel()

            # 写入唯一权威槽
            set_memory_db(memory_db)

            sheet_count = len(memory_db.sheet_names())
            veh_count = len(memory_db.vehsuffix) if hasattr(memory_db, "vehsuffix") else 0

            WorkLogger.info(f"[open_project_file] 已加载: {candidate.file_name}")
            WorkLogger.info(f"[open_project_file] Sheet数: {sheet_count}, 车型后缀数: {veh_count}")

            return {
                "type": "text",
                "content": (
                    f"已加载项目文件: {candidate.file_name}\n"
                    f"匹配分数: {candidate.score:.0f}\n"
                    f"数据概览: {sheet_count} 个 Sheet"
                    + (f", {veh_count} 个车型后缀" if veh_count else "")
                ),
                "summary": {
                    "status": "unique_match",
                    "file_path": file_path,
                    "file_name": candidate.file_name,
                    "score": round(candidate.score, 1),
                    "sheet_count": sheet_count,
                    "veh_suffix_count": veh_count,
                    "action_taken": "loaded",
                }
            }

        except Exception as e:
            WorkLogger.error(f"[open_project_file] 加载失败: {e}")
            return {
                "type": "text",
                "content": f"文件匹配成功但加载失败: {candidate.file_name}\n错误详情: {e}",
                "summary": {
                    "status": "load_failed",
                    "file_path": file_path,
                    "error": str(e),
                }
            }

    # ------------------------------------------------------------------
    # 格式化返回值
    # ------------------------------------------------------------------

    @classmethod
    def _format_need_confirm(cls, candidates: List[CandidateFile]) -> Dict[str, Any]:
        """多个候选，需要用户确认"""
        content_lines = []
        summary_candidates = []
        for i, c in enumerate(candidates, 1):
            line = f"{i}. {c.file_name} (得分: {c.score:.0f})"
            content_lines.append(line)
            summary_candidates.append({
                "rank": i,
                "file_path": c.file_path,
                "file_name": c.file_name,
                "score": round(c.score, 1),
            })

        text_content = "\n".join(content_lines)
        return {
            "type": "list",
            "title": "找到多个匹配的项目文件，请确认要打开哪一个：",
            "content": content_lines,
            "summary": {
                "status": "need_confirm",
                "candidates": summary_candidates,
                "count": len(candidates),
                "hint": "请让用户回复序号（如 '第一个' / '1'）或完整文件名，然后再次调用本工具时传入更精确的 query",
            }
        }

    @classmethod
    def _format_no_match(
        cls, reason: str = "", all_files: Optional[List[CandidateFile]] = None
    ) -> Dict[str, Any]:
        """未找到匹配"""
        content_lines = []
        if all_files:
            for i, c in enumerate(all_files, 1):
                content_lines.append(f"{i}. {c.file_name}")

        title = "未找到匹配的项目文件"
        if reason:
            title += f"（{reason}）"

        if content_lines:
            content_lines.insert(0, "当前 data 目录下可用的项目文件：")

        return {
            "type": "list" if content_lines else "text",
            "title": title,
            "content": content_lines if content_lines else "data 目录下暂无 Excel 文件",
            "summary": {
                "status": "no_match",
                "reason": reason,
                "all_files_count": len(all_files) if all_files else 0,
                "hint": "建议让用户提供更多关键词（如项目名、版本号、是否最新）后重试",
            }
        }


# 向后兼容别名
OpenProjectFileFunction = PubfnOpenProjectFile
