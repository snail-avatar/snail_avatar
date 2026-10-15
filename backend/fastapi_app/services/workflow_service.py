# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : workflow_service.py
# @Desc    : workflow_service
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
Workflow Service — HTTP 层特有：执行 workflow + 格式化给前端

共享逻辑（registry 管理、YAML 匹配、纯构建）已搬到：
  snail_avatar.backend.agents.core.workflow_base.workflow_registry

本文件只保留 FastAPI 路由特有的：
  - run_workflow()：执行 + 写回 memorydb + 节点/变量/可视化格式化
  - get_workflow_nodes()：只构建不执行，返回节点拓扑（前端 DAG 图）
"""

import time
from typing import Any, Dict, List, Optional, Tuple

# === 从共享层 import（agent 也用同一个 workflow_registry）===
from snail_avatar.backend.agents.core.workflow_base.workflow_registry import (
    _safe_json,
    WORKFLOW_REGISTRY,
    scan_workflows,
    _resolve_registry,
    _resolve_yaml_path,
    build_workflow_from_yaml_file,
)

# 向后兼容别名（workflows.py router 里有 import WORKFLOW_REGISTRY / scan_workflows）
# 不需要额外导出，上面已经直接 import 进来了


# =========================================================================
# 执行工作流（HTTP 层特有）
# =========================================================================

def run_workflow(
    panel_or_wfid: str,
    vehicle_suffix: str,
    memory_db: Any,
) -> Dict[str, Any]:
    """
    执行指定 workflow，返回执行结果 + 节点列表

    使用 workflow_builder.build_workflow_from_yaml_file（和 flet 架构同一条正确路径），
    不再需要 post-build 打补丁。
    """
    reg = _resolve_registry(panel_or_wfid)

    # 1. 先匹配出具体的 workflow YAML 路径
    yaml_path = _resolve_yaml_path(reg, memory_db, vehicle_suffix)

    # 2. SSTS workflow：用现成的 _prepare_sandbox（内部会 auto_load_for_agent）
    sandbox = None
    if reg.get("use_ssts_executor", False):
        try:
            sandbox, _ = _prepare_sandbox(panel_or_wfid, memory_db)
            print(f"[DEBUG sandbox] prepared for {panel_or_wfid}, "
                  f"loaded_files={sandbox.loaded_file_count}, "
                  f"has Motor={bool(sandbox.list_instances('Motor', vehicle_suffix))}, "
                  f"has Battery={bool(sandbox.list_instances('Battery', vehicle_suffix))}")
        except Exception as e:
            print(f"[DEBUG sandbox] _prepare_sandbox FAILED: {e}")
            sandbox = None

    # 3. 用 workflow_builder 正确构建（和 flet 同一条路径，无缺陷）
    wf = build_workflow_from_yaml_file(
        yaml_path=yaml_path,
        vehicle_suffix=vehicle_suffix,
        memory_db=memory_db,
        nodes_pkg_path=reg["nodes_pkg_path"],
        sandbox=sandbox,
    )

    # 3. 执行
    start = time.time()
    exec_result = wf.run_all(reset_first=True)
    duration = round(time.time() - start, 3)

    # 3.5 写回计算结果到 memory_db（仅 SSTS/VTS output）
    # 让 VTS/SSTS 面板和 MemoryDB 面板能看到最新计算值
    # 注意：intermediate 中间变量已经通过 inter_data（带 workflow_id 隔离层）在节点间正确流转，
    # reset_first 会清空整个 workflow_id 层。绝对不能再写入 memorycore，否则会污染 SSTS 参数！
    def _write_back_node_outputs(node_instance: Any) -> int:
        """把一个节点的 SSTS/VTS output 值写回 memory_db，返回写入数量"""
        count = 0
        if memory_db is None or not hasattr(memory_db, 'set_ssts_vts_param'):
            return 0
        suffix = vehicle_suffix or getattr(node_instance, 'vehicle_suffix', '')
        if not suffix:
            return 0

        # 3.5a SSTS/VTS output：ssts_vts_schema 里 direction="output" → ssts_values
        # 这些是最终性能指标（如 t_0_100, v_max_1km），本来就应该写进 memorycore
        # 注意：node 的 numerical_solve() 里已经自己调过 _sync_ssts_vts_output 写了一遍，
        # 这里是 run_workflow 收尾时的兜底写入（防止某些 node 漏写）
        try:
            ssts_schema = getattr(node_instance, "ssts_vts_schema", {}) or {}
            ssts_values = getattr(node_instance, "ssts_values", {}) or {}
            for vname, meta in ssts_schema.items():
                if not isinstance(meta, dict):
                    continue
                if meta.get("direction") != "output":
                    continue
                val = ssts_values.get(vname)
                if val is None:
                    continue
                db_key = f"{vname}_result_{suffix}"
                try:
                    ok = memory_db.set_ssts_vts_param(db_key, val)
                    if ok:
                        count += 1
                except Exception:
                    pass
        except Exception:
            pass

        # !!! 3.5b intermediate output 已删除（污染 memorycore 的根因）!!!
        # intermediate 变量（如 bat_pmax 轮端等效值）只能在 inter_data 层流转，
        # 绝对不能用 set_ssts_vts_param 写进 memorycore，否则下次 run 时会被
        # _load_and_check_ssts_vts() 当作 SSTS 原始参数读到，导致 bat_pmax 等
        # 每次 run 被 ×mot_pow_eff×axle_eff 覆盖一次，无限递减。

        return count

    write_back_total = 0
    for nid, node in wf.all_nodes.items():
        ni = node.node_instance
        write_back_total += _write_back_node_outputs(ni)

    # 4. 收集节点状态 + 输入输出变量（前端 autoLayout 不使用 position，传占位值即可）
    node_list = []
    for nid, node in wf.all_nodes.items():
        ni = node.node_instance
        try:
            state = getattr(ni, "state", "unknown")
            state_str = state.name.lower() if hasattr(state, "name") else str(state).lower()
        except Exception:
            state_str = "unknown"

        # 收集输入变量（ssts_vts_schema 里 direction="input" 的）
        input_vars = {}
        try:
            ssts_schema = getattr(ni, "ssts_vts_schema", {}) or {}
            ssts_values = getattr(ni, "ssts_values", {}) or {}
            for vname, meta in ssts_schema.items():
                if not isinstance(meta, dict):
                    continue
                # 只收 input；output 走下面的 output_vars
                if meta.get("direction") == "output":
                    continue
                input_vars[vname] = {
                    "value": _safe_json(ssts_values.get(vname, meta.get("default"))),
                    "unit": meta.get("unit", ""),
                    "description": meta.get("description", vname),
                    "direction": "input",
                }
        except Exception:
            pass

        # SSTSCalculationNode：注入沙箱快照摘要
        # 直接复用 SSTSSandbox.snapshot() —— 结构与参数浏览器 Tab 完全一致
        # （suffix → component → instance → _variants → variant → sheets → sheet 元信息）
        # 已自动剥掉大数组数据（x/y/z 等），只留 type+shape 摘要，payload 安全
        # 白名单过滤：从 node YAML 读 sandbox_components，只保留本节点关心的零部件
        try:
            sandbox = getattr(ni, "sandbox", None)
            if sandbox is not None:
                suffix = getattr(ni, "vehicle_suffix", "")
                full = sandbox.snapshot()
                suffix_data = full.get("data", {}).get(suffix, {})
                # 白名单过滤（node YAML 声明 sandbox_components → 只留这些 component）
                allowed = getattr(ni, "sandbox_components", None) or []
                filtered = suffix_data
                if allowed:
                    filtered = {k: v for k, v in suffix_data.items() if k in allowed}
                if filtered:
                    input_vars["sandbox_snapshot"] = {
                        "value": filtered,
                        "unit": "",
                        "description": f"沙箱 {suffix} 快照（组件白名单: {allowed or '全部'}）",
                        "direction": "input",
                    }
        except Exception:
            pass

        print(f"[DEBUG final] node={nid}, input_vars_keys={list(input_vars.keys())}")

        # 收集输出变量（合并两类：ssts_vts_schema direction=output + intermediate_output_schema）
        output_vars = {}
        try:
            # 3.6a SSTS/VTS output（direction="output" 的 ssts_vts_schema）
            ssts_schema = getattr(ni, "ssts_vts_schema", {}) or {}
            ssts_values = getattr(ni, "ssts_values", {}) or {}
            for vname, meta in ssts_schema.items():
                if not isinstance(meta, dict):
                    continue
                if meta.get("direction") != "output":
                    continue
                output_vars[vname] = {
                    "value": _safe_json(ssts_values.get(vname, meta.get("default"))),
                    "unit": meta.get("unit", ""),
                    "description": meta.get("description", vname),
                    "type": str(meta.get("type", "")),
                    "schema_type": "ssts_vts",
                }

            # 3.6b intermediate output（intermediate_output_schema）
            out_schema = getattr(ni, "intermediate_output_schema", {}) or {}
            out_values = getattr(ni, "intermediate_output_values", None)
            if out_values is None:
                out_values = getattr(ni, "output_values", {}) or {}
            for vname, meta in out_schema.items():
                if isinstance(meta, dict):
                    val = None
                    try:
                        val = out_values.get(vname) if isinstance(out_values, dict) else None
                    except Exception:
                        val = None
                    output_vars[vname] = {
                        "value": _safe_json(val),
                        "unit": meta.get("unit", ""),
                        "description": meta.get("description", vname),
                        "type": str(meta.get("type", "")),
                        "schema_type": "intermediate",
                    }
        except Exception:
            pass

        # 收集 visualization 数据（和 flet workflow_tab_base.py 同一路径）
        visualization_list = []
        try:
            # 路径1：子类显式实现的 generate_visualization()
            if hasattr(ni, 'generate_visualization'):
                viz = ni.generate_visualization()
                if viz is not None:
                    # generate_visualization 可能返回单个 dict 或 list
                    if isinstance(viz, list):
                        visualization_list.extend(viz)
                    else:
                        visualization_list.append(viz)
            # 路径2：YAML auto-infer 兜底（flet 的 ChartPanel.update_chart 也是这个顺序）
            if not visualization_list and hasattr(ni, '_auto_infer_visualization_from_yaml'):
                auto = ni._auto_infer_visualization_from_yaml()
                if auto is not None:
                    visualization_list.extend(auto if isinstance(auto, list) else [auto])
        except Exception as e:
            import traceback; traceback.print_exc()
            pass

        node_list.append({
            "node_id": nid,
            "node_display_name": getattr(ni, "node_display_name", nid),
            "state": state_str,
            "position": [0, 0],  # 前端 autoLayout 不使用此值
            "upstream": node.upstream_node_ids,
            "has_visualization": bool(visualization_list),
            "visualizations": [_safe_json(v) for v in visualization_list],
            "input_vars": input_vars,
            "output_vars": output_vars,
        })

    return {
        "workflow_id": wf.workflow_id,
        "workflow_name": wf.topology_config.get("workflow_name", wf.workflow_id),
        "vehicle_suffix": vehicle_suffix,
        "duration_sec": duration,
        "completed": exec_result.get("completed", 0),
        "errors": exec_result.get("errors", 0),
        "nodes": node_list,
    }


def get_workflow_nodes(
    panel_or_wfid: str,
    vehicle_suffix: str = "",
    memory_db: Any = None,
) -> List[Dict[str, Any]]:
    """
    只构建工作流不执行，返回节点拓扑（用于前端 DAG 图渲染）
    """
    reg = _resolve_registry(panel_or_wfid)

    yaml_path = _resolve_yaml_path(reg, memory_db, vehicle_suffix)

    wf = build_workflow_from_yaml_file(
        yaml_path=yaml_path,
        vehicle_suffix=vehicle_suffix,
        memory_db=memory_db,
        nodes_pkg_path=reg["nodes_pkg_path"],
    )

    nodes = []
    for nid, node in wf.all_nodes.items():
        ni = node.node_instance
        nodes.append({
            "node_id": nid,
            "node_display_name": getattr(ni, "node_display_name", nid),
            "node_category": getattr(ni, "node_category", ""),
            "node_description": getattr(ni, "node_description", ""),
            "position": [0, 0],  # 前端 autoLayout 不使用此值
            "upstream": node.upstream_node_ids,
            "ssts_vts_schema": _safe_json(getattr(ni, "ssts_vts_schema", {})),
            "intermediate_output_schema": _safe_json(getattr(ni, "intermediate_output_schema", {})),
        })
    return nodes


# =========================================================================
# SSTS 沙箱快照 / 单 sheet 详情（UI 沙箱内存 Tab 用）
# =========================================================================

def _prepare_sandbox(panel_or_wfid: str,
                     memory_db: Any) -> Tuple[Any, Dict[str, Any]]:
    """
    内部辅助：根据 panel_or_wfid 定位 agent config → 创建 SSTSSandbox → auto_load_for_agent。

    返回 (sandbox, agent_config)。两个 HTTP 端点（snapshot / sheet_detail）共用。
    """

    reg = _resolve_registry(panel_or_wfid)
    agent_dir = reg.get("agent_dir", "")

    # 1. 找到 agent config yaml（读 sandbox_config）
    agent_config: Dict[str, Any] = {}
    if agent_dir:
        import os as _os
        import yaml as _yaml
        config_dir = _os.path.join(agent_dir, "config")
        if _os.path.isdir(config_dir):
            for fname in ["agent.yaml",
                          f"{reg.get('panel_id', '')}.yaml",
                          "energy_regeneration.yaml"]:
                cand = _os.path.join(config_dir, fname)
                if _os.path.isfile(cand):
                    try:
                        with open(cand, "r", encoding="utf-8") as f:
                            agent_config = _yaml.safe_load(f) or {}
                        break
                    except Exception as e:
                        continue
            if not agent_config:
                # 兜底：扫 config/*.yaml，找含 sandbox_config 的
                for root, _, files in _os.walk(config_dir):
                    for fname in files:
                        if not fname.endswith((".yaml", ".yml")):
                            continue
                        cand = _os.path.join(root, fname)
                        try:
                            with open(cand, "r", encoding="utf-8") as f:
                                data = _yaml.safe_load(f) or {}
                            if isinstance(data, dict) and "sandbox_config" in data:
                                agent_config = data
                                break
                        except Exception:
                            continue
                    if agent_config:
                        break

    # 2. 创建 sandbox + 自动加载
    from snail_avatar.backend.agents.core.workflow_base.ssts_sandbox import SSTSSandbox

    sb = SSTSSandbox(global_db=memory_db)
    n = sb.auto_load_for_agent(agent_config, memory_db)

    return sb, agent_config


def get_sandbox_snapshot(panel_or_wfid: str,
                         vehicle_suffix: str,
                         memory_db: Any) -> Dict[str, Any]:
    """
    创建 SSTSSandbox → 自动加载 → 返回 snapshot
    """
    sb, _ = _prepare_sandbox(panel_or_wfid, memory_db)

    snap = sb.snapshot()
    return _safe_json(snap)


def get_sandbox_sheet_detail(panel_or_wfid: str,
                             vehicle_suffix: str,
                             component: str,
                             instance: str,
                             variant: str,
                             sheet_name: str,
                             memory_db: Any) -> Dict[str, Any]:
    """
    创建临时 SSTSSandbox → auto_load_for_agent → get_sheet_data → 返回单个 sheet 的完整数据。

    和 get_sandbox_snapshot 类似，但只返回一个 sheet（leaf 节点）的完整数据，
    用于前端"点击 sheet 节点 → 右侧展示该 sheet 完整数据"。
    """
    sb, _ = _prepare_sandbox(panel_or_wfid, memory_db)

    sheet_data = sb.get_sheet_data(
        suffix=vehicle_suffix,
        component=component,
        instance=instance,
        variant=variant,
        sheet_name=sheet_name,
    )

    if sheet_data is None:
        return {
            "ok": False,
            "error": (f"未找到 {vehicle_suffix}/{component}/{instance}/{variant}/{sheet_name}"),
        }

    return {
        "ok": True,
        "vehicle_suffix": vehicle_suffix,
        "component": component,
        "instance": instance,
        "variant": variant,
        "sheet_name": sheet_name,
        "data": _safe_json(sheet_data),
    }
