"""Agent Framework Tool Module

提供工具调用功能，支持从 type hints 和 docstring 自动生成 OpenAI 格式的工具 schema。

Example:
    from tools import tool

    @tool
    def search_weather(
        location: str,
        unit: Literal["celsius", "fahrenheit"] = "celsius"
    ) -> dict[str, Any]:
        \"\"\"搜索指定位置的天气

        Args:
            location: 位置名称
            unit: 温度单位

        Returns:
            天气信息
        \"\"\"
        return {"temperature": 25}

    # 获取各种 schema
    print(search_weather.openai_schema)   # OpenAI 完整格式
    print(search_weather.input_schema)    # 输入参数 schema
    print(search_weather.output_schema)   # 输出 schema
"""

from .decorator import tool, Tool
from .schema import get_input_schema, get_output_schema, get_openai_tool_schema

__all__ = [
    "tool",
    "Tool",
    "get_input_schema",
    "get_output_schema",
    "get_openai_tool_schema",
]
