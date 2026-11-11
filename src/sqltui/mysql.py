"""Synchronous MySQL adapter. Each operation owns and closes its connection."""

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from .auth import ConnectionCredentials, build_connection_options
from .config import Settings
from .models import ColumnInfo, QueryResult, TableInfo


class MySQLRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def test_connection(self, credentials: ConnectionCredentials) -> None:
        with (
            _closing(self._connect(credentials)) as connection,
            _closing(connection.cursor()) as cursor,
        ):
            cursor.execute("SELECT 1")
            cursor.fetchone()

    def list_databases(self, credentials: ConnectionCredentials) -> list[str]:
        with (
            _closing(self._connect(credentials)) as connection,
            _closing(connection.cursor()) as cursor,
        ):
            cursor.execute("SHOW DATABASES")
            return [row[0] for row in cursor.fetchall()]

    def list_tables(self, credentials: ConnectionCredentials) -> list[TableInfo]:
        if not credentials.database:
            return []
        sql = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = %s
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        with (
            _closing(self._connect(credentials)) as connection,
            _closing(connection.cursor()) as cursor,
        ):
            cursor.execute(sql, (credentials.database, "BASE TABLE"))
            rows = cursor.fetchall()
        return [TableInfo(schema=row[0], name=row[1]) for row in rows]

    def describe_table(
        self, credentials: ConnectionCredentials, table: TableInfo
    ) -> list[ColumnInfo]:
        sql = """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """
        with (
            _closing(self._connect(credentials)) as connection,
            _closing(connection.cursor()) as cursor,
        ):
            cursor.execute(sql, (table.schema, table.name))
            rows = cursor.fetchall()
        return [ColumnInfo(name=row[0], data_type=row[1], nullable=row[2] == "YES") for row in rows]

    def preview_table(
        self, credentials: ConnectionCredentials, table: TableInfo
    ) -> QueryResult:
        sql = (
            f"SELECT * FROM {quote_identifier(table.schema)}."
            f"{quote_identifier(table.name)} LIMIT {self._settings.max_result_rows}"
        )
        return self.execute_query(credentials, sql)

    def execute_query(self, credentials: ConnectionCredentials, sql: str) -> QueryResult:
        started = perf_counter()
        with (
            _closing(self._connect(credentials)) as connection,
            _closing(connection.cursor()) as cursor,
        ):
            try:
                cursor.execute(sql)
                if cursor.description:
                    columns = tuple(column[0] for column in cursor.description)
                    fetched = cursor.fetchmany(self._settings.max_result_rows + 1)
                    truncated = len(fetched) > self._settings.max_result_rows
                    rows = tuple(
                        tuple(row) for row in fetched[: self._settings.max_result_rows]
                    )
                    row_count = len(rows)
                else:
                    columns = ()
                    rows = ()
                    row_count = max(cursor.rowcount, 0)
                    truncated = False
                connection.commit()
            except Exception as error:
                try:
                    connection.rollback()
                except Exception as rollback_error:  # noqa: BLE001 - preserve the query failure
                    error.add_note(f"Rollback also failed: {rollback_error}")
                raise
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=row_count,
                elapsed_seconds=perf_counter() - started,
                truncated=truncated,
            )

    def _connect(self, credentials: ConnectionCredentials) -> Any:
        try:
            import mysql.connector
        except ImportError as error:
            raise RuntimeError(
                "mysql-connector-python is unavailable; install the project dependencies"
            ) from error
        return mysql.connector.connect(
            **build_connection_options(credentials, self._settings)
        )


def quote_identifier(identifier: str) -> str:
    """Quote a MySQL identifier (not a value) for generated preview SQL."""
    if not identifier:
        raise ValueError("SQL identifiers cannot be empty")
    return "`" + identifier.replace("`", "``") + "`"


@contextmanager
def _closing(resource: Any) -> Iterator[Any]:
    """Close resources without hiding the operation error if cleanup also fails."""
    try:
        yield resource
    except BaseException as operation_error:
        try:
            resource.close()
        except Exception as cleanup_error:  # noqa: BLE001 - preserve the operation failure
            operation_error.add_note(f"Resource cleanup also failed: {cleanup_error}")
        raise
    else:
        resource.close()