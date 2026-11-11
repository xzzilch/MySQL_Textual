# SQLTUI

SQLTUI is a local-first terminal interface for MySQL, written entirely in Python. It uses Textual for keyboard navigation and responsive terminal widgets.

## Architectural Blueprint

```text
Textual app and screens
        | typed commands / results
        v
MySQLService (async facade, bounded worker pool)
        | run_in_executor; no connector calls on the UI event loop
        v
MySQLRepository (one short-lived connection per operation)
        | mysql-connector-python
        v
Local MySQL server
```

- **Presentation (`app.py`, `app.tcss`)** owns screens, input validation feedback, tab navigation, and result rendering. It does not construct database connections directly.
- **Authentication (`auth.py`)** accepts a host, port, optional initial database, username, and password. Passwords are masked, excluded from credential representations, used only for the session, and never written to disk.
- **Configuration (`config.py`)** loads non-secret connection/query timeout, result-limit, and worker settings from environment variables.
- **Service (`service.py`)** is the async boundary. A bounded `ThreadPoolExecutor` keeps synchronous connector calls away from Textual's event loop. Connections are not shared across workers.
- **Repository (`mysql.py`)** owns connection lifecycle, catalog SQL, bounded previews, transactions, and query execution. Metadata values are parameterized; generated preview SQL uses backtick-escaped identifiers.
- **Models (`models.py`)** define the small typed contract passed from repository to UI.

### User workflow

1. Enter the MySQL host, port, username, password, and optional initial database in the connection dialog.
2. Browse online databases and base tables in **Catalog**; selecting a table shows its columns and nullability, and **Preview rows** shows a bounded sample.
3. Choose a database in **Query**, edit SQL, and run it. Results are bounded, binary values are summarized, and elapsed time/row counts are shown.

The session overview presents the connected endpoint, account, credential-storage policy, and count of visible databases. Use `F1`, `F2`, and `F3` to switch between Overview, Catalog, and Query; `Ctrl+R` refreshes database metadata, and `F5` runs the active query.

Query execution intentionally permits arbitrary SQL because this is a management client. Use a least-privilege MySQL account. Successful statements are committed; failed statements are rolled back. Only the first result set is displayed. The configured connector read timeout bounds waiting for server responses. Python cannot forcibly stop a connector call already running in a worker thread, so closing the UI does not guarantee immediate cancellation.

## Requirements and Setup

- Python 3.12 or newer
- MySQL 8.0 or newer (local or reachable server)
- A MySQL user with access to the databases you want to manage

Install from this repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Launch with:

```sh
sqltui
# or
python -m sqltui
```

The first screen prompts for a MySQL host, port, username, password, and optional database. No connection secrets are read from environment variables or saved by the application. The default local endpoint is `127.0.0.1:3306`.

## Native Packages

SQLTUI remains a terminal application: its native app-menu/Start Menu shortcut opens the interactive TUI in a terminal window. The packaged folder contains Python and connector dependencies, so Python does not need to be installed on the target machine. Build on each target OS separately; PyInstaller does not cross-compile Windows and Linux bundles.

### CachyOS / Linux

From the project directory, with the project virtual environment active:

```sh
python -m pip install -e '.[build]'
python packaging/build.py
bash packaging/linux/install.sh
```

SQLTUI will appear in the desktop application menu and can also be started in a terminal with `~/.local/bin/sqltui`. `Terminal=true` opens a terminal window for the TUI. The install script copies the self-contained bundle under `~/.local/share/sqltui` and installs the icon and desktop entry under `~/.local/share`.

### Windows 10/11

Build on a 64-bit Windows machine using PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[build]"
.venv\Scripts\python packaging\build.py
```

Install Inno Setup 6, then run `packaging\windows\build-installer.ps1` in PowerShell. The installer will be created as `dist\installer\SQLTUI-Setup-x64.exe`; it installs SQLTUI with Start Menu and optional desktop shortcuts. It launches as a console TUI, not a graphical window.

The Linux and Windows build artifacts must each be built on their own operating system. Only the CachyOS bundle can be built and tested from Linux; the Windows installer recipe is provided but requires Windows and Inno Setup to produce and verify.

For native builds from source control, run the **Build SQLTUI packages** workflow manually or push a `v*` tag. It builds on Linux and Windows runners and uploads separate `sqltui-linux-cachyos` and `sqltui-windows-x64` artifacts.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SQLTUI_CONNECT_TIMEOUT` | `5` | Connection timeout in seconds |
| `SQLTUI_QUERY_TIMEOUT` | `60` | Connector read timeout in seconds |
| `SQLTUI_MAX_RESULT_ROWS` | `500` | Maximum rows buffered and displayed per result |
| `SQLTUI_MAX_WORKERS` | `4` | Maximum simultaneous MySQL operations |

## Tests

```sh
python -m pytest
```

The test suite covers MySQL connection options, secret representation, identifier quoting, async worker execution, and UI catalog/query flows without requiring a live MySQL server.

UI database operations run as Textual workers. Database/table/query selections are checked again after each awaited operation; results are discarded if the user changed context or disconnected while the request was in flight. Connector calls already executing in worker threads cannot be forcibly interrupted, so they may finish in the background, but they cannot update a stale or unmounted screen.

Development and pull-request guidance is in [CONTRIBUTING.md](CONTRIBUTING.md). The CI workflow checks Linux and Windows; the packaging workflow creates native artifacts on each operating system.
