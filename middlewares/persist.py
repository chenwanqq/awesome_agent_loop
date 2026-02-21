from typing import Optional, override
from agents import AgentState
from functools import partial
from .base import Middleware
import os
import json

class PersistMiddleware(Middleware):
    """持久化中间件"""

    def __init__(self, tmp_dir: str, initial_session_name: Optional[str]):
        self.tmp_dir = tmp_dir
        self.initial_session_name = initial_session_name

    def _load_persist_from_file(self, session_dir: str) -> AgentState:
        if not os.path.isdir(session_dir):
            os.makedirs(session_dir, exist_ok=True)

        file_path = os.path.join(session_dir, "conversation.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return AgentState(**data)

    @override
    def agent_init_func(self, state: AgentState) -> None:
        state.tmp_dir = self.tmp_dir
        if self.initial_session_name:
            new_state = self._load_persist_from_file(
                os.path.join(self.tmp_dir, self.initial_session_name)
            )
            # 不改变指向，只改变值
            for field_name,_ in new_state.__class__.model_fields.items():
                value = getattr(new_state, field_name)
                setattr(state, field_name, value)

    def _save_persist_to_file(self, state: AgentState) -> tuple[bool, str]:
        try:
            session_dir = os.path.join(self.tmp_dir, state.name)
            if not os.path.isdir(session_dir):
                os.makedirs(session_dir, exist_ok=True)

            file_path = os.path.join(session_dir, "conversation.json")
            with open(file_path, "w", encoding="utf-8") as f:
                # 排除 tmp_states，因为它是临时状态，可能包含不可序列化的对象（如 Tool）
                json.dump(state.model_dump(exclude={"tmp_states"}), f, ensure_ascii=False)

            return True, None
        except Exception as e:
            return False, str(e)

    @override
    def pre_user_query_hooks(self) -> list:
        """返回中间件提供的用户查询前钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def post_user_query_hooks(self) -> list:
        """返回中间件提供的用户查询后钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def pre_tool_use_hooks(self) -> list:
        """返回中间件提供的工具使用前钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def post_tool_use_hooks(self) -> list:
        """返回中间件提供的工具使用后钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def pre_response_hooks(self) -> list:
        """返回中间件提供的响应前钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def post_response_hooks(self) -> list:
        """返回中间件提供的响应后钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def pre_llm_call_hooks(self) -> list:
        """返回中间件提供的LLM调用前钩子函数列表"""
        return [partial(self._save_persist_to_file)]

    @override
    def post_llm_call_hooks(self) -> list:
        """返回中间件提供的LLM调用后钩子函数列表"""
        return [partial(self._save_persist_to_file)]
