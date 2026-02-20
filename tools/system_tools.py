"""系统工具 - 文件操作和命令执行

提供基础的文件操作和命令行执行功能，参考 nanobot 的实现。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from .decorator import tool, Permission


MAX_OUTPUT_LENGTH = 10000


def _get_full_path(path: str) -> Path:
    """将路径转换为绝对路径

    Args:
        path: 文件路径（绝对路径或相对路径）

    Returns:
        绝对路径的 Path 对象
    """
    return Path(path).expanduser().resolve()


@tool(default_permission=Permission.ALLOW)
def read_file(path: str, limit: int = 1000, offset: int = 1) -> str:
    """读取文件内容

    Args:
        path: 文件路径（绝对路径或相对路径）
        limit: 最多读取的行数（默认1000行）
        offset: 开始读取的行号（从1开始，默认第1行）

    Returns:
        文件内容，失败返回 "error: ..."
    """
    try:
        file_path = _get_full_path(path)

        if not file_path.exists():
            return f"error: File not found: {path}"

        if not file_path.is_file():
            return f"error: Not a file: {path}"

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # 调整 offset 为 0-based
        start = max(0, offset - 1)
        end = min(start + limit, len(lines))

        content = "".join(lines[start:end])
        return content

    except PermissionError:
        return f"error: Permission denied: {path}"
    except Exception as e:
        return f"error: Failed to read file: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """创建新文件并写入内容，自动创建父目录

    重要：此工具只能用于创建新文件。如果文件已存在，会返回错误。
    修改已有文件请使用 edit_file。

    Args:
        path: 文件路径
        content: 要写入的内容

    Returns:
        成功/失败信息
    """
    try:
        file_path = _get_full_path(path)

        # 检查文件是否已存在
        if file_path.exists():
            return f"error: File already exists: {path}. Use edit_file to modify existing files."

        # 自动创建父目录
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully created file: {path}"

    except PermissionError:
        return f"error: Permission denied: {path}"
    except Exception as e:
        return f"error: Failed to write file: {e}"


@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """编辑文件，替换指定文本

    Args:
        path: 文件路径
        old_text: 要被替换的文本
        new_text: 用于替换的新文本

    Returns:
        成功/失败信息
    """
    try:
        file_path = _get_full_path(path)

        if not file_path.exists():
            return f"error: File not found: {path}"

        if not file_path.is_file():
            return f"error: Not a file: {path}"

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # 检查 old_text 是否存在
        if old_text not in content:
            return f"error: Text not found in file: {old_text[:100]}..."

        # 替换文本
        new_content = content.replace(old_text, new_text, 1)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully edited file: {path}"

    except PermissionError:
        return f"error: Permission denied: {path}"
    except Exception as e:
        return f"error: Failed to edit file: {e}"


@tool(default_permission=Permission.ALLOW)
def list_dir(path: str = ".") -> str:
    """列出目录内容

    Args:
        path: 目录路径（默认为当前目录）

    Returns:
        目录内容列表，包含文件和子目录
    """
    try:
        dir_path = _get_full_path(path)

        if not dir_path.exists():
            return f"error: Directory not found: {path}"

        if not dir_path.is_dir():
            return f"error: Not a directory: {path}"

        entries = []
        for entry in sorted(dir_path.iterdir()):
            entry_type = "dir" if entry.is_dir() else "file"
            entries.append(f"{entry_type}: {entry.name}")

        if not entries:
            return f"Directory '{path}' is empty."

        return "\n".join(entries)

    except PermissionError:
        return f"error: Permission denied: {path}"
    except Exception as e:
        return f"error: Failed to list directory: {e}"


@tool
def exec(command: str, working_dir: Optional[str] = None, timeout: int = 60) -> str:
    """执行 shell 命令

    Args:
        command: 要执行的命令
        working_dir: 工作目录（可选，默认为当前目录）
        timeout: 超时时间（秒，默认60秒）

    Returns:
        命令输出（stdout + stderr），输出截断于10000字符
    """
    try:
        # 确定工作目录
        cwd = None
        if working_dir:
            cwd = _get_full_path(working_dir)
            if not cwd.exists():
                return f"error: Working directory not found: {working_dir}"
            if not cwd.is_dir():
                return f"error: Not a directory: {working_dir}"

        # 执行命令
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        # 合并 stdout 和 stderr
        output = result.stdout
        if result.stderr:
            if output:
                output += "\n" + result.stderr
            else:
                output = result.stderr

        # 截断输出
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + f"\n... (output truncated, total length: {len(output)})"

        # 添加退出码信息
        if result.returncode != 0:
            output = f"[exit code: {result.returncode}]\n{output}"

        return output if output else "(no output)"

    except subprocess.TimeoutExpired:
        return f"error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"error: Failed to execute command: {e}"
