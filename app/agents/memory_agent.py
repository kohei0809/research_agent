# app/agents/memory_agent.py
from __future__ import annotations

"""
Memory / Dedup Node（検証しやすい版）

目的：
- 過去に保存したアイテムと比較して、重複候補を除外する
- MVPの検証では「確実に重複が弾かれる」ことが重要

この版の方針：
1) まず "item_id 一致" で重複判定（確実）
2) 次に "url 一致" で重複判定（確実）
3) 最後に「類似検索（distance閾値）」で重複判定（補助）

これで、同じURL/同じIDのアイテムは2回目に必ず弾かれる。
"""

from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any

from app.graph.state import WeeklyResearchState, ContentItem
from app.memory.chroma_store import ChromaStore
from app.utils.logger import get_logger, log_with_run_id

logger = get_logger(__name__)


def _item_text_for_embedding(item: ContentItem) -> str:
    """
    類似検索用の埋め込みテキスト。
    MVPでは title + venue で十分。
    """
    title = item.get("title", "")
    venue = item.get("venue", "")
    return f"{title}\n{venue}".strip()


def memory_dedup_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    フロー：
    1) Chromaを開く
    2) 保存済みの item_id を読み出す（seen_item_ids）
    3) URL一致判定を行うため、近傍検索で候補のmetadata(url)を取得して比較
    4) 重複でないものだけ deduped_items に残す
    5) deduped_items を Chroma に保存
    """
    run_id = state.get("run_id")
    now = datetime.now(timezone.utc).isoformat()

    store = ChromaStore(
        persist_dir="data/chroma_db",
        collection_name="weekly_items",
    )

    # 保存済みID一覧（確実な重複判定のため）
    seen_ids = set(store.get_all_ids())
    state["seen_item_ids"] = list(seen_ids)

    candidates = state.get("filtered_items", [])
    deduped: List[ContentItem] = []

    log_with_run_id(logger, "info", run_id, f"Memory/Dedup started: candidates={len(candidates)} seen_ids={len(seen_ids)}")

    def is_duplicate(item: ContentItem) -> Tuple[bool, float, str, str]:
        """
        戻り値：
          (is_duplicate, distance, nearest_id, reason)

        reason はデバッグしやすいように残す：
        - "id_match"
        - "url_match"
        - "similarity_threshold"
        - "not_duplicate"
        """
        item_id = item.get("item_id", "")
        url = item.get("url", "")

        # (1) item_id一致：最も確実
        if item_id and item_id in seen_ids:
            return True, 0.0, item_id, "id_match"

        # (2) 類似検索して、最も近い1件のmetadata(url)と比較
        #     URL一致なら確実に重複扱い（例：タイトルが少し変わっても弾ける）
        text = _item_text_for_embedding(item)
        res: Dict[str, Any] = store.query_similar(text, n_results=1)

        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]  # Chromaはqueryでmetadatasが返ることが多い

        nearest_id = ids[0] if ids else ""
        dist = float(dists[0]) if dists else 999.0
        nearest_url = ""
        if metas and isinstance(metas[0], dict):
            nearest_url = str(metas[0].get("url", ""))

        if url and nearest_url and url == nearest_url:
            return True, dist, nearest_id, "url_match"

        # (3) 最後に距離閾値（補助）
        DUP_DIST_THRESHOLD = 0.25
        if nearest_id and dist <= DUP_DIST_THRESHOLD:
            return True, dist, nearest_id, "similarity_threshold"

        return False, dist, nearest_id, "not_duplicate"

    duplicates = 0

    for it in candidates:
        dup, score, nearest, reason = is_duplicate(it)

        # 判定結果を保存（後で見返せるように）
        it["dedup"] = {
            "is_duplicate": dup,
            "score": score,
            "nearest_id": nearest,
            "reason": reason,
        }

        if dup:
            duplicates += 1
            log_with_run_id(logger, "debug", run_id, f"Duplicate: reason={reason} score={score:.4f} title={it.get('title','')[:60]}")
        else:
            deduped.append(it)

    state["deduped_items"] = deduped

    # 重複でないものだけ保存（次回以降の重複除去に使う）
    ids: List[str] = []
    texts: List[str] = []
    metas: List[dict] = []

    for it in deduped:
        ids.append(it["item_id"])
        texts.append(_item_text_for_embedding(it))
        metas.append(
            {
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "source_type": it.get("source_type", "other"),
                "published_at": it.get("published_at") or "",
                "week_id": state.get("week_id", ""),
            }
        )

    if ids:
        store.upsert_items(ids=ids, texts=texts, metadatas=metas)

    state["memory_write_results"] = {
        "stored": len(ids),
        "skipped_as_duplicate": duplicates,
        "timestamp": now,
    }

    log_with_run_id(
        logger,
        "info",
        run_id,
        f"Memory/Dedup finished: stored={len(ids)} duplicates={duplicates} remaining={len(deduped)}",
    )

    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "memory",
            "action": "dedup_and_store",
            "rationale": "Dedup by id/url match first, then similarity as fallback.",
            "payload": state["memory_write_results"],
            "timestamp": now,
        }
    )

    return state
