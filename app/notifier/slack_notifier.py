# app/notifier/slack_notifier.py
from __future__ import annotations

"""
Slack Notifier Node

役割：
- Stateに入っている最終候補（deduped_items）をMarkdownに整形し、Slackへ投稿する
- Incoming Webhook を使う（MVPで一番簡単）

将来：
- Slack App（chat.postMessage）に移行すれば、スレッド返信やファイル添付も可能
"""

import os
from datetime import datetime, timezone
from typing import List

import requests

from app.graph.state import WeeklyResearchState, ContentItem


def _build_digest_md(items: List[ContentItem], week_id: str, trend_stats: dict | None = None) -> str:
    """
    Slack投稿用Markdownを生成（週報完成形に近づけた版）。

    表示構成：
    1) Trend（Rising / Top Tags）
    2) Items（タイトル/URL/スコア/タグ）
       - summary（短い概要）
       - insights（示唆：最大3）

    NOTE:
    - Slackは長いと読まれないので、summaryは短く、insightsも少数に制限する
    - analyzerが失敗したアイテムは summary/insights が無いことがあるので安全に扱う
    """
    lines = []
    lines.append(f"*Weekly AI Agent Digest*  (`{week_id}`)")
    lines.append("")

    # ---------------------------
    # Trend summary (optional)
    # ---------------------------
    if trend_stats:
        rising = trend_stats.get("rising") or []
        top_tags = trend_stats.get("top_tags") or []

        lines.append("*🔥 Rising Tags (vs previous saved week)*")
        if not rising:
            lines.append("• _No significant changes detected._")
        else:
            for r in rising[:6]:
                tag = r.get("tag", "-")
                delta = r.get("delta", 0)
                sign = "+" if isinstance(delta, int) and delta > 0 else ""
                lines.append(f"• `{tag}` ({sign}{delta})")
        lines.append("")

        lines.append("*📊 Top Tags This Week*")
        if not top_tags:
            lines.append("• _No tags found._")
        else:
            for t in top_tags[:8]:
                tag = t.get("tag", "-")
                count = t.get("count", 0)
                delta = t.get("delta", 0)
                sign = "+" if isinstance(delta, int) and delta > 0 else ""
                lines.append(f"• `{tag}`: {count} ({sign}{delta})")
        lines.append("")
        lines.append("---")
        lines.append("")
        
    # スコアでMust Readを抽出（閾値は運用で調整）
    MUST_READ_THRESHOLD = 19.0
    must_read = []
    others = []

    for it in items:
        score = (it.get("importance") or {}).get("total")
        if isinstance(score, (int, float)) and score >= MUST_READ_THRESHOLD:
            must_read.append(it)
        else:
            others.append(it)

    # Must Read があれば先頭に短く載せる
    if must_read:
        lines.append("*⭐ Must Read This Week*")
        for it in must_read[:5]:
            title = it.get("title", "(no title)")
            url = it.get("url", "")
            score = (it.get("importance") or {}).get("total")
            lines.append(f"• [{title}]({url})  (score: *{score:.1f}/25*)")
        lines.append("")
        lines.append("---")
        lines.append("")


    # ---------------------------
    # Items list
    # ---------------------------
    items = must_read + others
    if not items:
        lines.append("_No relevant items found this run._")
        return "\n".join(lines)

    for i, it in enumerate(items, start=1):
        title = it.get("title", "(no title)")
        url = it.get("url", "")
        source = it.get("source_type", "other")
        pub = it.get("published_at") or "unknown"

        tags = it.get("tags") or []
        importance = it.get("importance") or {}
        score = importance.get("total")

        summary = (it.get("summary") or "").strip()
        insights = it.get("insights") or []

        tag_str = ", ".join(tags[:6]) if tags else "-"
        score_str = f"{score:.1f}/25" if isinstance(score, (int, float)) else "-"

        lines.append(f"*{i}.* [{title}]({url})")
        lines.append(f"• source: `{source}`  • published: `{pub}`")
        lines.append(f"• score: *{score_str}*  • tags: `{tag_str}`")

        # summary（短めを想定。念のため長すぎたら切る）
        if summary:
            if len(summary) > 220:
                summary = summary[:220] + "…"
            lines.append(f"• summary: {summary}")

        # insights（最大3）
        if insights:
            lines.append("• insights:")
            for ins in insights[:3]:
                ins = str(ins).strip()
                if not ins:
                    continue
                if len(ins) > 140:
                    ins = ins[:140] + "…"
                lines.append(f"  - {ins}")

        lines.append("")  # 1アイテムごとに空行

    return "\n".join(lines)

def slack_notify_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    Node処理：
    1) deduped_items（なければ filtered_items）からダイジェストMarkdown作成
    2) SLACK_WEBHOOK_URL があればSlackへ送る
    3) 結果を slack_post_result に保存
    """
    now = datetime.now(timezone.utc).isoformat()

    # Slack Incoming Webhook URL（環境変数）
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()

    week_id = state.get("week_id", "unknown-week")

    # 通知対象は analyzer の結果（enriched_items）を最優先。
    # analyzerが失敗した場合にも動くように deduped_items / filtered_items にフォールバックする。
    items = (
        state.get("enriched_items")
        or state.get("deduped_items")
        or state.get("filtered_items")
        or []
    )

    # slack_notify_node の中で、digest_md を作る行を置き換え
    trend_stats = state.get("trend_stats")
    digest_md = _build_digest_md(items, week_id, trend_stats=trend_stats)
    state["digest_markdown"] = digest_md

    # Webhookが未設定なら送信しない（ローカル検証用）
    if not webhook_url:
        state.setdefault("errors", [])
        state["errors"].append(
            {"node": "slack_notify", "error": "SLACK_WEBHOOK_URL is not set. Skipped posting."}
        )
        state["slack_post_result"] = {"ok": False, "skipped": True}
        return state

    # Slackへ投稿
    resp = requests.post(webhook_url, json={"text": digest_md}, timeout=20)
    ok = 200 <= resp.status_code < 300

    # 成功/失敗をStateに残す（運用/デバッグのため）
    state["slack_post_result"] = {
        "ok": ok,
        "status_code": resp.status_code,
        "response_text": resp.text[:500],
        "timestamp": now,
    }

    if not ok:
        state.setdefault("errors", [])
        state["errors"].append(
            {"node": "slack_notify", "error": f"Slack post failed: {resp.status_code} {resp.text[:200]}"}
        )

    # A2Aログ（任意）
    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "notifier",
            "action": "post_to_slack",
            "rationale": "Post digest markdown via Slack Incoming Webhook.",
            "payload": {"items": len(items), "ok": ok},
            "timestamp": now,
        }
    )
    return state
