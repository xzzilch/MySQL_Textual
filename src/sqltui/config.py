"""Runtime configuration. Secrets are intentionally not stored in settings."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    connection_timeout_seconds: int = 5
    query_timeout_seconds: int = 60
    max_result_rows: int = 500
    max_workers: int = 4

    def __post_init__(self) -> None:
        for name in (
            "connection_timeout_seconds",
            "query_timeout_seconds",
            "max_result_rows",
            "max_workers",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load non-secret tuning options, validating values at the boundary."""
        defaults = cls()
        return cls(
            connection_timeout_seconds=_positive_int(
                "SQLTUI_CONNECT_TIMEOUT", defaults.connection_timeout_seconds
            ),
            query_timeout_seconds=_positive_int(
                "SQLTUI_QUERY_TIMEOUT", defaults.query_timeout_seconds
            ),
            max_result_rows=_positive_int("SQLTUI_MAX_RESULT_ROWS", defaults.max_result_rows),
            max_workers=_positive_int("SQLTUI_MAX_WORKERS", defaults.max_workers),
        )


def _positive_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed
