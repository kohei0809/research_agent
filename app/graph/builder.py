# app/graph/builder.py
from __future__ import annotations

"""
LangGraph のグラフ定義（拡張版）。

今回の追加：
- memory（重複排除）後に analyzer（LLM分析）を挿入した。

パイプライン（現状）：
  collector -> filter -> memory -> analyzer -> slack_notify -> END

今後の拡張予定：
- trend（週次トレンド分析）
- summarizer（要約）
- insight（示唆生成）
- MCPによるcollector実装（現状はダミー）
"""

from langgraph.graph import StateGraph, END

from app.graph.state import WeeklyResearchState, ensure_state_defaults
from app.agents.collector import collector_node
from app.agents.filter import filter_node
from app.agents.memory_agent import memory_dedup_node
from app.agents.analyzer import analyzer_node
from app.notifier.slack_notifier import slack_notify_node


def build_graph() -> StateGraph:
    """
    グラフ構築（順序がそのまま処理順）。

    - analyzerを memory の後に置く理由：
      重複排除後の「本当に必要なアイテム」にだけLLMコストを払うため。
    """
    graph = StateGraph(WeeklyResearchState)

    graph.add_node("collector", collector_node)
    graph.add_node("filter", filter_node)
    graph.add_node("memory", memory_dedup_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("slack_notify", slack_notify_node)

    graph.set_entry_point("collector")

    graph.add_edge("collector", "filter")
    graph.add_edge("filter", "memory")
    graph.add_edge("memory", "analyzer")
    graph.add_edge("analyzer", "slack_notify")
    graph.add_edge("slack_notify", END)

    return graph


def run_graph(initial_state: WeeklyResearchState) -> WeeklyResearchState:
    """
    手動実行用のヘルパー。

    ensure_state_defaults():
      - list/dictを空で埋めておくことでノード実装がシンプルになる
    """
    initial_state = ensure_state_defaults(initial_state)
    app = build_graph().compile()
    return app.invoke(initial_state)
