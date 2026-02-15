# app/agents/analyzer.py
from __future__ import annotations

"""
Analyzer Node（LLMで「週報向け」情報を付与）

役割：
- deduped_items を入力として、各アイテムに以下を付与する：
  - summary（概要）
  - key_points（要点）
  - insights（示唆）
  - keywords（キーワード）
  - tags（タグ）
  - importance（重要度）

設計意図：
- 週報の価値は「リンク集」より「何が言えるか」にあるため、
  ここで要約と示唆を生成してSlackに載せる。
- dedup後に実行することで、LLMコストを最小化。

運用上の考慮：
- 1件失敗しても全体停止しない（errorsに記録して継続）
- 出力が長くなりすぎないようプロンプト側で制約
"""

from datetime import datetime, timezone
from typing import List

from app.graph.state import WeeklyResearchState, ContentItem
from app.llm.openai_client import OpenAIAnalyzer
from app.utils.logger import get_logger, log_with_run_id

logger = get_logger(__name__)


def analyzer_node(state: WeeklyResearchState) -> WeeklyResearchState:
    run_id = state.get("run_id")
    now = datetime.now(timezone.utc).isoformat()

    items = state.get("deduped_items", [])
    if not items:
        log_with_run_id(logger, "info", run_id, "Analyzer skipped: no items.")
        state["enriched_items"] = []
        return state

    log_with_run_id(logger, "info", run_id, f"Analyzer started: items={len(items)}")

    llm = OpenAIAnalyzer()
    enriched: List[ContentItem] = []

    for idx, it in enumerate(items, start=1):
        title = it.get("title", "")
        venue = it.get("venue", "") or ""
        url = it.get("url", "")
        pub = it.get("published_at") or "unknown"

        try:
            analysis = llm.analyze_item(title=title, venue=venue, url=url, published_at=pub)

            # ---- 週報向けの情報（今回追加）----
            it["summary"] = analysis.summary
            it["key_points"] = analysis.key_points
            it["insights"] = analysis.insights

            # ---- 既存（すでにあった）----
            it["keywords"] = analysis.keywords
            it["tags"] = analysis.tags
            it["importance"] = analysis.importance.model_dump()

            enriched.append(it)

            score = it.get("importance", {}).get("total")
            log_with_run_id(
                logger,
                "info",
                run_id,
                f"Analyzed {idx}/{len(items)}: score={score} title={title[:60]}",
            )

        except Exception as e:
            # 週次運用では「止めない」が正義。原因はerrorsに残す。
            state.setdefault("errors", [])
            state["errors"].append({"node": "analyzer", "error": str(e)})

            log_with_run_id(logger, "error", run_id, f"Analyzer failed {idx}/{len(items)}: {e}")

            # 失敗アイテムも残す（Slack側で欠落を許容する設計にしておく）
            enriched.append(it)

    state["enriched_items"] = enriched

    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "analyzer",
            "action": "attach_digest_fields",
            "rationale": "Attach summary/key_points/insights + keywords/tags/importance via OpenAI Structured Outputs.",
            "payload": {"items": len(items), "model": llm.model},
            "timestamp": now,
        }
    )

    log_with_run_id(logger, "info", run_id, "Analyzer finished.")
    return state
