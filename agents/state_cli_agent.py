from litellm import completion
import dotenv
import os
from tools import Tool, tavily_search, tavily_extract, read_file, write_file, edit_file, list_dir, exec
from tools import Permission
from typing import Literal, Optional
import json
from rich.console import Console
from rich.prompt import Prompt
from datetime import datetime
from prompt_toolkit import PromptSession
from pydantic import BaseModel
import traceback
from names_generator import generate_name
from functools import partial

# Import internal tools for todo management
from internal_tools import (
    create_todo,
    edit_todo,
    clear_todo,
    add_todo_message,
    get_todo,
)


dotenv.load_dotenv()


def build_system_prompt(system_prompt: str = None, use_agents_md: bool = True, use_date: bool = True) -> str:
    system_prompt = system_prompt or ""
    if use_agents_md:
        # 在当前位置寻找agents.md(不区分大小写)，返回真正的文件名
        agents_md = next(
            (f for f in os.listdir() if f.lower() == "agents.md"), None)
        if agents_md:
            with open(agents_md, "r") as f:
                system_prompt += f.read()
    if use_date:
        system_prompt += f"当前日期是{datetime.now().strftime('%Y-%m-%d')}"

    return system_prompt

# Same thought as LangGraph


class AgentState(BaseModel):
    messages: list[dict] = []
    current_mode: Literal["plan", "default", "auto_edit"] = "default"
    override_authorization: dict[str, Permission] = {}
    tmp_states: dict = {}
    todo_list: list = []  # 存储 todo 列表
    name: str = generate_name()
    tmp_dir: str = ".tmp"

    def clear_state(self):
        self.messages = []
        self.tmp_states = {}
        self.todo_list = []
        self.name = generate_name()


class Agent:
    def __init__(self, model: str, base_url: str, api_key: str, system_prompt: Optional[str] = None, tools: list[Tool] = [], internal_tools: list = [], timeout: int = 120, verbose: Literal["none", "debug", "auto"] = "auto", max_turns: int = 20,
                 persist: bool = True, load_persist: str = None, tmp_dir: str = ".tmp",
                 pre_user_query_hooks: list[callable] = [],
                 post_user_query_hooks: list[callable] = [],
                 pre_tool_use_hooks: list[callable] = [],
                 post_tool_use_hooks: list[callable] = [],
                 pre_response_hooks: list[callable] = [],
                 post_response_hooks: list[callable] = [],
                 pre_llm_call_hooks: list[callable] = [],
                 post_llm_call_hooks: list[callable] = []):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.tools = tools
        self.internal_tools = internal_tools
        self.tool_schema = [tool.openai_schema for tool in self.tools] + \
            [it.openai_schema for it in self.internal_tools]
        self.tool_dict = {tool.name: tool for tool in self.tools}
        self.internal_tool_dict = {
            tool.name: tool for tool in self.internal_tools}
        self.timeout = timeout
        self.verbose = verbose
        self.max_turns = max_turns
        self.pre_user_query_hooks = pre_user_query_hooks
        self.post_user_query_hooks = post_user_query_hooks
        self.pre_tool_use_hooks = pre_tool_use_hooks
        self.post_tool_use_hooks = post_tool_use_hooks
        self.pre_response_hooks = pre_response_hooks
        self.post_response_hooks = post_response_hooks
        self.pre_llm_call_hooks = pre_llm_call_hooks
        self.post_llm_call_hooks = post_llm_call_hooks
        

        all_hooks = [self.pre_user_query_hooks, self.post_user_query_hooks, self.pre_tool_use_hooks, self.post_tool_use_hooks,
                     self.pre_response_hooks, self.post_response_hooks, self.pre_llm_call_hooks, self.post_llm_call_hooks]

        os.makedirs(tmp_dir, exist_ok=True)

        if load_persist:
            # load_persist 是 session 名称
            session_dir = os.path.join(tmp_dir, load_persist)
            self.state = self._load_persist_from_file(session_dir)
        else:
            self.state = AgentState()
            self.state.tmp_dir = tmp_dir

        if persist:
            for hook in all_hooks:
                hook.append(partial(self._save_persist_to_file))

    def _save_persist_to_file(self, state: AgentState) -> tuple[bool, str]:
        session_dir = os.path.join(state.tmp_dir,state.name)
        if not os.path.isdir(session_dir):
            os.makedirs(session_dir, exist_ok=True)

        file_path = os.path.join(session_dir, "conversation.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(exclude=["tmp_states"]), f, indent=2, ensure_ascii=False)
        return True, None

    def _load_persist_from_file(self, session_dir: str) -> AgentState:
        if not os.path.isdir(session_dir):
            os.makedirs(session_dir, exist_ok=True)

        file_path = os.path.join(session_dir, "conversation.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return AgentState(**data)

    def clear_state(self):
        self.state.clear_state()

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
                 system_prompt: str, tools: list[Tool] = [],
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
            tools=tools,
            internal_tools=[create_todo, edit_todo, clear_todo, get_todo],
            timeout=timeout,
            verbose=verbose,
            max_turns=max_turns,
            tmp_dir=tmp_dir,
            load_persist=load_persist,
            pre_tool_use_hooks=[self.interactive_authorization],
            pre_llm_call_hooks=[add_todo_message],
        )
        self.session = PromptSession()

    def _list_saved_states(self):
        """列出所有保存的会话"""
        if not os.path.exists(self.tmp_dir):
            self.console.print(f"[yellow]目录 {self.tmp_dir} 不存在，没有保存的会话。[/yellow]")
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

        self.console.print("[green]可用的会话：[/green]")
        for session_name in sorted(sessions):
            session_dir = os.path.join(self.tmp_dir, session_name)
            conv_path = os.path.join(session_dir, "conversation.json")
            mtime = os.path.getmtime(conv_path)
            time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            size = os.path.getsize(conv_path)
            self.console.print(f"  • {session_name} (修改时间: {time_str}, 大小: {size} bytes)")

    def interactive_authorization(self, state: AgentState) -> tuple[bool, str]:
        tool = state.tmp_states["current_tool"]
        tool_args = state.tmp_states["current_tool_args"]

        if state.current_mode == "auto_edit":
            return True, None

        if tool.name in state.override_authorization and state.override_authorization[tool.name] == Permission.ALLOW:
            return True, None

        if tool.default_permission == Permission.ALLOW:
            return True, None

        if tool.name not in state.override_authorization:
            choice = Prompt.ask(f"是否授权执行工具 {tool.name}，参数 {tool_args}？", choices=[
                                "yes", "no", "always"])
            if choice == "yes":
                return True, None
            elif choice == "always":
                state.override_authorization[tool.name] = Permission.ALLOW
                return True, None
            else:
                return False, f"工具 {tool.name} 执行被拒绝"

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

            match query:
                case "exit":
                    break
                case "/clear":
                    self.agent.clear_state()
                    continue

                case "/plan":
                    self.agent.state.current_mode = "plan"
                    continue

                case "/auto_edit":
                    self.agent.state.current_mode = "auto_edit"
                    continue

                case "/default":
                    self.agent.state.current_mode = "default"
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
        model=f"openai/{os.getenv('OPENAI_MODEL_NAME')}",
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        system_prompt=build_system_prompt(
            "你是一个智能助手.如果遇到复杂的问题，请你调用todo相关的工具，创建并维护todo list以帮助你完成任务"),
        tools=[tavily_search, tavily_extract, read_file,
               write_file, edit_file, list_dir, exec],
        tmp_dir=args.tmp_dir,
        resume=args.resume
    )

    # 只有在 agent 初始化成功时才运行交互循环
    if cli.agent is not None:
        cli.run()
