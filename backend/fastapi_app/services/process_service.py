# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : process_service.py
# @Desc    : process_service
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""
流程执行服务 — 管理 ProcessContext 后台运行 + SSE 进度推送

核心架构：
  ProcessService 维护 instance_key → RunState 的映射。
  RunState 包含：
    - queue.Queue       : 进度事件队列（SSE endpoint 从此消费）
    - threading.Lock    : 防止同一 instance_key 并发 run_flow
    - threading.Event   : 完成信号（后台线程 set，主线程 wait）
    - threading.Thread  : 后台 run_flow 线程
    - started / finished: 状态标志

SSE 事件格式（统一 JSON，含 type 字段）：
  {"type": "step_start",    "step_id": "...", "step_name": "...", "loop_item": "...", ...}
  {"type": "step_progress", "progress": 0.45, "current_loop_item": "...", "outer_step": "..."}
  {"type": "step_complete", "step_id": "...", "step_result": {...}}
  {"type": "heartbeat",     "ts": "..."}
  {"type": "done",          "status": "success|error|stopped|paused", "summary": {...}}
  {"type": "error",         "message": "..."}
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, Optional

from snail_avatar.backend.fastapi_app.dependencies import get_process_context


class RunState:
    """单个 instance_key 的运行时状态容器"""

    def __init__(self):
        self.queue: queue.Queue = queue.Queue()
        self.lock: threading.Lock = threading.Lock()
        self.done_event: threading.Event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.started: bool = False
        self.finished: bool = False
        self.final_result: Optional[Dict[str, Any]] = None


class ProcessService:
    """流程执行服务（单例，模块级）"""

    # instance_key → RunState
    _states: Dict[str, RunState] = {}
    # 保护 _states dict 本身的锁
    _states_lock = threading.Lock()
    # per-instance 停止请求标记 — stop_process 把 instance_key 加到这里，
    # worker 线程在 run_flow 返回后检查并把 status 改为 stopped
    # 注意：ProcessEngine._stop_flag 是引擎级单例（跨 instance_key 共享），
    # 所以并发多车型 run_flow 时 stop() 会同时停所有。
    # 当前假设同一时间只有一个活跃 run_flow（snail_avatar 业务层设计如此）
    _stop_requests: set = set()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_json(obj: Any) -> Any:
        """递归处理不可 JSON 序列化的对象，把它们 str() 掉；NaN/Inf 转为 None"""
        import math
        if isinstance(obj, dict):
            return {k: ProcessService._safe_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ProcessService._safe_json(v) for v in obj]
        if isinstance(obj, float):
            # Python 原生 float('nan') / float('inf') 无法被 json.dumps 序列化
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, (str, int, bool)) or obj is None:
            return obj
        return str(obj)

    # ------------------------------------------------------------------
    # 内部状态管理
    # ------------------------------------------------------------------

    @classmethod
    def _get_or_create_state(cls, instance_key: str) -> RunState:
        """获取或创建 RunState（线程安全）"""
        with cls._states_lock:
            state = cls._states.get(instance_key)
            if state is None:
                state = RunState()
                cls._states[instance_key] = state
            return state

    @classmethod
    def _cleanup_state(cls, instance_key: str):
        """清理已完成的状态（保留 5 分钟后可清理，目前先不清理）"""
        pass

    # ------------------------------------------------------------------
    # 车型列表（复用 ListVehiclesFunction）
    # ------------------------------------------------------------------

    @classmethod
    def list_vehicles(cls) -> Dict[str, Any]:
        """列出可执行目标值定义的车型"""
        from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import collect_vehicles

        db = get_memory_db() or get_process_context()._memory_db
        if db is None:
            return {"vehicles": [], "total": 0, "message": "未加载数据"}

        try:
            names, name_to_mc_key = collect_vehicles(db)
        except Exception as e:
            return {"vehicles": [], "total": 0, "message": f"读取失败: {e}"}

        vehicles = []
        for name in names:
            mc_key = name_to_mc_key.get(name, name)
            # 尝试从 vehsuffix 里取对应 suffix
            suffix = ""
            try:
                for v in db.vehsuffix or []:
                    if isinstance(v, dict) and (v.get("车型") or v.get("车型名称")) == name:
                        suffix = str(v.get("车型后缀", "") or "")
                        break
            except Exception:
                pass
            vehicles.append({
                "name": name,
                "instance_key": mc_key,
                "suffix": suffix,
            })

        return {"vehicles": vehicles, "total": len(vehicles)}

    # ------------------------------------------------------------------
    # 步骤列表（前端预渲染时间线）
    # ------------------------------------------------------------------

    @classmethod
    def get_steps(cls) -> Dict[str, Any]:
        """获取流程的步骤拓扑（外层 + 内层 + 循环 + 条件映射）

        注意：OUTER_STEPS/INNER_STEPS 等是 context 初始化时的缓存。
        直接调 workflow_engine 的实时方法，确保最新结果。
        """
        ctx = get_process_context()
        engine = ctx._workflow_engine
        # 用实时方法（而非 context 的缓存 property）
        outer = engine.get_outer_steps()
        inner = engine.get_inner_steps()
        return {
            "outer_steps": [{"step_id": sid, "step_name": sname} for sid, sname in outer],
            "inner_steps": [{"step_id": sid, "step_name": sname} for sid, sname in inner],
            "loop_step_ids": engine.get_all_loop_ids(),
            "conditional_optional_map": engine.workflow.conditional_optional_map,
        }

    # ------------------------------------------------------------------
    # 启动流程（后台线程）
    # ------------------------------------------------------------------

    @classmethod
    def run_process(cls, instance_key: str, mode: str = "ALL",
                    target_category: str = "") -> Dict[str, Any]:
        """启动流程（非阻塞，立即返回）

        Returns:
            dict: {"ok": bool, "instance_key": str, "message": str, "already_running": bool}
        """
        state = cls._get_or_create_state(instance_key)

        # 防并发：同一 instance_key 正在跑则拒绝
        if not state.lock.acquire(blocking=False):
            return {
                "ok": False,
                "instance_key": instance_key,
                "message": f"车型 {instance_key} 的流程正在执行中，请等待完成后再启动",
                "already_running": True,
            }

        # 如果是上一次已完成的，重置状态
        if state.finished:
            state.queue = queue.Queue()
            state.done_event = threading.Event()
            state.finished = False
            state.final_result = None

        state.started = True

        # 重置 ProcessContext 执行状态（从头开始）
        try:
            ctx = get_process_context()
            ctx.reset_execution_state(instance_key)
        except Exception as e:
            state.lock.release()
            return {"ok": False, "message": f"重置执行状态失败: {e}", "instance_key": instance_key}

        # 注册 callback 闭包（每次 run 新建，避免全局 _emitted_step_ids 污染）
        emitted: set = set()  # 本次 run 内的去重集合

        def _progress_callback(step_info: Dict[str, Any]):
            """ProcessController 步骤级进度回调 — push 到 queue

            每次 callback 都推送最新版 states_tree，前端直接用它渲染进度。
            去重只防"同一 step + 同一 inner 的重复推送"，
            但 states_tree 变了就必须推（否则前端看不到状态变化）。
            """
            outer_step = step_info.get("outer_step", "")
            loop_item = step_info.get("current_loop_item", "")
            inner_name = step_info.get("inner_step_name", "")
            progress = step_info.get("progress", 0.0)

            # 过滤 INIT（不影响执行，只是不推 INIT 事件）
            if outer_step in ("INIT", ""):
                return

            # 构建事件 — 直接带 states_tree + loop 信息
            label = f"{loop_item} · {inner_name}" if loop_item and inner_name else (inner_name or outer_step)
            event = {
                "type": "step_progress",
                "step_id": outer_step,
                "step_name": label,
                "loop_item": loop_item,
                "progress": round(progress, 4),
                "timestamp": time.strftime("%H:%M:%S"),
                # ===== 新增：完整状态树（前端直接渲染） =====
                "states_tree": step_info.get("states_tree", []),
                "completed_loop_items": step_info.get("completed_loop_items", []),
                "remaining_loop_items": step_info.get("remaining_loop_items", []),
                "current_loop_item": step_info.get("current_loop_item", ""),
            }
            try:
                state.queue.put_nowait(event)
            except queue.Full:
                pass

            # 双写：同时往 AgentMessageLogger 写一份 flow_progress 事件
            # 这样 chat SSE 也能拿到进度（避免 function.run_flow 阻塞期间前端无事件）
            try:
                from snail_avatar.backend.core.agent_message_logger import AgentMessageLogger
                AgentMessageLogger.log(
                    "process_engine", "flow_progress",
                    label,
                    step_id=outer_step,
                    loop_item=loop_item,
                    progress=round(progress, 4),
                    instance_key=instance_key,
                )
            except Exception:
                pass

        # 注册 callback 到 ProcessController
        try:
            controller = ctx._get_controller(instance_key)
            controller.add_callback(_progress_callback)
        except Exception as e:
            state.lock.release()
            return {"ok": False, "message": f"注册回调失败: {e}", "instance_key": instance_key}

        # 后台线程：跑 run_flow → 推 done 事件 → release lock
        def _worker():
            result = None
            try:
                result = ctx.run_flow(instance_key=instance_key, mode=mode,
                                      target_category=target_category)
                state.final_result = result

                status = result.get("status", "unknown")
                # 如果 stop_process 被调用过，覆盖状态为 stopped
                if instance_key in cls._stop_requests and status in ("success", "unknown"):
                    status = "stopped"

                summary = cls._safe_json({
                    "instance_key": instance_key,
                    "status": status,
                    "message": result.get("message", ""),
                })

                if status == "success":
                    summary["summary"] = result.get("summary", "")

                state.queue.put_nowait({
                    "type": "done",
                    "status": status,
                    "summary": summary,
                    "timestamp": time.strftime("%H:%M:%S"),
                })

            except Exception as e:
                state.queue.put_nowait({
                    "type": "error",
                    "message": f"流程执行异常: {e}",
                    "timestamp": time.strftime("%H:%M:%S"),
                })
                state.final_result = {"status": "error", "message": str(e)}
            finally:
                # 移除 stop 请求标记
                cls._stop_requests.discard(instance_key)
                # 移除 callback（避免残留）
                try:
                    controller._callbacks.remove(_progress_callback)
                except (ValueError, AttributeError):
                    pass

                state.finished = True
                state.done_event.set()
                state.lock.release()

        state.thread = threading.Thread(target=_worker, daemon=True,
                                        name=f"process-{instance_key}")
        state.thread.start()

        return {
            "ok": True,
            "instance_key": instance_key,
            "message": f"流程已启动，后台执行中（instance_key={instance_key}）",
        }

    # ------------------------------------------------------------------
    # SSE 事件流生成器
    # ------------------------------------------------------------------

    @classmethod
    def stream_events(cls, instance_key: str):
        """SSE generator — 消费 queue 并 yield data: {...} 行

        协议：
          1. 立即发送 connected 事件
          2. 循环从 queue.get(timeout=HEARTBEAT_INTERVAL) 读事件
          3. 超时（无新事件）→ 发 heartbeat
          4. 收到 done/error → yield 后 return
          5. run 结束后仍保持 ~30s 可重连窗口（如果 finished 但 queue 还有数据）
        """
        HEARTBEAT_INTERVAL = 15  # 秒
        IDLE_TIMEOUT = 600       # 秒（空闲超时：600 秒无任何真实事件才断流）

        state = cls._get_or_create_state(instance_key)

        # connected
        yield f"data: {json.dumps({'type': 'connected', 'instance_key': instance_key})}\n\n"

        # 空闲超时计时器：每次收到真实事件时重置，避免绝对上限误杀长流程
        last_event_time = time.time()
        while True:
            # 检查是否超时（run 还没启动）
            if not state.started and time.time() - last_event_time > 10:
                yield f"data: {json.dumps({'type': 'error', 'message': '流程未启动或已结束'})}\n\n"
                return

            # 读 queue，带心跳
            try:
                event = state.queue.get(timeout=HEARTBEAT_INTERVAL)
            except queue.Empty:
                # 心跳
                yield f"data: {json.dumps({'type': 'heartbeat', 'ts': time.strftime('%H:%M:%S')})}\n\n"

                # 如果已 finished + queue 空 → 退出
                if state.finished and state.queue.empty():
                    yield f"data: {json.dumps({'type': 'done', 'status': state.final_result.get('status') if state.final_result else 'unknown', 'summary': cls._safe_json(state.final_result)}, ensure_ascii=False)}\n\n"
                    return

                # 空闲超时保护（600s 无真实事件才断，避免代理/防火墙断连）
                if time.time() - last_event_time > IDLE_TIMEOUT:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'SSE 空闲超时'})}\n\n"
                    return
                continue

            # 收到真实事件 → 重置空闲超时计时器
            last_event_time = time.time()

            # yield 事件
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # done / error 类型 → 结束 SSE
            if event.get("type") in ("done", "error"):
                return

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    @classmethod
    def get_status(cls, instance_key: str) -> Dict[str, Any]:
        """获取流程当前状态"""
        ctx = get_process_context()
        state = cls._get_or_create_state(instance_key)

        # 从 ProcessController 读状态
        try:
            controller = ctx._get_controller(instance_key)
            ctrl_state = controller.get_state()
            progress = controller.get_progress()
            is_complete = controller.is_complete()
        except Exception:
            ctrl_state = {}
            progress = 0.0
            is_complete = False

        return {
            "instance_key": instance_key,
            "is_running": state.started and not state.finished,
            "is_finished": state.finished,
            "progress": round(progress, 4),
            "is_complete": is_complete,
            "controller_state": ctrl_state,
            "final_result": state.final_result,
        }

    # ------------------------------------------------------------------
    # 步骤结果
    # ------------------------------------------------------------------

    @classmethod
    def get_results(cls, instance_key: str) -> Dict[str, Any]:
        """获取所有步骤执行结果"""
        ctx = get_process_context()
        state = cls._get_or_create_state(instance_key)

        try:
            controller = ctx._get_controller(instance_key)
            step_results = getattr(controller, "_step_results", [])
        except Exception:
            step_results = []

        # 提取最终总结（FINAL_SUMMARY）
        summary_text = ""
        for record in reversed(step_results):
            if record.get("step_id") in ("FINAL_SUMMARY",):
                sr = record.get("step_result", {})
                if isinstance(sr, dict):
                    summary_text = sr.get("content", "") or sr.get("result", {}).get("content", "")
                break

        return {
            "instance_key": instance_key,
            "total_steps": len(step_results),
            "final_status": state.final_result.get("status") if state.final_result else None,
            "summary_text": summary_text,
            "step_results": step_results,
        }

    # ------------------------------------------------------------------
    # 停止流程
    # ------------------------------------------------------------------

    @classmethod
    def stop_process(cls, instance_key: str) -> Dict[str, Any]:
        """停止正在执行的流程

        实现：
          1. 把 instance_key 加到 _stop_requests（worker 退出后会把 status 改为 stopped）
          2. 调 ProcessEngine.stop() 设置引擎级停止标志（让 run_flow 尽快退出）
          注意：engine.stop() 是全局的，会同时停止所有并发车型的 run_flow，
          但 _stop_requests 保证只有被请求停止的那个 instance_key 最终状态为 stopped。
        """
        state = cls._get_or_create_state(instance_key)

        if not state.started or state.finished:
            return {"ok": False, "message": f"车型 {instance_key} 当前没有正在执行的流程"}

        # 记录 per-instance 停止请求
        cls._stop_requests.add(instance_key)

        try:
            ctx = get_process_context()
            ctx.workflow_engine.stop()
        except Exception as e:
            cls._stop_requests.discard(instance_key)
            return {"ok": False, "message": f"停止失败: {e}"}

        # 推送停止事件给 SSE 消费者
        try:
            state.queue.put_nowait({
                "type": "error",
                "message": "流程已被用户停止",
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception:
            pass

        return {"ok": True, "message": f"已发送停止指令给 {instance_key}"}

    # ------------------------------------------------------------------
    # 暂停 / 继续
    # ------------------------------------------------------------------

    @classmethod
    def pause_process(cls, instance_key: str) -> Dict[str, Any]:
        """暂停正在执行的流程（在单步之间的检查点生效）

        底层调 ProcessEngine.pause() → _pause_event.clear()
        主循环在下一步开始前会 _pause_event.wait() 阻塞住。
        当前正在执行的 LLM 步骤**不会被中途打断**（等它自己返回）。
        """
        state = cls._get_or_create_state(instance_key)

        if not state.started or state.finished:
            return {"ok": False, "message": f"车型 {instance_key} 当前没有正在执行的流程"}

        try:
            ctx = get_process_context()
            ctx.workflow_engine.pause()
        except Exception as e:
            return {"ok": False, "message": f"暂停失败: {e}"}

        # 推送暂停事件给 SSE 消费者（前端据此更新按钮状态 + isPaused 标志）
        try:
            state.queue.put_nowait({
                "type": "status_change",
                "new_status": "paused",
                "message": "流程已暂停",
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception:
            pass

        return {"ok": True, "message": f"已暂停 {instance_key}（当前步骤完成后生效）"}

    @classmethod
    def resume_process(cls, instance_key: str) -> Dict[str, Any]:
        """继续已暂停的流程

        底层调 ProcessEngine.resume() → _pause_event.set()
        主循环的 wait() 会立即返回，继续从暂停点往下执行。
        """
        state = cls._get_or_create_state(instance_key)

        if not state.started or state.finished:
            return {"ok": False, "message": f"车型 {instance_key} 当前没有正在执行的流程"}

        try:
            ctx = get_process_context()
            ctx.workflow_engine.resume()
        except Exception as e:
            return {"ok": False, "message": f"继续失败: {e}"}

        # 推送继续事件
        try:
            state.queue.put_nowait({
                "type": "status_change",
                "new_status": "running",
                "message": "流程已继续",
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception:
            pass

        return {"ok": True, "message": f"已继续 {instance_key}"}

    # ------------------------------------------------------------------
    # 单步执行（两种场景）
    #   A. 流程已 paused → resume_step() 让主循环走一步 + 自动再 pause
    #   B. 流程未启动/已结束 → 新线程跑 ctx.run_single_step()
    # ------------------------------------------------------------------

    @classmethod
    def step_process(cls, instance_key: str) -> Dict[str, Any]:
        """单步执行

        场景 A（推荐）: 流程已暂停 → 主循环走一步后自动再暂停（Step-then-pause）
        场景 B: 流程未启动/已结束 → 新开线程执行一个 run_single_step

        流程正在 running（未暂停）时不允许点单步。
        """
        state = cls._get_or_create_state(instance_key)

        try:
            ctx = get_process_context()
        except Exception as e:
            return {"ok": False, "message": f"获取 ProcessContext 失败: {e}"}

        # ============ 场景 A：流程已启动且未结束 ============
        if state.started and not state.finished:
            # 还在 running 态（pause_event 是 set）→ 不允许 step
            if ctx.workflow_engine._pause_event.is_set():
                return {"ok": False, "message": "流程正在执行中，请先暂停再点「单步执行」"}

            # 已 paused → Step-then-pause
            # 注册回调：主循环走完这一步并自动 pause 后，推送 paused 事件给 SSE
            def _on_step_auto_paused():
                cls._push_status(state, "paused", "单步执行完成（已自动暂停）")
            ctx.workflow_engine._step_then_pause_callbacks.append(_on_step_auto_paused)

            ctx.workflow_engine.resume_step()

            # 推送 running 状态事件
            cls._push_status(state, "running", "单步执行中...")
            return {"ok": True, "message": "单步执行指令已发送"}

        # ============ 场景 B：流程未启动/已结束 → 新线程 ============
        if not state.lock.acquire(blocking=False):
            return {"ok": False, "message": "单步执行冲突，请稍后再试"}

        try:
            # 注册 callback（同 run_process，但只跑一步）
            emitted: set = set()

            def _progress_callback(step_info: Dict[str, Any]):
                outer_step = step_info.get("outer_step", "")
                loop_item = step_info.get("current_loop_item", "")
                inner_name = step_info.get("inner_step_name", "")
                progress = step_info.get("progress", 0.0)

                if outer_step in ("INIT", ""):
                    return

                label = f"{loop_item} · {inner_name}" if loop_item and inner_name else (inner_name or outer_step)
                try:
                    state.queue.put_nowait({
                        "type": "step_progress",
                        "step_id": outer_step,
                        "step_name": label,
                        "loop_item": loop_item,
                        "progress": round(progress, 4),
                        "timestamp": time.strftime("%H:%M:%S"),
                        # ===== 新增：完整状态树 =====
                        "states_tree": step_info.get("states_tree", []),
                        "completed_loop_items": step_info.get("completed_loop_items", []),
                        "remaining_loop_items": step_info.get("remaining_loop_items", []),
                        "current_loop_item": step_info.get("current_loop_item", ""),
                    })
                except Exception:
                    pass

            controller = ctx._get_controller(instance_key)
            controller.add_callback(_progress_callback)

            state.started = True

            def _step_worker():
                try:
                    # run_single_step 只执行一步就返回（自动跳过 INIT / condition）
                    result = ctx.run_single_step(instance_key=instance_key, mode="ALL")

                    # 推送 paused（step 后停在暂停态，方便用户 review）
                    status = result.get("status", "unknown")
                    cls._push_status(state, "paused", f"单步执行完成（{status}）")
                except Exception as e:
                    cls._push_event(state, {
                        "type": "error",
                        "message": f"单步执行失败: {e}",
                        "timestamp": time.strftime("%H:%M:%S"),
                    })
                finally:
                    # Bug2 fix: 场景 B 没有主循环，step 完成后标记 finished=True
                    # 否则下次点 step 会被场景 A 的 _pause_event.is_set() 检查误伤
                    state.finished = True
                    state.lock.release()

            threading.Thread(target=_step_worker, daemon=True).start()
            return {"ok": True, "message": "单步执行已启动"}

        except Exception as e:
            state.lock.release()
            return {"ok": False, "message": f"启动单步执行失败: {e}"}

    # ------------------------------------------------------------------
    # 重复本步
    #   流程未启动但有快照 → 新线程跑 ctx.repeat_last_step()
    #   流程正在跑（无论 paused 还是 running）→ 不允许（状态不稳定）
    #   没有快照 → 返回错误
    # ------------------------------------------------------------------

    @classmethod
    def repeat_process(cls, instance_key: str) -> Dict[str, Any]:
        """重复执行上一步（从快照恢复后重新跑一个单步）

        前置条件：ProcessController 有 snapshot（至少执行过一步）。
        流程正在运行时不允许重复（快照会被覆盖）。
        """
        state = cls._get_or_create_state(instance_key)

        try:
            ctx = get_process_context()
        except Exception as e:
            return {"ok": False, "message": f"获取 ProcessContext 失败: {e}"}

        # 流程正在跑 → 不允许
        if state.started and not state.finished:
            return {"ok": False, "message": "流程正在执行中，请等待完成或停止后再点「重复本步」"}

        # 检查有没有快照
        if not ctx.has_snapshot(instance_key):
            return {"ok": False, "message": "无可重复的步骤（还没执行过任何单步），请先执行至少一步"}

        if not state.lock.acquire(blocking=False):
            return {"ok": False, "message": "重复执行冲突，请稍后再试"}

        try:
            # 注册 callback
            emitted: set = set()

            def _progress_callback(step_info: Dict[str, Any]):
                outer_step = step_info.get("outer_step", "")
                loop_item = step_info.get("current_loop_item", "")
                inner_name = step_info.get("inner_step_name", "")

                label = f"{loop_item} · {inner_name}" if loop_item and inner_name else (inner_name or outer_step)
                try:
                    state.queue.put_nowait({
                        "type": "step_progress",
                        "step_id": outer_step,
                        "step_name": f"[重复] {label}",
                        "loop_item": loop_item,
                        "progress": round(step_info.get("progress", 0.0), 4),
                        "timestamp": time.strftime("%H:%M:%S"),
                        # ===== 新增：完整状态树 =====
                        "states_tree": step_info.get("states_tree", []),
                        "completed_loop_items": step_info.get("completed_loop_items", []),
                        "remaining_loop_items": step_info.get("remaining_loop_items", []),
                        "current_loop_item": step_info.get("current_loop_item", ""),
                    })
                except Exception:
                    pass

            controller = ctx._get_controller(instance_key)
            controller.add_callback(_progress_callback)

            state.started = True

            def _repeat_worker():
                try:
                    result = ctx.repeat_last_step(instance_key=instance_key, mode="ALL")
                    status = result.get("status", "unknown")
                    cls._push_status(state, "paused", f"重复执行完成（{status}）")
                except Exception as e:
                    cls._push_event(state, {
                        "type": "error",
                        "message": f"重复执行失败: {e}",
                        "timestamp": time.strftime("%H:%M:%S"),
                    })
                finally:
                    # Bug2 fix: 同 _step_worker
                    state.finished = True
                    state.lock.release()

            threading.Thread(target=_repeat_worker, daemon=True).start()
            return {"ok": True, "message": "重复本步已启动"}

        except Exception as e:
            state.lock.release()
            return {"ok": False, "message": f"启动重复执行失败: {e}"}

    # ------------------------------------------------------------------
    # 内部工具：统一推送 SSE 事件
    # ------------------------------------------------------------------

    @staticmethod
    def _push_status(state, new_status: str, message: str):
        try:
            state.queue.put_nowait({
                "type": "status_change",
                "new_status": new_status,
                "message": message,
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception:
            pass

    @staticmethod
    def _push_event(state, event: Dict[str, Any]):
        try:
            state.queue.put_nowait(event)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sheet 数据查询（产品定义 / VTS / SSTS）
    # ------------------------------------------------------------------

    @classmethod
    def get_sheet(cls, instance_key: str, sheet_key: str) -> Dict[str, Any]:
        """从 memory_db 读取指定 sheet 的原始数据（产品定义 / VTS / SSTS）

        Args:
            instance_key: 车型 mc_key（如 reevlto_reev）
            sheet_key: sheet 关键字，如 "base_产品定义"、"target_vts"、"target_ssts"
        """
        from snail_avatar.backend.agents.core.public_functions_core.common.db_data_helper import get_sheet_data
        from snail_avatar.backend.agents.core.public_functions_core.vts.data_formatter import (
            PRODUCT_DEF_SHEET_KEY, VTS_SHEET_KEY, SSTS_SHEET_KEY,
        )

        ctx = get_process_context()
        db = getattr(ctx, "_memory_db", None)
        if db is None:
            from snail_avatar.backend.agents.core.public_functions_core.common.memory_db import get_memory_db
            db = get_memory_db()

        if db is None:
            return {"instance_key": instance_key, "sheet_key": sheet_key, "data": None, "note": "数据库未加载"}

        raw = get_sheet_data(db, instance_key, sheet_key)

        # 产品定义需要展平（dict of dict of list → list of flat items）
        if sheet_key == PRODUCT_DEF_SHEET_KEY:
            flat_items = []
            if isinstance(raw, dict):
                for cat1_data in raw.values():
                    if isinstance(cat1_data, dict):
                        for cat2_data in cat1_data.values():
                            if isinstance(cat2_data, list):
                                flat_items.extend(cat2_data)
                    elif isinstance(cat1_data, list):
                        flat_items.extend(cat1_data)
            elif isinstance(raw, list):
                flat_items = raw
            # 必须过 _safe_json 处理 NaN/Inf（Excel 空单元格 → NaN）
            return {
                "instance_key": instance_key,
                "sheet_key": sheet_key,
                "data": cls._safe_json(flat_items),
                "total": len(flat_items),
            }

        # VTS/SSTS 保持原始结构（前端自行展平）
        return {
            "instance_key": instance_key,
            "sheet_key": sheet_key,
            "data": cls._safe_json(raw),
        }

    # ------------------------------------------------------------------
    # 流程沙箱数据查询
    # ------------------------------------------------------------------

    @classmethod
    def get_sandbox(cls, instance_key: str) -> Dict[str, Any]:
        """读取流程执行后的沙箱私有数据（ProcessController.sandbox）"""
        ctx = get_process_context()
        try:
            sandbox = ctx.get_sandbox_data(instance_key)
        except Exception:
            sandbox = None

        return {
            "instance_key": instance_key,
            "data": cls._safe_json(sandbox),
            "is_empty": not bool(sandbox),
        }
