# Snail Avatar 模型调用现状

> 更新时间: 2026-10-13 (路由模型 flash→plus 切换 + 类别识别框架引入)
> 百炼官方模型文档: https://help.aliyun.com/zh/model-studio/text-generation-model/

---

## 一、当前系统模型调用清单

| # | 模型名 | 定位 | 百炼状态 | 用途 |
|---|--------|------|---------|------|
| 1 | `qwen3.5-plus` | **主力模型** | 旧版可用 | Agent 主对话、流程步骤执行、错误修订、**路由决策(2026-10-13 接入)**、Agent LLM 兜底常量 |
| 2 | `qwen3.5-flash` | **轻量模型** | 旧版可用 | 对话摘要、结果格式化、Python 兜底常量（路由决策曾用，2026-10-13 切换至 plus，见坑 6） |
| 3 | `qwen3-vl-embedding` | Embedding | 存在(多模态 Embedding 推荐) | 空气动力学/PE 专家知识库向量检索 |

### 分层映射

| 任务层级 | 模型 | 涉及 Agent / 模块 |
|---------|------|-----------------|
| Agent 主对话 (重任务) | qwen3.5-plus | main_agent + 6 个专家 Agent (target_definition / aero_expert / PE_expert / VTS_SSTS / economy / power) |
| 流程步骤执行 | qwen3.5-plus | ProcessLLMStep 默认 + target_definition 两个 step YAML |
| 错误修订 | qwen3.5-plus | llm_error_revision |
| 结果格式化 | qwen3.5-flash | result_formatter |
| 对话摘要 | qwen3.5-flash | 所有 Agent 的 summary_config + conversation_summarizer 默认值 |
| 路由决策 | qwen3.5-plus | llm_router（2026-10-13 从 flash 切换，见坑 6） |
| Embedding | qwen3-vl-embedding | aero_expert_agent / pe_expert_agent |

---

## 二、API 架构

| 维度 | 值 |
|------|------|
| SDK | dashscope 1.27.7 |
| **调用方式** | **OpenAI 兼容端点 (requests.post)** |
| **端点** | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` |
| **迁移前** | `dashscope.Generation.call()` (旧 Generation API) |
| **迁移原因** | 旧 Generation API 只支持 qwen-plus / qwen-flash,**不支持 qwen3.5 系列**(返回 400 url error) |

### deploy.py 参数映射

| 当前参数 | 兼容端点 payload 字段 | 备注 |
|---------|---------------------|------|
| model_name | model | 直接传递 |
| messages (system + 历史) | messages | 直接传递 |
| max_new_tokens | max_tokens | 直接传递 |
| temperature / top_p / presence_penalty | 同名字段 | 直接传递 |
| tools (function definitions) | tools | 格式本身兼容 |
| output_format=json | response_format: {"type":"json_object"} | 条件加入 |
| result_format | (已删除) | 旧 Generation API 专属 |
| extra_body | (已拍平) | 嵌套会被端点忽略 |
| stream | 顶层 bool | requests.post(stream=True) 控制 |
| **enable_thinking** | **顶层 False (硬编码)** | **见下方深度思考章节** |

### usage 字段映射 (兼容端点 → 下游旧格式)

| 兼容端点字段 | 下游旧字段 |
|-------------|-----------|
| prompt_tokens | input_tokens |
| completion_tokens | output_tokens |
| total_tokens | total_tokens |

---

## 三、深度思考配置

### 代码层面 (deploy.py _build_api_params)

```python
payload = {
    ...
    "enable_thinking": False,   # 全局统一关闭,拍平到顶层
}
```

**硬编码关闭,所有模型所有 Agent 一视同仁。** 当前 YAML config 中没有任何 thinking 相关字段,代码也不支持按 Agent 差异化覆盖。

### 为什么关闭

| 维度 | enable_thinking=True | enable_thinking=False |
|------|---------------------|----------------------|
| 路由器 JSON 输出 | 4000+ reasoning tokens,30s 超时 → 路由 fallback 走错 | 2~3s 正常返回 |
| FC 工具选择 | 20~30s | 2~3s |
| 成本 | reasoning_tokens 白付(输出价格翻倍以上) | 只有可见输出计费 |
| 响应可见输出 vs reasoning | 1% / 99% | 100% |

### 模型差异

| 模型 | 收到 enable_thinking=False | 实际行为 |
|------|---------------------------|---------|
| qwen3.5-plus | ✅ 生效 | 深度思考关闭,可能仍有 ~5% 隐式轻思考 |
| qwen3.5-flash | ✅ 生效 | 同上 |
| qwen-plus (旧版,如果有残留) | ⚠️ 可能不识别 | 旧 Generation API 本就不支持思考模式,参数被忽略,本来就是普通推理 |

### 隐式轻思考

qwen3.5-plus / qwen3.5-flash 即使 enable_thinking=False,usage 里仍可能带少量 reasoning_tokens (~total 的 5-10%)。这是模型架构自带的隐式推理,不是深度思考模式,量很小,不影响速度和成本。

### 未来如需某些 Agent 开启深度思考

当前 deploy.py 注释已预留扩展点,实现方向:

```python
# YAML 里加 thinking_enabled: true 时才开启
if config.get("thinking_enabled", False):
    payload["enable_thinking"] = True
```

按当前策略保持全系统关闭是合理的——Agent 场景追求稳定 FC + 快速响应,不是深度推理的文字质量。

---

## 四、已下线 / 不再使用的模型

| 模型 | 原用途 | 状态 |
|------|--------|------|
| qwen3-max | 原主力 (Agent 主 + 流程 + 修订) | 百炼文档中无此模型 ID,**已下线** |
| qwen-plus (旧版 Generation API 用法) | 旧 Generation API 兼容模型 | 百炼旧版仍可用,但**旧端点已废弃**,改用兼容端点后不受影响 |
| qwen-flash (旧版 Generation API 用法) | 旧 Generation API 兼容模型 | 同上 |
| qwen3-8b | result_formatter.py 兜底常量 | 被 YAML 覆盖,从未生效 |

---

## 五、配置速查

### Agent llm_config.model_name (主力)

main_agent + 6 个专家 Agent: **qwen3.5-plus**

### 各 Agent summary_config.llm_config.model_name (摘要)

所有 Agent 摘要 + router: **qwen3.5-flash**

### 路由决策 router.llm_config.model_name

**qwen3.5-plus**（2026-10-13 从 flash 切换，见坑 6）

### result_formatter.model_name

**qwen3.5-flash**

### llm_error_revision.model_name

**qwen3.5-plus** (Python 兜底 `LLM_DEFAULT = "qwen3.5-plus"`)

### ProcessLLMStep 默认

**qwen3.5-plus**

### Deploy 层 LLMDeploy 默认值

`LLMDeploy.__init__` 默认 model_name: **qwen3.5-plus**

---

## 六、迁移过程中踩过的坑(备忘)

### 坑 1: extra_body 嵌套 enable_thinking 被端点忽略
- 现象: 迁移到兼容端点后所有 LLM 调用极慢(40s+),路由器 30s 超时
- 根因: `{"extra_body": {"enable_thinking": False}}` —— OpenAI Python SDK 会自动拍平,但 requests.post 直接发会把 extra_body 当普通顶层字段,端点不认识这个 key
- 修复: 直接 `"enable_thinking": False` 拍平到 payload 顶层

### 坑 2: AgentMessageLogger queue 跨对话残留
- 现象: 前端第二次对话没有最终气泡,日志里 done (client disconnected)
- 根因: `chat_service.py` 的 SSE 生成器在第二次对话开头 drain 出残留的上一次 `agent_response` + `done` 事件 → 前端收到残留 done 后立即 disconnect() 掐断 SSE → 真正的 final 事件到不了前端
- 修复: 每次 chat_stream 请求进来先排干 `start_size` 条残留旧消息

### 坑 3: FastAPI lint 移除 debug print 时 try/except 缩进损坏
- 现象: 服务启动阶段 SyntaxError,import chat_service.py 失败
- 根因: 清理 debug print 时 final+done 块从 try 块内 8 空格缩进掉到 0 空格,Python 语法错误
- 修复: 恢复正确缩进

### 坑 4: /api/chat/info 端点依赖旧 agent.llm 属性
- 现象: 前端状态栏永远显示"加载中..."
- 根因: 端点靠运行时反射 `main_agent.llm.model_name`,但 deploy.py 重构后 LLM 实例统一收敛在 `deploy._llm_instances` 字典里,main_agent 没有 `.llm` 属性
- 修复: 直接从 `deploy._llm_instances.get("main_agent")` 取 LLMDeploy 实例的 model_name,加 fallback `"qwen3.5-plus"`

### 坑 5: 前端两套执行过程时间线重复
- 现象: AI 回复气泡上方和下方各显示一份相同的执行过程;下次对话开始后下方那份消失
- 根因: `ChatPanel.vue` 同时渲染 bubble.events (气泡快照) 和 store.events (全局累积),final 到达时 store.events 还没清空(要等下次 sendMessage),瞬间重复
- 修复: 给全局时间线加 `v-if="store.isLoading && store.events.length > 0"` —— 执行中显示,final 后气泡自己的 snapshot 永远显示,下次对话 sendMessage 清 store.events

### 坑 6: 路由器 LLM 模型推理能力不足导致路由错误 (路由 flash → plus)
- 现象:
  - 用户输入 "请提供增程车型的**能耗**法规信息",路由器应选 `pe_expert_agent`(动力经济性领域)
  - 实际被错误路由到 `aero_expert_agent`(空气动力学领域)
  - LLM reason 编了幻觉: "匹配空气动力学专家知识库"——用户根本没提空气动力学相关关键词
  - 同类问题复现: 用户三次明确说"请 PE 专家",flash 模型仍因延续性锁死错误 agent
- 根因(当前最可能的解释,待进一步验证):
  - qwen3.5-flash 模型能完成**粗粒度分类**("法规" → 专家知识检索类),但在**多步精细推理**(类别内多个 agent 逐一对照 routing_keywords 做匹配)时执行不可靠
  - flash 倾向于走捷径:看到类别内多个 agent 后,直接选排列靠前的选项,跳过逐一关键词对照,还会编幻觉理由
  - prompt 信息本身是充分的:agent_inventory 里包含了每个 agent 的完整 routing_keywords,类别识别框架也明确了"动力经济性领域" vs "空气动力学领域"——flash 模型没有严格利用这些信息
  - 一个待验证的假设:flash 是蒸馏/轻量模型,在需要"将用户输入字符串在多个候选关键词列表里逐个查匹配"的操作上,不如plus 模型稳定
- 修复:
  - router.yaml 的 model_name 从 `qwen3.5-flash` 改为 `qwen3.5-plus`
  - 同时引入了 router.yaml 的类别识别框架 + agent_nicknames 配置(在 flash→plus 切换的同一次迭代中完成)
  - 修复后立即验证正确:相同用户输入,plus 模型正确选 pe_expert_agent,reason 真实反映推理过程
- TODO: ⚠️ 路由成本优化的可能性
  - plus 比 flash 贵,路由 token 成本虽低但长期有差距
  - 后续可以考虑:是否能通过更精简的 prompt / 更聚焦的规则 / 纯规则路由 fallback 优化,让 flash 模型在简化场景下也能可靠工作
  - 建议在积累更多路由案例后系统性评估:plus 路由的准确率 vs flash 路由 + 更强规则 fallback 的成本收益比

---

## 七、百炼官方同类模型速查(2026-10-11)

| 模型ID | 代际 | 上下文 | 思考 | FC | 视觉 | 定位 |
|--------|------|--------|------|-----|------|------|
| `qwen3.8-max` | 最新旗舰 | 1M | ✓ | ✓ | 是 | 最强推理 |
| `qwen3.7-plus` | 最新主力平衡 | 1M | ✓ | ✓ | 否 | 能力成本均衡 |
| `qwen3.7-flash` | 最新主力轻量 | 1M | ✓ | ✓ | 否 | 低成本,接近旗舰 |
| `qwen3.5-plus` | 旧版(当前主力) | 1M | ✓ | ✓ | 否 | 仍可用,稳定 |
| `qwen3.5-flash` | 旧版(当前轻量) | 1M | ✓ | ✓ | 是 | 全场景通用 |
| `qwen-plus` | 最老版 | 1M | ✓ | ✓ | 否 | Generation API 遗留 |
| `qwen-flash` | 最老版 | 1M | ✓ | ✓ | 否 | Generation API 遗留 |

注:当前使用的 qwen3.5-plus / qwen3.5-flash 在百炼上归类为"旧版 Qwen3.5 系列",兼容端点 `/compatible-mode/v1/chat/completions` 同时兼容旧版和新版所有模型 ID。
