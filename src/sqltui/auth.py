"""In-memory MySQL connection credentials and connector options."""

from dataclasses import dataclass, field
from typing import Any

from .config import Settings


@dataclass(frozen=True, slots=True)
class ConnectionCredentials:
    host: str
    port: int = 3306
    username: str = "root"
    password: str | None = field(default=None, repr=False)
    database: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.host, str) or not self.host.strip():
            raise ValueError("MySQL host is required")
        if not isinstance(self.username, str) or not self.username.strip():
            raise ValueError("MySQL username is required")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise TypeError("Port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if self.password is not None and not isinstance(self.password, str):
            raise ValueError("Password must be text")
        if self.database is not None and (
            not isinstance(self.database, str) or not self.database.strip()
        ):
            raise ValueError("Database must be omitted or contain a name")


def build_connection_options(
    credentials: ConnectionCredentials, settings: Settings
) -> dict[str, Any]:
    """Build connector options without logging or persisting credentials."""
    return {
        "host": credentials.host,
        "port": credentials.port,
        "user": credentials.username,
        "password": credentials.password or "",
        "database": credentials.database,
        "connection_timeout": settings.connection_timeout_seconds,
        "read_timeout": settings.query_timeout_seconds,
        "write_timeout": settings.connection_timeout_seconds,
    }
