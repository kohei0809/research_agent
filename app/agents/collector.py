# app/agents/collector.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from app.graph.state import WeeklyResearchState, ContentItem


def collector_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    TODO: MCP4種（arxiv/web/search/file）を使って収集する。
    いまは動作確認用にダミーデータを入れる。
    """
    now = datetime.now(timezone.utc).isoformat()

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

    state.setdefault("collected_items", [])
    state["collected_items"].extend(dummy)

    # A2A向けの決定ログ（任意）
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
