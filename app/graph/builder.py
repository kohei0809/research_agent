# app/graph/builder.py
from __future__ import annotations

"""
LangGraph のグラフ定義。

このプロジェクトでは、週次（将来は土曜定期）で
「収集 → フィルタ → 重複排除/記憶 → Slack通知」
のパイプラインを実行する。

まずはMVPとして最小構成を組み、
後から「要約」「キーワード/タグ」「重要度」「トレンド」等のノードを追加する。
"""

from langgraph.graph import StateGraph, END

from app.graph.state import WeeklyResearchState, ensure_state_defaults
from app.agents.collector import collector_node
from app.agents.filter import filter_node
from app.agents.memory_agent import memory_dedup_node
from app.notifier.slack_notifier import slack_notify_node


def build_graph() -> StateGraph:
    """
    グラフ構築：
      collector -> filter -> memory -> slack_notify -> END

    - collector: MCP等で情報収集（現状はダミー）
    - filter: AIエージェント関連だけ残す（現状はルール）
    - memory: Chromaで重複排除 + 保存
    - slack_notify: 週次ダイジェストをSlackへ送信
    """
    graph = StateGraph(WeeklyResearchState)

    # ノード登録（ノード名はログやエラー箇所特定に使うので分かりやすく）
    graph.add_node("collector", collector_node)
    graph.add_node("filter", filter_node)
    graph.add_node("memory", memory_dedup_node)
    graph.add_node("slack_notify", slack_notify_node)

    # 入口ノード（起点）
    graph.set_entry_point("collector")

    # ノード間の遷移（順番）
    graph.add_edge("collector", "filter")
    graph.add_edge("filter", "memory")
    graph.add_edge("memory", "slack_notify")

    # 最終ノードから終了
    graph.add_edge("slack_notify", END)

    return graph


def run_graph(initial_state: WeeklyResearchState) -> WeeklyResearchState:
    """
    手動実行用のヘルパー。
    - compile()して invoke()するだけだが、main.py から呼び出しやすいように分離している。

    注意：
    - LangGraphはStateの一部が欠けていても動くが、
      list/dictが未初期化だとノード側で扱いづらいので ensure_state_defaults() で空を埋める。
    """
    initial_state = ensure_state_defaults(initial_state)
    app = build_graph().compile()
    return app.invoke(initial_state)
