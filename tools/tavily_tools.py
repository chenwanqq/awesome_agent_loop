"""Tavily 搜索和内容提取工具

需要设置环境变量 TAVILY_API_KEY 才能使用这些工具。
"""

from __future__ import annotations

import os
from typing import Any, Literal, Optional

from .decorator import tool


def _get_tavily_client():
    """获取 Tavily 客户端实例"""
    try:
        from tavily import TavilyClient
    except ImportError:
        raise ImportError(
            "tavily-python is required. Install it with: pip install tavily-python"
        )

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY environment variable is not set. "
            "Get your API key from https://tavily.com"
        )

    return TavilyClient(api_key=api_key)


@tool
def tavily_search(
    query: str,
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic",
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    include_answer: bool = True,
    time_range: Optional[Literal["day", "week", "month", "year"]] = None,
) -> dict[str, Any]:
    """使用 Tavily 进行网页搜索

    Tavily 是一个专为 AI 应用设计的搜索引擎，提供高质量的搜索结果
    和 AI 生成的答案摘要。

    Args:
        query: 搜索查询字符串
        search_depth: 搜索深度，影响结果质量和速度
            - "basic": 基础搜索，速度快
            - "advanced": 高级搜索，结果更全面
            - "fast": 快速搜索
            - "ultra-fast": 超快速搜索
        topic: 搜索主题类型
            - "general": 一般搜索
            - "news": 新闻搜索
            - "finance": 金融搜索
        max_results: 返回的最大结果数量，范围 1-20
        include_answer: 是否包含 AI 生成的答案摘要
        time_range: 时间范围过滤
            - "day": 最近一天
            - "week": 最近一周
            - "month": 最近一月
            - "year": 最近一年
            - None: 不限制时间

    Returns:
        Tavily 搜索结果，包含以下字段:
        - query: 原始查询
        - answer: AI 生成的答案摘要（如果 include_answer=True）
        - results: 搜索结果列表，每个结果包含 title, url, content, score 等
        - images: 相关图片 URL 列表（如果有）
        - usage: API 使用统计
    """
    client = _get_tavily_client()

    params = {
        "query": query,
        "search_depth": search_depth,
        "topic": topic,
        "max_results": max_results,
        "include_answer": include_answer,
    }

    if time_range:
        params["time_range"] = time_range

    return client.search(**params)


@tool
def tavily_extract(
    url: str,
    extract_depth: Literal["basic", "advanced"] = "basic",
) -> str:
    """从指定 URL 提取网页内容

    使用 Tavily Extract API 从单个网页中提取文本内容。

    Args:
        url: 要提取内容的网页 URL
        extract_depth: 提取深度
            - "basic": 基础提取，获取主要内容
            - "advanced": 高级提取，获取更完整的内容

    Returns:
        提取的网页文本内容（Markdown 格式）
    """
    client = _get_tavily_client()

    response = client.extract(
        urls=[url],
        extract_depth=extract_depth,
    )

    # 提取成功，返回内容
    if response.get("results"):
        result = response["results"][0]
        return result.get("raw_content", "")

    # 提取失败，返回错误信息
    if response.get("failed_results"):
        error = response["failed_results"][0].get("error", "Unknown error")
        return f"error: Failed to extract content from {url}: {error}"

    return f"error: Failed to extract content from {url}"
