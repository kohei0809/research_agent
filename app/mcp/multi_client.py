# app/mcp/multi_client.py
from __future__ import annotations

"""
langchain-mcp-adapters 0.1.0 対応のMCP呼び出しユーティリティ。

重要：
- MultiServerMCPClient は async context manager に非対応
- サーバーごとに `client.session(server_name)` を開いてツールを呼ぶ

参考（エラー文の指示そのまま）：
1) client = MultiServerMCPClient(...)
   tools = await client.get_tools()
2) client = MultiServerMCPClient(...)
   async with client.session(server_name) as session:
       tools = await load_mcp_tools(session)
"""

import os
from typing import Any, Dict, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


def _tools_list_to_dict(tools: List[Any]) -> Dict[str, Any]:
    """
    langchain-mcp-adapters の load_mcp_tools は List[Tool] を返す。
    ここを {tool.name: tool} に正規化して使いやすくする。
    """
    out: Dict[str, Any] = {}
    for t in tools:
        name = getattr(t, "name", None)
        if not name:
            # 念のため：name が無いツールはスキップ
            continue
        out[name] = t
    return out


def build_mcp_server_config() -> Dict[str, Dict[str, Any]]:
    """
    4つのMCPサーバー構成（あなたの要望に合わせる）
    - arxiv   : arXiv API
    - rss     : RSS/Atom
    - scrape  : Blogスクレイピング
    - twitter : Twitterトピック
    """
    return {
        "arxiv":   {"transport": "stdio", "command": "uvx", "args": ["arxiv-mcp-server"]},
        "rss":     {"transport": "stdio", "command": os.getenv("MCP_RSS_CMD", "npx"),     "args": os.getenv("MCP_RSS_ARGS", "rss-mcp").split()},
        "scrape":  {"transport": "stdio", "command": os.getenv("MCP_SCRAPE_CMD", "npx"),  "args": ["-y", "@playwright/mcp"]},
    }


async def list_tools(client: MultiServerMCPClient, server: str) -> Dict[str, Dict[str, str]]:
    """
    指定サーバのツール一覧を返す（ツール名 -> {description}）。
    """
    async with client.session(server) as session:
        tools_list = await load_mcp_tools(session)  # ← List[Tool]
        tools_dict = _tools_list_to_dict(tools_list)

    return {
        name: {"description": getattr(tool, "description", "") or ""}
        for name, tool in tools_dict.items()
    }

async def call_tool(
    client: MultiServerMCPClient,
    server: str,
    tool_name: str,
    tool_args: Dict[str, Any],
) -> Any:
    """
    指定サーバの tool_name を実行する。
    """
    async with client.session(server) as session:
        tools_list = await load_mcp_tools(session)  # ← List[Tool]
        tools_dict = _tools_list_to_dict(tools_list)

        tool = tools_dict.get(tool_name)
        if tool is None:
            available = sorted(tools_dict.keys())
            raise KeyError(
                f"Tool '{tool_name}' not found on server '{server}'. Available: {available}"
            )

        # LangChain Tool 互換：ainvoke があれば ainvoke、なければ invoke を試す
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(tool_args)
        if hasattr(tool, "invoke"):
            return tool.invoke(tool_args)

        # 最後の保険
        raise TypeError(f"Tool '{tool_name}' does not support invoke/ainvoke")
    