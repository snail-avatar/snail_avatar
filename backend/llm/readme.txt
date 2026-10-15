# LLM 目录

此目录包含所有与 LLM Agent 相关的功能，提供智能助手服务。

## 目录结构

```
llm/
├── __init__.py              # 包初始化文件
├── agent_base.py            # Agent 基类
├── pe_sim_engineer.py       # PE 仿真工程师 Agent
├── deploy.py                # LLM 部署模块
└── tools/                   # Agent 可用工具
    ├── calc_engine_tool.py  # 调用计算引擎的工具
    └── memory_db_tool.py    # 查询内存数据库的工具
```

## 主要模块

1. **AgentBase**：Agent 基类，提供通用的 Agent 功能
   - 工具注册和管理
   - 基本的 Agent 运行流程

2. **PESimEngineerAgent**：PE 仿真工程师 Agent
   - 专业的电动汽车动力经济性仿真工程师
   - 支持参数更新和计算执行
   - 分析计算结果并提供专业解释

3. **Deploy**：LLM 部署模块
   - 初始化和管理 LLM 实例
   - 提供与 LLM 交互的接口

4. **Tools**：Agent 可用工具
   - **CalcEngineTool**：调用计算引擎执行计算
   - **MemoryDBTool**：查询和操作内存数据库

## 功能说明

- **智能助手**：提供专业的电动汽车仿真工程分析
- **参数管理**：帮助用户更新和管理仿真参数
- **结果分析**：分析计算结果并提供专业解释
- **工具调用**：通过工具调用执行计算和查询数据