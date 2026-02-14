# app/memory/chroma_store.py
from __future__ import annotations

"""
ChromaStore（ローカル永続メモリ）- fastembed版（torch不要）

なぜ fastembed？
- sentence-transformers は torch 依存で、環境によって torch が入らず詰まりがち
- fastembed は ONNX 系で軽量・インストールが通りやすい（無料）
- 自己研鑽で「まず動かす」には最適

このStoreの責務：
- 文字列をベクトル化（embed）
- Chromaへ保存（upsert）
- 類似検索（query）
- 保存済みID一覧取得（get_all_ids）

将来：
- Cloud Run へ載せる場合は永続ストレージを工夫する（Volume / GCS等）
"""

import os
from typing import List, Dict

import chromadb
from chromadb.config import Settings

# torch不要の埋め込み
from fastembed import TextEmbedding


class ChromaStore:
    """
    ローカル永続の Chroma + fastembed による埋め込み。
    """

    def __init__(
        self,
        persist_dir: str = "data/chroma_db",
        collection_name: str = "weekly_items",
        # fastembedがサポートするモデル名を指定（軽量で無難なもの）
        # 例: "BAAI/bge-small-en-v1.5" など
        embed_model: str = "BAAI/bge-small-en-v1.5",
    ) -> None:
        os.makedirs(persist_dir, exist_ok=True)

        # fastembed の埋め込み器（初回はモデルDLが走ることがあります）
        self._embedder = TextEmbedding(model_name=embed_model)

        # Chroma 永続クライアント
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # コレクション（なければ作成）
        self._col = self._client.get_or_create_collection(name=collection_name)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        テキストをベクトル化して list[list[float]] を返す。
        fastembed の embed は generator を返すので list 化する。
        """
        vectors = list(self._embedder.embed(texts))
        # vectors は numpy array 相当が入るので tolist() で Python list 化
        return [v.tolist() for v in vectors]

    def upsert_items(self, ids: List[str], texts: List[str], metadatas: List[Dict]) -> None:
        """
        ベクトルDBに保存（upsert）。
        - ids: item_id
        - texts: 埋め込み対象テキスト（title等）
        - metadatas: url や published_at など、後で参照したい属性
        """
        embeddings = self.embed(texts)
        self._col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def query_similar(self, text: str, n_results: int = 5) -> Dict:
        """
        類似検索。
        - 戻り値は Chroma の query 結果 dict
        - distances の意味は距離指標に依存するが、一般に「小さいほど近い」
        """
        emb = self.embed([text])[0]
        return self._col.query(query_embeddings=[emb], n_results=n_results)

    def get_all_ids(self, limit: int = 100000) -> List[str]:
        """
        保存済みID一覧を取得。
        MVPでは全件取得でOK。
        件数が増えたら週で絞るなど最適化余地あり。
        """
        res = self._col.get(limit=limit, include=["metadatas"])
        return list(res.get("ids", []))
