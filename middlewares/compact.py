"""上下文压缩中间件"""

import os
import json
import uuid
from typing import Optional, override
from functools import partial
from litellm import token_counter, completion
from agents import AgentState
from .base import Middleware


class CompactMiddleware(Middleware):
    """上下文压缩中间件

    当消息累积到一定长度时，通过删除冗余内容、归档超长内容、以及LLM摘要等方式压缩历史消息，
    以节省token和上下文空间。
    """

    def __init__(self, tmp_dir: str = ".tmp",
                 model: Optional[str] = None,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 compact_threshold: int = 128000,
                 max_compacted_length: int = 12800,
                 max_content_length: int = 1000,
                 keep_recent_n: int = 4,
                 auto_compact: bool = True):
        """初始化CompactMiddleware

        Args:
            tmp_dir: 临时目录路径，用于存放归档文件
            model: 模型名称，用于token计算和摘要生成
            api_key: API密钥
            base_url: 基础URL
            compact_threshold: 触发自动压缩的token阈值 (默认 8000)
            max_compacted_length: 压缩后允许的最大token数 (默认 4000)
            max_content_length: 单条内容归档阈值，超过此长度的内容将被归档到文件 (默认 1000字符)
            keep_recent_n: 保留的最近消息数量 (默认 4条)
            auto_compact: 是否启用自动压缩 (默认 True)
        """
        self.tmp_dir = tmp_dir
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.compact_threshold = compact_threshold
        self.max_compacted_length = max_compacted_length
        self.max_content_length = max_content_length
        self.keep_recent_n = keep_recent_n
        self.auto_compact = auto_compact

    def _get_session_dir(self, state: AgentState) -> str:
        """获取当前会话目录"""
        return os.path.join(self.tmp_dir, state.name)

    def _message_to_json_safe(self, obj):
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        elif hasattr(obj, 'dict'):  # Pydantic v1 兼容
            return obj.dict()
        else:
            return obj

    def _archive_long_content(self, state: AgentState, message: dict, session_dir: str) -> tuple[bool, str]:
        """归档消息中的超长内容

        Args:
            state: Agent状态
            message: 消息字典
            session_dir: 会话目录路径

        Returns:
            (是否归档, 归档文件路径或空字符串)
        """
        archived = False
        archive_path = ""

        # 检查 content
        content = message.get("content", "")
        if content and len(content) > self.max_content_length:
            if not os.path.exists(session_dir):
                os.makedirs(session_dir, exist_ok=True)

            file_name = f"{uuid.uuid4()}.json"
            file_path = os.path.join(session_dir, file_name)

            # 保存原始内容
            with open(file_path, "w", encoding="utf-8") as f:
                # 将 message 转换为 JSON 安全的字典
                safe_message = self._message_to_json_safe(message)
                json.dump(safe_message,f)

            # 替换内容为摘要
            message["content"] = content[:self.max_content_length] + f"...更多请参见 {file_path}"
            archived = True
            archive_path = file_path

        # 检查 tool_calls
        tool_calls = message.get("tool_calls", [])

        if not os.path.exists(session_dir):
            os.makedirs(session_dir, exist_ok=True)

        file_name = f"{uuid.uuid4()}.json"
        file_path = os.path.join(session_dir, file_name)
        if tool_calls:
            for tool_call in tool_calls:
                tool_args = tool_call.get("function", {}).get("arguments", "")
                if tool_args and len(str(tool_args)) > self.max_content_length:
                    # 只需要归档一次
                    if not os.path.exists(file_path):
                        with open(file_path, "w", encoding="utf-8") as f:
                            # 将 tool_call 对象转换为字典以便 JSON 序列化
                            safe_message = self._message_to_json_safe(message)
                            json.dump(safe_message,f)

                    # 替换参数为摘要
                    tool_call["function"]["arguments"] = str(tool_args)[:self.max_content_length] + f"...更多请参见 {file_path}"
                    archived = True
                    if not archive_path:
                        archive_path = file_path

        return archived, archive_path

    def _calculate_tokens(self, state: AgentState) -> int:
        """计算当前消息的token数

        Args:
            state: Agent状态

        Returns:
            token数量
        """

        tokens = token_counter(model=self.model, messages=state.messages)
        state.total_tokens = tokens
        return tokens

    def _generate_summary(self, state: AgentState, messages_to_summarize: list[dict]) -> str:
        """使用LLM生成消息摘要

        Args:
            state: Agent状态
            messages_to_summarize: 需要摘要的消息列表

        Returns:
            摘要文本
        """
        if not self.model or not self.api_key:
            return f"[无法生成摘要: 缺少模型配置] 原对话包含 {len(messages_to_summarize)} 条消息"

        # 获取系统提示
        system_message = ""
        for msg in state.messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
                break

        # 获取最近的user消息
        recent_user_messages = []
        for msg in reversed(state.messages):
            if msg.get("role") == "user":
                recent_user_messages.insert(0, msg.get("content", ""))
            if len(recent_user_messages) >= self.keep_recent_n:
                break

        # 构建摘要请求
        summary_prompt = f"""你的任务是对历史消息进行压缩，以节省上下文空间。请你输出一段不超过2000字的summary，简单概括之前agent与user进行了什么交互。

用户给agent赋予的角色是: {system_message if system_message else ''}

你可以用户最近的输入来推断用户当前的意图。用户最近{len(recent_user_messages)}次的输入为:
{chr(10).join([f"- {msg}" for msg in recent_user_messages])}

待压缩的信息为以下消息:
"""

        # 添加待压缩消息
        for i, msg in enumerate(messages_to_summarize):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            summary_prompt += f"\n[{i+1}] {role}: {content}"

        try:
            response = completion(
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
                messages=[
                    {"role": "system", "content": "你是一个专门用于压缩和摘要对话历史的助手。请用简洁的语言概括对话内容。"},
                    {"role": "user", "content": summary_prompt}
                ],
                timeout=120
            )
            return response.choices[0].message.content
        except Exception as e:
            # 如果摘要生成失败，返回一个简单的摘要
            return f"[对话历史摘要生成失败: {str(e)}] 原对话包含 {len(messages_to_summarize)} 条消息"

    def _compact_context(self, state: AgentState) -> tuple[bool, str]:
        """执行上下文压缩

        Args:
            state: Agent状态

        Returns:
            (是否成功压缩, 压缩结果信息)
        """
        if not state.messages:
            return False, "没有消息需要压缩"

        # 计算压缩前的token数
        tokens_before = state.total_tokens

        # 分离需要保留和需要压缩的消息
        print("步骤1: 分离需要保留和需要压缩的消息")
        system_messages = []
        other_messages = []

        for msg in state.messages:
            if msg.get("role") == "system":
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        # 保留消息策略：从后往前找到非tool消息，如果从该位置到末尾的消息数>=keep_recent_n就停止
        if len(other_messages) <= self.keep_recent_n:
            return False, "消息数量过少，无需压缩"

        keep_index = len(other_messages)

        for i in range(len(other_messages) - 1, -1, -1):
            msg = other_messages[i]

            is_tool_msg = msg.get("role") == "tool"

            if not is_tool_msg:
                # 计算从当前位置到末尾的消息数
                messages_from_here = len(other_messages) - i
                if messages_from_here >= self.keep_recent_n:
                    keep_index = i
                    break

        messages_to_keep = other_messages[keep_index:]
        messages_to_compact = other_messages[:keep_index]

        # 步骤2: 删除 reasoning_content
        print("步骤2: 删除 reasoning_content")
        for msg in messages_to_compact:
            if "reasoning_content" in msg:
                del msg["reasoning_content"]

        # 步骤3: 归档超长内容
        print("步骤3: 归档超长内容")
        session_dir = self._get_session_dir(state)
        archived_files = []

        for msg in messages_to_compact:
            archived, path = self._archive_long_content(state, msg, session_dir)
            if archived and path:
                archived_files.append(path)

        # 步骤4: 计算token数，如仍超阈值则生成LLM摘要
        # 先构建临时消息列表计算token
        print(f"步骤4: 计算token数，如仍超阈值则生成LLM摘要")
        temp_messages = system_messages + messages_to_compact + messages_to_keep
        state.messages = temp_messages
        tokens_after_step3 = self._calculate_tokens(state)

        if tokens_after_step3 > self.max_compacted_length:
            # 需要LLM摘要
            summary = self._generate_summary(state, messages_to_compact)

            # 替换为摘要消息
            summary_message = {
                "role": "assistant",
                "content": f"[历史对话摘要]\n{summary}"
            }

            state.messages = system_messages + [summary_message] + messages_to_keep

        # 计算压缩后的token数
        tokens_after = self._calculate_tokens(state)

        result_info = f"压缩完成: {tokens_before} tokens -> {tokens_after} tokens, 归档文件: {len(archived_files)}个"
        return True, result_info

    def _pre_llm_call_hook(self, state: AgentState) -> tuple[bool, Optional[str]]:
        """LLM调用前的钩子函数

        检查token数是否超过阈值，如超过且auto_compact为True，则自动执行压缩
        """
        if not self.auto_compact:
            return True, None

        if not self.model:
            return True, None

        # 计算当前token数
        current_tokens = self._calculate_tokens(state)

        if current_tokens > self.compact_threshold:
            success, info = self._compact_context(state)
            if success:
                return True, f"[yellow]上下文已自动压缩: {info}[/yellow]"

        return True, None

    def _cmd_compact(self, state: AgentState) -> tuple[bool, str]:
        """/compact 命令 - 手动触发上下文压缩"""
        success, info = self._compact_context(state)
        if success:
            return True, f"[green]上下文压缩成功: {info}[/green]"
        else:
            return True, f"[yellow]上下文无需压缩: {info}[/yellow]"

    @override
    def agent_init_func(self, state: AgentState) -> None:
        """中间件初始化"""
        # 确保会话目录存在
        session_dir = self._get_session_dir(state)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir, exist_ok=True)

    @override
    def slash_cmds(self) -> dict[str, callable]:
        """返回斜杠命令"""
        return {
            "compact": partial(self._cmd_compact)
        }

    @override
    def pre_llm_call_hooks(self) -> list:
        """返回LLM调用前钩子函数列表"""
        return [partial(self._pre_llm_call_hook)]

