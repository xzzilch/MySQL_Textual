import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, Select, TabbedContent, TextArea

from sqltui.app import SQLTUI, MainScreen
from sqltui.auth import ConnectionCredentials
from sqltui.models import ColumnInfo, QueryResult, TableInfo


class FakeService:
    def __init__(self):
        self.closed = False

    async def test_connection(self, credentials):
        return None

    def close(self):
        self.closed = True

    async def list_databases(self, credentials):
        return ["master", "sample"]

    async def list_tables(self, credentials):
        return [TableInfo(credentials.database or "sample", "Items")]

    async def describe_table(self, credentials, table):
        return [ColumnInfo("id", "int", False)]

    async def preview_table(self, credentials, table):
        return QueryResult(("id",), ((1,),), 1, 0.01)

    async def execute_query(self, credentials, sql):
        return QueryResult(("answer",), ((42,),), 1, 0.02)


class DelayedCatalogService(FakeService):
    def __init__(self):
        super().__init__()
        self.started = {name: asyncio.Event() for name in ("db1", "db2")}
        self.release = {name: asyncio.Event() for name in ("db1", "db2")}
        self.delay = False

    async def list_databases(self, credentials):
        return ["db1", "db2"]

    async def list_tables(self, credentials):
        database = credentials.database
        if self.delay:
            self.started[database].set()
            await self.release[database].wait()
        return [TableInfo(database, f"{database}_items")]


class DelayedQueryService(FakeService):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def list_databases(self, credentials):
        return ["db1", "db2"]

    async def list_tables(self, credentials):
        return [TableInfo(credentials.database, "items")]

    async def execute_query(self, credentials, sql):
        self.started.set()
        await self.release.wait()
        self.finished.set()
        return QueryResult(("database",), ((credentials.database,),), 1, 0.01)


class DelayedConnectService(FakeService):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def test_connection(self, credentials):
        self.started.set()
        await self.release.wait()


class WorkspaceHarness(App[None]):
    def __init__(self, service=None, credentials=None):
        super().__init__()
        self.test_service = service or FakeService()
        self.test_credentials = credentials or ConnectionCredentials(
            host="localhost", database="sample"
        )

    def compose(self) -> ComposeResult:
        yield MainScreen(
            self.test_service,
            self.test_credentials,
        )


@pytest.mark.asyncio
async def test_catalog_preview_and_query_results_render() -> None:
    app = WorkspaceHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.query_one(MainScreen)
        await screen._load_tables()

        tables = app.query_one("#tables", DataTable)
        assert tables.row_count == 1

        screen.selected_table = TableInfo("sample", "Items")
        await screen._preview_selected_table()
        preview = app.query_one("#catalog-results", DataTable)
        assert preview.row_count == 1

        await screen._execute_query()
        results = app.query_one("#query-results", DataTable)
        assert results.row_count == 1
        await pilot.pause()


@pytest.mark.asyncio
async def test_mysql_login_form_mounts_with_local_defaults() -> None:
    app = SQLTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#host", Input).value == "127.0.0.1"
        assert app.query_one("#port", Input).value == "3306"
        assert app.query_one("#username", Input).value == "root"
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_workspace_shortcuts_navigate_tabs_and_run_query() -> None:
    app = WorkspaceHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabs = app.query_one("#workspace-tabs", TabbedContent)

        await pilot.press("f2")
        assert tabs.active == "catalog"
        await pilot.press("f3")
        assert tabs.active == "query"
        await pilot.press("f5")
        await pilot.pause()

        assert app.query_one("#query-results", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_old_catalog_response_cannot_replace_new_database_tables() -> None:
    service = DelayedCatalogService()
    app = WorkspaceHarness(
        service,
        ConnectionCredentials(host="localhost", database="db1"),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        screen = app.query_one(MainScreen)
        service.delay = True

        old_request = asyncio.create_task(screen._load_tables("db1"))
        await service.started["db1"].wait()

        app.query_one("#database-select", Select).value = "db2"
        await service.started["db2"].wait()

        service.release["db2"].set()
        await pilot.pause()
        await pilot.pause()
        service.release["db1"].set()
        await old_request
        await pilot.pause()

        rows = app.query_one("#tables", DataTable)
        assert rows.row_count == 1
        assert rows.get_row_at(0) == ["db2", "db2_items"]

        await screen._load_tables("db1")
        assert rows.get_row_at(0) == ["db2", "db2_items"]


def test_table_row_keys_round_trip_arbitrary_identifier_text() -> None:
    table = TableInfo("db\x1fname", "item\x1fname")

    assert MainScreen._table_from_key(MainScreen._table_key(table)) == table


@pytest.mark.asyncio
async def test_query_result_is_discarded_after_database_change() -> None:
    service = DelayedQueryService()
    app = WorkspaceHarness(
        service,
        ConnectionCredentials(host="localhost", database="db1"),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.query_one(MainScreen)
        app.query_one("#workspace-tabs", TabbedContent).active = "query"
        await pilot.pause()
        await pilot.click("#run-query")
        await service.started.wait()

        app.query_one("#query-database-select", Select).value = "db2"
        await pilot.pause()
        service.release.set()
        await service.finished.wait()
        await pilot.pause()

        assert app.query_one("#query-results", DataTable).row_count == 0


@pytest.mark.asyncio
async def test_query_result_is_discarded_after_sql_edit() -> None:
    service = DelayedQueryService()
    app = WorkspaceHarness(
        service,
        ConnectionCredentials(host="localhost", database="db1"),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.query_one("#workspace-tabs", TabbedContent).active = "query"
        await pilot.pause()
        await pilot.click("#run-query")
        await service.started.wait()

        app.query_one("#query-editor", TextArea).text = "SELECT 'edited';"
        await pilot.pause()
        service.release.set()
        await service.finished.wait()
        await pilot.pause()

        assert app.query_one("#query-results", DataTable).row_count == 0


@pytest.mark.asyncio
async def test_disconnect_tears_down_workspace_before_reconnecting() -> None:
    app = SQLTUI()
    service = FakeService()
    app.service = service
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#connect")
        await pilot.pause()
        await pilot.pause()
        assert app.query_one(MainScreen)

        await pilot.click("#disconnect")
        await pilot.pause()
        await pilot.pause()

        assert service.closed
        assert app.query_one("#auth-dialog")


@pytest.mark.asyncio
async def test_connect_runs_in_worker_and_cannot_be_cancelled_mid_request() -> None:
    app = SQLTUI()
    service = DelayedConnectService()
    app.service = service
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#connect")
        await service.started.wait()
        assert app.query_one("#cancel").disabled

        await pilot.press("escape")
        assert app.query_one("#auth-dialog")

        service.release.set()
        await pilot.pause()
        await pilot.pause()
        assert app.query_one(MainScreen)


@pytest.mark.asyncio
async def test_login_rejects_invalid_port_without_crashing() -> None:
    app = SQLTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#port", Input).value = ""
        await pilot.click("#connect")
        assert "Port must be a whole number" in str(app.query_one("#login-error").render())
        await pilot.press("escape")
