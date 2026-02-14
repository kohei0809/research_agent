# app/agents/collector.py
from __future__ import annotations

"""
Collector Node（収集ノード）

役割：
- MCP（arXiv / web / search / file）から最新・話題の論文/記事を収集し、
  State.collected_items に追加する。

現状：
- まずパイプラインを動かすことを優先し、ダミーデータを返している。
- 次ステップでMCP連携に差し替える。
"""

from datetime import datetime, timezone
from typing import List

from app.graph.state import WeeklyResearchState, ContentItem


def collector_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    LangGraphノード関数（Stateを受け取り、Stateを返す）。
    """
    now = datetime.now(timezone.utc).isoformat()

    # NOTE: 実運用ではここでMCPを呼び出し、収集対象（論文/記事）を増やす。
    # - arXiv: "agent", "tool use", "workflow", "langgraph" などで検索
    # - web/blog/news: RSSや検索結果から収集
    # - search: 横断検索（話題の拾い漏れ対策）
    # - file: 収集ログや設定ファイルの読み書き等（将来）
    dummy: List[ContentItem] = [
        {
            "item_id": "arxiv:dummy-0001",
            "source_type": "arxiv",
            "title": "Dummy Paper: Agentic Systems with Tool Use",
            "url": "https://arxiv.org/abs/0000.00001",
            "published_at": "2026-02-10",
            "venue": "arXiv cs.AI",
            "raw_metadata": {"fetched_at": now, "query": "agent tool use"},
        },
        {
            "item_id": "web:dummy-0002",
            "source_type": "web",
            "title": "Dummy Blog: Building Reliable AI Agents",
            "url": "https://example.com/blog/reliable-agents",
            "published_at": "2026-02-12",
            "venue": "Example Blog",
            "raw_metadata": {"fetched_at": now, "query": "reliable agents"},
        },
    ]

    # collected_items は「未フィルタの収集結果」置き場。
    # 後段の filter ノードがここから必要なものだけ抽出する。
    state.setdefault("collected_items", [])
    state["collected_items"].extend(dummy)

    # A2A向けに「何をしたか」を残すと、後から分析しやすい（任意）
    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "collector",
            "action": "collect_items",
            "rationale": "MVP: using dummy items before MCP integration.",
            "payload": {"count": len(dummy)},
            "timestamp": now,
        }
    )
    return state
