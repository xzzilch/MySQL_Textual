"""Textual presentation layer for the local MySQL client."""

import json
import sys
from dataclasses import replace
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from .auth import ConnectionCredentials
from .models import QueryResult, TableInfo
from .service import DatabaseOperationError, MySQLService


class LoginScreen(ModalScreen[ConnectionCredentials | None]):
    """Collect ephemeral credentials and verify the connection before entry."""

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._connecting = False

    def compose(self) -> ComposeResult:
        with Vertical(id="auth-dialog"):
            yield Label("Connect to MySQL", id="auth-title")
            with VerticalScroll(id="auth-fields"):
                yield Label("Host")
                yield Input(value="127.0.0.1", id="host")
                yield Label("Port")
                yield Input(value="3306", id="port", type="integer")
                yield Label("Initial database (optional)")
                yield Input(placeholder="Choose after connecting", id="initial-database")
                yield Label("Username")
                yield Input(value="root", id="username")
                yield Label("Password")
                yield Input(placeholder="Password", password=True, id="password")
            yield Static("", id="login-error")
            with Horizontal(classes="actions"):
                yield Button("Connect", variant="primary", id="connect")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#host", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            if not self._connecting:
                self.dismiss(None)
            return
        if event.button.id != "connect":
            return
        if self._connecting:
            return

        try:
            host = self.query_one("#host", Input).value.strip()
            port_text = self.query_one("#port", Input).value.strip()
            if not port_text.isascii() or not port_text.isdecimal():
                raise ValueError("Port must be a whole number")
            port = int(port_text)
            database = self.query_one("#initial-database", Input).value.strip() or None
            username = self.query_one("#username", Input).value.strip() or None
            password_input = self.query_one("#password", Input)
            credentials = ConnectionCredentials(
                host=host,
                port=port,
                database=database,
                username=username or "",
                password=password_input.value or "",
            )
        except (TypeError, ValueError) as error:
            if self.is_mounted:
                self.query_one("#login-error", Static).update(str(error))
            return

        password_input.value = ""
        self._connecting = True
        self.query_one("#login-error", Static).update("Connecting...")
        self.query_one("#connect", Button).disabled = True
        self.query_one("#cancel", Button).disabled = True
        self.run_worker(
            self._verify_connection(credentials),
            exclusive=True,
            group="connection",
            name="verify-connection",
        )

    async def _verify_connection(self, credentials: ConnectionCredentials) -> None:
        try:
            await self.app.service.test_connection(credentials)  # type: ignore[attr-defined]
        except DatabaseOperationError as error:
            if self.is_mounted:
                self.query_one("#login-error", Static).update(
                    f"Connection failed: {_safe_error(error, credentials)}"
                )
            return
        else:
            if self.is_mounted:
                self.dismiss(credentials)
        finally:
            self._connecting = False
            if self.is_mounted:
                self.query_one("#connect", Button).disabled = False
                self.query_one("#cancel", Button).disabled = False

    def action_cancel(self) -> None:
        if not self._connecting:
            self.dismiss(None)


class MainScreen(Container):
    """Tabbed workspace for MySQL overview, catalog browsing, and SQL work."""

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("f1", "show_overview", "Overview"),
        ("f2", "show_catalog", "Catalog"),
        ("f3", "show_query", "Query"),
        ("ctrl+r", "refresh_databases", "Refresh"),
        ("f5", "run_query", "Run Query"),
    ]

    def __init__(self, service: MySQLService, credentials: ConnectionCredentials) -> None:
        super().__init__(id="main-screen")
        self.service = service
        self.credentials = credentials
        self.selected_table: TableInfo | None = None
        self._database_generation = 0
        self._catalog_generation = 0
        self._inspection_generation = 0
        self._preview_generation = 0
        self._query_generation = 0
        self._query_running = False

    def compose(self) -> ComposeResult:
        with Vertical(id="main-shell"):
            with Horizontal(id="connection-bar"):
                yield Label(self._connection_label(), id="connection-label")
                yield Button("Disconnect", id="disconnect")
            with TabbedContent(initial="overview", id="workspace-tabs"):
                with TabPane("Overview", id="overview"):
                    with Horizontal(id="overview-heading"):
                        yield Label("SESSION OVERVIEW", classes="section-title")
                        yield Static("CONNECTED", id="session-state")
                    yield Static("MySQL connection and current access context", id="overview-hint")
                    yield DataTable(id="session-details")
                    yield Static("Loading accessible databases...", id="session-summary")
                with TabPane("Catalog", id="catalog"):
                    with Horizontal(classes="toolbar"):
                        yield Select(
                            [], prompt="Loading databases...", allow_blank=True,
                            id="database-select",
                        )
                        yield Button("Refresh", id="refresh-databases")
                        yield Button("Preview rows", id="preview-table", disabled=True)
                    with Horizontal(id="catalog-body"):
                        yield DataTable(id="tables")
                        with Vertical(id="table-inspector"):
                            yield Label("Table details", classes="section-title")
                            yield Static("Select a table to inspect its columns.", id="table-details")
                    yield DataTable(id="catalog-results")
                    yield Static("", id="catalog-status", classes="status-line")
                with TabPane("Query", id="query"):
                    with Horizontal(classes="toolbar"):
                        yield Label("Database")
                        yield Select(
                            [], prompt="Loading databases...", allow_blank=True,
                            id="query-database-select",
                        )
                        yield Button("Run query", variant="primary", id="run-query")
                    yield TextArea(
                        "SELECT TABLE_NAME FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME LIMIT 100;",
                        language="sql",
                        id="query-editor",
                    )
                    yield Static("Ready", id="query-status", classes="status-line")
                    yield DataTable(id="query-results")

    def on_mount(self) -> None:
        self._configure_tables()
        self.run_worker(self._load_databases(), exclusive=True, name="load-databases")

    def on_unmount(self) -> None:
        self._database_generation += 1
        self._catalog_generation += 1
        self._inspection_generation += 1
        self._preview_generation += 1
        self._query_generation += 1

    def _configure_tables(self) -> None:
        details = self.query_one("#session-details", DataTable)
        details.add_columns("Session property", "Value")
        details.add_rows(
            [
                ("Server", f"{self.credentials.host}:{self.credentials.port}"),
                ("Username", self.credentials.username),
                ("Initial database", self.credentials.database or "Not selected"),
                ("Credential storage", "Memory only"),
            ]
        )
        tables = self.query_one("#tables", DataTable)
        tables.add_columns("Schema", "Table")
        self.query_one("#catalog-results", DataTable).add_columns("Preview")
        self.query_one("#query-results", DataTable).add_columns("Results")

    def _connection_label(self) -> str:
        database = self.credentials.database or "no database selected"
        return f"Connected to {self.credentials.host}:{self.credentials.port} / {database}"

    async def _load_databases(self) -> None:
        self._database_generation += 1
        generation = self._database_generation
        try:
            databases = await self.service.list_databases(self.credentials)
            if not self.is_mounted or generation != self._database_generation:
                return
            self.query_one("#session-summary", Static).update(
                f"{len(databases)} databases available to this account"
            )
            options = [(name, name) for name in databases]
            for selector_id in ("database-select", "query-database-select"):
                selector = self.query_one(f"#{selector_id}", Select)
                previous = self._selected_database(selector_id)
                selector.set_options(options)
                selected = previous if previous in databases else None
                if selected is None and self.credentials.database in databases:
                    selected = self.credentials.database
                if selected is None and databases:
                    selected = databases[0]
                selector.value = selected if selected is not None else Select.BLANK
            await self._load_tables(self._selected_database("database-select"))
        except DatabaseOperationError as error:
            if self.is_mounted and generation == self._database_generation:
                self.query_one("#catalog-status", Static).update(
                    f"Could not load databases: {_safe_error(error, self.credentials)}"
                )

    async def _load_tables(self, database: str | None = None) -> None:
        selected_database = self._selected_database("database-select")
        if database is not None and database != selected_database:
            return
        database = selected_database
        self._catalog_generation += 1
        generation = self._catalog_generation
        self._inspection_generation += 1
        self._preview_generation += 1
        table_widget = self.query_one("#tables", DataTable)
        table_widget.clear()
        self.selected_table = None
        self.query_one("#preview-table", Button).disabled = True
        self.query_one("#catalog-results", DataTable).clear(columns=True)
        self.query_one("#catalog-results", DataTable).add_column("Preview")
        if not database:
            self.query_one("#table-details", Static).update("Choose a database to browse tables.")
            self.query_one("#catalog-status", Static).update("")
            return
        self.query_one("#table-details", Static).update(f"Loading tables from {database}...")
        self.query_one("#catalog-status", Static).update("Loading tables...")
        try:
            tables = await self.service.list_tables(replace(self.credentials, database=database))
            if (
                not self.is_mounted
                or generation != self._catalog_generation
                or database != self._selected_database("database-select")
            ):
                return
            for table in tables:
                table_widget.add_row(table.schema, table.name, key=self._table_key(table))
            self.query_one("#table-details", Static).update(
                f"{len(tables)} tables in {database}. Select a row to inspect columns."
            )
            self.query_one("#catalog-status", Static).update("")
        except DatabaseOperationError as error:
            if (
                self.is_mounted
                and generation == self._catalog_generation
                and database == self._selected_database("database-select")
            ):
                self.query_one("#catalog-status", Static).update(
                    f"Could not load tables: {_safe_error(error, self.credentials)}"
                )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "database-select":
            database = event.value if isinstance(event.value, str) else None
            self.run_worker(
                self._load_tables(database),
                exclusive=True,
                group="catalog",
                name="load-tables",
            )
        elif event.select.id == "query-database-select" and self._query_running:
            self._query_generation += 1
            self.query_one("#query-status", Static).update(
                "Database changed; the in-flight result will be discarded."
            )

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "query-editor" and self._query_running:
            self._query_generation += 1
            self.query_one("#query-status", Static).update(
                "SQL changed; the in-flight result will be discarded."
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "tables":
            return
        table = self._table_from_key(event.row_key.value)
        if table is None:
            return
        database = self._selected_database("database-select")
        if not database or table.schema != database:
            return
        self._inspection_generation += 1
        generation = self._inspection_generation
        self.selected_table = table
        self.query_one("#preview-table", Button).disabled = True
        self.query_one("#table-details", Static).update("Loading table definition...")
        self.run_worker(
            self._inspect_table(table, database, generation),
            exclusive=True,
            group="inspection",
            name="inspect-table",
        )

    async def _inspect_table(
        self, table: TableInfo, database: str, generation: int
    ) -> None:
        try:
            columns = await self.service.describe_table(
                replace(self.credentials, database=database), table
            )
            if (
                not self.is_mounted
                or generation != self._inspection_generation
                or self.selected_table != table
                or database != self._selected_database("database-select")
            ):
                return
            details = "\n".join(
                f"{column.name}  {column.data_type}  "
                f"{'NULL' if column.nullable else 'NOT NULL'}"
                for column in columns
            ) or "No columns found."
            self.query_one("#table-details", Static).update(
                f"{table.schema}.{table.name}\n{details}"
            )
            self.query_one("#preview-table", Button).disabled = False
        except DatabaseOperationError as error:
            if (
                self.is_mounted
                and generation == self._inspection_generation
                and database == self._selected_database("database-select")
            ):
                self.query_one("#table-details", Static).update(
                    f"Could not inspect table: {_safe_error(error, self.credentials)}"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-databases":
            self.run_worker(
                self._load_databases(),
                exclusive=True,
                group="databases",
                name="refresh-databases",
            )
        elif event.button.id == "preview-table":
            self.run_worker(
                self._preview_selected_table(),
                exclusive=True,
                group="preview",
                name="preview-table",
            )
        elif event.button.id == "run-query":
            self.run_worker(
                self._execute_query(),
                exclusive=True,
                group="query",
                name="execute-query",
            )
        elif event.button.id == "disconnect":
            self.app.run_worker(
                self.app.disconnect(),  # type: ignore[attr-defined]
                exclusive=True,
                group="lifecycle",
                name="disconnect",
            )

    def action_show_overview(self) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = "overview"

    def action_show_catalog(self) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = "catalog"

    def action_show_query(self) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = "query"

    def action_refresh_databases(self) -> None:
        self.run_worker(
            self._load_databases(),
            exclusive=True,
            group="databases",
            name="refresh-databases",
        )

    def action_run_query(self) -> None:
        if self.query_one("#workspace-tabs", TabbedContent).active == "query":
            self.run_worker(
                self._execute_query(),
                exclusive=True,
                group="query",
                name="execute-query",
            )

    async def _preview_selected_table(self) -> None:
        table = self.selected_table
        if table is None:
            return
        database = self._selected_database("database-select")
        if not database or table.schema != database:
            return
        self._preview_generation += 1
        generation = self._preview_generation
        self.query_one("#preview-table", Button).disabled = True
        self.query_one("#catalog-status", Static).update("Loading preview...")
        try:
            result = await self.service.preview_table(
                replace(self.credentials, database=database), table
            )
            if (
                not self.is_mounted
                or generation != self._preview_generation
                or self.selected_table != table
                or database != self._selected_database("database-select")
            ):
                return
            self._render_result(self.query_one("#catalog-results", DataTable), result)
            suffix = " (limited)" if result.truncated else ""
            self.query_one("#catalog-status", Static).update(
                f"Showing {len(result.rows)} rows{suffix} in "
                f"{result.elapsed_seconds:.2f}s"
            )
        except DatabaseOperationError as error:
            if (
                self.is_mounted
                and generation == self._preview_generation
                and self.selected_table == table
                and database == self._selected_database("database-select")
            ):
                self.query_one("#catalog-status", Static).update(
                    f"Preview failed: {_safe_error(error, self.credentials)}"
                )

    async def _execute_query(self) -> None:
        sql = self.query_one("#query-editor", TextArea).text.strip()
        database = self._selected_database("query-database-select")
        status = self.query_one("#query-status", Static)
        if not sql:
            status.update("Enter a SQL statement first.")
            return
        if not database:
            status.update("Choose a database first.")
            return
        button = self.query_one("#run-query", Button)
        self._query_generation += 1
        generation = self._query_generation
        self._query_running = True
        button.disabled = True
        status.update("Executing...")
        try:
            result = await self.service.execute_query(
                replace(self.credentials, database=database), sql
            )
            if (
                not self.is_mounted
                or generation != self._query_generation
                or database != self._selected_database("query-database-select")
            ):
                return
            self._render_result(self.query_one("#query-results", DataTable), result)
            count_label = "rows returned" if result.columns else "rows affected"
            suffix = " (display limited)" if result.truncated else ""
            status.update(
                f"{result.row_count} {count_label}{suffix} in {result.elapsed_seconds:.2f}s"
            )
        except DatabaseOperationError as error:
            if (
                self.is_mounted
                and generation == self._query_generation
                and database == self._selected_database("query-database-select")
            ):
                status.update(f"Query failed: {_safe_error(error, self.credentials)}")
        finally:
            self._query_running = False
            if self.is_mounted:
                button.disabled = False

    def _render_result(self, table: DataTable, result: QueryResult) -> None:
        table.clear(columns=True)
        if not result.columns:
            table.add_column("Execution")
            table.add_row("Statement completed; no result set.")
            return
        table.add_columns(*result.columns)
        if not result.rows:
            table.add_row(*("" for _ in result.columns))
            return
        for row in result.rows:
            table.add_row(*(self._display_value(value) for value in row))

    @staticmethod
    def _display_value(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bytes):
            return f"<binary: {len(value)} bytes>"
        text = str(value).replace("\n", " ").replace("\r", " ")
        return text if len(text) <= 300 else text[:297] + "..."

    def _selected_database(self, selector_id: str) -> str | None:
        value = self.query_one(f"#{selector_id}", Select).value
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _table_key(table: TableInfo) -> str:
        return json.dumps((table.schema, table.name), separators=(",", ":"))

    @classmethod
    def _table_from_key(cls, key: str) -> TableInfo | None:
        try:
            parts = json.loads(key)
        except (json.JSONDecodeError, TypeError):
            return None
        if (
            isinstance(parts, list)
            and len(parts) == 2
            and all(isinstance(part, str) for part in parts)
        ):
            return TableInfo(parts[0], parts[1])
        return None


class SQLTUI(App[None]):
    """Application lifecycle and top-level screen management."""

    TITLE = "SQLTUI"
    CSS_PATH = "app.tcss"
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("ctrl+q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.service = MySQLService()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(id="root")
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(LoginScreen(), self._on_login)

    def _on_login(self, credentials: ConnectionCredentials | None) -> None:
        if credentials is None:
            self.exit()
            return
        self.run_worker(self._show_main(credentials), exclusive=True, name="open-workspace")

    async def _show_main(self, credentials: ConnectionCredentials) -> None:
        await self.query_one("#root", Container).mount(MainScreen(self.service, credentials))

    async def disconnect(self) -> None:
        self.service.close()
        await self.query_one("#root", Container).remove_children()
        if not self.is_mounted:
            return
        self.service = MySQLService()
        self.push_screen(LoginScreen(), self._on_login)

    def on_unmount(self) -> None:
        self.service.close()


def main() -> None:
    try:
        app = SQLTUI()
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    app.run()


def _safe_error(error: Exception, credentials: ConnectionCredentials) -> str:
    message = str(error)
    if credentials.password:
        message = message.replace(credentials.password, "[redacted]")
    return message
