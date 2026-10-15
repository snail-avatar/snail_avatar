# SSTS 计算 Agent 框架设计方案

> 版本：v1.0  |  日期：2026-09-25  |  适用首个案例：a401_energy_regeneration

---

## 一、背景与定位

### 1.1 两类计算 Agent 的区别

| 维度 | VTS 计算 Agent（a302/a303） | SSTS 计算 Agent（a401 起） |
|------|--------------------------|--------------------------|
| 输入来源 | 全局 SSTS 参数（来自 MemoryDatabase） | 零部件具体参数（文件夹加载 + 可选 SSTS 参数） |
| 输出去向 | 全局 VTS 参数（写回 MemoryDatabase） | 局部派生参数（沙箱内，可选回写全局） |
| 数据源 | 全局 Excel 导入的唯一真相源 | Agent 私有文件夹 + 全局只读桥接 |
| 数据隔离 | 无（全局共享） | 沙箱隔离，防止污染 |
| 典型案例 | a302_economy_agent（经济性）、a303_power_agent（动力性） | a401_energy_regeneration（能量回收） |

### 1.2 a401_energy_regeneration 定位

根据零部件具体参数（如电机回收效率 MAP 图、制动系统规格、电池 SOC 策略）进行 SSTS 参数计算和特殊部件指标分析的专业子 Agent。

---

## 二、现有架构中 ssts_compute_agent.py 的状态

**文件位置**：`agents/core/agent_base/ssts_compute_agent.py`

**事实核对**：
- 文件存在，是最初架构设计时的残留桩类
- 注释写着 `继承关系：SSTSComputeAgent → LLMConversationAgent`，但代码实际是 `class SSTSComputeAgent:`（只继承 object）
- 注册表 `_ssts_agent_registry` 空无一物
- 没有任何 sub agent 继承或使用它
- `__init__.py` 已有 import 声明，改造后自动生效

**决策**：改造而非删除。将其重写为真正能用的 `SSTSWorkflowAgentBase`，保留文件名和 `__init__.py` 导出，最小化破坏性变更。

---

## 三、完整继承链设计

```
LLMConversationAgent                              ← 共享：LLM 对话 + Function Calling
    │
    ├── VTSComputeAgent(现有)                      ← VTS 注册 + 契约接口
    │     └── WorkflowAgentBase(现有)               ← 工作流懒加载 + run_full_calculation
    │           └── GenericWorkflowAgent(现有)      ← 配置驱动的 VTS 实现（a302/a303）
    │
    └── SSTSWorkflowAgentBase(重写 ssts_compute_agent.py)  ← SSTS 注册 + 沙箱 + commit 接口
          └── GenericSSTSWorkflowAgent(新增)               ← 配置驱动的 SSTS 实现（a401）
```

**关键设计理由**：
SSTS agent 本质上也是工作流计算类 agent——需要 DAG 拓扑、节点自动发现、WorkflowExecutor、run_full_calculation 等全部能力。差异点只是额外的沙箱、文件夹参数读取、可视化。因此 SSTSWorkflowAgentBase 继承 WorkflowAgentBase，叠加 SSTS 能力，而非另起炉灶。

这样 VTS 和 SSTS 两条链共享 WorkflowAgentBase 的全部能力，避免代码重复。

---

## 四、项目数据目录结构与自动关联逻辑

### 4.1 data 目录的物理布局

```
d:\AI_model\snail_avatar\data\
│
├── 蜗牛项目-VTS_SSTS_V6.0_ini.xlsx           # Excel VTS/SSTS 参数文件（根目录）
├── 蜗牛项目-VTS_SSTS_V6.0_ini_更新.xlsx
├── 越野项目-VTS_SSTS_V0.0_ini.xlsx
│
└── 蜗牛项目/                                   # 同名项目文件夹（与 Excel stem 对应）
    ├── 增程车型/
    │   └── Motor/
    │       ├── Emotor_F/motor_parameter.xlsx
    │       └── Emotor_R/motor_parameter.xlsx
    └── 纯电车型/
        └── Motor/
            ├── Emotor_F/motor_parameter.xlsx
            └── Emotor_R/motor_parameter.xlsx
```

### 4.2 文件打开与 db memory 创建链路

```
用户点击工具栏"打开"按钮
  或
LLM 调用 open_project_file(query="蜗牛项目 V6.0")
        │
        ▼
PubfnOpenProjectFile._execute_atomic()
        │
        ▼
_scan_data_dir() → data 目录根下扫描所有 .xlsx 文件
        │
        ▼
_load_file() 构造 MemoryDatabase(file_path=".../蜗牛项目-VTS_SSTS_V6.0_ini.xlsx")
        │
        ▼
memory_db.load_from_excel()  →  创建全局 db memory（memorycore + inter_data + vehsuffix）
        │
        ▼
app_state.memory_db = memory_db   ←  写入全局状态，VTS/SSTS agent 从此共享
```

**VTS agent 到此即止**——只需要 app_state.memory_db 即可工作。

### 4.3 SSTS agent 的额外步骤：项目文件夹自动关联

SSTS agent 在 db memory 创建之后，需要自动执行项目文件夹识别与零部件参数加载：

```
MemoryDatabase 创建完成（memory_db.file_path 已知）
        │
        ▼
SSTSWorkflowAgentBase._auto_detect_project_folder(memory_db)
        │
        ├─ ① 解析 memory_db.file_path 的 stem
        │     "蜗牛项目-VTS_SSTS_V6.0_ini.xlsx" → "蜗牛项目"
        │     规则：取 stem 中第一个项目名 token，或 data/ 目录下同名文件夹
        │
        ├─ ② 构建项目根路径
        │     data_dir = os.path.dirname(memory_db.file_path)
        │     project_folder = os.path.join(data_dir, "蜗牛项目")
        │     兜底：若不存在则尝试 KNOWN_PROJECT_NAMES 匹配 data_dir 下的子目录
        │
        ├─ ③ 遍历项目文件夹，按 Agent 配置过滤加载
        │     SSTSWorkflowAgentBase.sandbox_config["load_paths"] = ["Motor/**", "Brake/**"]
        │     只加载本 agent 需要的零部件参数文件
        │
        └─ ④ 加载到 SSTSSandbox
              sandbox.load_from_folder(project_folder, filter_patterns=[...])
              → sandbox.project_folder = project_folder（记录关联）
              → sandbox.file_path = memory_db.file_path（反向记录源文件）
```

### 4.4 项目文件夹识别规则

| 规则 | 说明 | 示例 |
|------|------|------|
| **规则 1（主路径）** | `os.path.join(data_dir, 项目名)`，项目名从 Excel stem 提取 | `data_dir/"蜗牛项目"` |
| **规则 2（兜底）** | 遍历 data_dir 子目录名，匹配 `CandidateFile.project_name` | `data_dir/"蜗牛项目"` 即使 stem 略有不同 |
| **规则 3（多级兜底）** | 遍历 data_dir 子目录名，模糊匹配 stem 中的中文 token | stem 含 "越野" → `data_dir/"越野项目"` |
| **未找到** | 置 sandbox.project_folder = None，SSTSSandbox 为空，agent 可运行但无零部件参数 | — |

### 4.5 车型子文件夹的自动匹配

项目文件夹下通常按车型再分一级子目录（增程车型、纯电车型）。SSTS agent 需要根据 `memory_db.vehsuffix` 中的能源形式字段自动选择：

```python
# SSTSWorkflowAgentBase._match_vehicle_subfolder(memory_db, project_folder)
# 从 memory_db.vehsuffix 提取当前车型的能源形式（EV / REEV / PHEV ...）
# 匹配 project_folder 下对应的子文件夹名
# 匹配不到时 fallback 到全部车型
```

**示例**：memory_db.vehsuffix 中有车型后缀 `reevlto`（增程）→ 匹配 `增程车型/` → sandbox 只加载此子目录下的参数文件。

### 4.6 生命周期与联动

```
场景 A：用户打开项目文件
  → pubfn_open_project_file 创建 memory_db
  → app_state.memory_db = memory_db
  → SSTS agent 下次被调用时，_extra_init 检测到 memory_db.file_path 变更
    → 自动重新识别项目文件夹 + 重载 sandbox

场景 B：SSTS agent 被首次调用时 memory_db 尚未创建
  → sandbox 为空，agent 返回提示："请先打开项目文件"
  → 通过 is_ready 或 auto_detect_project_folder 方法懒加载

场景 C：用户切换到另一个项目文件
  → app_state.memory_db 被替换
  → SSTS agent 检测到 file_path 变化 → 自动重建 sandbox + 重载
```

### 4.7 自动关联的触发点

| 触发点 | 位置 | 说明 |
|--------|------|------|
| **懒加载模式**（推荐） | SSTSWorkflowAgentBase._extra_init() | 每次 agent 初始化时检查 app_state.memory_db 是否变更，变更则重建 sandbox |
| **主动触发模式** | PubfnOpenProjectFile._load_file() 末尾 | 在 memory_db 创建后，主动通知所有已注册的 SSTS agent 执行 reload_sandbox |
| **手动触发** | LLM 调用 reload_sandbox 工具 | 用户明确要求切换文件夹或重新加载时 |

### 4.8 db_key 后缀处理策略（方案 A：沙箱只用后缀，db 对接时自动拼接）

#### 4.8.1 MemoryDatabase 对外 db_key 格式约定

MemoryDatabase 中所有 SSTS/VTS 参数的 db_key 统一格式为：

```
{base_key}_{type}_{vehicle_suffix}
```

其中 type 固定三种：
- `result` — 当前值 / 计算结果（如 `mass_curb_result_reevlto`）
- `target` — 目标值（如 `mass_curb_target_reevlto`）
- `pass` — 达标标识（如 `mass_curb_pass_reevlto`）

基础产品定义参数不带 type 段：
- `{base_key}_{vehicle_suffix}` — 如 `body_reevlto`、`powertrain_type_reevlto`

MemoryDatabase.memorycore 内部的顶层键是复合键（如 `"增程车型_reevlto"`），但这是内部组织细节。对外暴露的 `get_ssts_vts_param(db_key)` / `set_ssts_vts_param(db_key, value)` 完全基于完整 db_key 匹配，不需要关心顶层键名。

#### 4.8.2 CalculationNode 现有后缀处理（VTS agent 链路）

后缀拼接**完全在运行时动态完成**——node YAML 里的 ssts_vts_schema 只写 base key：

```yaml
# node YAML 定义（不带后缀）
ssts_vts_schema:
  mot_reg_eff:
    db_key: mot_reg_eff          # base key
    direction: input
```

CalculationNode 运行时由 WorkflowExecutor 注入 `self.vehicle_suffix = "reevlto"`，然后：

```python
# 读取
db_key = f"{var_name}_result_{self.vehicle_suffix}"
value = memory_db.get_ssts_vts_param(db_key)

# 写入
db_key = f"{var_name}_result_{self.vehicle_suffix}"
memory_db.set_ssts_vts_param(db_key, value)
```

**现有结论：只要 SSTSWorkflowExecutor 同样注入 vehicle_suffix，SSTSCalculationNode 继承来的所有后缀拼接逻辑零修改即可复用。**

#### 4.8.3 SSTSSandbox 的后缀处理（新增组件）

SSTSSandbox 是全局实例（不绑定单一车型），它必须自己管理后缀转换。核心原则：

1. **沙箱内存中只存 base key + 后缀作为顶层 key**：
   ```
   _params = {
       "reevlto": { "mot_reg_eff": 0.85, "m_b_energy": 0.3 },
       "evlto":   { "mot_reg_eff": 0.90 }
   }
   ```
   
2. **SSTSCalculationNode 访问沙箱时直接传 self.vehicle_suffix**：
   ```python
   # SSTSCalculationNode.numerical_solve() 内
   mot_map = self.sandbox.get("mot_regen_map", vehicle_suffix=self.vehicle_suffix)
   # 零转换：self.vehicle_suffix = "reevlto" 直接作为沙箱顶层 key
   ```

3. **只有在沙箱与 MemoryDatabase 对接时才拼接后缀**：
   ```python
   # sandbox.get_global() → 读全局 DB
   db_key = f"{name}_result_{vehicle_suffix}"
   value = self._global_db.get_ssts_vts_param(db_key)
   
   # sandbox.commit() → 写回全局 DB
   for veh_suffix in self.vehicle_suffixes:
       db_key = f"{param_name}_result_{veh_suffix}"
       self._global_db.set_ssts_vts_param(db_key, value)
   ```

#### 4.8.4 与 MemoryDatabase.memorycore 复合键的关系

MemoryDatabase.memorycore 内部的顶层键是 `"增程车型_reevlto"`（车型名_后缀复合键），但这是 MemoryDatabase 的内部组织方式。SSTSSandbox 不应该复用这个格式，理由：

| 考量 | 说明 |
|------|------|
| 与 CalculationNode.vehicle_suffix 对齐 | node 访问沙箱时直接传 self.vehicle_suffix="reevlto"，零查表、零拆分 |
| 后缀是稳定标识符 | 车型名可能在 vehsuffix 表里修改（如 "增程车型"→"增程式"），后缀不变 |
| db_key 拼接零损耗 | commit / get_global 时直接用后缀拼 db_key，不需要拆分复合键 |
| MemoryDatabase 的复合键是内部细节 | 对外接口只认完整 db_key，不依赖 memorycore 顶层键名 |

#### 4.8.5 后缀处理分层责任图

```
┌─────────────────────────────────────────────────────────────┐
│  SSTSSandbox（沙箱内部）                                    │
│  _params = { "reevlto": {"mot_reg_eff": 0.85}, ... }       │
│  存储：base key（不带后缀） + 车型后缀做顶层 key             │
└──────────────┬──────────────────────┬──────────────────────┘
               │                      │
    sandbox.get_global("mass_curb",    sandbox.commit()
              "reevlto")               → 遍历所有 suffix
               │                      │
               ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│  后缀拼接层（沙箱 → DB 边界）                               │
│  db_key = f"{base_key}_result_{vehicle_suffix}"             │
│  db_key = f"{base_key}_target_{vehicle_suffix}"             │
└──────────────┬──────────────────────┬──────────────────────┘
               │                      │
               ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│  MemoryDatabase（全局 DB）                                  │
│  memorycore["增程车型_reevlto"]["..."][item]["db_key"]       │
│  = "mass_curb_result_reevlto"                               │
└─────────────────────────────────────────────────────────────┘

SSTSCalculationNode 继承来的后缀处理（与 VTS agent 完全一致，零修改）：
  node.vehicle_suffix = "reevlto"  ← 由 SSTSWorkflowExecutor 注入
    ├─→ node.ssts_values["mot_reg_eff"]  ← 父类 _load_and_check_ssts_vts()
    │    内部自动拼 db_key = "mot_reg_eff_result_reevlto"
    │
    └─→ self.sandbox.get("x", vehicle_suffix=self.vehicle_suffix)
         ← 沙箱接口，传后缀直接定位
```

---

## 五、框架各层详细设计

### 5.1 SSTSSandbox（局部沙箱）

**文件**：`agents/core/workflow_base/ssts_sandbox.py`（新增）

```python
class SSTSSandbox:
    """SSTS Agent 的局部沙箱（方案 A：顶层按车型后缀分割）

    与全局 MemoryDatabase 的关系：
    - 隔离：私有参数只在沙箱内，不污染全局
    - 只读桥接：通过 sandbox.get_global(name, vehicle_suffix) 读取全局参数
    - 可选回写：sandbox.mark_for_commit(name) 标记后 commit() 写回全局

    【数据结构 - 顶层按车型后缀分割】
    沙箱数据以 "车型后缀"（如 "reevlto"、"evlto"）为第一层 key，
    第二层为 base key（不带后缀）与值的映射。
    与 MemoryDatabase.memorycore 的顶层键 "增程车型_reevlto" 不同，
    沙箱只用后缀作为 key，这与 CalculationNode.vehicle_suffix 完全对齐，
    避免每次访问都需要从复合键拆分后缀。

    _params 结构：
    {
        "reevlto": {                              # 车型后缀（不含车型名）
            "mot_reg_eff": 0.85,                  # base key（不带后缀）
            "m_b_energy": 0.3,
            "mot_regen_map": {...},               # 复杂结构（MAP图等）
            ...
        },
        "evlto": { ... }
    }

    db_key 拼接（与 MemoryDatabase 对接时自动完成）：
    - 读取/写入 SSTS 参数：f"{base_key}_result_{vehicle_suffix}"
    - 读取/写入 SSTS 目标值：f"{base_key}_target_{vehicle_suffix}"
    - 读取基础产品定义：f"{base_key}_{vehicle_suffix}"

    项目关联属性（由 SSTSWorkflowAgentBase 自动填充）：
    - project_folder:  str | None    项目文件夹绝对路径（如 "D:/.../data/蜗牛项目"）
    - vehicle_subfolder: str | None  车型子文件夹名（如 "增程车型"），None 表示未匹配
    - memory_db_file_path: str | None 关联的 MemoryDatabase 源 Excel 文件路径
    - loaded_file_count: int           最近一次 load 的文件数（用于状态提示）
    - last_load_time: datetime | None  最近一次加载的时间戳
    - vehicle_suffixes: list[str]      已加载的车型后缀列表（如 ["reevlto", "evlto"]）
    - vehsuffix_table: list[dict]     从 memory_db.vehsuffix 复制的车型元数据表
    """
```

**核心接口**：

| 方法 | 说明 |
|------|------|
| `load_from_folder(folder_path, filter_patterns=None) -> int` | 扫描文件夹，自动识别 .json/.yaml/.csv/.xlsx 文件并加载；filter_patterns 为 glob 模式列表（如 `["Motor/**", "Brake/**"]`），为空则加载全部；返回成功文件数 |
| `load_file(file_path) -> dict` | 加载单个参数文件，返回 {param_name: value} |
| `get(name, vehicle_suffix, default=None)` | 读取指定车型的参数（base key 不带后缀） |
| `set(name, vehicle_suffix, value, is_private=False, meta=None)` | 设置指定车型的参数 |
| `get_vehicle_params(vehicle_suffix) -> dict` | 返回指定车型的全部参数 {base_key: value} |
| `get_all() -> dict` | 返回全部参数 {vehicle_suffix: {base_key: value}} |
| `get_global(name, vehicle_suffix) -> Any` | 只读桥接全局 MemoryDatabase；内部自动拼 db_key = `{name}_result_{vehicle_suffix}` |
| `mark_for_commit(*names)` | 标记 base key 名，commit() 时对所有车型逐个拼后缀回写 |
| `commit() -> int` | 将标记参数写回全局 MemoryDB；遍历所有 vehicle_suffix，每个拼 `{name}_result_{suffix}` 写回 |
| `unmark_for_commit(*names)` | 取消标记 |
| `snapshot() -> dict` | 导出当前状态（供 LLM 工具调用） |
| `is_project_loaded() -> bool` | 是否已关联项目文件夹并成功加载（vehicle_suffixes 非空） |
| `clear()` | 清空所有参数（用于项目切换时重置） |
| `add_vehicle_suffix(suffix, vehicle_subfolder=None)` | 手动添加车型后缀到沙箱（通常由 load_from_folder 自动完成） |

### 5.2 SSTSWorkflowAgentBase（重写 ssts_compute_agent.py）

**文件**：`agents/core/agent_base/ssts_compute_agent.py`（重写）

```python
class SSTSWorkflowAgentBase(WorkflowAgentBase):
    """SSTS 计算 Agent 基类（重写原残留桩类）

    在 WorkflowAgentBase 基础上叠加 3 项 SSTS 能力：
    1. SSTSSandbox — 局部沙箱（隔离 + 只读桥接 + commit 回写）
    2. 文件夹参数读取 — load_from_folder()
    3. 可视化结果收集 — visualization_results

    自动注册机制（镜像 VTSComputeAgent）：
      - is_ssts_agent = True
      - ssts_category = "能量回收"
    """
```

**类属性（与 VTSComputeAgent 对称）**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `_ssts_agent_registry` | dict | 注册表（key: ssts_category, value: agent_class） |
| `is_ssts_agent` | bool | 默认 False，子类覆写为 True 以注册 |
| `ssts_category` | str | SSTS 类别，如 "能量回收" |
| `is_vts_agent` | bool | 默认 False（SSTS 不参与 VTS 统一计算） |

**`_extra_init` 覆写**：执行顺序如下：
1. `super()._extra_init()` → WorkflowAgentBase 创建 `_workflow_cache`
2. 创建 `SSTSSandbox(global_db=self._memory_db)` 实例
3. 调用 `_auto_detect_project_folder()` → 从 `memory_db.file_path` 解析项目文件夹 → 加载零部件参数到 sandbox
4. 记录检测到的文件路径，后续调用时若 file_path 变化则自动重建 sandbox

**公开接口**：

| 方法 | 说明 |
|------|------|
| `get_sandbox() -> SSTSSandbox` | 获取沙箱实例 |
| `reload_sandbox(folder_path=None) -> int` | 重新加载文件夹参数；folder_path=None 时自动重新识别项目文件夹 |
| `commit_sandbox_to_global() -> int` | 将沙箱中标记的参数写回全局 |
| `get_visualization_results() -> dict` | 获取最新计算的可视化结果 |
| `is_ready() -> bool` | sandbox 是否已成功关联项目文件夹并加载（前置条件检查） |
| `get_project_info() -> dict` | 返回当前关联的项目信息（项目名、文件夹路径、车型子目录、加载文件数） |
| `get_ssts_agents()` / `clear_ssts_registry()` | 类方法，注册表发现接口 |

**私有方法（框架内部用）**：

| 方法 | 说明 |
|------|------|
| `_auto_detect_project_folder(memory_db) -> str \| None` | 从 memory_db.file_path 自动识别项目文件夹路径，找不到返回 None |
| `_extract_project_name_from_path(file_path) -> str` | 从 Excel 文件路径的 stem 中提取项目名 token |
| `_match_vehicle_subfolder(memory_db, project_folder) -> list[dict]` | 遍历项目文件夹的车型子目录，匹配 memory_db.vehsuffix 中的车型后缀。返回 `[{"vehicle_suffix": "reevlto", "subfolder": "增程车型", "veh_info": {...}}]` 列表。将结果传给 `sandbox.add_vehicle_suffix("reevlto", "增程车型")` 建立后缀-key映射 |

### 5.3 SSTSCalculationNode（扩展 CalculationNode）

**文件**：`agents/core/workflow_base/calc_nodes_base.py`（文件末尾新增子类，不修改基类）

```python
class SSTSCalculationNode(CalculationNode):
    """SSTS 计算节点基类

    在 CalculationNode 之上增加 2 个能力：
    1. self.sandbox — 局部沙箱（由 SSTSWorkflowExecutor 注入）
    2. generate_visualization() — 生成图表数据（钩子，子类可选实现）

    interface 保持不变：numerical_solve(memory_db), semantic_solve()
    """
```

**新增属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `sandbox` | Optional[SSTSSandbox] | 局部沙箱引用（执行时由 SSTSWorkflowExecutor 注入） |

**新增钩子方法**：

| 方法 | 返回 | 说明 |
|------|------|------|
| `generate_visualization() -> Optional[dict]` | dict 或 None | 生成计算结果的图表配置。返回 None 表示不生成。 |

**可视化返回格式**（JSON 为主，base64 可选降级）：

```json
{
    "chart_type": "line | bar | scatter | contour | table",
    "title": "图表标题",
    "x_label": "X轴标签",
    "y_label": "Y轴标签",
    "series": [
        {"name": "曲线名", "x": [...], "y": [...]}
    ],
    "base64_image": "..."    // 可选：预渲染图片（降级用）
}
```

**设计理由**：返回 JSON 配置为主避免大量图片数据撑爆 LLM function calling 上下文窗口，base64 仅作可选降级。

### 5.4 SSTSWorkflowExecutor（扩展 WorkflowExecutor）

**文件**：`agents/core/workflow_base/workflow_base.py`（新增类，不修改 WorkflowExecutor）

```python
class SSTSWorkflowExecutor(WorkflowExecutor):
    """SSTS 工作流执行器

    额外职责：
    1. 将 sandbox 注入到所有 SSTSCalculationNode
    2. 收集 generate_visualization() 结果
    3. 执行结束后可选触发 sandbox.commit()
    """
```

**新增属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `sandbox` | SSTSSandbox | 局部沙箱实例 |
| `auto_commit` | bool | 执行结束后是否自动 commit |
| `visualization_results` | Dict[str, dict] | 各节点的可视化结果（node_id → viz dict） |

**execute() 覆写**：注入 sandbox → 调用 `super().execute()` → 收集可视化结果 → 可选自动 commit。

### 5.5 build_workflow_from_yaml 扩展

**文件**：`agents/core/workflow_base/workflow_base.py`（修改函数签名，增加可选参数）

**不新增独立工厂函数**——在现有 `build_workflow_from_yaml` 上增加 3 个可选参数：

| 新增参数 | 类型 | 默认值 | 说明 |
|---------|------|--------|------|
| `sandbox` | SSTSSandbox \| None | None | SSTS Agent 时传入 |
| `auto_commit` | bool | False | 执行后是否自动 commit |
| `use_ssts_executor` | bool | False | True 时使用 SSTSWorkflowExecutor |

返回的 SimpleNamespace 额外包含：`visualization_results` 和 `sandbox` 属性。

VTS agent 调用时不传这 3 个参数，行为完全不变。

### 5.6 GenericSSTSWorkflowAgent（配置驱动实现）

**文件**：`agents/core/agent_base/generic_ssts_workflow_agent.py`（新增）

与 GenericWorkflowAgent 对称。从 YAML 读取所有配置，零自定义 Python。

```python
class GenericSSTSWorkflowAgent(SSTSWorkflowAgentBase):
    """配置驱动的通用 SSTS 工作流 Agent"""
```

**职责**：
1. 读取 agent YAML 配置
2. 设置 ssts_category / panel_id / sandbox_config
3. 创建 WorkflowFunctionFactory 注册中心（SSTS 扩展工具类型）
4. 通过 super().__init__() 完成全链路初始化

### 5.7 WorkflowFunctionFactory 扩展

**文件**：`agents/core/public_functions_core/workflow/workflow_function_factory.py`（修改 TOOL_TYPE_MAP）

新增 4 种 SSTS 专用工具类型：

| 类型键 | 模板类 | 说明 |
|--------|--------|------|
| `load_folder_params` | AbstractLoadFolderParamsFunction | 从文件夹加载零部件参数 |
| `update_sandbox` | AbstractUpdateSandboxFunction | 修改沙箱内参数值 |
| `commit_to_global` | AbstractCommitToGlobalFunction | 将沙箱标记参数回写全局 MemoryDB |
| `get_visualization` | AbstractGetVisualizationFunction | 获取计算结果的图表数据 |

每个模板类与现有模板（`AbstractRunFullCalculationFunction` 等）模式完全一致：实现 `get_schema()` 返回 JSON Schema，`execute()` 执行工具逻辑。

### 5.8 UI 面板扩展

```
BaseCalculationPanel(现有)
    ├── GenericCalculationPanel(现有，VTS 用)
    └── GenericSSTSCalculationPanel(新增，配置驱动的 SSTS 面板)
```

**文件**：`agents/core/ui_panel/workflow/ssts_calculation_panel.py` + `generic_ssts_calculation_panel.py`（新增）

**SSTS 面板与 VTS 面板的差异**：
- 底部或侧边增加图表展示区（渲染 visualization_results 中的 chart 配置）
- 增加沙箱参数检视器（查看/编辑当前参数、触发 reload/commit）
- 增加文件夹加载入口按钮

---

## 六、`__init__.py` 导出更新

```python
# agents/core/agent_base/__init__.py 导出清单（变更后）
from .ssts_compute_agent import SSTSWorkflowAgentBase   # 重写后类名变更
from .vts_compute_agent import VTSComputeAgent
from .generic_ssts_workflow_agent import GenericSSTSWorkflowAgent   # 新增
```

---

## 七、文件变更清单

| 操作 | 文件路径 | 变更说明 |
|------|---------|---------|
| 重写 | `agents/core/agent_base/ssts_compute_agent.py` | 从残留桩类 → SSTSWorkflowAgentBase 真实基类 |
| 修改 | `agents/core/agent_base/__init__.py` | 更新导出声明 |
| 修改 | `agents/core/workflow_base/calc_nodes_base.py` | 文件末尾新增 SSTSCalculationNode 子类（不修改基类） |
| 修改 | `agents/core/workflow_base/workflow_base.py` | ① build_workflow_from_yaml 增加 sandbox/use_ssts_executor 可选参数 ② 新增 SSTSWorkflowExecutor 类 |
| 新增 | `agents/core/workflow_base/ssts_sandbox.py` | SSTSSandbox 完整实现 |
| 新增 | `agents/core/agent_base/generic_ssts_workflow_agent.py` | 配置驱动的 SSTS Agent 实现 |
| 修改 | `agents/core/public_functions_core/workflow/workflow_function_factory.py` | TOOL_TYPE_MAP 新增 4 种 SSTS 工具类型 |
| 新增 | `agents/core/public_functions_core/workflow/function_templates/load_folder_params.py` | 加载文件夹参数工具模板 |
| 新增 | `agents/core/public_functions_core/workflow/function_templates/update_sandbox.py` | 修改沙箱参数工具模板 |
| 新增 | `agents/core/public_functions_core/workflow/function_templates/commit_to_global.py` | 回写全局工具模板 |
| 新增 | `agents/core/public_functions_core/workflow/function_templates/get_visualization.py` | 获取图表工具模板 |
| 新增 | `agents/core/ui_panel/workflow/ssts_calculation_panel.py` | SSTS 专用面板基类 |
| 新增 | `agents/core/ui_panel/workflow/generic_ssts_calculation_panel.py` | 配置驱动的 SSTS 面板 |
| 新增 | `agents/a401_energy_regeneration/config/energy_regeneration.yaml` | Agent 主配置 |
| 新增 | `agents/a401_energy_regeneration/config/workflow_energy_regen.yaml` | DAG 拓扑配置 |
| 新增 | `agents/a401_energy_regeneration/config/node_*.yaml` | 各节点元数据 |
| 新增 | `agents/a401_energy_regeneration/nodes/node_*.py` | 各节点算法实现（继承 SSTSCalculationNode） |
| 新增 | `agents/a401_energy_regeneration/component_templates/*.yaml` | 零部件参数模板文件 |
| 新增 | `agents/a401_energy_regeneration/data/*.json` | 示例数据文件 |

---

## 八、关键设计原则

### 8.1 最小侵入
对现有文件只做**新增**而非修改核心逻辑：
- `calc_nodes_base.py`：末尾加 SSTSCalculationNode 子类，CalculationNode 基类一行不动
- `workflow_base.py`：build_workflow_from_yaml 增加带默认值的可选参数，VTS agent 调用行为完全不变
- WorkflowFunctionFactory：TOOL_TYPE_MAP 加新 key，不改已有映射

### 8.2 沙箱可回写
`SSTSSandbox.mark_for_commit() + commit()` 让 SSTS 计算结果能被 VTS agent 读取。典型场景：能量回收效率优化后，影响经济性计算中的 `mot_reg_eff` 参数。

### 8.3 可视化返回 JSON 配置为主
避免 base64 图片撑爆 LLM function calling 上下文窗口。图表配置 JSON 体积小、可传递，base64 仅作可选降级（UI 渲染时可即时生成）。

### 8.4 接口一致
SSTSCalculationNode 的 `numerical_solve(memory_db)` / `semantic_solve()` 接口与 CalculationNode 完全一致。现有工具链（WorkflowFunctionFactory 的 run_full_calculation 等）零修改即可复用。

### 8.5 配置驱动
GenericSSTSWorkflowAgent 完全由 YAML 驱动。a401 与 a302/a303 同级——用户零 Python 代码即可创建新的 SSTS agent。

---

## 九、编码推进顺序建议

按依赖关系从底层到顶层推进：

```
Phase 1 — 基础层（无依赖）
  ├── ssts_sandbox.py                    ← SSTSSandbox 完整实现
  └── ssts_compute_agent.py 重写         ← SSTSWorkflowAgentBase

Phase 2 — 节点层（依赖 Phase 1）
  ├── calc_nodes_base.py 扩展            ← SSTSCalculationNode
  └── workflow_base.py 扩展              ← SSTSWorkflowExecutor + build_workflow_from_yaml 参数化

Phase 3 — Agent 层（依赖 Phase 1+2）
  └── generic_ssts_workflow_agent.py     ← 配置驱动实现

Phase 4 — 工具层（依赖 Phase 3）
  ├── WorkflowFunctionFactory 扩展
  └── 4 个工具模板实现

Phase 5 — UI 层（依赖 Phase 3）
  ├── ssts_calculation_panel.py
  └── generic_ssts_calculation_panel.py

Phase 6 — 具体案例 a401（依赖全部）
  ├── config/*.yaml
  ├── nodes/*.py
  └── component_templates/ + data/
```
