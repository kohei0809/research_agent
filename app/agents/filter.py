# app/agents/filter.py
from __future__ import annotations

from datetime import datetime, timezone

from app.graph.state import WeeklyResearchState, ContentItem


KEYWORDS = [
    "agent",
    "agentic",
    "multi-agent",
    "tool",
    "tool use",
    "workflow",
    "orchestration",
    "langgraph",
    "mcp",
    "a2a",
]


def _is_relevant(item: ContentItem) -> bool:
    text = f"{item.get('title','')} {item.get('venue','')}".lower()
    return any(k in text for k in KEYWORDS)


def filter_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    TODO: ここは将来的にLLM分類（+ルール併用）に置き換える。
    いまは軽量なルールフィルタで動作確認。
    """
    now = datetime.now(timezone.utc).isoformat()
    items = state.get("collected_items", [])

    filtered = [it for it in items if _is_relevant(it)]
    state["filtered_items"] = filtered
    # MVPではこの時点で通知候補にする（後でdedup/memoryへ拡張）
    state["deduped_items"] = filtered

    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "filter",
            "action": "filter_relevant_items",
            "rationale": "Rule-based filtering on title/venue for MVP.",
            "payload": {"in": len(items), "out": len(filtered)},
            "timestamp": now,
        }
    )
    return state
