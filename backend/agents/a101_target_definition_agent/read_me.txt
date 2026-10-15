================================================================================
a101_target_definition_agent — 执行逻辑参考手册
================================================================================

一、整体目的
--------------------------------------------------------------------------------
本 sub agent 用于在整车开发项目的"目标值定义"阶段，按专业分组自动完成
VTS（整车技术规格）和 SSTS（子系统技术规格）参数的目标值设定、校核、
优化和总结。

流程驱动方式：process.yaml 定义步骤编排，每个步骤的 data_sources / query /
post_process 由独立的 step YAML 文件配置，底层 public function 实现具体逻辑。

当前系统内置了 3 个专业（空气动力学、动力性、经济性），但本 agent 的设计
初衷是**通用的专业框架**——当系统新增类似 a201_aero_expert_agent、
a202_PE_expert_agent、a302_economy_agent、a303_power_agent 等底层 agent 后，
可以自动扩展出定义其他专业目标值的能力，无需修改本 agent 的代码或配置。


二、可扩展性设计分析
================================================================================

本 agent 的"新增专业自动扩展"能力已完整具备，核心机制分 6 层：

────────────────────────────────────────────────────────────────────────────────
2.1 专业列表动态化 ✅ 已实现
────────────────────────────────────────────────────────────────────────────────

循环项来源不是硬编码，而是 LLM 运行时动态生成：

  step1 DETECT_CATEGORIES 的 data_sources:
    ① vts_ssts_data_reader(operation="get_vts_categories")
       → 从 DB target_vts 表读取有哪些专业分节（如"底盘"、"NVH"、"碰撞安全"...）
    ② list_all_sub_agents()
       → 扫描 agents/*/config/*.yaml，发现所有可用子 agent

  step1 LLM 综合两方面信息，输出:
    structured_data.categories = ["空气动力学", "动力性", "经济性", "底盘", ...]
    structured_data.workflow_mapping = {"底盘": "a304_chassis_agent", ...}
    structured_data.expert_mapping    = {"底盘": "a203_chassis_expert_agent", ...}

  框架 loop_config.loop_items_source = "structured_data.categories"
  → 自动消费 LLM 输出的 categories 作为 loop_categories 循环项

  新增专业时：只要 VTS DB 里有对应专业分节 + agent_router 能发现新 agent，
  LLM 就会自动把新专业纳入 categories 列表。


────────────────────────────────────────────────────────────────────────────────
2.2 Agent 映射动态化 ✅ 已实现
────────────────────────────────────────────────────────────────────────────────

Step 配置中 agent_type 决定了 agent_id 的解析方式：

  agent_type: "fix"     → agent_id 硬编码在 YAML（如 step2_5 的 vts_ssts_agent）
  agent_type: "calculator" → 框架自动从 sandbox._agent_type_mappings["calculator"]
                            按 professional_category 键查找对应的 agent_id
  agent_type: "expert"     → 框架自动从 sandbox._agent_type_mappings["expert"]
                            按 professional_category 键查找对应的 agent_id

  sandbox 映射由 step1 post_process 的 set_step_agent 写入：
    sandbox.set_agent_type_mapping("calculator", workflow_mapping)
    sandbox.set_agent_type_mapping("expert",    expert_mapping)

  step2_2 DETERMINE_MAPPING  agent_type: "calculator" ← 动态
  step2_3 CHECK_REGULATIONS  agent_type: "expert"     ← 动态
  step2_6 OPTIMIZE_SSTS      agent_type: "calculator" ← 动态
  step2_5 VALIDATE_SSTS      agent_type: "fix"（固定 vts_ssts_agent）
                                但这个 agent 是通用 VTS 校核 agent，
                                不做领域计算，所有专业共用同一个

  新增专业时：LLM 在 step1 自动分配 workflow_mapping / expert_mapping 即可，
  后续步骤无需任何改动。


────────────────────────────────────────────────────────────────────────────────
2.3 Prompt 全变量化 ✅ 已实现
────────────────────────────────────────────────────────────────────────────────

所有 YAML prompt 中的专业名都是变量注入：

  query_template: |
    请确定专业「{professional_category}」的VTS指标与SSTS指标的映射关系。
    ...
    {task_prompt}

  task_prompt 中的示例虽然展示了具体专业名（如"空气动力学"），
  但这只是格式示例，不影响实际运行。所有 LLM 指令、约束、输出格式说明
  都没有硬编码的专业特定逻辑。

  step2_4 system_prompt 是通用的"目标值定义专家"角色，
  不包含任何领域特定的知识——领域知识来自 data_sources 加载的
  product_info + mappings + references，这些也是动态按专业提取的。


────────────────────────────────────────────────────────────────────────────────
2.4 Public Functions 全参数化 ✅ 已实现
────────────────────────────────────────────────────────────────────────────────

所有 Python 函数都接受 professional_category 参数，无硬编码专业名：

  a101_step2_2_save_process_data.py     — merge_ssts_to_process_data(step_id, sandbox, ..., args)
  a101_step2_4_validate_targets.py      — validate_targets(sandbox, category, ...)
  a101_step2_4_save_targets.py          — save_targets(sandbox, memory_db, ..., defined_ssts_db)
  a101_step2_4_revise_if_needed.py      — revise_if_needed(targets)
  301_pubfn_vts_calc.py                 — copy_target_to_current(db, instance_key, category, sandbox)
  a101_step2_6_update_targets.py        — update_optimized_targets(memory_db, sandbox, ..., professional_category)
  pubfn_db_schema_sync.py               — sync(mapping, memory_db, instance_key, ...)
  所有 data_sources 提取函数（step2_2/2_4/2_5/2_6_extract_data.py）
                                        — 全部接受 professional_category 参数

  grep 确认：整个 a101_target_definition_agent 目录及其引用的 public_functions
  中，没有任何 `if category == "空气动力学"` 或类似硬编码。


────────────────────────────────────────────────────────────────────────────────
2.5 DB Schema 动态化 ✅ 已实现
────────────────────────────────────────────────────────────────────────────────

DB 双表设计不涉及专业名硬编码：

  target_vts 表顶层按专业分节 → 新增专业 = 新增一个分节
  （由 step1 build_vts_structure 从 VTS DB 动态生成）
  target_ssts 表顶层按参数类型（"SSTS"/"VTS"）分节 → 专业无关
  所有表内参数项结构统一，按 db_key 匹配

  db_schema_sync 从 DB 拍平两张表构建权威字典，
  不依赖任何特定专业名。


────────────────────────────────────────────────────────────────────────────────
2.6 Agent Router 自动发现 ✅ 已实现
────────────────────────────────────────────────────────────────────────────────

agent_router（d:\AI_model\snail_avatar\agents\core\tools\routing\agent_router.py）
扫描 agents/*/config/*.yaml 发现所有子 agent，
每个子 agent 的 agent_id 配置在其自身 YAML 中（如 a201_aero_expert_agent/config/*.yaml）。

  list_all_sub_agents（公共函数，step1 data_sources 调用）
  → 返回所有已注册 agent 的列表和描述
  → step1 LLM 根据这些描述决定专业→agent 的映射

  新增 agent 的操作：
    1. 在 agents/ 下创建新 agent 目录和 config YAML
    2. 配置 agent_id 和 module_path
    3. agent_router 自动扫描发现，list_all_sub_agents 自动返回


────────────────────────────────────────────────────────────────────────────────
2.7 新增专业的操作清单（总结）
────────────────────────────────────────────────────────────────────────────────

当系统增加新的底层 agent（如 a203_chassis_workflow_agent）后，
让 a101 自动支持新专业（如"底盘"）的目标值定义，需要：

  ① 在 VTS 数据库（target_vts_memorycore）中添加新专业分节
     "底盘": [所有底盘相关的 VTS 参数项]

  ② 在 agents/ 下创建新 agent 的目录结构和 YAML 配置
     agents/a203_chassis_workflow_agent/config/*.yaml
     （配置 agent_id: "a203_chassis_workflow_agent" 和 module_path）

  ③ 确保 agent 具备 workflow agent 的标准接口
     - send_message(query) 方法
     - 能理解 VTS/SSTS 映射、校核、优化等通用任务描述

  ④ 运行时 step1 DETECT_CATEGORIES 会自动：
     - get_vts_categories 检测到"底盘"专业
     - list_all_sub_agents 发现新 agent
     - LLM 自动为"底盘"专业分配合适的 workflow/expert agent
     - 后续 loop 自动遍历执行

  ★ 以上步骤中，没有任何一步需要修改 a101_target_definition_agent 的
    代码或 YAML 配置。扩展完全通过数据驱动。


────────────────────────────────────────────────────────────────────────────────
2.8 当前唯一的"半固定"项
────────────────────────────────────────────────────────────────────────────────

step2_5 VALIDATE_SSTS 使用 fix 类型 agent_id: "vts_ssts_agent"。
  但这是通用的 VTS 校核 agent——它不做领域计算，只做：
    ① 运行 VTS 计算公式仿真
    ② 检查每个 VTS 的 current 是否 <= target（或 >= 视判断方向）
    ③ 输出 status: "pass"/"fail" + failed_VTS_items 列表

  所有专业共用同一个 vts_ssts_agent 完全合理，
  因为 VTS 校核的逻辑是通用的（仿真 + 比较），与领域无关。

  如果未来出现"需要不同校核策略"的专业（如碰撞安全需要特殊的
  有限元校核流程），可以把 step2_5 从 fix 改为 calculator 类型，
  让 LLM 为不同专业分配不同的校核 agent。但当前 3 个专业
  都是标准 VTS 校核，fix 类型够用。


二、数据结构约定
--------------------------------------------------------------------------------

1. DB Memory（内存数据库，持久化到 memorycore JSON）
   - 表 "target_ssts_{vehicle_suffix}"：存储 SSTS 目标值
     结构: {车型key: {target_ssts及计算条件_memorycore: {"SSTS": [...], "计算条件": [...]}}}
     注意：此表顶层按参数类型（SSTS/VTS）分节，不是按专业分节
   - 表 "target_vts_{vehicle_suffix}"：存储 VTS 目标值（与 SSTS 分开的独立表）
     结构: {车型key: {target_vts_memorycore: {"空气动力学": [...], "动力性": [...], "经济性": [...]}}}
     注意：此表顶层按专业分节
   - 两张表的每个参数项都是统一结构：
     {name, 单位, 参数值: [{名称: "目标值"|"当前值"|"达标标识", db_key, 值}]}

2. db_key 命名约定
   - xxx_target_{suffix}：目标值键（如 cd_style_target_reevlto）
   - xxx_result_{suffix}：当前/计算值键（如 cd_style_result_reevlto）
   - xxx_pass_{suffix}  ：达标标识键（值为 0/1）
   - xxx 无后缀         ：基础名（LLM 常输出基础名，需要代码补全后缀）

3. Sandbox process_data — vts_category_data 嵌套结构
   {
     "专业名": {
       "二级专业名": {
         "VTS_items": [
           {
             "name": "...", "unit": "...", "confidence": "...", "basis": "...",
             "param_values": [  ★ db_key 嵌套在 param_values 数组里！
               {"db_key": "xxx_target_{suffix}", "value": None}
             ]
           }
         ],
         "SSTS_parameter": [  ★ db_key 在顶层（与 VTS 不同）
           {"name": "...", "unit": "...", "db_key": "xxx", "value": None}
         ],
         "计算公式": "xxx = a + b"
       }
     }
   }

4. process_data — category_mapping（步骤1 DETECT_CATEGORIES 生成）
   {
     "sub_category_index": {"加速时间": "加速时间", ...},  # 精确匹配索引
     "category_mapping": {
       "动力性": {"加速时间": "加速时间", "最高车速": "最高车速", ...},
       ...
     }
   }
   用于 step2_2 save_to_process_data 的二级专业名标准化（向量相似度匹配）


三、流程步骤编排（process.yaml）
--------------------------------------------------------------------------------

顶层步骤：INIT → DETECT_CATEGORIES
  然后进入 loop_categories 循环（3 个专业依次执行）：

  loop 内顺序：
    ANALYZE_PRODUCT  (step2_1)   ← llm 类型，读取产品定义
    DETERMINE_MAPPING(step2_2)   ← agent 类型，调用 workflow agent 分析计算节点
    CHECK_REGULATIONS_AND_REFERENCES (step2_3) ← agent 类型，pipeline 模式
    DEFINE_INITIAL   (step2_4)   ← llm 类型，LLM 推理设定初版目标值
    VALIDATE_SSTS    (step2_5)   ← agent 类型，vts_ssts_agent 校核达标

    CHECK_VALIDATION (条件节点):
      status=pass → SUMMARIZE_CATEGORY → 下一个专业
      status=fail → OPTIMIZE_SSTS → SUMMARIZE_CATEGORY → 下一个专业

顶层收尾：FINAL_SUMMARY (step3) ← llm 类型

关键设计：step2_6 OPTIMIZE_SSTS 是条件执行的——只有 CHECK_VALIDATION 判定 fail
时才运行。如果 3 个专业全部一次通过，step2_6 整轮都不会执行。


四、各 Step 详细执行逻辑（含隐含兜底逻辑）
================================================================================

────────────────────────────────────────────────────────────────────────────────
Step 1: DETECT_CATEGORIES（检测专业）
────────────────────────────────────────────────────────────────────────────────

type: llm
config_file: step1_detect_categories_llm.yaml

功能：LLM 从 VTS 首层分类中识别需要执行的专业列表和排序。
输出结构化数据：{categories: ["空气动力学", "动力性", "经济性"], ...}

隐含逻辑：
  - 生成的 categories 列表决定 loop_categories 的循环次数和顺序
  - 专业排序很重要：先执行的专业会先写 DB，后续专业的 step2_4 会读取
    已定义的 SSTS（避免重复定义）


────────────────────────────────────────────────────────────────────────────────
Step 2.1: ANALYZE_PRODUCT（分析产品定义）
────────────────────────────────────────────────────────────────────────────────

type: llm
config_file: step2_1_analyze_product_llm.yaml

功能：LLM 读取产品定义信息，提取当前专业相关内容。

隐含逻辑：
  - 无复杂 post_process，LLM 输出直接存入 step_results
  - 下游 step2_4 通过 step2_4_extract_data 从 step_results 读取产品信息


────────────────────────────────────────────────────────────────────────────────
Step 2.2: DETERMINE_MAPPING（确定 VTS/SSTS 映射关系）  ★关键步骤
────────────────────────────────────────────────────────────────────────────────

type: agent（调用 workflow agent）
config_file: step2_2_determine_mapping_agent.yaml

data_sources:
  step2_2_format_vts_data → 从 process_data.vts_category_data 读取当前专业的
    VTS 指标列表，格式化为带编号、带 db_key 的可读文本（vts_text）

task_prompt 核心约束：
  1. LLM 分析计算节点，递归展开中间变量依赖链
  2. SSTS 去重规则：直接对应公式（如 vts=ssts）时，SSTS_parameter 必须为 []
  3. SSTS db_key 必须带 _target_{suffix} 后缀（与 VTS param_values 一致）
  4. 二级专业名必须与 VTS 列表中的分组名逐字符一致，禁止加装饰符

post_process 执行链（按顺序）：

  ① db_schema_sync（通用公共函数，pubfn_db_schema_sync.py）
    功能：从 DB target_ssts + target_vts 两张表构建权威参数字典，
          递归修正 LLM 输出中的 db_key / name / unit
    隐含兜底逻辑：
    - db_key 后缀补全：LLM 输出基础名（如 cd_style）时，
      先查 base_to_full 字典（从 DB 构建），找不到再尝试遍历所有车型后缀
      生成 {base}_target_{suffix} / {base}_result_{suffix} 试匹配
    - name 覆盖：DB 有权威中文名则覆盖 LLM 自编名称
    - unit 覆盖：DB 有权威单位且 LLM 没提供时补全
    - remove_unknown=True：DB 中完全不存在的幻觉 db_key 参数项直接删除
    - write_back=True：同步覆盖 sandbox step_results，确保下游读到修正后的数据

  ② save_to_process_data（私有函数，a101_step2_2_save_process_data.py）
    功能：将修正后的 sub_category 合并回 process_data.vts_category_data
    隐含兜底逻辑：
    - 二级专业名两阶段标准化：
        Stage 1: 精确匹配 category_mapping 索引
        Stage 2: 向量余弦相似度匹配（阈值 0.7）
        → 两阶段都失败时严格抛异常，不做猜测性修复
    - SSTS 重复 db_key 过滤（L268-307）：
        a) SSTS db_key == VTS db_key（完全相同）→ 删除
        b) SSTS db_key == VTS 基础名（补后缀后会相同）→ 删除
    - SSTS 后缀补全（L298-306）：
        如果 db_key 不含 _target_ / _result_，从同组 VTS 的 db_key 中
        提取 vehicle_suffix（如 "reevlto"），自动补为 {base}_target_{suffix}
        这是 LLM 输出不规范时的最后一道防线
    - VTS_items 回填：使用 PubfnSstsValidator.match_db_key 做模糊匹配
      （兼容不同后缀），回填 name/unit 等信息


────────────────────────────────────────────────────────────────────────────────
Step 2.3: CHECK_REGULATIONS_AND_REFERENCES（获取法规与参考数据）
────────────────────────────────────────────────────────────────────────────────

type: agent（query_mode: pipeline）
config_file: step2_3_check_regulations_agent.yaml

功能：调用 expert agent 获取法规要求、对标数据、参考值等。

隐含逻辑：
  - pipeline 模式：可能调用多个 expert agent 并行收集不同来源的数据
  - 结果存入 step_results，下游 step2_4 通过 step2_4_extract_data 读取


────────────────────────────────────────────────────────────────────────────────
Step 2.4: DEFINE_INITIAL（定义初版目标值） ★核心步骤
────────────────────────────────────────────────────────────────────────────────

type: llm（stage1_enabled=false，仅 stage2 JSON 输出）
config_file: step2_4_define_initial_llm.yaml

stage1 关闭原因：
  calculator 只能做简单数学运算，无法执行车辆动力学公式；
  且 LLM 容易循环调用 calculator 耗时十几分钟。
  step2_4 的本质是"基于行业经验/法规/参考数据拍合理值"，不需要 tool call。

data_sources 执行顺序：
  ① step2_4_extract_data(product_info) → step2_1 的产品信息
  ② step2_4_extract_data(get_filtered_mappings) → ★关键过滤
     设计意图：同一个 SSTS 可能被多个专业共享。如果前置专业（如空气动力学）
     的 step2_4 已定义了某 SSTS 的值（DB 有 target value），
     本步骤（如动力性）就不让 LLM 重复定义——过滤掉已定义的 SSTS，
     只展示未定义的。mappings_json 里会有"已定义SSTS参考"文本块。
  ③ step2_4_extract_data(get_defined_ssts_db) → DB 中已定义的 SSTS 字典
     供 post_process 使用：validate 用它排除 baseline，save 用它回填沙箱
  ④ step2_4_extract_data(get_references) → step2_3 的法规参考数据

task_prompt 核心约束：
  - SSTS 去重：同一 db_key 只在第一次出现的二级专业输出，后续 []
  - 已定义 SSTS：不展示给 LLM，prompt 里明确说明"已在参考中列出"
  - LLM 输出 value 必须填数字（不能 null）

post_process 执行链（按顺序）：

  ① db_schema_sync
     - 与 step2_2 相同的通用修正逻辑
     - remove_unknown=True, write_back=True

  ② step2_4_validate_targets（a101_step2_4_validate_targets.py）
    功能：以 process_data 为基准，验证 LLM 输出
    核心规则：
    - baseline_db_keys 排除 defined_ssts_db 中的 SSTS——这些已由前置专业
      定义，不应算作"缺失"
    - VTS db_key 不排除——VTS 总是需要验证
    - 验证动作：只删除幻觉（db_key 不在 baseline 中），不补充缺失
      ★ 这是刻意设计：之前的 validate 补 None 占位会触发 revise 卡死
      现在 validate 纯粹做"删幻觉"，missing_count 永远为 0
    - SSTS_parameter 验证：只保留在 baseline 里的，DB 找不到的算幻觉

  ③ step2_4_revise_if_needed（a101_step2_4_revise_if_needed.py）
    功能：条件性修订缺失参数
    隐含逻辑：
    - 先调用 _find_missing_params 检查有没有 value=None 的参数
    - 如果 missing_params 为空 → 直接返回 targets（跳过 LLM 调用）
      ★ 这是 validate 不补 None 的直接受益者——missing=0 时 revise 自动跳过
    - 如果有缺失 → 调用 llm_error_revision 工具进行迭代修订
      （step_a_prompt 列出缺失，step_b_prompt 定义验收标准）

  ④ step2_4_save_targets（a101_step2_4_save_targets.py）
    功能：回填沙箱 + 写入 DB
    隐含兜底逻辑：
    - 沙箱回填分两路：
      a) VTS 级别：按 db_key 匹配 param_values，回填 value/confidence/basis
      b) SSTS 级别：遍历 process_data 全量 SSTS_parameter（含已定义的）
         → defined_keys 里有的 db_key：用 DB 值覆盖（来自前置专业 step2_4）
         → 其他 db_key：找 LLM 输出值回填
         这样 process_data 里所有 SSTS（不管哪个专业定义的）都有值
    - DB 写入策略：已有非空有效值的 db_key 跳过（_has_existing_value）
      NaN 视为空值，允许覆盖
    - llm_ssts_by_key 扁平索引天然支持去重：
      同一 db_key 多次出现时，最后一次写入生效


────────────────────────────────────────────────────────────────────────────────
Step 2.5: VALIDATE_SSTS（SSTS 数值合理性校核）
────────────────────────────────────────────────────────────────────────────────

type: agent（agent_id: vts_ssts_agent，fix 类型）
config_file: step2_5_validate_targets_agent.yaml

data_sources 执行顺序（★严格先后依赖）：
  ① vts_calc(copy_target_to_current) → ★关键前置
     功能：将 DB 中所有 _target_ 值复制为 _result_ 值
     原因：step2_4 只写了 target 值，VTS 校核计算需要读 result 值
     隐含兜底逻辑（301_pubfn_vts_calc.py L200-325）：
     - 从 sandbox 收集 db_key：
       a) SSTS_parameter 顶层 db_key
       b) VTS_items 的 param_values 嵌套 db_key（之前代码只读顶层，已修复）
     - 同时读两张 DB 表：
       target_ssts 表（顶层按"SSTS"/"VTS"分节）
       target_vts 表（顶层按专业名分节）
       之前只读 target_ssts，VTS target 值复制失败——已修复
     - 不再按 cat1 名称过滤：以前过滤掉 "VTS" 节和专业名节，
       现在两种都处理
     - db_key 后缀替换：_target_ → _result_，写入同一 db_key
  ② step2_5_extract_data(extract_vts_params) → 提取 VTS 参数列表文本

Agent 调用：
  vts_ssts_agent.get_category_pass_status(category=专业名, vehicle_name=车型名)
  agent 执行 VTS 计算公式仿真，检查每个 VTS 是否达标

post_process：
  step2_5_parse_result(read_status_from_result) → 透传 structured_data.status

条件节点 CHECK_VALIDATION 读取 status：
  status=pass → 跳过 step2_6，直接 SUMMARIZE_CATEGORY
  status=fail → 进入 step2_6 优化


────────────────────────────────────────────────────────────────────────────────
Step 2.6: OPTIMIZE_SSTS（优化 SSTS 参数）
────────────────────────────────────────────────────────────────────────────────

type: agent（agent_type: calculator → 动态获取 workflow agent）
config_file: step2_6_optimize_ssts_agent.yaml

data_sources：
  ① step2_6_extract_data(format_vts_ssts_list) → VTS+SSTS 参数清单
  ② step2_6_extract_data(extract_validate_result) → step2_5 校核结果文本

Agent 工作：
  调用 economy_agent / power_agent 执行 SSTS 参数值修改，
  然后运行 VTS 计算验证是否达标。

task_prompt 工具调用规则：
  - db_key 后缀转换：工具调用时 target→result
  - var_name 取基础名（去掉后缀部分）

post_process：
  step2_6_update_targets(update_optimized_targets)
  隐含兜底逻辑（a101_step2_6_update_targets.py）：
  - result/target 双写：LLM 输出的 db_key 不管带哪种后缀，
    都同时生成 _target_ 和 _result_ 两个 db_key 写入 DB
    （因为 step2_6 判定参数值需要修改，目标值和当前值都要同步）
  - 沙箱回填用基础名匹配：_update_process_data 按 ssts_base_value_map
    （{基础db_key: optimized_value}）匹配 process_data 中的 SSTS_parameter
    （SSTS_parameter 的 db_key 是带后缀的完整 key，但代码做了精确匹配）


────────────────────────────────────────────────────────────────────────────────
Step 2.7: SUMMARIZE_CATEGORY（专业总结）
────────────────────────────────────────────────────────────────────────────────

type: llm
config_file: step2_7_summarize_category_llm.yaml

功能：LLM 总结当前专业的目标值设定过程、关键决策、风险评估。

data_sources：
  step2_7_get_reasoning_logics → 收集 step2_2~step2_6 的 reasoning_logic 汇总

post_process：直接存入 step_results，供 step3 汇总。


────────────────────────────────────────────────────────────────────────────────
Step 3: FINAL_SUMMARY（整体总结）
────────────────────────────────────────────────────────────────────────────────

type: llm
config_file: step3_final_summary_llm.yaml

功能：LLM 汇总所有专业的总结，生成完整的目标值定义报告。


五、公共函数一览表
--------------------------------------------------------------------------------

| 函数名                   | 所在文件                          | 调用位置         |
|------------------------|-----------------------------------|------------------|
| db_schema_sync         | pubfn_db_schema_sync.py           | step2_2/step2_4  |
| save_to_process_data   | a101_step2_2_save_process_data.py | step2_2          |
| step2_2_format_vts_data| a101_step2_2_format_vts_data.py   | step2_2          |
| step2_4_extract_data   | a101_step2_4_extract_data.py      | step2_4          |
| step2_4_validate_targets| a101_step2_4_validate_targets.py  | step2_4          |
| step2_4_revise_if_needed| a101_step2_4_revise_if_needed.py  | step2_4          |
| step2_4_save_targets   | a101_step2_4_save_targets.py      | step2_4          |
| vts_calc               | 301_pubfn_vts_calc.py             | step2_5          |
| step2_5_extract_data   | a101_step2_5_extract_data.py      | step2_5          |
| step2_5_parse_result   | a101_step2_5_parse_result.py      | step2_5          |
| step2_6_extract_data   | a101_step2_6_extract_data.py      | step2_6          |
| step2_6_update_targets | a101_step2_6_update_targets.py    | step2_6          |


六、关键设计决策记录
--------------------------------------------------------------------------------

1. prompt 第一，代码第二
   YAML prompt 是 LLM 与系统之间的主合同。代码兜底逻辑只做第二道防线，
   不做猜测性修复。例如二级专业名匹配失败时严格抛异常，不强行猜测。

2. stage1 关闭（step2_4）
   step2_4 是"拍值"而非"算值"。calculator 只能做数学运算，
   LLM 调用它只会浪费时间。关闭 stage1 后 max_new_tokens 设 20000。

3. step2_6 task_prompt 是单一 task_prompt 字段
   agent_step.py 只注入 {task_prompt} 变量，YAML 里不能拆成 task_prompt_core/
   task_prompt_output 等——会导致 str.format 抛 KeyError，返回原始模板。

4. validate 不补 None
   之前 validate 补 None 占位 → revise 条件满足 → 触发 LLM 修订 → 卡死。
   现在 validate 只删幻觉，missing_count 永远为 0 → revise 自动跳过。

5. SSTS 去重的两层防线
   a) prompt 约束：LLM 在后续 sub_category 输出 []
   b) 代码过滤：save_to_process_data 检查 db_key==VTS db_key 或基础名，
      自动删除重复项

6. copy_target_to_current 必须同时读两张表
   target_vts 表存 VTS 目标值，target_ssts 表存 SSTS 目标值，
   之前只读 target_ssts 导致 VTS result 值全是 None。

7. step2_6 双写策略
   优化值同时写 _target_（目标值）和 _result_（当前值）后缀，
   因为 step2_6 修改的是"设计目标"，不只是"当前计算值"。


七、数据库双表设计
--------------------------------------------------------------------------------

历史原因：VTS 和 SSTS 参数的 db_key 体系类似但实际分属两张独立表。

target_ssts 表结构：
  顶层按参数类型（"SSTS"、"VTS"）分节 → 每个节下是该类型所有参数的扁平列表
  例：memorycore["target_ssts及计算条件_memorycore"]["SSTS"] = [{...}, ...]

target_vts 表结构：
  顶层按专业名分节 → 每个节下是该专业所有 VTS 参数的扁平列表
  例：memorycore["target_vts_memorycore"]["空气动力学"] = [{...}, ...]

读取时需要同时查两张表，不能假设所有目标值都在同一张表。


八、常见问题排查指引
--------------------------------------------------------------------------------

| 现象                                   | 排查方向                                      |
|----------------------------------------|-----------------------------------------------|
| 二级专业名匹配失败（NameError/ValueError）| step2_2 prompt 是否有装饰符；category_mapping 是否完整 |
| SSTS db_key 无 _target_ 后缀           | db_schema_sync 补全逻辑是否生效；save_to_process_data 后缀兜底 |
| VTS result 值全是 None                  | copy_target_to_current 是否读了两张表；VTS_items param_values 嵌套 db_key 是否被收集 |
| validate hallucination_count 很高      | LLM 输出的 db_key 是否真的在 DB schema 中存在 |
| revise 循环卡死                         | validate 是否意外补了 None；revise missing_count 是否非零 |
| step2_6 不执行                         | CHECK_VALIDATION 的 status 是否一直是 pass     |
| step2_6 优化值没写入 DB                | 双写 target+result 是否都生效                  |
| 经济性 SSTS_parameter 为空              | step2_2 save_to_process_data 合并是否成功；后缀补全是否执行 |
