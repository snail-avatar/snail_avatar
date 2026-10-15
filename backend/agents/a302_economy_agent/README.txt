# Economy Agent 经济性仿真工程师智能体

此目录是完整自包含的经济性仿真工程师智能体，实现纯电动汽车能耗与续驶里程计算。

## 目录结构 - 【自包含多Agent架构】

```
economy_agent/
├── __init__.py              # 统一对外接口
├── agent.py                 # LLM层: 系统提示词 + Function调用声明
├── workflow.py              # 编排层: 工作流编排 + 节点发现 + 执行调度
├── README.txt               # 本说明文档
│
├── 📁 nodes/                # 算法层: 7个纯算法节点
│   ├── node_1_DriveCycleAnalyzer.py      # 驾驶循环分析器
│   ├── node_2_ResistanceCalculator.py     # 行驶阻力计算器
│   ├── node_3_MotorWorkpoint.py           # 电驱工作点计算器
│   ├── node_4_WheelEnergy.py              # 轮端能量计算器
│   ├── node_5_VehicleEnergy.py            # 车端能量计算器
│   ├── node_6_ACEnergy.py                 # 网端能量计算器
│   └── node_7_DrivingRange.py             # 续驶里程计算器
│
├── 📁 config/               # 配置层: YAML元数据
│   ├── workflow_ev_ECO.yaml               # 拓扑配置 + DAG依赖
│   ├── node_1_DriveCycleAnalyzer.yaml     # 节点元数据 + IO定义
│   ├── node_2_ResistanceCalculator.yaml
│   ├── node_3_MotorWorkpoint.yaml
│   ├── node_4_WheelEnergy.yaml
│   ├── node_5_VehicleEnergy.yaml
│   ├── node_6_ACEnergy.yaml
│   └── node_7_DrivingRange.yaml
│
└── 📁 ui/                   # UI层: 可视化面板
    └── eco_panel.py                      # DAG有向无环图画布
```

## 主要功能

**Economy 经济性计算智能体**：
   - 驾驶循环分析：分析驾驶循环的运动学特性
   - 行驶阻力计算：计算滚阻、风阻和拖滞阻力
   - 电驱工作点计算：计算电驱动力、扭矩和转速
   - 轮端能量计算：计算驱动和制动能量
   - 车端能耗计算：计算最终车端能耗
   - 续驶里程计算：基于能耗计算续驶里程
   - 网端能耗计算：计算网端能耗

## 调用方式

外界只需要这一行导入即可：

```python
from snail_avatar.agents import EconomyAgent
```

## 设计原则：约定优于配置

1. workflow_ev_ECO.yaml = 拓扑连接关系（DAG依赖 + UI位置）
2. node_X_xxx.yaml = 单个节点元数据（inputs/outputs/UI配置）
3. node_X_xxx.py = 纯算法逻辑，只实现 calculate() 方法

新增节点完全不需要修改任何Python代码！
只需要：
  1. nodes/node_8_NewNode.py
  2. config/node_8_NewNode.yaml
  3. config/workflow_ev_ECO.yaml 中添加拓扑
