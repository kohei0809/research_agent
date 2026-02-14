# app/memory/chroma_store.py
from __future__ import annotations

"""
ChromaStore（ローカル永続メモリ）

目的：
- 週次で配信した論文/記事をベクトルDBに保存し、次回以降の重複配信を防ぐ
- 将来的には「過去のトピック傾向」「関連コンテンツの参照」にも使う

採用理由：
- Chromaはローカル永続が簡単で無料、自己研鑽に最適
- Cloud Runへ移行する場合も、永続ストレージを工夫すれば継続利用可能
"""

import os
from typing import List, Dict

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class ChromaStore:
    """
    - PersistentClientでディスク永続化
    - 埋め込みは sentence-transformers をローカル利用（無料）
    """

    def __init__(
        self,
        persist_dir: str = "data/chroma_db",
        collection_name: str = "weekly_items",
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        # Chromaの永続ディレクトリを作成
        os.makedirs(persist_dir, exist_ok=True)

        # 埋め込みモデル（ローカル）
        # ※初回はモデルDLが走るので少し時間がかかる
        self._embedder = SentenceTransformer(model_name)

        # anonymized_telemetry=False にしておくと、匿名テレメトリ送信を抑制できる
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # 既存があればそれを使う。なければ作る。
        self._col = self._client.get_or_create_collection(name=collection_name)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        テキストをベクトル化する。
        normalize_embeddings=True で正規化しておくと、類似比較が安定しやすい。
        """
        vecs = self._embedder.encode(
            texts, show_progress_bar=False, normalize_embeddings=True
        )
        return vecs.tolist()

    def upsert_items(self, ids: List[str], texts: List[str], metadatas: List[Dict]) -> None:
        """
        ベクトルDBに保存する（upsertなので既存なら更新）。
        - ids: item_id
        - texts: 埋め込み対象文（title等）
        - metadatas: urlやpublished_atなど、後で参照したい属性
        """
        embeddings = self.embed(texts)
        self._col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def query_similar(self, text: str, n_results: int = 5) -> Dict:
        """
        類似検索（近いアイテムを探す）。
        - ここで返る "distances" の意味はコレクション設定に依存することがあるため、
          MVPでは「一番近い候補が存在するか」を重視して運用し、閾値は後で調整する。
        """
        emb = self.embed([text])[0]
        return self._col.query(query_embeddings=[emb], n_results=n_results)

    def get_all_ids(self, limit: int = 100000) -> List[str]:
        """
        既存保存済みIDの一覧を取得。
        MVPではシンプルに全件取得しているが、
        将来的に件数が増えたら週単位で絞る等の工夫が必要。
        """
        res = self._col.get(limit=limit, include=["metadatas"])
        return list(res.get("ids", []))
