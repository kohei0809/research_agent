# app/llm/openai_client.py
from __future__ import annotations

"""
OpenAI API クライアント（Responses API + Structured Outputs）。

今回の拡張：
- keywords/tags/importance に加えて summary/key_points/insights を生成する。
- 週次週報向けに「短く」「実務に繋がる」出力を強制する。

環境変数：
- OPENAI_API_KEY  : 必須（.envなら load_dotenv() が必要）
- OPENAI_MODEL    : 例 "gpt-4o-mini"
- OPENAI_TIMEOUT  : タイムアウト秒（デフォルト30）
"""

import os
from typing import Optional

from openai import OpenAI
from app.llm.openai_models import ItemAnalysis


_DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
_DEFAULT_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "30"))


class OpenAIAnalyzer:
    """
    解析用途のOpenAIラッパー。
    - ノード側は "analyze_item()" を呼ぶだけでよい状態にしておく
    - プロンプト改善・モデル差し替えはここに閉じ込める
    """

    def __init__(self, model: Optional[str] = None) -> None:
        # NOTE: OPENAI_API_KEY は SDK が環境変数から読む
        self.client = OpenAI()
        self.model = model or _DEFAULT_MODEL

    def analyze_item(self, title: str, venue: str, url: str, published_at: str) -> ItemAnalysis:
        """
        1アイテムの週報向け分析を生成する。

        入力はMVPではタイトル中心だが、将来は以下を追加すると精度が上がる：
        - abstract（論文）
        - 本文抜粋（記事）
        - 既存の類似コンテンツ情報（memoryから）
        """

        # system: 役割 + 制約を明確にし、出力を短く安定化させる
        system = (
            "You are an expert AI/Software Research Analyst.\n"
            "Your job: produce a concise weekly-digest analysis for a paper/article.\n\n"
            "Output rules (VERY IMPORTANT):\n"
            "- summary: Japanese, 3-5 short sentences. No hype.\n"
            "- key_points: up to 5 bullets, each <= 20 Japanese words.\n"
            "- insights: up to 3 bullets, each should suggest an actionable implication for engineers.\n"
            "- keywords: up to 8 short technical terms, no duplicates.\n"
            "- tags: up to 6 normalized categories in kebab-case (reusable across weeks).\n"
            "- importance: rate 1-5 for each dimension; total must equal the sum.\n"
            "- Do not invent citations or claim to have read the full text; infer only from provided fields.\n"
        )

        # user: 解析対象の事実情報（現状は最低限）
        user = (
            f"ITEM\n"
            f"Title: {title}\n"
            f"Venue: {venue}\n"
            f"URL: {url}\n"
            f"Published: {published_at}\n"
        )

        # Structured Outputs:
        # - text_format に Pydanticモデルを渡すと、output_parsed に検証済み結果が入る
        # - 週次運用で壊れにくい
        resp = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=ItemAnalysis,
            # 週報は安定性優先なので低め
            temperature=0.2,
            timeout=_DEFAULT_TIMEOUT,
        )

        return resp.output_parsed
