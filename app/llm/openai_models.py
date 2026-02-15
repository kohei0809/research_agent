# app/llm/openai_models.py
from __future__ import annotations

"""
OpenAI Structured Outputs 用のスキーマ（Pydantic）。

目的：
- LLM出力を「必ずこの形」で受け取り、後段処理を壊れにくくする
- 週次週報に必要な情報（要約・要点・示唆・重要度・タグ）を一括で生成する

設計方針：
- 週報で読める長さに強制する（長文化するとSlackで読みにくい & コスト増）
- タグはトレンド分析のキーになるので「再利用しやすい正規化」前提
"""

from pydantic import BaseModel, Field, conint, confloat
from typing import List


class ImportanceRating(BaseModel):
    """
    重要度スコア（5軸×1〜5、合計0〜25）
    - total は5軸の合計になるようにモデルに指示（不整合が出たら後段で補正も可能）
    """
    novelty: conint(ge=1, le=5) = Field(..., description="技術的新規性")
    practicality: conint(ge=1, le=5) = Field(..., description="実用可能性")
    reproducibility: conint(ge=1, le=5) = Field(..., description="再現性")
    impact: conint(ge=1, le=5) = Field(..., description="将来性/インパクト")
    buzz: conint(ge=1, le=5) = Field(..., description="話題性")
    total: confloat(ge=0, le=25) = Field(..., description="合計スコア（0-25）")
    rationale: str = Field(..., description="短い根拠（1〜3文）")


class ItemAnalysis(BaseModel):
    """
    1つの論文/記事に付与する分析結果。

    - summary: 週報でサッと読める短い概要（日本語推奨）
    - key_points: 重要点（最大5）
    - insights: 実装/運用/設計に効く示唆（最大3）
    - keywords: 技術キーワード（最大8、英語/短句推奨）
    - tags: 正規化カテゴリ（最大6、kebab-case推奨）
    """
    summary: str = Field(..., description="概要（短め、日本語で3〜5文程度）")
    key_points: List[str] = Field(..., description="要点（最大5、短文）")
    insights: List[str] = Field(..., description="示唆（最大3、実装/運用/設計に繋がる）")

    keywords: List[str] = Field(..., description="キーワード（最大8、重複なし）")
    tags: List[str] = Field(..., description="正規化タグ（最大6、kebab-case推奨）")

    importance: ImportanceRating
