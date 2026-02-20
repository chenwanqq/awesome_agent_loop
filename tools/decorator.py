"""Tool 装饰器和工具类"""

from __future__ import annotations

import functools
from enum import Enum
from typing import Callable

from .schema import get_input_schema, get_output_schema, get_openai_tool_schema


class Permission(str, Enum):
    """工具默认权限"""
    ALLOW = "allow"  # 默认允许执行
    ASK = "ask"      # 默认需要询问


class Tool:
    """工具类，包装函数并提供 schema 访问"""

    def __init__(self, func: Callable, default_permission: Permission = Permission.ASK):
        functools.update_wrapper(self, func)
        self.func = func
        self.name = func.__name__
        self.default_permission = default_permission
        self._input_schema = None
        self._output_schema = None
        self._openai_schema = None

    def __call__(self, *args, **kwargs):
        """调用被包装的函数"""
        return self.func(*args, **kwargs)

    @property
    def input_schema(self) -> dict:
        """获取输入参数 schema"""
        if self._input_schema is None:
            self._input_schema = get_input_schema(self.func)
        return self._input_schema

    @property
    def output_schema(self) -> dict:
        """获取输出 schema"""
        if self._output_schema is None:
            self._output_schema = get_output_schema(self.func)
        return self._output_schema

    @property
    def openai_schema(self) -> dict:
        """获取完整的 OpenAI 工具格式"""
        if self._openai_schema is None:
            self._openai_schema = get_openai_tool_schema(self.func)
        return self._openai_schema

    def get_schema(self) -> dict:
        """获取 OpenAI 工具格式（兼容方法）"""
        return self.openai_schema


def tool(func: Callable | None = None, *, default_permission: Permission = Permission.ASK) -> Tool:
    """@tool 装饰器 - 将函数转换为 Tool 对象

    Args:
        func: 被装饰的函数
        default_permission: 默认权限（allow/ask）

    Example:
        @tool(default_permission=Permission.ALLOW)
        def read_file(path: str) -> str:
            \"\"\"读取文件\"\"\"
            ...

        @tool
        def write_file(path: str, content: str) -> str:
            \"\"\"写入文件\"\"\"
            ...

        # 使用
        print(search_weather.openai_schema)
        print(search_weather.input_schema)
        print(search_weather.output_schema)
    """
    def decorator(f: Callable) -> Tool:
        return Tool(f, default_permission=default_permission)

    if func is None:
        return decorator
    return decorator(func)
