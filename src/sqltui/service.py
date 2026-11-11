"""Async boundary for MySQL work; the synchronous driver never blocks Textual."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, TypeVar

from .auth import ConnectionCredentials
from .config import Settings
from .models import ColumnInfo, QueryResult, TableInfo
from .mysql import MySQLRepository

T = TypeVar("T")


class DatabaseOperationError(RuntimeError):
    """A database operation failed and can be shown at the UI boundary."""


class MySQLService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_environment()
        self.repository = MySQLRepository(self.settings)
        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.max_workers, thread_name_prefix="sqltui-mysql"
        )
        self._semaphore = asyncio.Semaphore(self.settings.max_workers)
        self._closed = False

    async def test_connection(self, credentials: ConnectionCredentials) -> None:
        await self._run(self.repository.test_connection, credentials)

    async def list_databases(self, credentials: ConnectionCredentials) -> list[str]:
        return await self._run(self.repository.list_databases, credentials)

    async def list_tables(self, credentials: ConnectionCredentials) -> list[TableInfo]:
        return await self._run(self.repository.list_tables, credentials)

    async def describe_table(
        self, credentials: ConnectionCredentials, table: TableInfo
    ) -> list[ColumnInfo]:
        return await self._run(self.repository.describe_table, credentials, table)

    async def preview_table(
        self, credentials: ConnectionCredentials, table: TableInfo
    ) -> QueryResult:
        return await self._run(self.repository.preview_table, credentials, table)

    async def execute_query(self, credentials: ConnectionCredentials, sql: str) -> QueryResult:
        return await self._run(self.repository.execute_query, credentials, sql)

    async def _run(self, function: Callable[..., T], *args: Any) -> T:
        if self._closed:
            raise DatabaseOperationError("MySQL service is closed")
        loop = asyncio.get_running_loop()
        try:
            async with self._semaphore:
                if self._closed:
                    raise RuntimeError("MySQL service is closed")
                return await loop.run_in_executor(self._executor, partial(function, *args))
        except Exception as error:
            raise DatabaseOperationError(str(error)) from error

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._executor.shutdown(wait=False, cancel_futures=True)
