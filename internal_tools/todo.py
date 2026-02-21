"""Todo 模块 - 待办事项管理工具、Hooks 和 Schema"""

import jsonschema
from pydantic import BaseModel
import json

from .base import internal_tool
from tools.decorator import Permission


class TodoItem(BaseModel):
    """待办事项项"""
    task: str
    done: bool


# Todo列表的JSON Schema定义
TODO_LIST_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "任务描述"},
            "done": {"type": "boolean", "description": "是否完成"}
        },
        "required": ["task", "done"]
    }
}


def validate_todo_list(data: list, schema: dict = TODO_LIST_SCHEMA) -> None:
    """使用 jsonschema 验证 todo 列表格式

    Args:
        data: 待验证的数据
        schema: 使用的 JSON Schema

    Raises:
        jsonschema.ValidationError: 如果验证失败
    """
    jsonschema.validate(instance=data, schema=schema)


TODO_JSON_SCHEMA_DESC = """
Todo列表格式示例：
[
    {"task": "任务1", "done": true},
    {"task": "任务2", "done": false}
]
JSON Schema:
{
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "任务描述"},
            "done": {"type": "boolean", "description": "是否完成"}
        },
        "required": ["task", "done"]
    }
}
"""


@internal_tool(
    name="create_todo",
    description=f"""创建新的待办事项列表，替换当前列表

{TODO_JSON_SCHEMA_DESC}

Args:
    tasks: 待办事项列表，每项包含 task(描述) 和 done(是否完成)

Returns:
    操作结果消息
""",
    parameters={
        "tasks": {
            "type": "array",
            "description": "待办事项列表",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "任务描述"},
                    "done": {"type": "boolean", "description": "是否完成"}
                },
                "required": ["task", "done"]
            }
        }
    },
    required=["tasks"],
    default_permission=Permission.ALLOW
)
def create_todo(state, tasks: list[dict]) -> str:
    """创建新的待办事项列表，替换当前列表"""
    # 1. 使用 jsonschema.validate 校验 tasks 格式
    validate_todo_list(tasks)

    # 2. 设置 state.todo_list = tasks
    state.todo_list = tasks

    # 3. 返回成功消息
    task_count = len(tasks)
    return f"成功创建待办事项列表，共 {task_count} 项任务"


@internal_tool(
    name="edit_todo",
    description=f"""编辑待办事项列表，使用乐观锁机制确保一致性

{TODO_JSON_SCHEMA_DESC}

Args:
    old_todo: 当前列表（必须与存储的一致）
    new_todo: 新的待办事项列表

Returns:
    操作结果消息，如果 old_todo 与当前不匹配则返回错误
""",
    parameters={
        "old_todo": {
            "type": "array",
            "description": "当前列表（必须与存储的一致）",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "done": {"type": "boolean"}
                },
                "required": ["task", "done"]
            }
        },
        "new_todo": {
            "type": "array",
            "description": "新的待办事项列表",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "done": {"type": "boolean"}
                },
                "required": ["task", "done"]
            }
        }
    },
    required=["old_todo", "new_todo"],
    default_permission=Permission.ALLOW
)
def edit_todo(state, old_todo: list[dict], new_todo: list[dict]) -> str:
    """编辑待办事项列表，使用乐观锁机制确保一致性"""
    # 1. 使用 jsonschema.validate 校验 old_todo 和 new_todo 格式
    validate_todo_list(old_todo)
    validate_todo_list(new_todo)

    # 2. 比较 old_todo 与 state.todo_list
    current_todo = state.todo_list

    # 使用简单的方式比较列表内容
    if old_todo != current_todo:
        return "错误：编辑冲突，当前待办事项列表已更改，请刷新后重试"

    # 3. 如果匹配，设置 state.todo_list = new_todo，返回成功消息
    state.todo_list = new_todo
    task_count = len(new_todo)
    return f"成功更新待办事项列表，当前共 {task_count} 项任务"


@internal_tool(
    name="clear_todo",
    description="""清空所有待办事项

Returns:
    操作结果消息
""",
    parameters={},
    required=[],
    default_permission=Permission.ALLOW
)
def clear_todo(state) -> str:
    """清空所有待办事项"""
    # 清空 state.todo_list，返回成功消息
    previous_count = len(state.todo_list)
    state.todo_list = []
    return f"成功清空待办事项列表（已清除 {previous_count} 项任务）"


@internal_tool(
    name="get_todo",
    description="""获取当前待办事项列表

Returns:
    当前待办事项列表的JSON字符串
""",
    parameters={},
    required=[],
    default_permission=Permission.ALLOW
)
def get_todo(state) -> str:
    """获取当前待办事项列表"""
    return json.dumps(state.todo_list, ensure_ascii=False)


def add_todo_message(state) -> tuple[bool, str]:
    """在 user query 前插入 todo 信息

    1. 遍历 messages，移除 被<todo></todo>包裹 的消息
    2. 如果todo_list非空，插入一条新消息，内容为<todo>{todo_list}</todo>
    3. 返回 (True, None) 表示继续执行
    """
    for i in range(len(state.messages)-1, -1, -1):
        if state.messages[i]["role"] == "user" and state.messages[i]["content"].startswith("<todo>") and state.messages[i]["content"].endswith("</todo>"):
            state.messages.pop(i)
            break

    if state.todo_list:
        state.messages.append({
            "role": "user",
            "content": f"<todo>{json.dumps(state.todo_list, ensure_ascii=False, separators=(',', ':'))}</todo>"
        })
    
    msg = None
    if state.todo_list is not None and len(state.todo_list) > 0:
        msg = json.dumps(state.todo_list, ensure_ascii=False)
    return True, msg
