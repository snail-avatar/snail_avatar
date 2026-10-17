# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : expert_panels.py
# @Desc    : expert_panels
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

# -*- coding: utf-8 -*-
"""
expert_panels — 专家面板数据接口（只读 + 导入/导出）

从各 agent YAML 配置和数据文件中读取：
  - ui_config.tabs     → 面板 Tab 配置（建库/图谱/规则/案例）
  - rules/*.yaml       → 规则数据列表
  - cases/*.yaml       → 案例数据列表
  - kg/entities.json   → 知识图谱节点
  - kg/relations.json  → 知识图谱关系
  - export_to_excel / import_from_excel → 各引擎的真实导入导出

agent_id 映射到 agent 目录：
  aero_expert_agent → snail_avatar/agents/a201_aero_expert_agent
  pe_expert_agent   → snail_avatar/agents/a202_PE_expert_agent
"""
import importlib
import json
import os
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

import yaml

router = APIRouter(prefix="/api/expert", tags=["expert-panels"])

# agent_id → agent_dir 映射（对应 snail_avatar/agents/ 下的目录名）
AGENT_DIR_MAP = {
    "aero_expert_agent": "a201_aero_expert_agent",
    "pe_expert_agent": "a202_PE_expert_agent",
}

# agents 根目录（expert_panels.py 在 fastapi_app/routers/ 下，向上 3 层到 snail_avatar/）
AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent / "agents"


def _get_agent_dir(agent_id: str) -> Path:
    """解析 agent_id → 绝对路径"""
    dir_name = AGENT_DIR_MAP.get(agent_id)
    if not dir_name:
        raise HTTPException(status_code=404, detail=f"未知的 agent_id: {agent_id}")
    agent_dir = AGENTS_ROOT / dir_name
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"Agent 目录不存在: {agent_dir}")
    return agent_dir


def _load_yaml(path: Path) -> Any:
    """安全读取 YAML"""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _load_json(path: Path) -> Any:
    """安全读取 JSON"""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_agent_path(agent_dir: Path, relative: str) -> Path:
    """解析 agent 内相对路径 → 绝对路径"""
    return (agent_dir / relative).resolve()


# ============================================================
# 1. 面板配置（ui_config.tabs）
# ============================================================

class PanelConfigResp(BaseModel):
    ok: bool
    agent_id: str
    panel_id: str = ""
    panel_name: str = ""
    tabs: List[Dict[str, Any]] = []
    tabs_raw: List[Dict[str, Any]] = []


@router.get("/{agent_id}/config", response_model=PanelConfigResp)
def get_panel_config(agent_id: str):
    """返回 agent 的 ui_config（面板 Tab 配置）"""
    agent_dir = _get_agent_dir(agent_id)

    # 找 config yaml
    config_yaml = None
    for candidate in ["config/agent.yaml", f"config/{agent_id}.yaml"]:
        cfg = _load_yaml(agent_dir / candidate)
        if cfg:
            config_yaml = cfg
            break

    if not config_yaml:
        # fallback: 扫描 config/ 目录下第一个 yaml
        cfg_dir = agent_dir / "config"
        if cfg_dir.exists():
            for f in sorted(cfg_dir.glob("*.yaml")):
                config_yaml = _load_yaml(f)
                if config_yaml:
                    break

    if not config_yaml:
        return PanelConfigResp(ok=False, agent_id=agent_id)

    ui_config = config_yaml.get("ui_config", {})
    tabs_raw = ui_config.get("tabs", [])

    # 简化：每个 tab 只返回前端需要的字段
    tabs = []
    for t in tabs_raw:
        tabs.append({
            "type": t.get("type", ""),
            "label": t.get("label", ""),
            "has_vector_index": bool(t.get("vector_collection_name")),
        })

    return PanelConfigResp(
        ok=True,
        agent_id=agent_id,
        panel_id=ui_config.get("panel_id", ""),
        panel_name=ui_config.get("panel_name", ""),
        tabs=tabs,
        tabs_raw=tabs_raw,  # 保留完整配置供前端后续扩展
    )


# ============================================================
# 2. 规则列表
# ============================================================

@router.get("/{agent_id}/rules")
def get_rules(agent_id: str):
    """返回规则列表"""
    agent_dir = _get_agent_dir(agent_id)
    cfg = get_panel_config(agent_id)

    # 从 tabs_raw 找到 rules tab 的 data_path
    data_path = None
    for t in cfg.tabs_raw:
        if t.get("type") == "rules":
            data_path = t.get("data_path")
            break

    if not data_path:
        return {"ok": True, "rules": [], "data_path": None}

    full_path = _resolve_agent_path(agent_dir, data_path)
    content = _load_yaml(full_path)
    if not content:
        return {"ok": True, "rules": [], "data_path": str(full_path), "reason": "文件不存在或解析失败"}

    rules = content.get("rules", content if isinstance(content, list) else [])
    return {"ok": True, "rules": rules, "data_path": str(full_path)}


# ============================================================
# 3. 案例列表
# ============================================================

@router.get("/{agent_id}/cases")
def get_cases(agent_id: str):
    """返回案例列表"""
    agent_dir = _get_agent_dir(agent_id)
    cfg = get_panel_config(agent_id)

    data_path = None
    for t in cfg.tabs_raw:
        if t.get("type") == "cases":
            data_path = t.get("data_path")
            break

    if not data_path:
        return {"ok": True, "cases": [], "data_path": None}

    full_path = _resolve_agent_path(agent_dir, data_path)
    content = _load_yaml(full_path)
    if not content:
        return {"ok": True, "cases": [], "data_path": str(full_path), "reason": "文件不存在或解析失败"}

    cases = content.get("cases", content if isinstance(content, list) else [])
    return {"ok": True, "cases": cases, "data_path": str(full_path)}


# ============================================================
# 4. 知识图谱（节点 + 关系）
# ============================================================

@router.get("/{agent_id}/knowledge_graph")
def get_graph(agent_id: str):
    """返回知识图谱（entities + relations）"""
    agent_dir = _get_agent_dir(agent_id)
    cfg = get_panel_config(agent_id)

    data_dir = None
    for t in cfg.tabs_raw:
        if t.get("type") == "knowledge_graph":
            data_dir = t.get("data_dir")
            break

    if not data_dir:
        return {"ok": True, "nodes": [], "relations": []}

    kg_dir = _resolve_agent_path(agent_dir, data_dir)

    entities = _load_json(kg_dir / "entities.json") or {}
    relations = _load_json(kg_dir / "relations.json") or {}

    nodes = entities.get("nodes", []) if isinstance(entities, dict) else []
    rels = relations.get("relations", []) if isinstance(relations, dict) else []

    # 构建 node_id → node 映射，方便前端找 from_name / to_name
    node_map = {n.get("id"): n for n in nodes if isinstance(n, dict)}

    # 给 relations 加上 from_name / to_name（前端直接显示）
    enriched_rels = []
    for r in rels:
        if not isinstance(r, dict):
            continue
        from_node = node_map.get(r.get("from", ""), {})
        to_node = node_map.get(r.get("to", ""), {})
        enriched_rels.append({
            **r,
            "from_name": from_node.get("name", r.get("from", "")),
            "to_name": to_node.get("name", r.get("to", "")),
        })

    return {
        "ok": True,
        "nodes": nodes,
        "relations": enriched_rels,
        "kg_dir": str(kg_dir),
    }


# ============================================================
# 5. 建库管理状态（向量库目录存在性 + 文件列表）
# ============================================================

@router.get("/{agent_id}/kb-stats")
def get_kb_stats(agent_id: str):
    """返回向量库状态：物理文件 + 所有 Chroma collection 的统计"""
    agent_dir = _get_agent_dir(agent_id)

    # 找 embedding.yaml
    embedding_cfg = None
    for candidate in ["components/embedding/embedding.yaml"]:
        cfg = _load_yaml(agent_dir / candidate)
        if cfg:
            embedding_cfg = cfg
            break

    if not embedding_cfg:
        return {"ok": False, "reason": "未找到 embedding.yaml", "persist_dir": "", "exists": False}

    vs = embedding_cfg.get("vector_store", {})
    persist_rel = vs.get("persist_dir", "")
    default_collection = vs.get("collection_name", "")

    if not persist_rel:
        return {"ok": False, "reason": "persist_dir 未配置", "exists": False}

    # 解析 persist_dir（相对于 embedding.yaml 所在目录）
    emb_dir = agent_dir / "components" / "embedding"
    persist_path = (emb_dir / persist_rel).resolve()

    exists = persist_path.exists()
    files = []
    total_size = 0
    if exists:
        for f in persist_path.iterdir():
            if f.is_file():
                sz = f.stat().st_size
                total_size += sz
                files.append({
                    "name": f.name,
                    "size": sz,
                    "mtime": f.stat().st_mtime,
                })

    # --- 从 Chroma 读取所有 collection 的统计 ---
    all_collections: List[Dict[str, Any]] = []
    total_vectors = 0
    ingested_files: List[Dict[str, Any]] = []
    if exists:
        try:
            from snail_avatar.backend.agents.core.tools.embedding.vector_store import VectorStore
            vs_obj = VectorStore(
                persist_dir=str(persist_path),
                embedding_fn=None,
            )
            # Chroma client 实例已存在于 vs_obj._client
            client = vs_obj._client
            all_names = [c.name for c in client.list_collections()]

            for col_name in sorted(all_names):
                col = client.get_collection(name=col_name)
                cnt = col.count()
                total_vectors += cnt

                col_info: Dict[str, Any] = {
                    "collection_name": col_name,
                    "vector_count": cnt,
                }

                # 聚合 source 统计（仅当有数据时）
                if cnt > 0:
                    try:
                        results = col.get(include=["metadatas"])
                        source_counts: Dict[str, int] = {}
                        for meta in results.get("metadatas", []) or []:
                            src = meta.get("source", "") if meta else ""
                            if src:
                                source_counts[src] = source_counts.get(src, 0) + 1
                        # 单个 collection 内的 source 列表
                        col_info["sources"] = [
                            {"name": s, "chunks": c} for s, c in sorted(source_counts.items())
                        ]
                        # 汇总到全局 ingested_files
                        for src, c in sorted(source_counts.items()):
                            existing = next((x for x in ingested_files if x["name"] == src), None)
                            if existing:
                                existing["chunks"] += c
                            else:
                                ingested_files.append({"name": src, "chunks": c})
                    except Exception:
                        pass

                all_collections.append(col_info)
        except Exception:
            # Chroma 读取失败不影响主状态返回
            pass

    # data_dir 下有哪些可入库文件
    data_dir = agent_dir / "data"
    data_files = []
    if data_dir.exists():
        SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".txt", ".md"}
        for f in data_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED:
                data_files.append({"name": f.name, "size": f.stat().st_size})

    return {
        "ok": True,
        "persist_dir": str(persist_path),
        "persist_dir_exists": exists,
        "default_collection": default_collection,
        "all_collections": all_collections,
        "collection_count": len(all_collections),
        "total_vectors": total_vectors,
        "ingested_files": sorted(ingested_files, key=lambda x: x["name"]),
        "ingested_file_count": len(ingested_files),
        "vector_files": files,
        "vector_file_count": len(files),
        "vector_total_size": total_size,
        "data_dir": str(data_dir),
        "data_dir_exists": data_dir.exists(),
        "data_files": data_files,
        "data_file_count": len(data_files),
    }


# ============================================================
# 6. 通用引擎创建 + import/export Excel 辅助
# ============================================================

# tab_type → (engine_class_path, tab_cfg_attr, engine_kwarg_name)
# engine_class_path 在运行时动态 import（避免 import 错误阻塞路由注册）
ENGINE_MAP = {
    "rules": (
        "snail_avatar.backend.agents.core.knowledge_engines.rule_engine.RuleEngine",
        "data_path",     # ← YAML tabs[type=rules].data_path
        "rules_path",    # ← RuleEngine(data_path=...)
    ),
    "cases": (
        "snail_avatar.backend.agents.core.knowledge_engines.case_engine.CaseEngine",
        "data_path",     # ← YAML tabs[type=cases].data_path
        "cases_path",    # ← CaseEngine(cases_path=...)
    ),
    "knowledge_graph": (
        "snail_avatar.backend.agents.core.knowledge_engines.knowledge_graph_engine.KnowledgeGraphEngine",
        "data_dir",      # ← YAML tabs[type=knowledge_graph].data_dir
        "data_dir",      # ← KnowledgeGraphEngine(data_dir=...)
    ),
}


def _get_engine_for_tab(agent_id: str, tab_type: str):
    """根据 agent_id + tab_type 动态实例化引擎"""
    if tab_type not in ENGINE_MAP:
        raise HTTPException(status_code=400, detail=f"不支持的 tab_type: {tab_type}")

    agent_dir = _get_agent_dir(agent_id)
    cfg = get_panel_config(agent_id)
    tabs_raw = cfg.tabs_raw

    class_path, tab_attr, kwarg_name = ENGINE_MAP[tab_type]

    # 从 tabs_raw 找对应 tab 的数据路径
    tab_cfg = next((t for t in tabs_raw if t.get("type") == tab_type), {})
    rel_path = tab_cfg.get(tab_attr, "")
    if not rel_path:
        raise HTTPException(status_code=400, detail=f"该 tab 未配置 {tab_attr}")

    abs_path = _resolve_agent_path(agent_dir, rel_path)

    # 动态 import
    module_path, class_name = class_path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    EngineClass = getattr(mod, class_name)

    return EngineClass(**{kwarg_name: str(abs_path)})


# ============================================================
# 7. 导出 Excel（真实调用 engine.export_to_excel → 下载）
# ============================================================

@router.get("/{agent_id}/{tab_type}/export")
def export_excel(agent_id: str, tab_type: str):
    """调用引擎 export_to_excel 生成临时 Excel → 返回 FileResponse 下载"""
    if tab_type not in ENGINE_MAP:
        raise HTTPException(status_code=400, detail=f"不支持导出的 tab_type: {tab_type}")

    try:
        engine = _get_engine_for_tab(agent_id, tab_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"引擎加载失败: {e}")

    # 生成临时 Excel
    tmp_dir = tempfile.mkdtemp(prefix="expert_export_")
    export_name = f"{tab_type}_{agent_id}.xlsx"
    export_path = Path(tmp_dir) / export_name

    try:
        ok = engine.export_to_excel(str(export_path))
        if not ok or not export_path.exists():
            raise HTTPException(status_code=500, detail="引擎导出失败（返回 False 或文件未生成）")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出异常: {e}")

    return FileResponse(
        path=str(export_path),
        filename=export_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{export_name}"'},
    )


# ============================================================
# 8. 导入 Excel（接收 multipart → 调用 engine.import_from_excel）
# ============================================================

@router.post("/{agent_id}/{tab_type}/import")
async def import_excel(agent_id: str, tab_type: str, file: UploadFile = File(...)):
    """接收上传的 .xlsx → 保存临时文件 → 调用引擎 import_from_excel"""
    if tab_type not in ENGINE_MAP:
        raise HTTPException(status_code=400, detail=f"不支持导入的 tab_type: {tab_type}")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")

    # 保存到临时目录
    tmp_dir = tempfile.mkdtemp(prefix="expert_import_")
    tmp_path = Path(tmp_dir) / file.filename
    content = await file.read()
    tmp_path.write_bytes(content)

    try:
        engine = _get_engine_for_tab(agent_id, tab_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"引擎加载失败: {e}")

    try:
        ok = engine.import_from_excel(str(tmp_path))
        if ok:
            # 刷新内存引擎数据（下次 GET 就能读回来）
            engine.reload() if hasattr(engine, 'reload') else None
            return {"ok": True, "message": "导入成功"}
        else:
            return {"ok": False, "message": "导入失败（引擎返回 False）"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入异常: {e}")
    finally:
        # 清理临时文件（不阻塞响应）
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ============================================================
# 9. 构建向量索引（遍历引擎数据 → embedding → Chroma）
# ============================================================


def _items_to_chunks(tab_type: str, items: List[Dict[str, Any]]) -> List[Any]:
    """把引擎返回的条目转为 DocumentChunk，用于 VectorStore.add_documents

    不同 tab_type 拼接不同的文本字段作为 embedding 输入。
    """
    from snail_avatar.backend.agents.core.tools.embedding.data_types import DocumentChunk

    chunks = []
    for item in items:
        item_id = str(item.get("id", item.get("node_id", "")))
        if not item_id:
            continue

        if tab_type == "rules":
            # 规则：name + category + description + formula
            text_parts = [
                item.get("name", ""),
                item.get("category", ""),
                item.get("description", ""),
                item.get("formula", ""),
            ]
            source = item.get("source", "rules")
        elif tab_type == "cases":
            # 案例：title + category + vehicle_type + description + key_params + results
            text_parts = [
                item.get("title", ""),
                item.get("category", ""),
                item.get("vehicle_type", ""),
                item.get("description", ""),
                item.get("key_params", ""),
                item.get("results", ""),
            ]
            source = item.get("source", "cases")
        elif tab_type == "knowledge_graph":
            # 知识图谱节点：name + type + desc
            text_parts = [
                item.get("name", ""),
                item.get("type", ""),
                item.get("desc", item.get("description", "")),
            ]
            source = "knowledge_graph"
        else:
            continue

        text = "\n".join(p for p in text_parts if p).strip()
        if not text:
            continue

        # 把条目所有字段透传到 metadata（VectorStore 会清洗成 Chroma 支持的类型）
        meta = dict(item)
        meta["source"] = source

        chunks.append(DocumentChunk(
            chunk_id=item_id,
            text=text,
            metadata=meta,
        ))

    return chunks


@router.post("/{agent_id}/{tab_type}/build-vector-index")
def build_vector_index(agent_id: str, tab_type: str):
    """用引擎的全量数据重建 Chroma 向量索引（先清空，再全量写入）"""
    if tab_type not in ENGINE_MAP:
        raise HTTPException(status_code=400, detail=f"不支持的 tab_type: {tab_type}")

    agent_dir = _get_agent_dir(agent_id)
    cfg = get_panel_config(agent_id)
    tabs_raw = cfg.tabs_raw

    # 从 tabs_raw 拿 embedding_config 路径和 vector_collection_name
    tab_cfg = next((t for t in tabs_raw if t.get("type") == tab_type), {})
    embedding_rel = tab_cfg.get("embedding_config")
    collection_name = tab_cfg.get("vector_collection_name")

    if not embedding_rel:
        raise HTTPException(status_code=400, detail=f"该 tab 未配置 embedding_config")
    if not collection_name:
        raise HTTPException(status_code=400, detail=f"该 tab 未配置 vector_collection_name")

    embedding_cfg_path = _resolve_agent_path(agent_dir, embedding_rel)
    if not embedding_cfg_path.exists():
        raise HTTPException(status_code=400, detail=f"embedding 配置文件不存在: {embedding_cfg_path}")

    # 1. 实例化引擎 → 取全量条目
    try:
        engine = _get_engine_for_tab(agent_id, tab_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"引擎加载失败: {e}")

    t0 = time.time()
    if tab_type == "knowledge_graph":
        items = engine.get_all_nodes()
    else:
        items = engine.get_all()

    if not items:
        return {"ok": False, "message": "引擎无数据，跳过构建向量索引", "count": 0}

    # 2. 条目 → DocumentChunk
    chunks = _items_to_chunks(tab_type, items)
    if not chunks:
        return {"ok": False, "message": f"共 {len(items)} 条数据，但无有效文本可向量化", "count": 0}

    # 3. 构造 VectorStore + MultiModalEmbedding（VectorStore 默认从 embedding.yaml 读 persist_dir，
    #    但 collection_name 需用 tab_cfg 里的覆盖值，因为 embedding.yaml 里默认是 docs 的集合名）
    try:
        from snail_avatar.backend.agents.core.tools.embedding import MultiModalEmbedding, VectorStore

        embed_fn = MultiModalEmbedding(config_path=str(embedding_cfg_path))

        # 先加载 embedding.yaml 拿到 persist_dir，然后覆盖 collection_name 构造 VectorStore
        with open(embedding_cfg_path, "r", encoding="utf-8") as f:
            emb_cfg = yaml.safe_load(f) or {}
        vs_cfg = emb_cfg.get("vector_store", {})
        persist_dir = vs_cfg.get("persist_dir", "../../data/vector_db")
        # 相对 embedding.yaml 的路径
        persist_dir = str((embedding_cfg_path.parent / persist_dir).resolve())

        vs = VectorStore(
            persist_dir=persist_dir,
            embedding_fn=embed_fn,
        )
        # 切换到当前 tab 专属的 collection
        vs._collection_name = collection_name
        vs._collection = vs._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量库初始化失败: {e}")

    # 4. 清空旧索引 → 全量写入
    try:
        vs.clear_all()
        added = vs.add_documents(chunks)
        elapsed = round(time.time() - t0, 2)

        return {
            "ok": True,
            "message": "向量索引构建成功",
            "collection_name": collection_name,
            "total_items": len(items),
            "added": added,
            "elapsed_seconds": elapsed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量写入失败: {e}")


# ============================================================
# 10. 建库管理：文档入库（多文件上传 → 分块 → Chroma）
# ============================================================

SUPPORTED_DOC_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif", ".txt", ".md"}


@router.post("/{agent_id}/knowledge_base/ingest")
async def ingest_documents(agent_id: str, files: List[UploadFile] = File(...)):
    """接收上传的多份文档 → DocumentProcessor 分块 → VectorStore 写入"""
    agent_dir = _get_agent_dir(agent_id)

    # 1. 找 embedding.yaml（knowledge_base 的 embedding_config 在 tabs 里）
    cfg = get_panel_config(agent_id)
    kb_tab = next((t for t in cfg.tabs_raw if t.get("type") == "knowledge_base"), {})
    embedding_rel = kb_tab.get("embedding_config", "components/embedding/embedding.yaml")
    embedding_cfg_path = _resolve_agent_path(agent_dir, embedding_rel)

    if not embedding_cfg_path.exists():
        raise HTTPException(status_code=400, detail=f"embedding 配置文件不存在: {embedding_cfg_path}")

    # 2. 保存上传文件到临时目录
    import asyncio
    tmp_dir = tempfile.mkdtemp(prefix="expert_ingest_")
    saved_paths = []
    try:
        for f in files:
            if not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in SUPPORTED_DOC_EXT:
                continue  # 跳过不支持的类型
            tmp_path = Path(tmp_dir) / f.filename
            content = await f.read()
            tmp_path.write_bytes(content)
            saved_paths.append(str(tmp_path))
    except Exception as e:
        # 清理
        for p in Path(tmp_dir).iterdir():
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            Path(tmp_dir).rmdir()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"文件保存失败: {e}")

    if not saved_paths:
        return {"ok": False, "message": "没有支持的文档文件（支持类型: PDF / 图片 / TXT / MD）"}

    # 3. 构造 DocumentProcessor + VectorStore + MultiModalEmbedding
    try:
        from snail_avatar.backend.agents.core.tools.embedding import (
            DocumentProcessor, MultiModalEmbedding, VectorStore,
        )

        # 加载 embedding 配置
        with open(embedding_cfg_path, "r", encoding="utf-8") as f:
            emb_cfg = yaml.safe_load(f) or {}

        doc_proc_cfg = emb_cfg.get("document_processor", {})
        embed_fn = MultiModalEmbedding(config_path=str(embedding_cfg_path))

        # VectorStore：persist_dir 相对于 embedding.yaml
        vs_cfg = emb_cfg.get("vector_store", {})
        persist_dir = vs_cfg.get("persist_dir", "../../data/vector_db")
        persist_dir = str((embedding_cfg_path.parent / persist_dir).resolve())

        vs = VectorStore(
            persist_dir=persist_dir,
            embedding_fn=embed_fn,
            config_path=str(embedding_cfg_path),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量库初始化失败: {e}")

    # 4. 逐文件分块 + 写入
    t0 = time.time()
    proc = DocumentProcessor(config=doc_proc_cfg)

    total_chunks = 0
    files_ok = 0
    files_fail = 0
    per_file = []

    try:
        for fpath in saved_paths:
            fname = os.path.basename(fpath)
            try:
                chunks = proc.process_file(fpath)
                if chunks:
                    added = vs.add_documents(chunks)
                    total_chunks += added
                    files_ok += 1
                    per_file.append({"file": fname, "chunks": len(chunks), "added": added})
                else:
                    files_ok += 1
                    per_file.append({"file": fname, "chunks": 0, "added": 0, "note": "无可分块内容"})
            except Exception as e:
                files_fail += 1
                per_file.append({"file": fname, "error": str(e)})
    finally:
        # 清理临时文件
        try:
            for p in Path(tmp_dir).iterdir():
                p.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass

    elapsed = round(time.time() - t0, 2)
    return {
        "ok": True,
        "message": "文档入库完成",
        "collection_name": vs._collection_name,
        "files_total": len(saved_paths),
        "files_ok": files_ok,
        "files_fail": files_fail,
        "chunks_added": total_chunks,
        "elapsed_seconds": elapsed,
        "details": per_file,
    }
