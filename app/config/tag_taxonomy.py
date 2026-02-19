# app/config/tag_taxonomy.py
from __future__ import annotations

"""
タグ辞書（taxonomy / synonym mapping）

目的：
- LLMのタグ出力の「表記ゆれ」「同義語」を代表タグに統一する
- トレンド分析の精度と安定性を上げる
- Slack表示も一貫させる

運用：
- 最初は少数から始め、実データで増やす
- 「代表タグ」は kebab-case を推奨
"""

# 表記ゆれを代表タグに寄せる辞書
# key: 入力タグ（正規化後）
# value: 代表タグ
TAG_SYNONYMS = {
    "tool-calling": "tool-use",
    "tool-usage": "tool-use",
    "tool-invocation": "tool-use",

    "robustness": "reliability",
    "fault-tolerance": "reliability",

    "autonomous-agents": "autonomy",
    "agent-autonomy": "autonomy",

    "human-in-the-loop": "user-interaction",
    "ux": "user-interaction",

    "continuous-training": "continuous-learning",
    "online-learning": "continuous-learning",

    "data-quality-checks": "data-quality",
    "data-validation": "data-quality",
}

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
