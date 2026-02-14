# app/graph/state.py
from __future__ import annotations

from typing import TypedDict, List, Dict, Optional, Literal


# ----------------------------
# Domain Types
# ----------------------------

SourceType = Literal["arxiv", "web", "news", "blog", "search", "other"]


class ImportanceRating(TypedDict, total=False):
    """
    重要度スコア（0〜25想定。各軸1〜5）
    """
    total: float # 合計点
    novelty: int # 技術的新規制
    practicality: int # 実用可能性
    reproducibility: int # 再現性
    impact: int # 影響性
    buzz: int # 話題性
    rationale: str  # 1〜3文の根拠


class ContentItem(TypedDict, total=False):
    """
    論文/記事の共通表現。
    MCPから取った生情報(raw_metadata)を保持しつつ、
    後段で要約やタグ等を付与していく。
    """
    # Identity
    item_id: str                 # 例: sha256(url) or "arxiv:xxxx.yyyyy"
    source_type: SourceType
    title: str
    url: str

    # Metadata
    published_at: Optional[str]  # ISO date string "2026-02-14" (unknown ok)
    authors: Optional[List[str]]
    venue: Optional[str]         # 例: "arXiv cs.AI", "OpenAI Blog" 等

    # Extracted/Generated
    extracted_text: Optional[str]       # 必要ならHTML/PDFから抽出
    summary: Optional[str]              # 1-2段落の要約
    key_points: Optional[List[str]]     # 箇条書きの重要点
    keywords: Optional[List[str]]       # 抽出キーワード（重複可）
    tags: Optional[List[str]]           # 正規化タグ（推奨）
    importance: Optional[ImportanceRating]
    insights: Optional[List[str]]       # 実装/研究/運用の示唆など

    # Ops
    raw_metadata: Optional[Dict[str, object]]   # MCP取得の生データ
    dedup: Optional[Dict[str, object]]          # {"is_duplicate": bool, "score": float, "nearest_id": str}


class TrendStats(TypedDict, total=False):
    """
    週次のトレンド分析結果。
    """
    week_id: str  # "YYYY-Www"
    top_keywords: List[Dict[str, object]]   # [{"keyword": "...", "count": 12, "delta": +5}, ...]
    top_tags: List[Dict[str, object]]       # [{"tag": "...", "count": 8, "delta": +3}, ...]
    rising: List[Dict[str, object]]         # 急上昇 (keyword/tag混在でもOK)
    topic_clusters: List[Dict[str, object]] # [{"cluster": "tool-use", "items": [...], "summary": "..."}]


class AgentDecision(TypedDict, total=False):
    """
    A2A前提の“決定ログ”。どのエージェントが何を決めたか残す。
    """
    agent: str                 # "collector" | "filter" | "analyzer" | ...
    action: str                # "selected_sources" | "scored_items" | ...
    rationale: str
    payload: Dict[str, object]
    timestamp: str             # ISO datetime string


# ----------------------------
# LangGraph State
# ----------------------------

class WeeklyResearchState(TypedDict, total=False):
    """
    週次ダイジェスト生成パイプラインのLangGraph State。
    ノードはこのStateを受け取り、必要なキーを追加/更新する。
    """

    # Run control
    run_id: str                # UUID
    week_id: str               # "YYYY-Www"
    started_at: str            # ISO datetime
    mode: str                  # "manual" / "scheduled" (将来用)

    # Collection / processing
    collected_items: List[ContentItem]   # MCPで集めた生アイテム（未フィルタ）
    filtered_items: List[ContentItem]    # relevance filter後
    enriched_items: List[ContentItem]    # キーワード/タグ/重要度/要約/示唆等を付与

    # Memory / dedup
    seen_item_ids: List[str]             # 過去配信済みID等（Chroma/JSONからロード）
    deduped_items: List[ContentItem]     # 重複除去後（最終候補）
    memory_write_results: Dict[str, object]  # {"stored": n, "skipped": m, ...}

    # Analytics / output
    trend_stats: TrendStats              # トレンド分析結果
    digest_markdown: str                 # Slack投稿用 Markdown
    slack_post_result: Dict[str, object] # Slack APIレスポンスやstatus

    # A2A log
    decisions: List[AgentDecision]

    # Diagnostics
    errors: List[Dict[str, str]]         # [{"node": "...", "error": "..."}]
    debug: Dict[str, object]             # 任意の中間情報


# ----------------------------
# Helpers (optional)
# ----------------------------

def ensure_state_defaults(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    ノード実装を楽にするためのデフォルト埋め。
    LangGraphは部分Stateでも動くが、リスト系は空で初期化すると扱いやすい。
    """
    state.setdefault("collected_items", [])
    state.setdefault("filtered_items", [])
    state.setdefault("enriched_items", [])
    state.setdefault("seen_item_ids", [])
    state.setdefault("deduped_items", [])
    state.setdefault("memory_write_results", {})
    state.setdefault("trend_stats", {"week_id": state.get("week_id", "")})
    state.setdefault("digest_markdown", "")
    state.setdefault("slack_post_result", {})
    state.setdefault("decisions", [])
    state.setdefault("errors", [])
    state.setdefault("debug", {})
    return state
