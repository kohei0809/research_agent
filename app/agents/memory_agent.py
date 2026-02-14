# app/agents/memory_agent.py
from __future__ import annotations

from app.utils.logger import get_logger, log_with_run_id

logger = get_logger(__name__)

"""
Memory / Dedup Node

役割：
- フィルタ後の候補(filtered_items)について、
  既に過去に配信済み/保存済みのコンテンツと「類似」していないかを確認し、
  重複配信を防ぐ。
- 重複でないものだけを deduped_items に残し、Chromaに保存する。

注意：
- MVPでは「タイトル+媒体」だけで埋め込み類似を取る簡易版。
- 将来的には abstract/summary も埋め込みに含めると精度が上がる。
- distance閾値はデータ量により調整が必要（最初は大雑把でOK）。
"""

from datetime import datetime, timezone
from typing import List, Tuple

from app.graph.state import WeeklyResearchState, ContentItem
from app.memory.chroma_store import ChromaStore


def _item_text_for_embedding(item: ContentItem) -> str:
    """
    埋め込みに使うテキストを組み立てる。
    MVPでは title + venue 程度で十分。
    """
    title = item.get("title", "")
    venue = item.get("venue", "")
    return f"{title}\n{venue}".strip()


def memory_dedup_node(state: WeeklyResearchState) -> WeeklyResearchState:
    """
    Node処理フロー：
    1) Chromaを開く（ローカル永続）
    2) 既存アイテムID一覧を読み込む → state.seen_item_ids
    3) filtered_items を1件ずつ類似検索し、重複なら除外
    4) 残ったものを deduped_items にセット
    5) deduped_items を Chroma に保存（次回以降の重複防止に使う）
    """
    now = datetime.now(timezone.utc).isoformat()

    store = ChromaStore(
        persist_dir="data/chroma_db",
        collection_name="weekly_items",
    )

    # 既存保存済みID（重複の早期判定・デバッグ用）
    seen_ids = store.get_all_ids()
    state["seen_item_ids"] = seen_ids

    candidates = state.get("filtered_items", [])
    deduped: List[ContentItem] = []

    def is_duplicate(item: ContentItem) -> Tuple[bool, float, str]:
        """
        1件の候補について類似検索し、重複判定する。
        戻り値：
          (is_duplicate, distance, nearest_id)

        ※ distanceの意味はコレクション設定に依存しうるため、
           まずは「かなり近いものがあれば重複扱い」に寄せる。
        """
        text = _item_text_for_embedding(item)
        res = store.query_similar(text, n_results=1)

        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        nearest_id = ids[0] if ids else ""
        dist = float(dists[0]) if dists else 999.0

        # 強い重複条件：ID一致
        if nearest_id and nearest_id == item.get("item_id"):
            return True, dist, nearest_id

        # 近さによる重複判定（MVP用）
        # 小さいほど近い、と仮定して運用開始（必要ならログを見て調整）
        DUP_DIST_THRESHOLD = 0.25
        if nearest_id and dist <= DUP_DIST_THRESHOLD:
            return True, dist, nearest_id

        return False, dist, nearest_id

    # 1件ずつ重複判定し、dedupedに振り分け
    for it in candidates:
        dup, score, nearest = is_duplicate(it)

        # 後からデバッグできるように、判定結果を item.dedup に保存
        it["dedup"] = {"is_duplicate": dup, "score": score, "nearest_id": nearest}

        if not dup:
            deduped.append(it)

    state["deduped_items"] = deduped

    # dedupedのみをChromaに保存（次回以降の重複防止）
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

    # 実行結果（何件保存したか等）をStateに残す
    state["memory_write_results"] = {
        "stored": len(ids),
        "skipped_as_duplicate": len(candidates) - len(deduped),
        "timestamp": now,
    }

    # A2Aログ（任意）
    state.setdefault("decisions", [])
    state["decisions"].append(
        {
            "agent": "memory",
            "action": "dedup_and_store",
            "rationale": "Deduplicate by similarity search in Chroma, then store non-duplicates.",
            "payload": state["memory_write_results"],
            "timestamp": now,
        }
    )
    
    log_with_run_id(
        logger,
        "info",
        run_id,
        f"Dedup complete: stored={len(ids)}, skipped={len(candidates) - len(deduped)}"
    )
    return state
