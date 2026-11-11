import pytest

from sqltui.app import main
from sqltui.auth import ConnectionCredentials, build_connection_options
from sqltui.config import Settings
from sqltui.mysql import quote_identifier


def test_connection_options_and_secret_representation() -> None:
    credentials = ConnectionCredentials(
        host="localhost", port=3307, username="alice", password="p;ass}word", database="sample"
    )
    options = build_connection_options(credentials, Settings())

    assert options["host"] == "localhost"
    assert options["port"] == 3307
    assert options["user"] == "alice"
    assert options["password"] == "p;ass}word"
    assert options["database"] == "sample"
    assert "p;ass" not in repr(credentials)


def test_database_is_optional() -> None:
    credentials = ConnectionCredentials(host="localhost")

    options = build_connection_options(credentials, Settings())

    assert options["database"] is None


def test_credentials_reject_invalid_types_and_ranges() -> None:
    with pytest.raises(TypeError, match="Port must be an integer"):
        ConnectionCredentials(host="localhost", port="3306")
    with pytest.raises(ValueError, match="Port must be between"):
        ConnectionCredentials(host="localhost", port=0)
    with pytest.raises(ValueError, match="MySQL host is required"):
        ConnectionCredentials(host=None)


def test_settings_reject_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="max_workers must be a positive integer"):
        Settings(max_workers=0)


def test_quote_identifier_escapes_backtick() -> None:
    assert quote_identifier("weird`name") == "`weird``name`"


def test_quote_identifier_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        quote_identifier("")


def test_environment_settings_use_dataclass_defaults(monkeypatch) -> None:
    monkeypatch.delenv("SQLTUI_CONNECT_TIMEOUT", raising=False)

    assert (
        Settings.from_environment().connection_timeout_seconds
        == Settings().connection_timeout_seconds
    )


def test_main_reports_invalid_environment_configuration(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SQLTUI_MAX_WORKERS", "invalid")

    with pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 2
    assert "Configuration error: SQLTUI_MAX_WORKERS" in capsys.readouterr().err
