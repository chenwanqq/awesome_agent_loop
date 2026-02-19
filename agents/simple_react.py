from litellm import completion
import dotenv
import os
from tools import Tool, tavily_search, tavily_extract, read_file, write_file, edit_file, list_dir, exec
from typing import Literal
import json


dotenv.load_dotenv()
'''
response = completion(
    model = "openai/kimi-k2.5",
    base_url = os.getenv("OPENAI_BASE_URL"),
    api_key = os.getenv("OPENAI_API_KEY"),
    messages = [{"role": "user", "content": "你好"}]
)
print(response.choices[0].message)
'''


class Agent:
    def __init__(self, model: str, base_url: str, api_key: str, system_prompt: str, tools: list[Tool] = []):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_schema = [tool.openai_schema for tool in self.tools]
        self.tool_dict = {tool.name: tool for tool in self.tools}

    # 暂时只返回str
    def run_single_turn(self, query: str, max_turns: int = 5, verbose: Literal["none", "debug", "auto"] = "auto") -> str:
        messages = [{"role": "system", "content": self.system_prompt}, {
            "role": "user", "content": query}]
        for i in range(max_turns):
            if i < max_turns - 1:
                response = completion(
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    messages=messages,
                    tools=self.tool_schema,
                    tool_choice="auto"
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
                print(message.content)
            elif verbose == "debug":
                print(response)

            if message.tool_calls is None or len(message.tool_calls) == 0:
                return message.content
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
                    print(f"警告：工具 {tool_name} 不存在")
                    continue

                result = tool(**tool_args)
                if result is None and verbose in ["debug", "auto"]:
                    print(f"警告：工具 {tool_name} 执行返回 None")
                    continue

                if verbose == "debug":
                    print(f"工具 {tool_name} 执行参数：{tool_args}")
                    print(f"工具 {tool_name} 执行结果：{result}")

                if verbose == "auto":
                    result_str = str(result)
                    if len(result_str) < 100:
                        print(f"工具 {tool_name} 执行结果：{result_str}")
                    else:
                        print(f"工具 {tool_name} 执行结果：{result_str[:100]}...")

                # add tool result message
                messages.append({"role": "tool",
                                "content": str(result),
                                 "tool_call_id": tool_call.id,
                                 "name": tool_name})

if __name__ == "__main__":
    agent = Agent(
        model=f"openai/{os.getenv('OPENAI_MODEL_NAME')}",
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        system_prompt="你是一个智能助手",
        tools=[tavily_search, tavily_extract, read_file,
               write_file, edit_file, list_dir, exec]
    )
    agent.run_single_turn("请搜索一下最新的AI新闻,并将其在当前文件夹下保存为latest_ai_news.md")
