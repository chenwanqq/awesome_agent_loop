"""权限校验中间件"""

from functools import partial
from typing import override
from rich.prompt import Prompt

from middlewares.base import Middleware
from agents.state import AgentState
from tools import Permission
from .base import Middleware


class InteractiveAuthorizationMiddleware(Middleware):
    """交互式权限校验中间件

    在工具执行前向用户请求授权，支持以下规则：
    1. auto_edit 模式下自动授权
    2. 已在 override_authorization 中标记为 ALLOW 的工具自动授权
    3. default_permission 为 ALLOW 的工具自动授权
    4. 其他情况交互式询问用户（yes/no/always）
    """

    @override
    def pre_tool_use_hooks(self) -> list[callable]:
        return [partial(self._interactive_authorization)]


    def _interactive_authorization(self, state: AgentState) -> tuple[bool, str | None]:
        tool = state.tmp_states["current_tool"]
        tool_args = state.tmp_states["current_tool_args"]

        if state.current_mode == "auto_edit":
            return True, None

        if tool.name in state.override_authorization and state.override_authorization[tool.name] == Permission.ALLOW:
            return True, None

        if tool.default_permission == Permission.ALLOW:
            return True, None

        if tool.name not in state.override_authorization:
            choice = Prompt.ask(
                f"是否授权执行工具 {tool.name}，参数 {tool_args}？",
                choices=["yes", "no", "always"]
            )
            if choice == "yes":
                return True, None
            elif choice == "always":
                state.override_authorization[tool.name] = Permission.ALLOW
                return True, None
            else:
                return False, f"工具 {tool.name} 执行被拒绝"

        return True, None
