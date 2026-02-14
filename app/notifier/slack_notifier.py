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


def _build_digest_md(items: List[ContentItem], week_id: str) -> str:
    """
    Slack投稿用Markdownを生成。
    MVPでは「タイトル + URL + source + publish日」程度。
    次ステップで summary / insights / rating / tags を追加する。
    """
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

        # Slackでは [text](url) がリンクとして扱える
        lines.append(f"*{i}.* [{title}]({url})")
        lines.append(f"• source: `{source}`  • published: `{pub}`")
        lines.append("")
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

    # 通知対象は、重複排除済みの deduped_items を優先する
    items = state.get("deduped_items", state.get("filtered_items", []))

    digest_md = _build_digest_md(items, week_id)
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
