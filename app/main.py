# app/main.py
from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app.graph.builder import run_graph
from app.graph.state import WeeklyResearchState


def _current_week_id_jst() -> str:
    # 週番号生成（ISO week）
    jst = ZoneInfo("Asia/Tokyo")
    now = datetime.now(jst)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def main() -> None:
    run_id = str(uuid.uuid4())
    week_id = _current_week_id_jst()

    initial_state: WeeklyResearchState = {
        "run_id": run_id,
        "week_id": week_id,
        "started_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        "mode": "manual",
    }

    final_state = run_graph(initial_state)

    # ローカル確認用
    print("=== DONE ===")
    print("run_id:", final_state.get("run_id"))
    print("week_id:", final_state.get("week_id"))
    print("items(collected):", len(final_state.get("collected_items", [])))
    print("items(filtered):", len(final_state.get("filtered_items", [])))
    print("slack_post_result:", final_state.get("slack_post_result"))
    if final_state.get("errors"):
        print("errors:", final_state["errors"])


if __name__ == "__main__":
    main()
