from abc import ABC
from typing import Optional

from tools import Tool
from internal_tools import InternalTool

from agents.state import AgentState


class Middleware(ABC):
    """Middleware 基类"""

    def agent_init_func(self, state: AgentState) -> None:
        """中间件初始化函数，会在Agent初始化时调用"""
        pass

    def aditional_system_message(self) -> Optional[str]:
        """额外的系统消息，追加到system message后面"""
        return None

    def tools(self) -> list[Tool]:
        """返回中间件提供的工具列表"""
        return []

    def internal_tools(self) -> list[InternalTool]:
        """返回中间件提供的内部工具列表"""
        return []

    def pre_user_query_hooks(self) -> list:
        """返回中间件提供的用户查询前钩子函数列表"""
        return []

    def post_user_query_hooks(self) -> list:
        """返回中间件提供的用户查询后钩子函数列表"""
        return []

    def pre_tool_use_hooks(self) -> list:
        """返回中间件提供的工具使用前钩子函数列表"""
        return []

    def post_tool_use_hooks(self) -> list:
        """返回中间件提供的工具使用后钩子函数列表"""
        return []

    def pre_response_hooks(self) -> list:
        """返回中间件提供的响应前钩子函数列表"""
        return []

    def post_response_hooks(self) -> list:
        """返回中间件提供的响应后钩子函数列表"""
        return []

    def pre_llm_call_hooks(self) -> list:
        """返回中间件提供的LLM调用前钩子函数列表"""
        return []

    def post_llm_call_hooks(self) -> list:
        """返回中间件提供的LLM调用后钩子函数列表"""
        return []
