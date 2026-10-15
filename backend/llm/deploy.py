# @Time    : 2026
# @Author  : 李涛
# @File    : deploy.py
# @Desc    : LLM部署与管理
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""LLM 部署模块

此模块用于初始化和获取 LLM 实例，提供与 LLM 交互的接口。
基于阿里云百炼 OpenAI 兼容端点 (compatible-mode/v1/chat/completions) 实现大模型调用。

架构结构（三模块拆分，单一职责）：
    APIKeyProvider  - 负责从环境变量 / config.ini 获取 API Key
    LLMEnvironment  - 负责检查依赖包、验证 API Key、保存 api_key 供 HTTP 认证使用
    LLMDeploy       - 负责调用 LLM 生成响应（普通 / 流式 / function calling）
                      通过 requests 直接 POST 到百炼 OpenAI 兼容端点
"""

import json as _json
import os
from typing import Optional, Any
import requests
from snail_avatar.backend.core.work_log import WorkLogger

_llm_instances = {}

# 百炼 OpenAI 兼容端点（华北2地域）
# 文档: https://help.aliyun.com/zh/model-studio/first-api-call-to-qwen
_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# =============================================================================
# APIKeyProvider - 凭证获取
# =============================================================================

class APIKeyProvider:
    """API Key 获取器

    按优先级尝试：
        1. 环境变量 DASHSCOPE_API_KEY
        2. 项目根目录 config.ini 的 [API] DASHSCOPE_API_KEY
    """

    def get_key(self) -> Optional[str]:
        """获取 API Key

        Returns:
            Optional[str]: 找到的 API Key；找不到返回 None
        """
        # 1. 环境变量优先
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            return api_key

        # 2. 从 snail_avatar 目录 config.ini 读取
        try:
            import configparser
            config = configparser.ConfigParser()
            # 往上走三级：backend/llm/deploy.py → backend/ → snail_avatar/
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(project_root, "config.ini")
            if config.read(config_path, encoding="utf-8"):
                if "API" in config and "DASHSCOPE_API_KEY" in config["API"]:
                    api_key = config["API"]["DASHSCOPE_API_KEY"]
                    WorkLogger.info("从配置文件读取 API Key 成功")
                    return api_key
        except Exception as e:
            WorkLogger.error(f"读取配置文件失败: {e}")

        return None


# =============================================================================
# LLMEnvironment - 环境检查 / 模型加载
# =============================================================================

class LLMEnvironment:
    """LLM 环境管理器

    职责：
        - 检查 API Key 是否可用
        - 维护 ready 状态，供 LLMDeploy 懒加载时调用
        - 保存 api_key 供 LLMDeploy 构造 HTTP 请求头使用

    注：百炼 LLM 调用已迁移到 OpenAI 兼容端点 /compatible-mode/v1/chat/completions，
    通过 HTTP POST + Authorization Bearer 认证，不再依赖 dashscope.Generation SDK。
    但 Embedding 仍使用 dashscope.MultiModalEmbedding，因此仍需设置 dashscope.api_key。
    """

    def __init__(self, agent_id: str, model_name: str):
        self.agent_id = agent_id
        self.model_name = model_name
        self.api_provider = APIKeyProvider()
        self.ready = False
        self.api_key: Optional[str] = None

    def ensure_ready(self) -> bool:
        """确保 LLM 环境可用（懒加载：已就绪则直接返回 True）

        Returns:
            bool: 环境是否可用
        """
        if self.ready:
            return True

        try:
            WorkLogger.info(f"正在检查阿里云百炼服务 [{self.agent_id}]...")
            api_key = self.api_provider.get_key()

            if not api_key:
                WorkLogger.error("错误: 未找到 DASHSCOPE_API_KEY")
                WorkLogger.error("请通过以下方式之一设置 API Key:")
                WorkLogger.error("  1. 环境变量: 设置 DASHSCOPE_API_KEY")
                WorkLogger.error("  2. 配置文件: 在项目根目录创建 config.ini，添加 [API] DASHSCOPE_API_KEY=xxx")
                return False

            # 设置 dashscope.api_key（Embedding 模块仍依赖此全局变量）
            import dashscope
            dashscope.api_key = api_key

            # 保存 API Key 给 LLMDeploy 构造 Authorization 头
            self.api_key = api_key
            self.ready = True
            WorkLogger.info(f"模型 {self.model_name} 环境就绪!")
            return True
        except ImportError:
            WorkLogger.error("错误: dashscope 包未安装，请执行 pip install dashscope")
            return False
        except Exception as e:
            WorkLogger.error(f"加载模型失败: {e}")
            return False


# =============================================================================
# _JSONRepairer - 截断 JSON 修复工具
# =============================================================================

class _JSONRepairer:
    """修复被截断的 JSON 文本（LLM 输出 Token 超限场景）

    策略：从后向前扫描，找到最后一个未闭合的容器（{} / [] / ""），
    逐层闭合它们，让 JSON 至少能被 json.loads 成功解析。

    假设：截断发生在 JSON 值的中间或末尾，不会破坏前半部分的结构。
    """

    @staticmethod
    def repair(text: str) -> Optional[str]:
        """尝试修复被截断的 JSON 文本

        修复策略（按优先级尝试）：
        1. 直接闭合：补全未闭合的 "、}、]
        2. 逐步截断 + 闭合：从末尾逐字符/逐容器截断，每次截断后重新扫描并闭合

        Args:
            text: 可能被截断的 JSON 子串

        Returns:
            修复后的字符串；无法修复返回 None
        """
        import json as _json

        if not text:
            return None

        # 策略 1: 直接闭合
        fixed = _JSONRepairer._try_close(text)
        if fixed is not None:
            try:
                _json.loads(fixed)
                return fixed
            except Exception:
                pass

        # 策略 2: 从后向前按容器边界截断 + 闭合
        # 每次截断到最后一个完整的 } 或 ] 或 "value", 然后闭合
        scan_pos = len(text)
        while scan_pos > 0:
            # 找上一个容器边界
            last_close = max(
                text.rfind('}', 0, scan_pos),
                text.rfind(']', 0, scan_pos)
            )
            if last_close <= 0:
                # 没有找到任何闭合容器，放弃
                break

            # 如果上一个字符是逗号，去掉它（避免末尾逗号）
            truncate_at = last_close + 1
            while truncate_at > 0 and text[truncate_at - 1] in (',', ':', ' ', '\n', '\t'):
                truncate_at -= 1
            if truncate_at <= 0:
                break

            candidate = text[:truncate_at]
            fixed = _JSONRepairer._try_close(candidate)
            if fixed is not None:
                try:
                    _json.loads(fixed)
                    return fixed
                except Exception:
                    pass

            scan_pos = truncate_at - 1

        # 策略 3: 从后向前按逗号位置截断
        # 去掉最后一个不完整的 key-value 对
        scan_pos = len(text)
        for _ in range(20):  # 最多尝试 20 次
            comma_pos = text.rfind(',', 0, scan_pos)
            if comma_pos <= 0:
                break
            # 确保逗号不在字符串内部（粗略判断：引号计数）
            before = text[:comma_pos]
            if before.count('"') % 2 == 0:
                # 逗号可能在字符串外，尝试截断
                candidate = before
                fixed = _JSONRepairer._try_close(candidate)
                if fixed is not None:
                    try:
                        _json.loads(fixed)
                        return fixed
                    except Exception:
                        pass
            scan_pos = comma_pos - 1

        return None

    @staticmethod
    def _try_close(text: str) -> Optional[str]:
        """扫描文本，补全未闭合的引号和容器

        假设截断点不会破坏已有闭合关系。
        """
        if not text:
            return None

        result = text
        stack = []          # 未闭合的容器栈 ('{' / '[')
        in_string = False
        escape_next = False

        i = 0
        while i < len(result):
            ch = result[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if ch == '\\' and in_string:
                escape_next = True
                i += 1
                continue

            if ch == '"':
                in_string = not in_string
                i += 1
                continue

            if in_string:
                i += 1
                continue

            if ch in '{[':
                stack.append(ch)
            elif ch in '}]':
                if stack and ((stack[-1] == '{' and ch == '}') or (stack[-1] == '[' and ch == ']')):
                    stack.pop()

            i += 1

        if not stack and not in_string:
            # 原本就是完整的 JSON
            return result

        # 先处理容器内部：如果末尾是 key 后跟 ':' 或未完成的 value，
        # 补 null 作为占位 value
        if stack:
            last_open = stack[-1]
            # 检查末尾是否有未闭合的 key: 值 结构
            stripped = result.rstrip()
            if stripped.endswith(':'):
                result = stripped + ' null'
            elif stripped.endswith(','):
                result = stripped[:-1]
            # 容器内如果只有一个 key 但没 value，也补 null
            elif stripped.rstrip('":').endswith('"') and not stripped.rstrip().endswith(('}', ']', 'null', 'true', 'false')):
                # 可能是 key 后紧跟的 value 被截断
                # 找到最后一个 ':' 的位置
                colon_pos = result.rfind(':')
                if colon_pos > 0:
                    # 检查是否在字符串外
                    before_colon = result[:colon_pos]
                    if before_colon.count('"') % 2 == 0:
                        result = result[:colon_pos + 1] + ' null'

        # 闭合字符串
        if in_string:
            result += '"'

        # 倒序闭合容器
        closing_map = {'{': '}', '[': ']'}
        for open_ch in reversed(stack):
            close_ch = closing_map[open_ch]
            result += close_ch

        return result


# =============================================================================
# LLMDeploy - LLM 响应生成（仅核心功能）
# =============================================================================

def initialize_llm(agent_id, system_prompt, config):
    """初始化 LLM 实例

    Args:
        agent_id: Agent 唯一标识
        system_prompt: 系统提示词
        config: LLM 配置参数

    Returns:
        bool: 初始化是否成功
    """
    try:
        llm = get_llm_instance(agent_id, system_prompt, config)
        return llm.env.ensure_ready()
    except Exception as e:
        WorkLogger.error(f"初始化 LLM 失败: {e}")
        return False


def get_llm_instance(agent_id, system_prompt, config):
    """获取 LLM 实例

    Args:
        agent_id: Agent 唯一标识
        system_prompt: 系统提示词
        config: LLM 配置参数

    Returns:
        LLMDeploy: LLM 实例
    """
    if agent_id not in _llm_instances:
        _llm_instances[agent_id] = LLMDeploy(agent_id, system_prompt, config)
    return _llm_instances[agent_id]


class LLMDeploy:
    """LLM 部署类 - 基于阿里云百炼 dashscope API

    （重构后：仅负责调用 LLM 生成响应；环境准备由 LLMEnvironment 处理；
    凭证获取由 APIKeyProvider 处理。）
    """

    def __init__(self, agent_id, system_prompt, config):
        """初始化 LLM 部署

        Args:
            agent_id: Agent 唯一标识
            system_prompt: 系统提示词
            config: 模型配置参数
        """
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.config = config
        # 以下 6 个 LLM 参数：优先从各 Agent 的 YAML 配置文件读取
        # （如 agents/00_main_agent/config/main_agent.yaml 中 llm_config 节）
        # YAML 中存在该 key 则使用 YAML 值；不存在则使用右侧的默认值兜底
        # 注意：YAML 中显式写为 null 时不会回退到默认值，将保持为 None
        self.model_name = config.get("model_name", "qwen3.5-plus")
        self.max_new_tokens = config.get("max_new_tokens", 64000)
        self.temperature = config.get("temperature", 0.7)
        self.top_p = config.get("top_p", 0.95)
        self.presence_penalty = config.get("presence_penalty", 1.5)
        self.context_window = config.get("context_window", 256000)
        self.output_format = config.get("output_format", "text")
        self.json_schema = config.get("json_schema", None)
        self.last_usage_info = {}

        # 环境检查 / 模型加载由 LLMEnvironment 负责
        self.env = LLMEnvironment(agent_id, self.model_name)

    def load_model(self) -> bool:
        """确保 LLM 环境就绪（检查 API Key 和 dashscope 依赖）

        语义上等价于 LLMEnvironment.ensure_ready()，返回 True 表示就绪。
        保留 load_model 方法名以兼容旧调用方的主动检查需求。
        不调用此方法时，generate_response() 会在内部懒加载环境。
        """
        return self.env.ensure_ready()

    def _build_messages(self, conversation_history) -> list:
        """构建发送给 LLM 的消息列表：system_prompt + 对话历史"""
        system_prompt = self.system_prompt
        if self.output_format == "json":
            if "json" not in system_prompt.lower():
                system_prompt += "\n\n请以 JSON 格式输出结果。"
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        return messages

    def _build_api_params(self, messages, tools, stream=False):
        """构造百炼 OpenAI 兼容端点的请求 payload

        参数映射（Generation API → 兼容端点）：
            model / messages / max_tokens / temperature / top_p / presence_penalty
              → 直接用，字段名一致
            result_format → 删除（兼容端点不需要）
            stream → 移到顶层 bool 字段
            response_format → 字段名和值一致，保留
            enable_thinking → 拍平到顶层（不能嵌套在 extra_body 里，
                              requests.post 会把 extra_body 当普通字段发，端点不认识）
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "presence_penalty": self.presence_penalty,
            "stream": bool(stream),
            # 统一关闭深度思考模式，避免 qwen3.5+ 系列默认启用导致成本翻倍
            # 后续如需启用，可按 Agent 单独在 config 中覆盖
            "enable_thinking": False,
        }
        if self.output_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
        return payload

    def _extract_usage(self, usage_obj) -> dict:
        """从兼容端点响应中提取 tokens 使用信息

        旧 Generation API 字段: input_tokens / output_tokens / total_tokens
        新兼容端点字段: prompt_tokens / completion_tokens / total_tokens + reasoning_tokens_details

        统一映射为旧字段名，保证下游调用方无需改动。
        """
        usage_info = {}
        if isinstance(usage_obj, dict):
            usage_info = {
                "input_tokens": usage_obj.get("prompt_tokens", 0),
                "output_tokens": usage_obj.get("completion_tokens", 0),
                "total_tokens": usage_obj.get("total_tokens", 0),
            }
        return usage_info

    def _extract_message_content(self, assistant_output: Any) -> str:
        """从 assistant_output 提取 content 文本（兼容 dict 和对象）"""
        if isinstance(assistant_output, dict):
            return assistant_output.get("content", "")
        return getattr(assistant_output, "content", "")

    def _extract_tool_calls(self, assistant_output: Any) -> Optional[list]:
        """从 assistant_output 提取 tool_calls（兼容 dict 和对象）"""
        if isinstance(assistant_output, dict):
            return assistant_output.get("tool_calls")
        return getattr(assistant_output, "tool_calls", None)

    @staticmethod
    def _parse_json_content(content: str) -> Any:
        """从 LLM 返回的文本中稳健地提取并解析 JSON

        处理的 LLM 输出变体：
        1. 纯 JSON 文本: {"key": "value"}
        2. Markdown 代码块包裹: ```json\n{...}\n``` 或 ```\n{...}\n```
        3. 前后夹杂解释文本: 根据 find('{') + rfind('}') 提取
        4. Python dict 格式（单引号）: {'key': 'value'}
        5. 轻微截断（末尾缺括号）: 尝试补全后再解析

        Args:
            content: LLM 返回的原始文本

        Returns:
            解析成功的 dict/list，失败返回 None
        """
        import json as _json
        import ast as _ast

        if not content or not isinstance(content, str):
            return None

        raw = content.strip()

        # 尝试 1: 直接 json.loads
        try:
            return _json.loads(raw)
        except Exception:
            pass

        # 尝试 2: 剥离 markdown 代码块
        # 匹配 ```json ... ``` 或 ``` ... ```
        import re
        md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL | re.IGNORECASE)
        if md_match:
            inner = md_match.group(1).strip()
            try:
                return _json.loads(inner)
            except Exception:
                raw = inner  # markdown 剥离后继续尝试其他方法

        # 尝试 3: 提取大括号 / 中括号包围的子串
        for open_ch, close_ch in [('{', '}'), ('[', ']')]:
            start = raw.find(open_ch)
            end = raw.rfind(close_ch)
            if start >= 0 and end > start:
                candidate = raw[start:end + 1]
                try:
                    return _json.loads(candidate)
                except Exception:
                    # 截断修复: 尝试逐层补全缺失的闭合符号
                    fixed = _JSONRepairer.repair(candidate)
                    if fixed is not None:
                        try:
                            return _json.loads(fixed)
                        except Exception:
                            pass

        # 尝试 4: Python dict 格式（单引号）
        try:
            return _ast.literal_eval(raw)
        except Exception:
            pass

        return None

    def generate_response(self, prompt, conversation_history, tools):
        """生成 LLM 响应（非流式，支持 function calling）

        通过 HTTP POST 调用百炼 OpenAI 兼容端点 /compatible-mode/v1/chat/completions。

        Args:
            prompt: 提示词（当前未使用，实际消息由 conversation_history 拼接而来）
            conversation_history: 对话历史（如 agent.conversation.get_history()）
            tools: 工具定义列表（function calling 使用）

        Returns:
            dict: 普通响应 -> {"content": str, "usage": dict}
                  工具调用 -> {"tool_call": {"id":..., "name":..., "arguments":...}, "usage": dict}
        """
        if not self.env.ensure_ready():
            return {"content": "错误: 模型加载失败，请检查 API Key 配置", "usage": {}}

        try:
            messages = self._build_messages(conversation_history)
            payload = self._build_api_params(messages, tools, stream=False)

            WorkLogger.info(f"[LLM] agent_id={self.agent_id}, model={self.model_name}")
            WorkLogger.info(f"[LLM] output_format={self.output_format}")

            if payload.get("response_format"):
                WorkLogger.info(f"[LLM] response_format={payload['response_format']}")

            headers = {
                "Authorization": f"Bearer {self.env.api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(
                f"{_COMPAT_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )

            if resp.status_code != 200:
                try:
                    err = resp.json()
                    err_msg = f"错误: 生成响应失败, HTTP {resp.status_code}, " \
                              f"error={err.get('error', {}).get('message', err)}"
                except Exception:
                    err_msg = f"错误: 生成响应失败, HTTP {resp.status_code}, body={resp.text[:300]}"
                WorkLogger.error(f"[LLM] 响应失败: {err_msg}")
                return {"content": err_msg, "usage": {}}

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]  # {"role":..., "content":..., "tool_calls":[...]}
            usage_info = self._extract_usage(data.get("usage", {}))

            # --- 检查是否为工具调用 ---
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                tool_call = tool_calls[0] if isinstance(tool_calls, list) else tool_calls

                tool_call_id = tool_call.get("id")
                func_dict = tool_call.get("function", {})
                function_name = func_dict.get("name")
                arguments_json = func_dict.get("arguments")

                # 确保 arguments 始终为字符串格式
                if arguments_json is None:
                    arguments_str = "{}"
                elif isinstance(arguments_json, str):
                    arguments_str = arguments_json
                elif isinstance(arguments_json, dict):
                    arguments_str = _json.dumps(arguments_json, ensure_ascii=False)
                else:
                    arguments_str = str(arguments_json)

                return {
                    "tool_call": {
                        "id": tool_call_id,
                        "name": function_name,
                        "arguments": arguments_str,
                    },
                    "usage": usage_info,
                }

            # --- 普通文本响应 ---
            content = msg.get("content", "")
            self.last_usage_info = usage_info

            if self.output_format == "json":
                parsed = self._parse_json_content(content)
                if parsed is None:
                    # 返回原始文本供上层进一步处理（而非直接抛异常吞掉有效数据）
                    return {"content": content, "usage": usage_info}
                content = parsed

            return {"content": content, "usage": usage_info}

        except Exception as e:
            error_type, error_msg = self._classify_error(e)
            result = {"content": error_msg, "usage": {}}
            if error_type:
                result["error_type"] = error_type
            return result
    
    def _classify_error(self, e: Exception) -> tuple:
        """分类网络错误，提供明确的错误提示
        
        按错误类型分层：DNS(解析)→连接→TLS→HTTP状态码→业务码
        
        Args:
            e: 异常对象
            
        Returns:
            tuple: (错误类型, 错误消息)
                   错误类型: "network" | "unknown"
        """
        import socket
        
        error_str = str(e).lower()
        
        if 'getaddrinfo failed' in error_str or 'name resolution' in error_str or 'name or service not known' in error_str:
            return (
                "network",
                "【网络错误】DNS解析失败\n"
                "无法解析域名 dashscope.aliyuncs.com，请检查：\n"
                "1. 网络连接是否正常\n"
                "2. DNS配置是否正确\n"
                "3. 是否需要配置代理服务器\n"
                "4. 企业防火墙是否允许访问阿里云百炼API"
            )
        elif 'connection refused' in error_str or 'connection reset' in error_str:
            return (
                "network",
                "【网络错误】连接被拒绝\n"
                "无法连接到阿里云百炼服务器，请检查：\n"
                "1. 网络连接是否正常\n"
                "2. 防火墙是否允许访问443端口\n"
                "3. 是否需要配置代理服务器"
            )
        elif 'ssl' in error_str or 'tls' in error_str:
            return (
                "network",
                "【网络错误】SSL/TLS连接失败\n"
                "请检查SSL证书配置或网络代理设置"
            )
        elif 'timeout' in error_str:
            return (
                "network",
                "【网络错误】请求超时\n"
                "网络连接超时，请检查网络稳定性或稍后重试"
            )
        else:
            return ("unknown", f"生成响应失败: {e}")

    def generate_streaming_response(self, prompt, conversation_history, callback, tools):
        """流式生成 LLM 响应

        通过 SSE 解析百炼兼容端点的流式输出。

        Args:
            prompt: 提示词
            conversation_history: 对话历史
            callback: 流式回调函数，接收每个 chunk 的文本
            tools: 工具定义列表

        Returns:
            str: 完整响应文本
        """
        if not self.env.ensure_ready():
            error_msg = "错误: 模型加载失败，请检查 API Key 配置"
            if callback:
                callback(error_msg)
            return error_msg

        try:
            messages = self._build_messages(conversation_history)
            payload = self._build_api_params(messages, tools, stream=True)

            headers = {
                "Authorization": f"Bearer {self.env.api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(
                f"{_COMPAT_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=300,
                stream=True,
            )

            if resp.status_code != 200:
                err_text = resp.text[:500]
                WorkLogger.error(f"[LLM] 流式响应失败: HTTP {resp.status_code}, {err_text}")
                if callback:
                    callback(f"错误: 流式响应失败, HTTP {resp.status_code}")
                return f"错误: 流式响应失败, HTTP {resp.status_code}"

            full_response = ""
            usage_info = {}

            for line in resp.iter_lines():
                if not line:
                    continue
                s = line.decode("utf-8", errors="replace").strip()
                if not s.startswith("data:"):
                    continue
                s = s[5:].strip()  # 去掉 "data:" 前缀
                if s == "[DONE]":
                    break

                try:
                    chunk = _json.loads(s)
                except Exception:
                    continue

                choices = chunk.get("choices")
                if choices:
                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # 文本增量
                    content = delta.get("content")
                    if content:
                        full_response += content
                        if callback:
                            callback(content)

                # usage 信息通常在最后一个 chunk (finish_reason != null) 中
                chunk_usage = chunk.get("usage")
                if chunk_usage:
                    usage_info = self._extract_usage(chunk_usage)

            self.last_usage_info = usage_info

            if self.output_format == "json":
                parsed = self._parse_json_content(full_response)
                if parsed is None:
                    # 流式结果也解析失败则返回原始文本
                    return full_response
                return parsed

            return full_response

        except Exception as e:
            WorkLogger.error(f"流式生成失败: {e}")
            error_type, error_msg = self._classify_error(e)
            if callback:
                callback(error_msg)
            # 返回带 error_type 的标记，便于上层识别
            result = {"content": error_msg, "usage": {}}
            if error_type:
                result["error_type"] = error_type
            return result

    def get_last_usage_info(self):
        """获取最后一次响应的 tokens 使用信息

        Returns:
            dict: tokens 使用信息（input_tokens, output_tokens, total_tokens）
        """
        return self.last_usage_info


# =============================================================================
# EmbeddingDeploy - Embedding 嵌入服务（统一调度层）
# =============================================================================

_embedding_instances = {}


class EmbeddingProvider:
    """Embedding Provider 抽象基类"""

    def __init__(self, api_key: str, config: dict):
        self.api_key = api_key
        self.config = config

    def embed(self, items: list) -> list:
        """执行嵌入，返回向量列表"""
        raise NotImplementedError

    @property
    def dimension(self) -> int:
        """向量维度"""
        return self.config.get("dimension", 2560)


class DashScopeEmbeddingProvider(EmbeddingProvider):
    """阿里云百炼 Embedding Provider"""

    def __init__(self, api_key: str, config: dict):
        super().__init__(api_key, config)
        self._model_name = config.get("model", "qwen3-vl-embedding")
        import dashscope
        dashscope.api_key = api_key

    def embed(self, items: list) -> list:
        from dashscope import MultiModalEmbedding
        try:
            resp = MultiModalEmbedding.call(
                model=self._model_name,
                input=items,
            )
            if resp.status_code == 200 and resp.output:
                embeddings = resp.output.get("embeddings", [])
                if embeddings:
                    return embeddings[0].get("embedding", [])
            return []
        except Exception:
            return []


def get_embedding_instance(config: dict = None) -> "EmbeddingDeploy":
    """获取 Embedding 实例（单例）

    Args:
        config: Embedding 配置参数

    Returns:
        EmbeddingDeploy: Embedding 实例
    """
    config = config or {}
    cache_key = str(config.get("provider", "dashscope")) + ":" + str(config.get("model", "qwen3-vl-embedding"))
    if cache_key not in _embedding_instances:
        _embedding_instances[cache_key] = EmbeddingDeploy(config)
    return _embedding_instances[cache_key]


class EmbeddingDeploy:
    """Embedding 部署类 - 统一封装多模态嵌入 API"""

    def __init__(self, config: dict = None):
        self.config = config or {}

        self._api_key = APIKeyProvider().get_key() or ""

        provider_type = self.config.get("provider", "dashscope")
        self._provider = self._create_provider(provider_type)

    def _create_provider(self, provider_type: str) -> EmbeddingProvider:
        """根据 provider 类型创建对应的 Provider 实例"""
        if provider_type == "dashscope":
            return DashScopeEmbeddingProvider(self._api_key, self.config)
        else:
            raise ValueError(f"不支持的 Embedding Provider: {provider_type}")

    def embed(self, items: list) -> list:
        """执行嵌入（通用接口）

        Args:
            items: 输入项列表，每项包含 text 或 image 字段

        Returns:
            list: 向量列表
        """
        if not self._api_key:
            return []
        return self._provider.embed(items)

    def embed_text(self, text: str) -> list:
        """纯文本嵌入"""
        return self.embed([{"text": text}])

    def embed_image(self, image_path: str) -> list:
        """图片嵌入"""
        return self.embed([{"image": image_path}])

    def embed_mixed(self, items: list) -> list:
        """混合模态嵌入"""
        return self.embed(items)

    @property
    def dimension(self) -> int:
        """向量维度"""
        return self._provider.dimension

    @property
    def api_key(self) -> str:
        """API Key"""
        return self._api_key
