import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dotenv
from typing import Literal, Optional
from rich.console import Console
from datetime import datetime
from prompt_toolkit import PromptSession
import traceback
from middlewares import InteractiveAuthorizationMiddleware, SystemMiddleware, TavilyMiddleware, PersistMiddleware, TodoMiddleware, CompactMiddleware, SubAgentMiddleware

from multiagents.agent import Agent


dotenv.load_dotenv()

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
            middlewares=[
                InteractiveAuthorizationMiddleware(),
                SystemMiddleware(),
                TavilyMiddleware(),
                PersistMiddleware(tmp_dir=tmp_dir, initial_session_name=load_persist),
                TodoMiddleware(),
                CompactMiddleware(tmp_dir=tmp_dir, model=model, api_key=api_key, base_url=base_url),
                SubAgentMiddleware(base_url=base_url, api_key=api_key, model=model,console=self.console)
            ],
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
                # 去掉 / 前缀，解析命令和参数
                parts = query[1:].split(maxsplit=1)
                cmd = parts[0]
                cmd_query = parts[1] if len(parts) > 1 else ""
                continue_execution, result = self.agent.execute_slash_cmd(cmd, cmd_query)
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
