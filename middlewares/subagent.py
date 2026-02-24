from .base import Middleware
from typing import override
from multiagents import Agent
from pathlib import Path
from tools import Tool

from .authorization import InteractiveAuthorizationMiddleware
from .system import SystemMiddleware
from .tavily import TavilyMiddleware

import frontmatter


class SubAgentMiddleware(Middleware):
    def __init__(self, model, base_url, api_key, sub_agent_dirs: list[str] = [".agents/"], middlewares: list[Middleware] = [InteractiveAuthorizationMiddleware(), SystemMiddleware(), TavilyMiddleware()]):
        # (name, description, agent)
        self.sub_agents: list[tuple[str, str, Agent]] = []
        self._tools: list[Tool] = []

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

    def _create_subagent_tool(self, agent: Agent, agent_name: str, agent_description: str):
        """创建一个调用 subagent 的工具函数"""
        def subagent_tool(query: str) -> str:
            results = []
            for item in agent.run(query):
                if isinstance(item, str):
                    results.append(item)
            return "\n".join(results)

        # 动态设置函数名和文档字符串
        subagent_tool.__name__ = f"create_{agent_name}_sub_agent"
        subagent_tool.__doc__ = f"创建{agent_name}子agent以执行特定任务，该子agent的描述为：{agent_description}"

        return subagent_tool

    @override
    def tools(self) -> list[Tool]:
        return self._tools


if __name__ == "__main__":
    subagent_middleware = SubAgentMiddleware("mock", "mock", "mock")
    for tool in subagent_middleware.tools():
        print(tool.get_schema())
