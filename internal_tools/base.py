"""InternalTools 基础模块 - 支持访问 AgentState 的工具"""

import functools
import inspect
from typing import Callable, Any

from tools.decorator import Permission
from tools.schema import _parse_google_docstring, get_input_schema, get_openai_tool_schema


class InternalTool:
    """InternalTool 基类 - 包装函数，支持访问 AgentState

    与普通 Tool 不同，InternalTool 的第一个参数是 state: AgentState
    这使得工具可以读取和修改代理的状态

    支持从 docstring 自动解析 description 和 parameters，
    同时保持 backward compatibility（支持显式传入参数）
    """

    def __init__(
        self,
        func: Callable,
        name: str = None,
        description: str = None,
        parameters: dict = None,
        required: list = None,
        default_permission: Permission = Permission.ALLOW,
        skip_first_param: bool = True,
    ):
        functools.update_wrapper(self, func)
        self.func = func
        self.name = name or func.__name__
        self._description_override = description
        self._parameters_override = parameters
        self._required_override = required
        self.default_permission = default_permission
        self.skip_first_param = skip_first_param

        # lazy loading 缓存
        self._description = None
        self._input_schema = None
        self._openai_schema = None

    def __call__(self, state: Any, **kwargs) -> str:
        """调用工具函数，自动注入 state"""
        return self.func(state, **kwargs)

    @property
    def description(self) -> str:
        """获取工具描述，优先使用显式传入的值，否则从 docstring 解析"""
        if self._description is None:
            if self._description_override:
                self._description = self._description_override
            else:
                docstring = inspect.getdoc(self.func) or ""
                desc, _ = _parse_google_docstring(docstring)
                self._description = desc
        return self._description

    @property
    def parameters(self) -> dict:
        """获取参数 schema，优先使用显式传入的值，否则从函数签名生成"""
        return self.input_schema.get("properties", {})

    @property
    def required(self) -> list:
        """获取必需参数列表，优先使用显式传入的值，否则从函数签名推断"""
        return self.input_schema.get("required", [])

    @property
    def input_schema(self) -> dict:
        """获取输入参数 schema（lazy loading）"""
        if self._input_schema is None:
            if self._parameters_override is not None:
                # 使用显式传入的参数
                self._input_schema = {
                    "type": "object",
                    "properties": self._parameters_override,
                    "required": self._required_override or [],
                }
            else:
                # 从函数签名和 docstring 自动生成
                self._input_schema = get_input_schema(
                    self.func, skip_first_param=self.skip_first_param
                )
        return self._input_schema

    @property
    def openai_schema(self) -> dict:
        """构建 OpenAI 格式的工具 schema（lazy loading）"""
        if self._openai_schema is None:
            if self._parameters_override is not None:
                # 使用显式传入的参数（backward compatibility）
                self._openai_schema = {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": self.description,
                        "parameters": {
                            "type": "object",
                            "properties": self._parameters_override,
                            "required": self._required_override or [],
                        },
                    },
                }
            else:
                # 从函数签名和 docstring 自动生成
                schema = get_openai_tool_schema(
                    self.func, skip_first_param=self.skip_first_param
                )
                # 允许覆盖 name
                schema["function"]["name"] = self.name
                self._openai_schema = schema
        return self._openai_schema


def internal_tool(
    func: Callable = None,
    *,
    name: str = None,
    description: str = None,
    parameters: dict = None,
    required: list = None,
    default_permission: Permission = Permission.ALLOW,
) -> InternalTool:
    """@internal_tool 装饰器 - 将函数转换为 InternalTool

    支持多种用法：
        # 无参数调用，自动从 docstring 解析
        @internal_tool
        def my_tool(state: AgentState, arg1: str) -> str:
            '''工具的 description

            Args:
                arg1: 参数描述
            '''
            ...

        # 仅指定权限
        @internal_tool(default_permission=Permission.ASK)
        def my_tool(state: AgentState, arg1: str) -> str:
            ...

        # 完整参数调用（backward compatibility）
        @internal_tool(
            name="custom_name",
            description="自定义描述",
            parameters={"arg1": {"type": "string"}},
            required=["arg1"],
        )
        def my_tool(state: AgentState, arg1: str) -> str:
            ...

    Args:
        func: 被装饰的函数
        name: 工具名称（可选，默认使用函数名）
        description: 工具描述（可选，默认从 docstring 解析）
        parameters: 参数 schema（可选，默认从函数签名生成）
        required: 必需参数列表（可选，默认从类型注解推断）
        default_permission: 默认权限（可选，默认为 ALLOW）
    """
    if func is not None:
        # 直接调用: @internal_tool
        return InternalTool(
            func,
            name=name,
            description=description,
            parameters=parameters,
            required=required,
            default_permission=default_permission,
        )
    else:
        # 带参数调用: @internal_tool(...)
        def decorator(f: Callable) -> InternalTool:
            return InternalTool(
                f,
                name=name,
                description=description,
                parameters=parameters,
                required=required,
                default_permission=default_permission,
            )

        return decorator
