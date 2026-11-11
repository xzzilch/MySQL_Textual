"""Typed results shared between the MySQL service and the terminal UI."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TableInfo:
    schema: str
    name: str


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int
    elapsed_seconds: float
    truncated: bool = False
