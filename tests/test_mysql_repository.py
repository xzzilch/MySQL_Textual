import pytest

from sqltui.auth import ConnectionCredentials
from sqltui.config import Settings
from sqltui.models import TableInfo
from sqltui.mysql import MySQLRepository


class FakeCursor:
    def __init__(self, rows, execute_error=None, close_error=None):
        self.rows = rows
        self.calls = []
        self.closed = False
        self.execute_error = execute_error
        self.close_error = close_error

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if self.execute_error:
            raise self.execute_error

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class FakeConnection:
    def __init__(self, cursor, cursor_error=None, rollback_error=None):
        self.fake_cursor = cursor
        self.closed = False
        self.cursor_error = cursor_error
        self.rollback_error = rollback_error
        self.rollback_called = False

    def cursor(self):
        if self.cursor_error:
            raise self.cursor_error
        return self.fake_cursor

    def close(self):
        self.closed = True

    def rollback(self):
        self.rollback_called = True
        if self.rollback_error:
            raise self.rollback_error


def test_table_catalog_uses_bound_values_and_closes_connection() -> None:
    cursor = FakeCursor([("sample", "orders")])
    connection = FakeConnection(cursor)
    repository = MySQLRepository(Settings())
    repository._connect = lambda credentials: connection

    tables = repository.list_tables(
        ConnectionCredentials(host="localhost", database="sample")
    )

    assert tables == [TableInfo(schema="sample", name="orders")]
    query, params = cursor.calls[0]
    assert "TABLE_SCHEMA = %s" in query
    assert params == ("sample", "BASE TABLE")
    assert cursor.closed
    assert connection.closed


def test_preview_quotes_mysql_identifiers() -> None:
    repository = MySQLRepository(Settings(max_result_rows=25))
    captured = {}
    repository.execute_query = lambda credentials, query: captured.update(query=query)

    repository.preview_table(
        ConnectionCredentials(host="localhost", database="weird`db"),
        TableInfo(schema="weird`db", name="order`items"),
    )

    assert captured["query"] == "SELECT * FROM `weird``db`.`order``items` LIMIT 25"


def test_query_failure_keeps_primary_error_and_closes_all_resources() -> None:
    cursor = FakeCursor(
        [],
        execute_error=RuntimeError("primary query failure"),
        close_error=RuntimeError("cursor close failure"),
    )
    connection = FakeConnection(
        cursor,
        rollback_error=RuntimeError("rollback failure"),
    )
    repository = MySQLRepository(Settings())
    repository._connect = lambda credentials: connection

    with pytest.raises(RuntimeError, match="primary query failure") as raised:
        repository.execute_query(ConnectionCredentials(host="localhost"), "bad SQL")

    assert connection.rollback_called
    assert cursor.closed
    assert connection.closed
    assert any("rollback failure" in note for note in raised.value.__notes__)
    assert any("cursor close failure" in note for note in raised.value.__notes__)


def test_connection_closes_if_cursor_creation_fails() -> None:
    connection = FakeConnection(
        FakeCursor([]), cursor_error=RuntimeError("cursor unavailable")
    )
    repository = MySQLRepository(Settings())
    repository._connect = lambda credentials: connection

    with pytest.raises(RuntimeError, match="cursor unavailable"):
        repository.execute_query(ConnectionCredentials(host="localhost"), "SELECT 1")

    assert connection.closed
