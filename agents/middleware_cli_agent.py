from litellm import completion
import dotenv
import os
from tools import Tool
from typing import Literal, Optional
import json
from rich.console import Console
from datetime import datetime
from prompt_toolkit import PromptSession
import traceback
from middlewares import Middleware, InteractiveAuthorizationMiddleware, SystemMiddleware, TavilyMiddleware, PersistMiddleware, TodoMiddleware

from agents.state import AgentState


dotenv.load_dotenv()


class Agent:
    def __init__(self, model: str, base_url: str, api_key: str, system_prompt: Optional[str] = None, tools: list[Tool] = [],
                 timeout: int = 120, verbose: Literal["none", "debug", "auto"] = "auto", max_turns: int = 20,
                 middlewares: list[Middleware] = []):
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
        self.tools = tools
        self.internal_tools = []

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
    def _cmd_exit(state: AgentState):
        """/exit 命令 - 退出 CLI"""
        return False, None  # should_continue=False, 退出循环

    @staticmethod
    def _cmd_clear(state: AgentState):
        """/clear 命令 - 清空状态"""
        state.clear_state()
        return True, None  # should_continue=True, 继续循环

    @staticmethod
    def _cmd_plan(state: AgentState):
        """/plan 命令 - 切换到 plan 模式"""
        state.current_mode = "plan"
        return True, None

    @staticmethod
    def _cmd_auto_edit(state: AgentState):
        """/auto_edit 命令 - 切换到 auto_edit 模式"""
        state.current_mode = "auto_edit"
        return True, None

    @staticmethod
    def _cmd_default(state: AgentState):
        """/default 命令 - 切换到 default 模式"""
        state.current_mode = "default"
        return True, None

    def register_slash_cmd(self, name: str, handler: callable):
        """注册新的斜杠命令

        Args:
            name: 命令名称（不含 / 前缀）
            handler: 处理函数，接收 AgentState 参数，返回 (continue_execution, result)
                    handler 签名: fn(state: AgentState) -> tuple[bool, any]
        """
        self.slash_cmd[name] = handler

    def execute_slash_cmd(self, cmd: str) -> tuple[bool, any]:
        """执行斜杠命令

        Args:
            cmd: 命令名称（不含 / 前缀）

        Returns:
            (是否继续运行, 执行结果/输出消息)
        """
        if cmd in self.slash_cmd:
            return self.slash_cmd[cmd](self.state)
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
                yield response.usage
                for hook in self.post_response_hooks:
                    continue_execution, hook_msg = hook(self.state)
                    if hook_msg is not None:
                        yield hook_msg
                    if not continue_execution:
                        return
                return

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


class CLI:
    def __init__(self, model: str, base_url: str, api_key: str,
                 system_prompt: str,
                 timeout: int = 120, verbose: Literal["none", "debug", "auto"] = "auto",
                 max_turns: int = 20, tmp_dir: str = ".tmp",
                 resume: Optional[str] = None):

        self.console = Console()
        self.tmp_dir = tmp_dir

        # 处理 --resume 逻辑
        load_persist = None
        if resume is not None:
            if resume == "":
                # --resume 无参数，列出所有可用会话
                self._list_saved_states()
                self.agent = None  # 标记为未初始化，不进入交互模式
                return
            else:
                # --resume {name}
                load_persist = resume

        self.agent = Agent(
            model=model,
            base_url=base_url,
            api_key=api_key,
            system_prompt=system_prompt,
            timeout=timeout,
            verbose=verbose,
            max_turns=max_turns,
            middlewares=[InteractiveAuthorizationMiddleware(), SystemMiddleware(), TavilyMiddleware(
            ), PersistMiddleware(tmp_dir=tmp_dir, initial_session_name=load_persist), TodoMiddleware()],
        )
        self.session = PromptSession()

        # 如果是恢复会话，打印最近的历史消息
        if load_persist:
            self._print_recent_history()

    def _list_saved_states(self):
        """列出所有保存的会话"""
        if not os.path.exists(self.tmp_dir):
            self.console.print(
                f"[yellow]目录 {self.tmp_dir} 不存在，没有保存的会话。[/yellow]")
            return

        # 查找所有子目录
        entries = [d for d in os.listdir(self.tmp_dir)
                   if os.path.isdir(os.path.join(self.tmp_dir, d))]

        # 过滤出有 conversation.json 的目录
        sessions = []
        for entry in entries:
            conv_path = os.path.join(self.tmp_dir, entry, "conversation.json")
            if os.path.exists(conv_path):
                sessions.append(entry)

        if not sessions:
            self.console.print(f"[yellow]目录 {self.tmp_dir} 中没有保存的会话。[/yellow]")
            return

        # 按修改时间排序，最新的放在最上面
        sessions_with_mtime = []
        for session_name in sessions:
            session_dir = os.path.join(self.tmp_dir, session_name)
            conv_path = os.path.join(session_dir, "conversation.json")
            mtime = os.path.getmtime(conv_path)
            sessions_with_mtime.append((session_name, mtime))

        sessions_with_mtime.sort(key=lambda x: x[1], reverse=True)

        self.console.print("[green]可用的会话：[/green]")
        for session_name, mtime in sessions_with_mtime:
            session_dir = os.path.join(self.tmp_dir, session_name)
            conv_path = os.path.join(session_dir, "conversation.json")
            time_str = datetime.fromtimestamp(
                mtime).strftime('%Y-%m-%d %H:%M:%S')
            size = os.path.getsize(conv_path)
            self.console.print(
                f"  • {session_name} (修改时间: {time_str}, 大小: {size} bytes)")

    def _print_recent_history(self, count: int = 5, max_length: int = 100):
        """打印最近的历史消息"""
        messages = self.agent.state.messages
        # 过滤content不为空的消息
        valid_messages = [m for m in messages if m.get("content")]
        # 取最近count条
        recent_messages = valid_messages[-count:]

        if recent_messages:
            self.console.print("\n[green]最近的历史消息：[/green]")
            for msg in recent_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                # 截断长内容
                if len(content) > max_length:
                    content = content[:max_length] + "..."
                self.console.print(f"  [{role}] {content}")
            self.console.print()

    def run(self):
        # 如果 agent 未初始化（如 --resume 无参数时），直接返回
        if self.agent is None:
            return

        self.console.print("欢迎使用智能助手")
        while True:
            if self.agent.state.current_mode == "plan":
                prompt_text = "plan> "
            elif self.agent.state.current_mode == "auto_edit":
                prompt_text = "auto_edit> "
            else:
                prompt_text = "> "

            query = self.session.prompt(prompt_text)

            if query.startswith("/"):
                cmd = query[1:]  # 去掉 / 前缀
                continue_execution, result = self.agent.execute_slash_cmd(cmd)
                if result is not None:
                    self.console.print(result)
                if not continue_execution:
                    break
                continue

            try:
                for message in self.agent.run(query):
                    self.console.print(message)
            except KeyboardInterrupt:
                continue
            except Exception as e:
                self.console.print(f"发生错误：{e}")
                traceback.print_exc()
                continue


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="智能助手 CLI")
    parser.add_argument("--resume", nargs="?", const="", default=None,
                        help="恢复保存的会话。不带参数时列出所有可用会话，带参数时加载指定会话。")
    parser.add_argument("--tmp-dir", default=".tmp",
                        help="指定状态持久化目录 (默认: .tmp)")
    args = parser.parse_args()

    cli = CLI(
        model=f"moonshot/{os.getenv('OPENAI_MODEL_NAME')}",
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        system_prompt="你是一个智能助手.",
        tmp_dir=args.tmp_dir,
        resume=args.resume
    )

    # 只有在 agent 初始化成功时才运行交互循环
    if cli.agent is not None:
        cli.run()
