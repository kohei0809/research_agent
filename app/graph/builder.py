# app/graph/builder.py
from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graph.state import WeeklyResearchState, ensure_state_defaults
from app.agents.collector import collector_node
from app.agents.filter import filter_node
from app.notifier.slack_notifier import slack_notify_node


def build_graph() -> StateGraph:
    """
    MVP: Collector -> Filter -> Slack
    """
    graph = StateGraph(WeeklyResearchState)

    graph.add_node("collector", collector_node)
    graph.add_node("filter", filter_node)
    graph.add_node("slack_notify", slack_notify_node)

    graph.set_entry_point("collector")
    graph.add_edge("collector", "filter")
    graph.add_edge("filter", "slack_notify")
    graph.add_edge("slack_notify", END)

    return graph


def run_graph(initial_state: WeeklyResearchState) -> WeeklyResearchState:
    """
    手動実行用ヘルパー。compileしてinvokeするだけ。
    """
    initial_state = ensure_state_defaults(initial_state)
    app = build_graph().compile()
    return app.invoke(initial_state)
