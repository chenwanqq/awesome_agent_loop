from typing import override,Optional
from internal_tools import (
    create_todo,
    edit_todo,
    clear_todo,
    add_todo_message,
    get_todo,
)
from .base import Middleware

class TodoMiddleware(Middleware):
    """待办事项中间件"""
    @override
    def additional_system_message(self) -> Optional[str]:
        return "如果遇到复杂的问题，请你调用todo相关的工具，创建并维护todo list以帮助你完成任务。"

    @override
    def internal_tools(self) -> list[callable]:
        return [create_todo, edit_todo, clear_todo, get_todo]
    
    @override
    def pre_llm_call_hooks(self) -> list[callable]:
        return [add_todo_message]