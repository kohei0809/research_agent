# app/llm/openai_models.py
from __future__ import annotations

"""
OpenAI Structured Outputs 用のスキーマ（Pydantic）を定義する。

目的：
- LLM出力を「必ずこの形」で受け取る（壊れにくい）
- JSONパース失敗やキー欠落に強い
- 後続ノード（Slack通知など）で扱いやすい

このプロジェクトでは、1アイテム（論文/記事）に対して
- keywords（キーワード）
- tags（正規化タグ）
- importance（重要度評価）
を付与するために使う。
"""

from pydantic import BaseModel, Field, conint, confloat
from typing import List


class ImportanceRating(BaseModel):
    """
    重要度スコア

    5軸（各1〜5）で評価し、合計を total（0〜25）として持つ。
    - novelty:      技術的新規性
    - practicality: 実用可能性（プロダクト/運用に乗るか）
    - reproducibility: 再現性（追試・実装しやすさ）
    - impact:       将来性/インパクト（中長期の重要性）
    - buzz:         話題性（コミュニティの注目度）

    NOTE:
    - total は「5軸の和」になるようにモデルに指示している。
      もし不整合が出る場合は、後段で合計を再計算して上書きする運用も可能。
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

    keywords:
      - 技術用語中心の短い単語列
      - 重複なしを推奨

    tags:
      - 正規化されたカテゴリ（後でトレンド分析のキーになる）
      - snake-case or kebab-case を推奨
      - 最大6程度
    """
    keywords: List[str] = Field(..., description="キーワード（最大8個程度）")
    tags: List[str] = Field(..., description="正規化タグ（最大6個程度）")
    importance: ImportanceRating
