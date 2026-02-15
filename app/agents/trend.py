# app/agents/trend.py
from __future__ import annotations

"""
Trend Node（週次トレンド分析）

目的：
- 週次ダイジェストに「今週何が伸びたか（rising）」を付ける
- LLMを使わず（コスト0）、ローカルの履歴JSONから差分を計算する

前提：
- analyzerノードが付与した tags / keywords が enriched_items に入っていること
- Memory(Chroma)は「重複排除」に使っているが、過去週の tags をメタに保存していないため、
  トレンド分析はまずローカル履歴（data/trend_history.json）でやる

将来の発展：
- Chromaに tags/keywords をメタデータとして保存する
- 過去記事との類似クラスタリング（topic_clusters）も追加
"""

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from app.graph.state import WeeklyResearchState, TrendStats, ContentItem
from app.utils.logger import get_logger, log_with_run_id

logger = get_logger(__name__)

# 週次履歴の保存先（プロジェクト直下からの相対パス想定）
HISTORY_PATH = "data/trend_history.json"

# 履歴をどれだけ保持するか（増えすぎ防止）
MAX_WEEKS_TO_KEEP = 24

# 表示上位数
TOP_N_TAGS = 8
TOP_N_KEYWORDS = 8
TOP_N_RISING = 6

# トレンドに出したくない「一般語」「メタタグ」
STOP_TAGS = {
    "insights",
    "best-practices",
    "engineering",
    "development",
    "experimentation",
    "self-efficacy",
    "efficiency",
    # ↑ ここは運用で増やしてOK（プロジェクト固有のノイズが必ず出る）
}


def _safe_list(v) -> List[str]:
    """
    tags/keywords が None のこともあり得るので安全にlist化する。
    """
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _load_history() -> Dict[str, dict]:
    """
    週次履歴（JSON）をロードする。
    データが無い場合は空を返す（初回実行想定）。
    """
    if not os.path.exists(HISTORY_PATH):
        return {}

    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        # JSON破損などがあってもパイプライン全体を止めない
        return {}


def _save_history(history: Dict[str, dict]) -> None:
    """
    週次履歴（JSON）を保存する。
    - data/ ディレクトリが無ければ作る
    """
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _week_sort_key(week_id: str) -> Tuple[int, int]:
    """
    week_id: "YYYY-Www" を (YYYY, ww) に分解してソートキーにする。
    不正形は最後に回す。
    """
    try:
        y, w = week_id.split("-W")
        return int(y), int(w)
    except Exception:
        return (0, 0)
    
    
def _normalize_tag(tag: str) -> str:
    tag = tag.strip().lower()
    tag = tag.replace("_", "-")
    tag = tag.replace(" ", "-")
    return tag


def _compute_counts(enriched_items: List[ContentItem]) -> Tuple[Counter, Counter]:
    """
    今週のタグ・キーワード頻度を集計する。
    - タグはトレンドの軸なので重要
    - キーワードは補助（タグよりブレやすい）
    """
    tag_counter: Counter = Counter()
    kw_counter: Counter = Counter()

    for it in enriched_items:
        tags = [_normalize_tag(t) for t in _safe_list(it.get("tags"))]
        tags = [t for t in tags if t and t not in STOP_TAGS]
        tag_counter.update(set(tags))

        kws = _safe_list(it.get("keywords"))

        # 1アイテム内で同じタグ/キーワードが重複する可能性があるため set() で潰す
        tag_counter.update(set(tags))
        kw_counter.update(set(kws))

    return tag_counter, kw_counter


def _delta_vs_prev(current: Counter, prev: Counter) -> List[Dict[str, object]]:
    """
    前週との差分（delta）を計算して、deltaが大きい順に返す。
    """
    deltas: List[Dict[str, object]] = []
    keys = set(current.keys()) | set(prev.keys())

    for k in keys:
        c = int(current.get(k, 0))
        p = int(prev.get(k, 0))
        d = c - p
        if d != 0:
            deltas.append({"key": k, "count": c, "prev": p, "delta": d})

    # delta降順、同率ならcount降順
    deltas.sort(key=lambda x: (x["delta"], x["count"]), reverse=True)
    return deltas


def trend_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    入力:
      - state["enriched_items"] : tags/keywords/importance が付与されたアイテム一覧（今週分）

    出力:
      - state["trend_stats"] : 週次トレンド情報
      - data/trend_history.json に今週の集計結果を保存（次回以降の差分に使う）
    """
    run_id = state.get("run_id")
    week_id = state.get("week_id", "unknown-week")
    now = datetime.now(timezone.utc).isoformat()

    enriched_items = state.get("enriched_items", [])
    if not enriched_items:
        log_with_run_id(logger, "info", run_id, "Trend skipped: no enriched_items.")
        state["trend_stats"] = {"week_id": week_id}
        return state

    log_with_run_id(logger, "info", run_id, f"Trend started: week_id={week_id} items={len(enriched_items)}")

    # (1) 今週の頻度集計
    tag_counter, kw_counter = _compute_counts(enriched_items)

    # (2) 履歴ロード
    history = _load_history()

    # (3) 前週（直近の保存済み週）を特定
    weeks_sorted = sorted(history.keys(), key=_week_sort_key)
    prev_week_id = weeks_sorted[-1] if weeks_sorted else None

    prev_tags = Counter(history.get(prev_week_id, {}).get("tag_counts", {})) if prev_week_id else Counter()
    prev_kws = Counter(history.get(prev_week_id, {}).get("keyword_counts", {})) if prev_week_id else Counter()

    # (4) delta計算（前週比）
    tag_deltas = _delta_vs_prev(tag_counter, prev_tags)
    kw_deltas = _delta_vs_prev(kw_counter, prev_kws)

    # Slack表示用に整形（上位のみ）
    top_tags = [{"tag": k, "count": int(c), "delta": int(c - prev_tags.get(k, 0))} for k, c in tag_counter.most_common(TOP_N_TAGS)]
    top_keywords = [{"keyword": k, "count": int(c), "delta": int(c - prev_kws.get(k, 0))} for k, c in kw_counter.most_common(TOP_N_KEYWORDS)]

    rising = []
    for d in tag_deltas[:TOP_N_RISING]:
        rising.append({"type": "tag", "tag": d["key"], "count": d["count"], "delta": d["delta"], "prev": d["prev"]})

    # (キーワードも載せたいなら追加。まずはタグ中心で十分)
    # for d in kw_deltas[:TOP_N_RISING]:
    #     rising.append({"type": "keyword", "keyword": d["key"], "count": d["count"], "delta": d["delta"], "prev": d["prev"]})

    # (5) stateに格納（TrendStats）
    trend_stats: TrendStats = {
        "week_id": week_id,
        "top_tags": top_tags,
        "top_keywords": top_keywords,
        "rising": rising,
        "topic_clusters": [],  # 将来拡張（クラスタリング）用の空枠
    }
    state["trend_stats"] = trend_stats

    # (6) 履歴更新（今週分を保存）
    history[week_id] = {
        "saved_at": now,
        "tag_counts": dict(tag_counter),
        "keyword_counts": dict(kw_counter),
        "items": len(enriched_items),
        "prev_week_id": prev_week_id,
    }

    # (7) 履歴の世代管理（増えすぎ防止）
    weeks_sorted = sorted(history.keys(), key=_week_sort_key)
    if len(weeks_sorted) > MAX_WEEKS_TO_KEEP:
        to_drop = weeks_sorted[:-MAX_WEEKS_TO_KEEP]
        for w in to_drop:
            history.pop(w, None)

    _save_history(history)

    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "trend",
            "action": "compute_weekly_trend",
            "rationale": "Compute tag/keyword frequency trend vs previous saved week and store history locally.",
            "payload": {"week_id": week_id, "prev_week_id": prev_week_id, "items": len(enriched_items)},
            "timestamp": now,
        }
    )

    log_with_run_id(
        logger,
        "info",
        run_id,
        f"Trend finished: prev_week={prev_week_id} top_tag={top_tags[0]['tag'] if top_tags else '-'}",
    )
    return state
