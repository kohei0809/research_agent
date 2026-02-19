# app/mcp/errors.py
from __future__ import annotations

import traceback
from typing import List


def format_exception(e: BaseException) -> str:
    """
    ExceptionGroup / TaskGroup で隠れてしまう根本原因を文字列化する。

    - Python 3.11+ の ExceptionGroup に対応
    - サブ例外を再帰的に展開
    """
    lines: List[str] = []

    def _walk(ex: BaseException, depth: int = 0) -> None:
        indent = "  " * depth
        lines.append(f"{indent}{type(ex).__name__}: {ex}")

        # ExceptionGroup の場合は中身を掘る
        if hasattr(ex, "exceptions") and isinstance(getattr(ex, "exceptions"), list):
            subs = getattr(ex, "exceptions")
            for sub in subs:
                _walk(sub, depth + 1)
        else:
            # 通常例外は traceback を付ける
            tb = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__))
            lines.append(f"{indent}--- traceback ---\n{tb}")

    _walk(e)
    return "\n".join(lines)
