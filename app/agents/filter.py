# app/agents/filter.py
from __future__ import annotations

"""
Filter Node（関連度フィルタ）

役割：
- 収集した論文/記事の中から「AIエージェント（やシステム開発）関連」に絞る。
- MVPでは軽量なルールで絞る（タイトルや媒体名に含まれるキーワードで判定）。

将来：
- LLM分類（+ルール）に置き換える
- 例えば "Agentic", "Tool Use", "Workflow", "RAG", "Orchestration" を広めに拾う等
"""

from datetime import datetime, timezone
from app.graph.state import WeeklyResearchState, ContentItem


# MVP: ルール判定用キーワード（将来は外部設定化してもOK）
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
    """
    ルールベースの関連度判定。
    - title + venue を連結し、小文字化して単純包含でチェックする
    """
    text = f"{item.get('title','')} {item.get('venue','')}".lower()
    return any(k in text for k in KEYWORDS)


def filter_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    Node処理：
    - State.collected_items を入力として
    - State.filtered_items に「関連あり」だけ出す
    - いまは後段が少ないので deduped_items にも同じものを入れておく
      （後で memory/dedup が入ると deduped_items が本命になる）
    """
    now = datetime.now(timezone.utc).isoformat()

    items = state.get("collected_items", [])
    filtered = [it for it in items if _is_relevant(it)]

    state["filtered_items"] = filtered

    # MVPの都合で一旦ここでも deduped_items を埋める。
    # ただし、memory_dedup_node が入った構成では
    # 後段で deduped_items が上書きされる（＝最終結果になる）。
    state["deduped_items"] = filtered

    # A2A決定ログ
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
