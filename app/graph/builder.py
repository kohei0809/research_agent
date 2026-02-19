# app/graph/builder.py
from __future__ import annotations

"""
LangGraph のグラフ定義（Trend追加版）。

パイプライン（現状）：
  collector -> filter -> memory -> analyzer -> trend -> slack_notify -> END

順序の意図：
- memory（重複排除）で候補を絞ってから analyzer（LLM）に回し、コスト最小化
- analyzerで tags/keywords/importance が付いた後に trend を実行し、
  今週の分布と前週との差分（rising）を計算する
- slack_notify で trend + items をまとめて通知する
"""

from langgraph.graph import StateGraph, END

from app.graph.state import WeeklyResearchState, ensure_state_defaults
#from app.agents.collector import collector_node
from app.agents.collector_mcp import collector_node
from app.agents.filter import filter_node
from app.agents.memory_agent import memory_dedup_node
from app.agents.analyzer import analyzer_node
from app.agents.trend import trend_node
from app.notifier.slack_notifier import slack_notify_node


def build_graph() -> StateGraph:
    graph = StateGraph(WeeklyResearchState)

    graph.add_node("collector", collector_node)
    graph.add_node("filter", filter_node)
    graph.add_node("memory", memory_dedup_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("trend", trend_node)
    graph.add_node("slack_notify", slack_notify_node)

    graph.set_entry_point("collector")

    graph.add_edge("collector", "filter")
    graph.add_edge("filter", "memory")
    graph.add_edge("memory", "analyzer")
    graph.add_edge("analyzer", "trend")
    graph.add_edge("trend", "slack_notify")
    graph.add_edge("slack_notify", END)

    return graph


def run_graph(initial_state: WeeklyResearchState) -> WeeklyResearchState:
    initial_state = ensure_state_defaults(initial_state)
    app = build_graph().compile()
    return app.invoke(initial_state)
