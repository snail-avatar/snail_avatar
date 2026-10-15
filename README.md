# Snail Avatar

多 Agent 架构的电动汽车性能开发智能辅助系统，面向汽车性能开发工程师，旨在替代一部分重复性分析工作，实现「对话式仿真 + 智能知识输出」的下一代研发模式。

## 项目定位

- 性能评估：加速、最高车速、爬坡、能耗、续驶里程等指标自动计算与评估
- 指标管控：VTS/SSTS 整车及子系统技术规格的达标状态监控与预警
- 指标分析：专业指标深度解读、影响因素分析、优化方向建议
- 知识输出：空气动力学、动力经济性等专业知识智能问答与推理

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                   浏览器 / 用户                    │
└─────────────────────┬───────────────────────────┘
                      │ HTTP (127.0.0.1:5173)
              ┌───────▼───────┐
              │  Vue3 前端     │
              │  (Vite + EP)  │
              └───────┬───────┘
                      │ REST API (127.0.0.1:8000)
              ┌───────▼───────┐
              │  FastAPI 后端  │
              └───────┬───────┘
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Agent    │  │ 核心框架  │  │ 数据中台  │
  │ 调度中心  │  │ 引擎集合  │  │ 内存数据库 │
  └────┬─────┘  └──────────┘  └──────────┘
       │
   ┌───┴───┬────┬────┬────┬────┐
   ▼       ▼    ▼    ▼    ▼    ▼
 a101    a201  a202  a301  a302  a303  a401
目标定义  气动   PE   VTS   经济   动力  能量回收
         专家  专家  SSTS
```

三层核心底座：

| 层 | 组成 |
|----|------|
| Agent 调度层 | MainAgent → AgentRouter（LLM 智能路由优先 + 关键词兜底）→ 各专业子 Agent 懒加载、上下文摘要传递、Function Calling |
| 核心框架层 | Agent 基类体系、Process Engine 流程引擎、DAG 工作流引擎、知识库引擎（向量/图谱/规则/案例）、工具系统 public_functions |
| 数据中台层 | MemoryDatabase 内存单例、Excel 车型参数持久化、db_key 唯一标识、按车型 / 工作流 / 节点分层共享 |

## Agent 体系

| Agent | 编号 | 类型 | 核心职责 |
|-------|------|------|---------|
| MainAgent | a000 | 对话入口型 | 总调度、子 Agent 路由、通用问答、Function Calling |
| TargetDefinitionAgent | a101 | 流程驱动型 | 跨专业 VTS/SSTS 目标值定义全流程编排（process.yaml 驱动） |
| AeroExpertAgent | a201 | 知识输出型 | 空气动力学专业知识问答（四大知识库驱动） |
| PEExpertAgent | a202 | 知识输出型 | 动力经济性专业知识问答（四大知识库驱动） |
| VTS_SSTS_Agent | a301 | 数据查询型 | VTS/SSTS 达标状态查询与分类汇总分析 |
| EconomyAgent | a302 | 计算工作流型 | 经济性仿真计算（DAG 工作流，多温度工况） |
| PowerAgent | a303 | 计算工作流型 | 动力性仿真计算（DAG 工作流，后驱车型） |
| EnergyRegenerationAgent | a401 | 计算工作流型 | 能量回收制动力分配计算（再生制动与摩擦制动协调分配）——开发中 |

## 核心亮点

**LLM 原生的计算流架构**（项目核心创新）

传统数值计算只输出"数"，LLM 拿到孤立数字无法解释、无法追问。本项目把语义求解作为计算的一等公民——每个节点同时跑 `numerical_solve()` 与 `semantic_solve()`，数与话同步产出。

- **TimeSeries 语义数据结构**：不再是裸 `np.ndarray`，自带 name / unit / desc 三语义字段。数值流到哪，语义跟到哪。
- **双求解器节点（CalculationNode）**：数值求解算参数，语义求解自动生成 Markdown 分析报告。算完即写报告，人不补文档。
- **范式转变**：传统仿真工具输出给"人"看（一张表 + 一张图）；我们的输出给"Agent"看（数 + 语义报告）。LLM 读到 report 即可直接做归因分析、DOE 变量推荐、优化方向建议。

**YAML 配置驱动、零代码扩展**

流程引擎（Process Engine）面向"人驱动的多步骤任务"（如目标值定义）；DAG 工作流面向"物理仿真计算"（如经济性/动力性求解）。新增专业 Agent = 新增目录 + 新增 YAML 配置，无需修改任何核心框架代码。

## 目录结构

```
snail_avatar/
├── backend/
│   ├── agents/              # 各专业 Agent（核心业务逻辑）
│   ├── core/                # 核心模块（数据解析器、记忆库等）
│   ├── fastapi_app/         # FastAPI Web 服务 + REST/SSE 路由
│   └── llm/                 # LLM 部署辅助
├── data/                    # 示例数据（VTS/SSTS 主数据源等）
├── frontend/
│   └── vue_app/             # Vue 3 前端应用
├── config example.ini       # 配置文件模板
├── LICENSE                  # MIT 协议
├── .gitignore
├── start_all.bat            # 一键启动前后端
├── start_backend.bat        # 仅启动后端
└── start_frontend.bat       # 仅启动前端
```

## 技术栈

### 后端

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| 运行语言 | Python 3.10+ | 建议 3.14 |
| Web 框架 | FastAPI + Uvicorn | 异步 API 服务，REST JSON + **SSE 阶段事件流推送** |
| LLM 服务 | 阿里云百炼 DashScope | **Qwen3-Max**（主模型）+ **Qwen-Flash**（摘要 / 路由） |
| 向量嵌入 | 多模态 Embedding | qwen3-vl-embedding，支持图文混合检索 |
| 向量存储 | ChromaDB | 专家知识库持久化 |
| 数据处理 | Pandas + NumPy + openpyxl | 工程计算与 Excel 车型参数表读写 |
| 配置驱动 | YAML | 工作流 / Agent / 节点全配置化，零代码扩展 |
| 可视化 | Matplotlib | 数据可视化 |

### 前端

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| 框架 | Vue 3 + TypeScript | 组件化 Web UI |
| 构建工具 | Vite | 快速开发与打包 |
| UI 组件 | Element Plus | 企业级组件库 |
| 图表 | ECharts | 数据可视化 |
| 状态管理 | Pinia | 全局状态 |
| 路由 | Vue Router | SPA 路由 |
| HTTP | Axios | REST API 调用 |
| Markdown + LaTeX | Markdown-It + KaTeX | Agent 分析报告渲染 |

### 架构演进

项目由上一版 **Flet 单机桌面应用**（Python 驱动 UI）升级为 **Vue3 Web 前端 + FastAPI 后端** 的前后端分离架构，带来浏览器跨端访问、UI 组件生态丰富、前后端并行开发、便于后续 Web 化部署等优势。

## 运行方法

### 环境要求

- **Python 3.10+**（建议 3.14）
- **Node.js 18+**（建议 20+）
- **npm / npx**（Node 自带）
- 网络畅通（首次运行需下载 Python 包、npm 包；LLM/Embedding 需访问阿里云百炼）

### 1. 获取代码

```bash
git clone <your-repo-url>
cd snail_avatar
```

### 2. 配置 API Key

复制示例配置文件，将名称中的 "config example.ini" 替换为 "config.ini"，替换为你自己的 **百炼（DashScope）API Key**：

```bash
# Windows
copy "config example.ini" config.ini

# macOS / Linux
cp "config example.ini" config.ini
```

然后编辑 `config.ini`：

```ini
[API]
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                    ↑ 替换为你的 DashScope API Key

[EMBEDDING]
provider=dashscope
```

> **获取 API Key**：登录 [阿里云百炼控制台](https://dashscope.console.aliyun.com/) → API-KEY → 创建新的 API-KEY。

### 3. 安装后端依赖

```bash
cd backend/fastapi_app
pip install -r requirements.txt
pip install dashscope pyyaml openpyxl chromadb
pip install numpy pandas matplotlib
```

> 也可以一次性安装所有：
> ```bash
> pip install fastapi uvicorn[standard] pydantic pydantic-settings dashscope pyyaml openpyxl chromadb numpy pandas matplotlib
> ```

### 4. 安装前端依赖

```bash
cd frontend/vue_app
npm install
```

### 5. 启动服务

**方式一：一键启动（推荐）**

双击根目录下的 `start_all.bat`（Windows），或手动执行：

```bash
# 在 Windows PowerShell 中（cd 到项目根目录的上一级）
cmd /k "snail_avatar\start_all.bat"
```

脚本会自动：
1. 清理 8000 / 5173 端口占用（**只杀这两个端口**，不会动其他 Python/Node 进程）
2. 启动后端 FastAPI（端口 8000）
3. 启动前端 Vite（端口 5173）
4. 8 秒后自动打开浏览器

**方式二：分别启动**

```bash
# 终端 A — 后端（工作目录必须在 snail_avatar 的上一级）
cd ..
python -m uvicorn snail_avatar.backend.fastapi_app.main:app --host 127.0.0.1 --port 8000

# 终端 B — 前端
cd frontend/vue_app
npx vite --host 127.0.0.1 --port 5173
```

### 6. 访问

启动成功后，浏览器打开：

```
http://127.0.0.1:5173
```

后端 API 文档（FastAPI 自动生成）：

```
http://127.0.0.1:8000/docs
```

## 首次运行注意事项

1. **专家知识库初始化**：首次进入气动专家 / PE 专家页面时，系统会读取 `backend/agents/a201_aero_expert_agent/data/*.xlsx` 和 `backend/agents/a202_PE_expert_agent/data/*.xlsx` 并调用 DashScope Embedding 向量化，写入本地 ChromaDB。这个过程耗时取决于 Excel 数据量和 API 速率限制。后续启动直接复用本地向量库，不会重复向量化。

2. **记忆库**：后端运行时会在 `backend/core/memory/` 下创建 SQLite 数据库（对话记忆）。这些是用户数据，不会随 git 提交。

## 开源说明

本项目遵循 **MIT 开源协议**，详见 [LICENSE](./LICENSE)。

你可以自由使用、修改、商用、二次分发，仅需保留 LICENSE 文件和源代码中的版权声明。

## 常见问题

**Q: 启动报 `ModuleNotFoundError: No module named 'snail_avatar'`？**

A: 后端启动的工作目录必须在 `snail_avatar` 的**上一级**。直接用 `start_backend.bat` 即可，它已经 `cd` 到了正确位置。如果你手动运行 uvicorn，注意目录层级。

**Q: 启动报 `taskkill` 相关错误？**

A: `start_all.bat` 中的端口清理可能因权限不足而失败（如系统服务占用了 8000/5173）。这种情况下手动关闭其他进程后重试即可，bat 脚本不会因此中断。

**Q: 向量库目录 `vector_db/` 是空的？**

A: 正常。ChromaDB 在首次加载专家知识库时才会创建向量索引文件（`.bin` / `.sqlite3`）。运行时生成的数据不会随 git 提交。

**Q: 哪些文件不随 git 提交？**

A: `config.ini`（含 API Key）、`backend/agents/*_expert_agent/data/vector_db/`（运行时向量库）、`uploads/`（上传临时文件）、`*.db`（本地数据库）、`node_modules/`、Python `__pycache__/`、以及除两个主数据源外的所有 `*.xlsx` 文件。详见 [.gitignore](./.gitignore)。
