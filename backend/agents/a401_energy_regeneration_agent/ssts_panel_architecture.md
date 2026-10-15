# SSTS 计算面板架构设计

> 版本：v1.0  |  日期：2026-09-26  |  适用：a401_energy_regeneration_agent

---

## 一、设计目标

在**不修改任何 VTS agent 核心逻辑**的前提下，通过 3 层 hook（可选参数 + 默认值 + 覆写扩展），让 SSTS agent 的 UI 面板自动把 `SSTSSandbox` 注入到工作流节点。

---

## 二、全链路数据流

```
GenericSSTSWorkflowAgent.create_panel()
    │
    ▼
SSTSCalculationPanel(sandbox=agent.sandbox)
    │  覆写 _create_workflow_tab hook
    ▼
BaseWorkflowTab(sandbox=sandbox, auto_commit=False)
    │  __init__ 有可选参数 sandbox=None
    ▼
_build_workflow() → workflow_builder.build_workflow_from_yaml_file(sandbox=sandbox)
    │  函数签名有可选参数 sandbox=None
    ▼
检测 sandbox != None → SSTSWorkflowExecutor(graph, ..., sandbox=sandbox)
    │  自动遍历所有节点，给 SSTSCalculationNode 注入 sandbox
    ▼
node.sandbox  ← SSTSCalculationNode.sandbox 属性就绪
```

**VTS 零回归保障**：
- GenericCalculationPanel 不覆写 hook → 默认 hook 不传 sandbox → sandbox=None
- BaseWorkflowTab.sandbox 默认为 None → 不传入 builder
- builder 检测 sandbox=None → 用原 WorkflowExecutor
- WorkflowExecutor 不注入 sandbox → 原行为完全不变

---

## 三、3 层 hook 位置

### Hook 1：workflow_builder.py — 函数级可选参数

```python
def build_workflow_from_yaml_file(..., sandbox=None, auto_commit=False):
    ...
    if sandbox is not None:
        executor = SSTSWorkflowExecutor(graph, ..., sandbox=sandbox, auto_commit=auto_commit)
    else:
        executor = WorkflowExecutor(graph, ...)    # 原路径不变
```

### Hook 2：BaseWorkflowTab — __init__ 可选参数 + _build_workflow 传递

```python
def __init__(self, ..., sandbox=None, auto_commit=False):
    self.sandbox = sandbox
    self.auto_commit = auto_commit
    ...

def _build_workflow(self):
    return build_workflow_from_yaml_file(
        ...,
        sandbox=self.sandbox,       # 默认 None 时行为不变
        auto_commit=self.auto_commit,
    )
```

### Hook 3：BaseCalculationPanel — _create_workflow_tab 覆写点

```python
# 默认实现（VTS 走这里）
def _create_workflow_tab(self, memory_db, vehicle_suffix, workflow_yaml_path):
    return BaseWorkflowTab(
        memory_db=memory_db,
        vehicle_suffix=vehicle_suffix,
        workflow_yaml_path=workflow_yaml_path,
        # sandbox 不传 → 默认 None
    )
```

子类覆写（SSTS 走这里）：
```python
class SSTSCalculationPanel(BaseCalculationPanel):
    def _create_workflow_tab(self, memory_db, vehicle_suffix, workflow_yaml_path):
        return BaseWorkflowTab(
            memory_db=memory_db,
            vehicle_suffix=vehicle_suffix,
            workflow_yaml_path=workflow_yaml_path,
            sandbox=self._sandbox,        # 显式传递
            auto_commit=self._auto_commit,
        )
```

---

## 四、新增文件与修改文件

### 修改文件（均为扩展点追加，不改现有执行路径）

| 文件 | 改动 | 行数 |
|------|------|------|
| `workflow_builder.py` | 函数签名加 `sandbox=None, auto_commit=False` + executor 创建处加 if/else 分支 | +7 |
| `workflow_tab_base.py` | `__init__` 加 `sandbox=None, auto_commit=False` + `_build_workflow` 传这两个参数 | +6 |
| `base_calculation_panel.py` | 硬编码 `BaseWorkflowTab(...)` 换 `self._create_workflow_tab(...)` + 新增 hook 默认实现 | +25 |
| `generic_ssts_workflow_agent.py` | `create_panel` 返回 `SSTSCalculationPanel(sandbox=self.sandbox)` | 重写 create_panel |

### 新增文件

| 文件 | 说明 |
|------|------|
| `ui_panel/workflow/ssts_calculation_panel.py` | SSTS 面板子类，覆写 `_create_workflow_tab` 传 sandbox |

---

## 五、预留扩展点（Phase 2 可追加）

| 扩展点 | 位置 | 用途 |
|--------|------|------|
| `self._ssts_extra_container` | BaseWorkflowTab._build_ui 里追加空 Column | 沙箱检视器、图表区、commit 按钮 |
| `_on_run_all_complete(result)` | hook（当前无） | 运行完成后触发 sandbox.commit() + 刷新可视化 |
| `_render_visualization(viz_dict)` | hook（当前无） | 渲染 SSTSCalculationNode.generate_visualization() 返回的图表 JSON |
| `BaseWorkflowTab.sandbox` | 已存在属性 | 节点通过 `self.sandbox.get("x", vehicle_suffix=self.vehicle_suffix)` 读取零部件参数 |

---

## 六、类继承链（当前状态）

```
RightPanelTabBase (抽象基类)
    └── BaseCalculationPanel (+ _create_workflow_tab hook)
            ├── GenericCalculationPanel (VTS, 不覆写 hook)
            └── SSTSCalculationPanel (SSTS, 覆写 hook 传 sandbox)

BaseWorkflowTab (+ sandbox=None 可选参数)
    ↑ 被 _create_workflow_tab 返回

CalculationNode (现有)
    └── SSTSCalculationNode (+ sandbox 属性, 由 SSTSWorkflowExecutor 自动注入)
```
