# app/utils/logger.py
from __future__ import annotations

"""
共通Loggerユーティリティ。

目的：
- 各ノードで統一フォーマットのログを出す
- run_id を含めてトレース可能にする
- 将来Cloud Run等に載せてもそのまま使える

基本方針：
- logging標準モジュールを利用
- シンプルなテキストログ（将来JSON化も可能）
"""

import logging
import os
from typing import Optional


LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """
    アプリ起動時に一度だけ呼ぶ。
    既にハンドラがある場合は二重登録しない。
    """
    root_logger = logging.getLogger()

    if root_logger.handlers:
        # 既に設定済みなら何もしない（main.py再実行時など）
        return

    root_logger.setLevel(LOG_LEVEL)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    モジュール単位でlogger取得。
    例：
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def log_with_run_id(
    logger: logging.Logger,
    level: str,
    run_id: Optional[str],
    message: str,
) -> None:
    """
    run_id を含めたログ出力ヘルパー。

    level: "info" / "debug" / "warning" / "error"
    """
    prefix = f"[run_id={run_id}] " if run_id else ""
    full_msg = prefix + message

    level = level.lower()
    if level == "debug":
        logger.debug(full_msg)
    elif level == "warning":
        logger.warning(full_msg)
    elif level == "error":
        logger.error(full_msg)
    else:
        logger.info(full_msg)
