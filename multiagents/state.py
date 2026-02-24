"""Agent 状态定义"""

from typing import Literal
from pydantic import BaseModel
from names_generator import generate_name
from tools import Permission


class AgentState(BaseModel):
    """Agent 状态类

    存储对话消息、当前模式、权限覆盖、临时状态、待办事项等
    """
    messages: list[dict] = []
    current_mode: Literal["plan", "default", "auto_edit"] = "default"
    override_authorization: dict[str, Permission] = {}
    tmp_states: dict = {}
    todo_list: list = []
    name: str = generate_name()
    tmp_dir: str = ".tmp"
    total_tokens: int = 0  # 当前上下文的token总数

    def clear_state(self):
        """清空状态，重置所有字段"""
        self.messages = []
        self.tmp_states = {}
        self.todo_list = []
        self.name = generate_name()
