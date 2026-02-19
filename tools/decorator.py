"""Tool 装饰器和工具类"""

from __future__ import annotations

import functools
from typing import Callable

from .schema import get_input_schema, get_output_schema, get_openai_tool_schema


class Tool:
    """工具类，包装函数并提供 schema 访问"""

    def __init__(self, func: Callable):
        functools.update_wrapper(self, func)
        self.func = func
        self.name = func.__name__
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


def tool(func: Callable) -> Tool:
    """@tool 装饰器 - 将函数转换为 Tool 对象

    Example:
        @tool
        def search_weather(location: str, unit: str = "celsius") -> dict:
            \"\"\"搜索天气

            Args:
                location: 位置
                unit: 单位
            \"\"\"
            return {"temp": 25}

        # 使用
        print(search_weather.openai_schema)
        print(search_weather.input_schema)
        print(search_weather.output_schema)
    """
    return Tool(func)
