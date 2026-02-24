from .base import Middleware
from typing import override, Any, Optional
from multiagents import Agent
from multiagents.state import AgentState
from pathlib import Path
from tools import Tool
from rich.console import Console

from .authorization import InteractiveAuthorizationMiddleware
from .system import SystemMiddleware
from .tavily import TavilyMiddleware

import frontmatter


class SubAgentMiddleware(Middleware):
    def __init__(self, model, base_url, api_key, console: Optional[Console] = None, sub_agent_dirs: list[str] = [".agents/"], middlewares: list[Middleware] = [InteractiveAuthorizationMiddleware(), SystemMiddleware(), TavilyMiddleware()]):
        self.console = console

        # (name, description, agent)
        self.sub_agents: list[tuple[str, str, Agent]] = []
        self._tools: list[Tool] = []
        self._slash_cmds: dict[str, callable] = {}

        for dir in sub_agent_dirs:
            for file in Path(dir).glob("*.md"):
                agent_markdown = frontmatter.load(file)
                if "name" not in agent_markdown.metadata or "description" not in agent_markdown.metadata:
                    continue

                initial_mode = agent_markdown.metadata.get(
                    "permissionMode", "default")
                if initial_mode not in ["default", "plan", "auto_edit"]:
                    initial_mode = "default"

                agent = Agent(model, base_url, api_key,
                              system_prompt=agent_markdown.content, middlewares=middlewares, initial_mode=initial_mode)

                name = agent_markdown.metadata["name"]
                description = agent_markdown.metadata["description"]
                self.sub_agents.append((name, description, agent))

                # 为每个 subagent 创建一个 Tool
                tool_func = self._create_subagent_tool(
                    agent, name, description)
                tool = Tool(tool_func)
                self._tools.append(tool)

                # 为每个 subagent 创建一个 Slash Cmd
                cmd_func = self._create_subagent_cmd(agent, name, description)
                self._slash_cmds[name] = cmd_func

    def _create_subagent_tool(self, agent: Agent, agent_name: str, agent_description: str):
        """创建一个调用 subagent 的工具函数"""
        def subagent_tool(query: str) -> str:
            agent_run = agent.run(query)
            try:
                while True:
                    middle_result = next(agent_run)
                    if self.console is not None:
                        self.console.print(middle_result)
            except StopIteration as e:
                agent.clear_state()
                return e.value

        # 动态设置函数名和文档字符串
        subagent_tool.__name__ = f"create_{agent_name}_sub_agent"
        subagent_tool.__doc__ = f"创建{agent_name}子agent以执行特定任务，该子agent的描述为：{agent_description}"

        return subagent_tool

    def _create_subagent_cmd(self, agent: Agent, agent_name: str, agent_description: str):
        """创建一个调用 subagent 的 slash cmd 处理函数

        slash cmd 签名: fn(query: str, state: AgentState) -> tuple[bool, any]
        """
        def subagent_cmd(query: str, state: AgentState) -> tuple[bool, any]:
            """执行 subagent 并返回结果"""
            if self.console:
                self.console.print(f"[cyan]启动 {agent_name} 子代理...[/cyan]")
                self.console.print(f"[dim]{agent_description}[/dim]")

            agent_run = agent.run(query)
            final_result = None
            try:
                while True:
                    middle_result = next(agent_run)
                    if self.console is not None:
                        self.console.print(middle_result)

            except StopIteration as e:
                agent.clear_state()
                final_result = e.value

            return True, final_result if final_result else f"{agent_name} 执行完成"

        return subagent_cmd

    @override
    def slash_cmds(self) -> dict[str, callable]:
        """返回中间件提供的斜杠命令字典"""
        return self._slash_cmds

    @override
    def tools(self) -> list[Tool]:
        return self._tools


if __name__ == "__main__":
    subagent_middleware = SubAgentMiddleware("mock", "mock", "mock")
    for tool in subagent_middleware.tools():
        print(tool.get_schema())
