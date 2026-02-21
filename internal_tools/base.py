"""InternalTools 基础模块 - 支持访问 AgentState 的工具"""

from pydantic import BaseModel
from typing import Callable, Any

from tools.decorator import Permission


class InternalTool:
    """InternalTool 基类 - 包装函数，支持访问 AgentState

    与普通 Tool 不同，InternalTool 的第一个参数是 state: AgentState
    这使得工具可以读取和修改代理的状态
    """

    def __init__(self, func: Callable, name: str = None, description: str = None,
                 parameters: dict = None, required: list = None,
                 default_permission: Permission = Permission.ALLOW):
        self.func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or ""
        self.parameters = parameters or {}
        self.required = required or []
        self.default_permission = default_permission

        # 构建 OpenAI 格式的工具 schema
        self.openai_schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required
                }
            }
        }

    def __call__(self, state: Any, **kwargs) -> str:
        """调用工具函数，自动注入 state"""
        return self.func(state, **kwargs)


def internal_tool(func: Callable = None, *,
                  name: str = None,
                  description: str = None,
                  parameters: dict = None,
                  required: list = None,
                  default_permission: Permission = Permission.ALLOW) -> InternalTool:
    """@internal_tool 装饰器 - 将函数转换为 InternalTool

    用法:
        @internal_tool
        def my_tool(state: AgentState, arg1: str) -> str:
            ...

        @internal_tool(parameters={"arg1": {"type": "string"}}, required=["arg1"])
        def my_tool(state: AgentState, arg1: str) -> str:
            ...
    """
    if func is not None:
        # 直接调用: @internal_tool
        return InternalTool(func, name=name, description=description,
                           parameters=parameters, required=required,
                           default_permission=default_permission)
    else:
        # 带参数调用: @internal_tool(...)
        def decorator(f: Callable) -> InternalTool:
            return InternalTool(f, name=name, description=description,
                               parameters=parameters, required=required,
                               default_permission=default_permission)
        return decorator
