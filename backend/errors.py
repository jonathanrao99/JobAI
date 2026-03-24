"""Sanitized HTTP errors: log internals, return generic client messages."""

from __future__ import annotations

from loguru import logger

INTERNAL_ERROR = "An unexpected error occurred. Please try again later."

__all__ = ["INTERNAL_ERROR", "log_internal_error"]


def log_internal_error(context: str, exc: BaseException) -> None:
    logger.exception(f"{context}: {exc}")
