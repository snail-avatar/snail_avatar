Public Functions 命名规则
========================

一、文件名格式
--------------
公共函数文件名格式为：{三位数字前缀}_pubfn_{功能描述}.py

示例：
- 000_pubfn_calculator.py
- 100_pubfn_vts_ssts_data_reader.py
- 301_pubfn_vts_calc.py


二、三位数字前缀规则
--------------------
第一位数字表示功能类别，后两位数字为该类别下的序列号。

【0xx】Agent 资源与基础工具类（Agent Resource）
  - 000_pubfn_calculator.py       数学计算器
  - 001_pubfn_list_sub_agents.py  列出系统中所有子 Agent

【1xx】数据读取类（Data Read）
  - 100_pubfn_vts_ssts_data_reader.py   VTS/SSTS 数据读取
  - 101_pubfn_product_data_reader.py    产品定义数据读取
  - 102_pubfn_pass_status_checker.py    VTS 达标情况查询

【2xx】数据转换与格式化类（Data Transform & Format）
  - 200_pubfn_sandbox_data_extractor.py 沙箱数据提取
  - 201_pubfn_pipeline_config_builder.py Pipeline 查询参数构建
  - 202_pubfn_format_vts_data.py        VTS 数据格式化
  - 203_pubfn_extract_step_context.py   Step 上下文提取
  - 204_pubfn_loop_config.py            循环配置保存
  - 205_pubfn_save_data_to_process.py   数据保存到 process_data

【3xx】数据校验与计算类（Validation & Calculation）
  - 300_pubfn_ssts_validator.py   SSTS 参数校验与转换
  - 301_pubfn_vts_calc.py         VTS 校核计算


三、私有函数命名
----------------
仅供特定 Agent 使用的私有函数（如 a101_target_definition_agent 专属），
采用 "a{agent_id}_step{步骤号}_{功能描述}.py" 格式命名，
不使用三位数字前缀，以区分公共函数与私有函数。

示例：
- a101_step1_save_mapping.py             a101 第1步：保存映射
- a101_step1_build_vts_structure.py      a101 第1步：构建 VTS 结构
- a101_step2_2_save_process_data.py     a101 第2.2步：保存过程数据


四、新增函数命名步骤
--------------------
1. 确认该函数所属的功能类别（0xx / 1xx / 2xx / 3xx）。
2. 查找该类别下现有最大序列号，新函数取序列号 + 1。
3. 按 "{三位数字前缀}_pubfn_{功能描述}.py" 格式创建文件。
4. 确保文件内包含继承自 FunctionBase / AtomicFunction 的类。
5. 在类的 "name" 属性中声明函数的唯一名称（LLM 调用时使用此名称）。


五、自动发现机制
----------------
框架通过扫描文件名包含 "pubfn" 且非 __ 开头的 .py 文件，
自动加载其中继承自 FunctionBase 的子类并完成注册。
命名不影响加载逻辑，仅用于分类、排序与人工识别。

六、参数获取方式
----------------

Step 执行时涉及 4 种参数来源，框架通过 `_resolve_variables` 方法统一解析：

6.1 step_args（框架构造参数包）
  来源：ProcessEngine 根据 args_config 配置自动构造
  内容：instance_key（实例标识）、vehicle_suffix（实例后缀）、professional_category（当前循环项）等
  用途：作为所有变量解析的基础数据源，供模板 {xxx} 占位符和函数参数 $args.xxx 引用
  示例：
    - $args.instance_key  → 获取当前实例标识
    - $args.professional_category → 获取当前专业名称

6.2 data_sources（数据源函数调用）
  来源：YAML 中 data_sources 段声明的公共函数调用结果
  用法：在步骤执行前自动调用声明的函数，结果存入字典供后续使用
  声明格式：
    data_sources:
      - function: "函数名"       # 必填，public_functions 中注册的类名
        args_mapping:            # 可选，函数参数映射
          参数名: 字面量或 $变量引用
        output: "输出键名"        # 必填，结果存入 data_sources 的键名
  用途：为 LLM 提供业务背景数据（如 VTS 分类列表、产品定义、法规信息）
  示例（step1_detect_categories_llm.yaml）：
    data_sources:
      - function: "vts_ssts_data_reader"
        args_mapping:
          operation: "get_vts_categories"
        output: "vts_categories"

6.3 memory_db（数据库实例）
  来源：get_memory_db() 全局获取
  用途：所有需要读写 MemoryCore 的公共函数自动注入，无需在 YAML 中声明
  引用方式：$memory_db
  示例（step2_5_validate_targets_agent.yaml）：
    args_mapping:
      memory_db: "$memory_db"

6.4 context_vars（上下文变量配置）
  来源：process.yaml 中 context_vars 段声明
  用途：解耦变量名与数据来源，供模板变量解析和函数参数注入共用
  支持类型：
    - mapping：从 step_args 或执行状态中查找
    - value：常量值
  声明格式：
    context_vars:
      变量名:
        mapping: "step_args中的键名"  # 从 step_args 查找
        或 value: "常量值"            # 直接使用
  示例（process.yaml）：
    context_vars:
      professional_category:
        mapping: "professional_category"
      agent_name:
        value: "目标值定义 Agent"

6.5 变量解析优先级
  _resolve_variables 按以下顺序解析变量，高优先级的值不被覆盖：
    1. extra_vars（已知值，如 data_sources 结果）
    2. memory_db（始终自动注入）
    3. step_args 中的值
    4. context_vars 配置补全（仅补充缺失的变量）

6.6 args_mapping 中的变量引用语法
  在 data_sources、execution_pipeline、post_process 的 args_mapping 中支持：
    - $args.xxx        step_args 中的参数
    - $memory_db       数据库实例
    - $context         Agent 实例
    - $data_sources.xxx 数据源结果
    - $post.xxx        前序后处理结果
    - $pipeline.xxx    execution_pipeline 节点结果
    - 字面量字符串     直接使用

6.7 execution_pipeline 参数获取
  Process 类型步骤通过 execution_pipeline 声明顺序执行的节点：
    execution_pipeline:
      - function: "函数名"
        args_mapping:
          参数名: $变量引用
        output: "输出键名"
  节点间通过 $pipeline.xxx 传递数据，参数解析同样走 _resolve_variables

6.8 post_process 参数获取
  所有步骤类型支持后处理钩子，通过 post_process 声明：
    post_process:
      - function: "函数名"
        args_mapping:
          参数名: $变量引用
        output: "输出键名"
  支持 $post.xxx 引用前序后处理结果，支持 $result 引用步骤原始输出
