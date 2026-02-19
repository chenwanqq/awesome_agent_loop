"""类型到 JSON Schema 的转换"""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Literal, Optional, Union, get_args, get_origin, get_type_hints
from types import UnionType


def _get_type_schema(py_type: Any) -> dict:
    """将 Python 类型转换为 JSON Schema"""
    origin = get_origin(py_type)
    args = get_args(py_type)

    # 处理 Optional[T] / T | None
    if origin is Union or origin is UnionType:
        # 检查是否是 Optional（Union with None）
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            schema = _get_type_schema(non_none_types[0])
            schema["nullable"] = True
            return schema
        # 其他 Union 类型暂不支持，返回 object
        return {"type": "object"}

    # 处理 Literal（枚举）
    # 兼容不同 Python 版本：get_origin 可能返回 typing.Literal 而不是 Literal
    if origin is Literal or str(origin) == "typing.Literal":
        return {"type": "string", "enum": list(args)}

    # 处理 List
    if origin is list:
        if args:
            return {"type": "array", "items": _get_type_schema(args[0])}
        return {"type": "array"}

    # 处理 Dict
    if origin is dict:
        if args and len(args) >= 2:
            return {"type": "object", "additionalProperties": _get_type_schema(args[1])}
        return {"type": "object"}

    # 基础类型映射
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        dict: {"type": "object"},
        list: {"type": "array"},
    }

    return type_map.get(py_type, {"type": "object"})


def _parse_google_docstring(docstring: str) -> tuple[str, dict[str, str]]:
    """解析 Google Style Docstring

    Returns:
        (description, param_descriptions)
    """
    if not docstring:
        return "", {}

    lines = docstring.strip().split("\n")

    # 提取主描述（Args: 之前的部分）
    description_lines = []
    param_descriptions = {}

    in_args_section = False
    in_any_section = False  # 标记是否已进入任意 section
    current_param = None

    # 识别 section headers
    section_headers = {
        "Args:",
        "Arguments:",
        "Returns:",
        "Return:",
        "Raises:",
        "Yields:",
        "Examples:",
        "Note:",
        "Notes:",
    }

    for line in lines:
        stripped = line.strip()

        # 检查是否是 section header (去掉缩进后匹配)
        if stripped in section_headers:
            in_any_section = True  # 进入任意 section
            if stripped in ("Args:", "Arguments:"):
                in_args_section = True
            else:
                in_args_section = False
            continue

        if in_args_section:
            # 解析参数行：name: description
            if stripped:
                # 检查是否是新的参数（Args: 后的第一级缩进）
                leading_spaces = len(line) - len(line.lstrip())
                if leading_spaces <= 4 and re.match(r"^\w+:", stripped):
                    match = re.match(r"^(\w+):\s*(.*)$", stripped)
                    if match:
                        current_param = match.group(1)
                        param_descriptions[current_param] = match.group(2)
                elif current_param and leading_spaces > 4:
                    # 参数描述的续行（更缩进的行）
                    param_descriptions[current_param] += " " + stripped
        elif not in_any_section and stripped:
            # 主描述部分（不在任何 section 内）
            description_lines.append(stripped)

    description = " ".join(description_lines).strip()
    return description, param_descriptions


def get_input_schema(func: Callable) -> dict:
    """获取函数的输入参数 JSON Schema

    Returns:
        {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    """
    sig = inspect.signature(func)
    docstring = inspect.getdoc(func) or ""
    type_hints = get_type_hints(func)

    _, param_descriptions = _parse_google_docstring(docstring)

    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name == "self" or name == "cls":
            continue

        py_type = type_hints.get(name, Any)
        schema = _get_type_schema(py_type)

        # 添加描述
        if name in param_descriptions:
            schema["description"] = param_descriptions[name]

        properties[name] = schema

        # 判断是否为必需参数
        if param.default is inspect.Parameter.empty:
            origin = get_origin(py_type)
            args = get_args(py_type)
            # 不是 Optional 类型
            if not (origin is Union or origin is UnionType and type(None) in args):
                required.append(name)

    return {"type": "object", "properties": properties, "required": required}


def get_output_schema(func: Callable) -> dict:
    """获取函数的返回值 JSON Schema

    Returns:
        JSON Schema object
    """
    type_hints = get_type_hints(func)
    return_type = type_hints.get("return", Any)

    return _get_type_schema(return_type)


def get_openai_tool_schema(func: Callable) -> dict:
    """获取完整的 OpenAI 工具调用格式

    Returns:
        {
            "type": "function",
            "name": "function_name",
            "description": "...",
            "parameters": {...}
        }
    """
    docstring = inspect.getdoc(func) or ""
    description, _ = _parse_google_docstring(docstring)

    input_schema = get_input_schema(func)

    return {
        "type": "function",
        "name": func.__name__,
        "description": description,
        "parameters": input_schema,
    }
