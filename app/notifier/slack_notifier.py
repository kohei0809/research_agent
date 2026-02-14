# app/notifier/slack_notifier.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List

import requests

from app.graph.state import WeeklyResearchState, ContentItem


def _build_digest_md(items: List[ContentItem], week_id: str) -> str:
    lines = []
    lines.append(f"*Weekly AI Agent Digest*  (`{week_id}`)")
    lines.append("")

    if not items:
        lines.append("_No relevant items found this run._")
        return "\n".join(lines)

    for i, it in enumerate(items, start=1):
        title = it.get("title", "(no title)")
        url = it.get("url", "")
        source = it.get("source_type", "other")
        pub = it.get("published_at") or "unknown"
        lines.append(f"*{i}.* [{title}]({url})")
        lines.append(f"• source: `{source}`  • published: `{pub}`")
        lines.append("")
    return "\n".join(lines)


def slack_notify_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    Slackへ通知（Incoming Webhook）。
    環境変数 SLACK_WEBHOOK_URL を使用。
    """
    now = datetime.now(timezone.utc).isoformat()
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()

    week_id = state.get("week_id", "unknown-week")
    items = state.get("deduped_items", state.get("filtered_items", []))

    digest_md = _build_digest_md(items, week_id)
    state["digest_markdown"] = digest_md

    if not webhook_url:
        # Webhookが未設定なら送信せずに結果だけ残す（ローカル確認用）
        state.setdefault("errors", [])
        state["errors"].append(
            {"node": "slack_notify", "error": "SLACK_WEBHOOK_URL is not set. Skipped posting."}
        )
        state["slack_post_result"] = {"ok": False, "skipped": True}
        return state

    resp = requests.post(webhook_url, json={"text": digest_md}, timeout=20)
    ok = 200 <= resp.status_code < 300

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
