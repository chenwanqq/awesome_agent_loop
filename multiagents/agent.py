from litellm import completion
import os
from tools import Tool
from typing import Literal, Optional
import json
from datetime import datetime
from middlewares import Middleware

from .state import AgentState


class Agent:
    def __init__(self, model: str, base_url: str, api_key: str, system_prompt: Optional[str] = None, tools: list[Tool] = None,
                 timeout: int = 120, verbose: Literal["none", "debug", "auto"] = "auto", max_turns: int = 20,
                 middlewares: list[Middleware] = None, initial_mode="default"):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.verbose = verbose
        self.max_turns = max_turns
        self.pre_user_query_hooks = []
        self.post_user_query_hooks = []
        self.pre_tool_use_hooks = []
        self.post_tool_use_hooks = []
        self.pre_response_hooks = []
        self.post_response_hooks = []
        self.pre_llm_call_hooks = []
        self.post_llm_call_hooks = []
        self.tools = tools if tools is not None else []
        self.internal_tools = []
        middlewares = middlewares if middlewares is not None else []

        # 构建系统提示
        self.system_prompt = self._build_system_prompt(
            system_prompt, middlewares=middlewares)

        # 注册中间件钩子
        for middleware in middlewares:
            self.pre_user_query_hooks.extend(middleware.pre_user_query_hooks())
            self.post_user_query_hooks.extend(
                middleware.post_user_query_hooks())
            self.pre_tool_use_hooks.extend(middleware.pre_tool_use_hooks())
            self.post_tool_use_hooks.extend(middleware.post_tool_use_hooks())
            self.pre_response_hooks.extend(middleware.pre_response_hooks())
            self.post_response_hooks.extend(middleware.post_response_hooks())
            self.pre_llm_call_hooks.extend(middleware.pre_llm_call_hooks())
            self.post_llm_call_hooks.extend(middleware.post_llm_call_hooks())
            self.tools.extend(middleware.tools())
            self.internal_tools.extend(middleware.internal_tools())

        # 去重：基于工具名称，保留第一个出现的工具（防御性编程）
        seen_tools = {}
        for tool in self.tools:
            if tool.name not in seen_tools:
                seen_tools[tool.name] = tool
        self.tools = list(seen_tools.values())

        seen_internal_tools = {}
        for tool in self.internal_tools:
            if tool.name not in seen_internal_tools:
                seen_internal_tools[tool.name] = tool
        self.internal_tools = list(seen_internal_tools.values())

        self.tool_schema = [tool.openai_schema for tool in self.tools] + \
            [it.openai_schema for it in self.internal_tools]
        self.tool_dict = {tool.name: tool for tool in self.tools}
        self.internal_tool_dict = {
            tool.name: tool for tool in self.internal_tools}

        self.state = AgentState()

        # 初始化 slash_cmd 字典
        self.slash_cmd = {}
        self._register_builtin_slash_cmds()
        for middleware in middlewares:
            self.slash_cmd.update(middleware.slash_cmds())

        # 初始化中间件
        for middleware in middlewares:
            middleware.agent_init_func(self.state)

        self.state.current_mode = initial_mode

    def _build_system_prompt(self, system_prompt: str = None, use_agents_md: bool = True, use_date: bool = True, middlewares: list[Middleware] = []) -> str:
        system_prompt = system_prompt or ""
        if use_agents_md:
            # 在当前位置寻找agents.md(不区分大小写)，返回真正的文件名
            agents_md = next(
                (f for f in os.listdir() if f.lower() == "agents.md"), None)
            if agents_md:
                with open(agents_md, "r") as f:
                    system_prompt += "\n" + f.read()
        if use_date:
            system_prompt += f"\n当前日期是{datetime.now().strftime('%Y-%m-%d')}"

        for middleware in middlewares:
            if middleware.aditional_system_message():
                system_prompt += "\n" + middleware.aditional_system_message()

        return system_prompt

    def clear_state(self):
        self.state.clear_state()

    def _register_builtin_slash_cmds(self):
        """注册内置斜杠命令"""
        self.slash_cmd["exit"] = self._cmd_exit
        self.slash_cmd["clear"] = self._cmd_clear
        self.slash_cmd["plan"] = self._cmd_plan
        self.slash_cmd["auto_edit"] = self._cmd_auto_edit
        self.slash_cmd["default"] = self._cmd_default

    @staticmethod
    def _cmd_exit(_, state: AgentState):
        """/exit 命令 - 退出 CLI"""
        return False, None  # should_continue=False, 退出循环

    @staticmethod
    def _cmd_clear(_, state: AgentState):
        """/clear 命令 - 清空状态"""
        state.clear_state()
        return True, None  # should_continue=True, 继续循环

    @staticmethod
    def _cmd_plan(_, state: AgentState):
        """/plan 命令 - 切换到 plan 模式"""
        state.current_mode = "plan"
        return True, None

    @staticmethod
    def _cmd_auto_edit(_, state: AgentState):
        """/auto_edit 命令 - 切换到 auto_edit 模式"""
        state.current_mode = "auto_edit"
        return True, None

    @staticmethod
    def _cmd_default(_, state: AgentState):
        """/default 命令 - 切换到 default 模式"""
        state.current_mode = "default"
        return True, None

    def register_slash_cmd(self, name: str, handler: callable):
        """注册新的斜杠命令

        Args:
            name: 命令名称（不含 / 前缀）
            handler: 处理函数，接收 query 和 state 参数，返回 (continue_execution, result)
                    handler 签名: fn(query: str, state: AgentState) -> tuple[bool, any]
        """
        self.slash_cmd[name] = handler

    def execute_slash_cmd(self, cmd: str, query: str = "") -> tuple[bool, any]:
        """执行斜杠命令

        Args:
            cmd: 命令名称（不含 / 前缀）
            query: 用户输入的原始查询字符串

        Returns:
            (是否继续运行, 执行结果/输出消息)
        """
        if cmd in self.slash_cmd:
            return self.slash_cmd[cmd](query, self.state)
        return True, f"[red]未知命令: /{cmd}[/red]"

    def get_messages(self) -> list[dict]:
        """获取当前消息列表"""
        return self.state.messages.copy()

    # 暂时只返回str
    def run(self, query: str):
        verbose = self.verbose
        max_turns = self.max_turns

        if not self.state.messages and self.system_prompt:
            self.state.messages.append(
                {"role": "system", "content": self.system_prompt})

        user_message = query

        # 1. 执行 pre_user_query_hooks
        for hook in self.pre_user_query_hooks:
            continue_execution, hook_msg = hook(self.state)
            if hook_msg is not None:
                yield hook_msg
            if not continue_execution:
                return

        if self.state.current_mode == "plan":
            user_message = f"根据用户的问题，生成一个计划，包含计划的详细说明，以及要完成用户问题的步骤。在进行计划的时候不要调用编辑性质的工具，只调用查询、读取性质的工具。用户问题是：{query}"

        self.state.messages.append({"role": "user", "content": user_message})

        for hook in self.post_user_query_hooks:
            continue_execution, hook_msg = hook(self.state)
            if hook_msg is not None:
                yield hook_msg
            if not continue_execution:
                return

        for i in range(max_turns):
            if i < max_turns - 1:
                for hook in self.pre_llm_call_hooks:
                    continue_execution, hook_msg = hook(self.state)
                    if hook_msg is not None:
                        yield hook_msg

                    if not continue_execution:
                        return

                response = completion(
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    messages=self.state.messages,
                    tools=self.tool_schema,
                    tool_choice="auto",
                    timeout=self.timeout
                )

                for hook in self.post_llm_call_hooks:
                    continue_execution, hook_msg = hook(self.state)
                    if hook_msg is not None:
                        yield hook_msg
                    if not continue_execution:
                        return
            else:
                self.state.messages.append(
                    {"role": "user", "content": "本轮对话还剩最后一次LLM调用机会，你不能再调用tool了，必须根据现有的结果生成最终的回答"})
                response = completion(
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    messages=self.state.messages,
                    tools=self.tool_schema,
                    tool_choice="none"
                )

            message = response.choices[0].message
            self.state.total_tokens = response.usage.total_tokens
            yield response.usage

            if verbose == "auto":
                yield "<think>" + message.reasoning_content + "</think>"
                yield message.content
            elif verbose == "debug":
                yield response

            if message.tool_calls is None or len(message.tool_calls) == 0:
                for hook in self.pre_response_hooks:
                    continue_execution, hook_msg = hook(self.state)
                    if hook_msg is not None:
                        yield hook_msg
                    if not continue_execution:
                        return
                self.state.messages.append({"role": message.role,
                                            "content": message.content,
                                            "reasoning_content": message.reasoning_content})
                if self.state.current_mode == "plan":
                    yield "你可以使用/auto_edit或/default来切换模式，执行计划"

                for hook in self.post_response_hooks:
                    continue_execution, hook_msg = hook(self.state)
                    if hook_msg is not None:
                        yield hook_msg
                    if not continue_execution:
                        return
                return message.content

            # add tool calling message
            self.state.messages.append({
                "role": message.role,
                "content": message.content,
                "tool_calls": message.tool_calls,
                "reasoning_content": message.reasoning_content
            })

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # 判断 tool 类型
                tool = self.tool_dict.get(tool_name)
                internal_tool = self.internal_tool_dict.get(tool_name)

                if tool is None and internal_tool is None and verbose in ["debug", "auto"]:
                    yield f"警告：工具 {tool_name} 不存在"
                    continue

                # 设置当前工具上下文到 tmp_states
                current_tool = tool if tool else internal_tool
                self.state.tmp_states["current_tool"] = current_tool
                self.state.tmp_states["current_tool_args"] = tool_args

                for pre_tool_use_hook in self.pre_tool_use_hooks:
                    tool_call_flag, msg = pre_tool_use_hook(self.state)
                    if msg is not None:
                        yield msg
                    if not tool_call_flag:
                        self.state.messages.append({"role": "tool",
                                                    "content": f"工具 {tool_name} 执行失败，{msg}",
                                                    "tool_call_id": tool_call.id,
                                                    "name": tool_name})
                        return

                try:
                    if tool:
                        result = tool(**tool_args)
                    elif internal_tool:
                        result = internal_tool(state=self.state, **tool_args)
                except Exception as e:
                    if verbose in ["debug", "auto"]:
                        yield f"工具 {tool_name} 执行异常：{e}"
                    self.state.messages.append({"role": "tool",
                                                "content": f"工具 {tool_name} 执行异常，{e}",
                                                "tool_call_id": tool_call.id,
                                                "name": tool_name})
                    continue

                if result is None and verbose in ["debug", "auto"]:
                    yield f"警告：工具 {tool_name} 执行返回 None"
                    continue

                if verbose == "debug":
                    yield f"工具 {tool_name} 执行参数：{tool_args}"
                    yield f"工具 {tool_name} 执行结果：{result}"

                if verbose == "auto":
                    result_str = str(result)
                    if len(result_str) < 100:
                        yield f"工具 {tool_name} 执行结果：{result_str}"
                    else:
                        yield f"工具 {tool_name} 执行结果：{result_str[:100]}..."

                # add tool result message
                self.state.messages.append({"role": "tool",
                                            "content": str(result),
                                            "tool_call_id": tool_call.id,
                                            "name": tool_name})

                for post_tool_use_hook in self.post_tool_use_hooks:
                    continue_execution, message = post_tool_use_hook(
                        self.state)
                    if message is not None:
                        yield message
                    if not continue_execution:
                        return
