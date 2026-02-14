# app/agents/analyzer.py
from __future__ import annotations

"""
Analyzer Node（LLMで分析付与）

役割：
- 重複排除後の候補（State.deduped_items）に対して、
  keywords / tags / importance を付与する。
- 付与済みの結果を State.enriched_items に保存する。
  （以降のトレンド分析/要約/示唆生成/Slack出力で利用）

なぜdedup後に実行する？
- LLMコストを抑えるため（重複候補に課金しない）
- 週報に載せる候補にだけ分析を集中するため

MVP実装の方針：
- 1アイテム = 1 APIコール（分かりやすさ優先）
- 失敗しても全体を落とさず、errorsに記録して継続
"""

from datetime import datetime, timezone
from typing import List

from app.graph.state import WeeklyResearchState, ContentItem
from app.llm.openai_client import OpenAIAnalyzer
from app.utils.logger import get_logger, log_with_run_id

logger = get_logger(__name__)


def analyzer_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    入力:
      - state["deduped_items"] : 重複排除済み候補リスト

    出力:
      - state["enriched_items"] : keywords/tags/importance が付与されたリスト
      - state["errors"]         : 失敗があれば追記
      - state["decisions"]      : A2Aログ（任意）
    """
    run_id = state.get("run_id")
    now = datetime.now(timezone.utc).isoformat()

    items = state.get("deduped_items", [])

    # 候補がなければ何もしない（Slack側で「なし」を出す）
    if not items:
        log_with_run_id(logger, "info", run_id, "Analyzer skipped: no items.")
        state["enriched_items"] = []
        return state

    log_with_run_id(logger, "info", run_id, f"Analyzer started: items={len(items)}")

    # OpenAI解析クライアント（modelは環境変数OPENAI_MODELで切替可）
    llm = OpenAIAnalyzer()

    enriched: List[ContentItem] = []

    # 1件ずつ解析（MVP）
    for idx, it in enumerate(items, start=1):
        title = it.get("title", "")
        venue = it.get("venue", "") or ""
        url = it.get("url", "")
        pub = it.get("published_at") or "unknown"

        try:
            # LLMに「構造化」出力で返させる
            analysis = llm.analyze_item(title=title, venue=venue, url=url, published_at=pub)

            # Stateのアイテムに付与（後続が使う）
            it["keywords"] = analysis.keywords
            it["tags"] = analysis.tags

            # Pydantic→dict（Stateは基本dictで持ち回す方針）
            it["importance"] = analysis.importance.model_dump()

            enriched.append(it)

            # 進捗ログ
            log_with_run_id(
                logger,
                "info",
                run_id,
                f"Analyzed {idx}/{len(items)}: score={it['importance'].get('total')} title={title[:60]}",
            )

        except Exception as e:
            # 1件失敗しても全体停止させない（週次バッチで重要）
            state.setdefault("errors", [])
            state["errors"].append({"node": "analyzer", "error": str(e)})

            log_with_run_id(
                logger,
                "error",
                run_id,
                f"Analyzer failed {idx}/{len(items)}: {e}",
            )

            # 失敗したアイテムも残しておく（後で再処理/原因分析しやすい）
            enriched.append(it)

    # enriched_items をStateに保存
    state["enriched_items"] = enriched

    # A2A的に「何をしたか」を記録（任意）
    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "analyzer",
            "action": "attach_keywords_tags_importance",
            "rationale": "Use OpenAI Structured Outputs to attach keywords/tags/importance per item.",
            "payload": {"items": len(items), "model": llm.model},
            "timestamp": now,
        }
    )

    log_with_run_id(logger, "info", run_id, "Analyzer finished.")
    return state
