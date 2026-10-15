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
    """返回向量库状态（从 embedding.yaml 读 persist_dir，检查目录）"""
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
    collection_name = vs.get("collection_name", "")

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
        "collection_name": collection_name,
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
