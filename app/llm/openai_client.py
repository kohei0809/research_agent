# app/llm/openai_client.py
from __future__ import annotations

"""
OpenAI API クライアント（Responses API + Structured Outputs）。

ここでは「解析（keywords/tags/importance）」専用の薄いラッパーを提供する。

設計意図：
- ノード側（analyzer.py）にAPIの細部が漏れないようにする
- モデル切替やプロンプト改善をこのファイルに閉じ込める
- Structured Outputs で壊れにくい出力を得る（Pydanticスキーマ）

環境変数：
- OPENAI_API_KEY  : OpenAI SDKが自動で読む
- OPENAI_MODEL    : 利用モデル（例 gpt-4o-mini）
- OPENAI_TIMEOUT  : タイムアウト秒
"""

import os
from typing import Optional

from openai import OpenAI
from app.llm.openai_models import ItemAnalysis


# デフォルト値（環境変数で上書き可能）
_DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
_DEFAULT_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "30"))


class OpenAIAnalyzer:
    """
    Analyzer用途のOpenAIクライアント。

    NOTE:
    - OpenAI() は OPENAI_API_KEY を環境変数から取得する
    - ここでは item 1件ずつ解析する（MVP）
    - 将来はバッチ化やコスト最適化を行う可能性あり
    """

    def __init__(self, model: Optional[str] = None) -> None:
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model or _DEFAULT_MODEL

    def analyze_item(self, title: str, venue: str, url: str, published_at: str) -> ItemAnalysis:
        """
        1アイテム分のキーワード/タグ/重要度を構造化で生成する。

        入力：
        - title: 記事/論文タイトル
        - venue: 媒体（arXivカテゴリ、ブログ名など）
        - url:   URL
        - published_at: 公開日（不明なら "unknown" でもOK）

        出力：
        - ItemAnalysis（Pydantic）：
          keywords/tags/importance を必ず含む

        精度改善ポイント：
        - ここに abstract や本文抜粋（extracted_text）を追加すると精度が上がる
        - ただしコストも増えるので、MVPではタイトル中心で運用開始が現実的
        """

        # system: 役割・制約を明確にし、出力の揺れを減らす
        system = (
            "You are an expert AI/Software Research Analyst.\n"
            "Given an item (paper/article), extract:\n"
            "- keywords (concise, tech terms)\n"
            "- tags (normalized, reusable categories)\n"
            "- importance rating (1-5 per dimension) with a short rationale\n"
            "Constraints:\n"
            "- keywords: up to 8, no duplicates\n"
            "- tags: up to 6, snake-case or kebab-case preferred, reusable\n"
            "- importance.total must be the sum of the 5 dimensions\n"
        )

        # user: 解析対象の事実データを渡す
        user = (
            f"ITEM\n"
            f"Title: {title}\n"
            f"Venue: {venue}\n"
            f"URL: {url}\n"
            f"Published: {published_at}\n"
        )

        # Structured Outputs:
        # - text_format に Pydanticモデルを渡すと output_parsed を返してくれる
        # - JSON崩れや想定外出力を大幅に減らせる
        resp = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=ItemAnalysis,
            # 週次バッチの安定性を優先して温度低め
            temperature=0.2,
            # ネットワーク・APIの不安定さ対策（必要に応じて調整）
            timeout=_DEFAULT_TIMEOUT,
        )

        # Pydanticオブジェクトがここに入る（型安全）
        return resp.output_parsed
