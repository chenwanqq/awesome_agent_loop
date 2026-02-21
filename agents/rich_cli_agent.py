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


class Agent:
    def __init__(self, model: str, base_url: str, api_key: str, system_prompt: Optional[str] = None, tools: list[Tool] = [], timeout: int = 120, verbose: Literal["none", "debug", "auto"] = "auto", max_turns: int = 20,
                 authorization_hook: Optional[callable] = None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_schema = [tool.openai_schema for tool in self.tools]
        self.tool_dict = {tool.name: tool for tool in self.tools}
        self.timeout = timeout
        self.verbose = verbose
        self.max_turns = max_turns
        self.authorization_hook = authorization_hook
        self.current_mode: Literal["plan", "default", "auto_edit"] = "default"

    # 暂时只返回str
    def run(self, query: str, messages: Optional[list[dict]] = None):
        verbose = self.verbose
        max_turns = self.max_turns
        if messages is None:
            messages = []

        if len(messages) == 0 and self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        user_message = query

        if self.current_mode == "plan":
            user_message = f"根据用户的问题，生成一个计划，包含计划的详细说明，以及要完成用户问题的步骤。在进行计划的时候不要调用编辑性质的工具，只调用查询、读取性质的工具。用户问题是：{query}"

        messages.append({"role": "user", "content": user_message})

        for i in range(max_turns):
            if i < max_turns - 1:
                response = completion(
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    messages=messages,
                    tools=self.tool_schema,
                    tool_choice="auto",
                    timeout=self.timeout
                )
            else:
                messages.append(
                    {"role": "user", "content": "本轮对话还剩最后一次LLM调用机会，你不能再调用tool了，必须根据现有的结果生成最终的回答"})
                response = completion(
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    messages=messages,
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
                messages.append({"role": message.role,
                                "content": message.content,
                                 "reasoning_content": message.reasoning_content})
                if self.current_mode == "plan":
                    yield "你可以使用/auto_edit或/default来切换模式，执行计划"
                yield response.usage
                return

            # add tool calling message
            messages.append({
                "role": message.role,
                "content": message.content,
                "tool_calls": message.tool_calls,
                "reasoning_content": message.reasoning_content
            })

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                tool = self.tool_dict[tool_name]
                if tool is None and verbose in ["debug", "auto"]:
                    yield f"警告：工具 {tool_name} 不存在"
                    continue

                if self.authorization_hook is not None and self.current_mode != "auto_edit" and not self.authorization_hook(tool, tool_args):
                    yield f"工具 {tool_name} 执行被拒绝"
                    break

                try:
                    result = tool(**tool_args)
                except Exception as e:
                    if verbose in ["debug", "auto"]:
                        yield f"工具 {tool_name} 执行异常：{e}"
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
                messages.append({"role": "tool",
                                "content": str(result),
                                 "tool_call_id": tool_call.id,
                                 "name": tool_name})


class CLI:
    def __init__(self, model: str, base_url: str, api_key: str,
                 system_prompt: str, tools: list[Tool] = [],
                 timeout: int = 120, verbose: Literal["none", "debug", "auto"] = "auto",
                 max_turns: int = 20):
        self.agent = Agent(
            model=model,
            base_url=base_url,
            api_key=api_key,
            system_prompt=system_prompt,
            tools=tools,
            timeout=timeout,
            verbose=verbose,
            max_turns=max_turns,
        )
        self.console = Console()
        self.override_authorization: dict[str, Permission] = dict()
        self.agent.authorization_hook = self.interactive_authorization

    def interactive_authorization(self, tool: Tool, tool_args: dict) -> bool:
        if tool.name in self.override_authorization and self.override_authorization[tool.name] == Permission.ALLOW:
            return True

        if tool.default_permission == Permission.ALLOW:
            return True

        if tool.name not in self.override_authorization:
            choice = Prompt.ask(f"是否授权执行工具 {tool.name}，参数 {tool_args}？", choices=[
                                "yes", "no", "always"])
            if choice == "yes":
                return True
            elif choice == "always":
                self.override_authorization[tool.name] = Permission.ALLOW
                return True
            else:
                return False

    def run(self):
        self.console.print("欢迎使用智能助手")
        messages = []
        while True:
            if self.agent.current_mode == "plan":
                query = input("plan> ")
            elif self.agent.current_mode == "auto_edit":
                query = input("auto_edit> ")
            else:
                query = input("> ")

            match query:
                case "exit":
                    break
                case "/clear":
                    messages = []
                    continue

                case "/plan":
                    self.agent.current_mode = "plan"
                    continue

                case "/auto_edit":
                    self.agent.current_mode = "auto_edit"
                    continue

                case "/default":
                    self.agent.current_mode = "default"
                    continue

            try:
                for message in self.agent.run(query, messages=messages):
                    self.console.print(message)
            except KeyboardInterrupt:
                continue
            except Exception as e:
                self.console.print(f"发生错误：{e}")
                continue


if __name__ == "__main__":
    cli = CLI(
        model=f"openai/{os.getenv('OPENAI_MODEL_NAME')}",
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        system_prompt=build_system_prompt("你是一个智能助手"),
        tools=[tavily_search, tavily_extract, read_file,
               write_file, edit_file, list_dir, exec],
    )
    cli.run()
