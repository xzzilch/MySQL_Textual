import asyncio
import threading

import pytest

from sqltui.auth import ConnectionCredentials
from sqltui.config import Settings
from sqltui.service import DatabaseOperationError, MySQLService


@pytest.mark.asyncio
async def test_database_work_runs_off_loop_thread_and_normalizes_errors() -> None:
    service = MySQLService(Settings(max_workers=1))
    worker_threads: list[int] = []

    def fail_with_driver_error(credentials: ConnectionCredentials) -> None:
        worker_threads.append(threading.get_ident())
        raise OSError("MySQL connector unavailable")

    service.repository.test_connection = fail_with_driver_error
    try:
        with pytest.raises(DatabaseOperationError, match="MySQL connector unavailable"):
            await service.test_connection(
                ConnectionCredentials(host="localhost")
            )
    finally:
        service.close()

    assert worker_threads
    assert worker_threads[0] != threading.get_ident()




@pytest.mark.asyncio
async def test_closed_service_rejects_new_operations() -> None:
    service = MySQLService(Settings(max_workers=1))
    service.close()

    with pytest.raises(DatabaseOperationError, match="service is closed"):
        await service.test_connection(ConnectionCredentials(host="localhost"))


@pytest.mark.asyncio
async def test_service_close_rejects_operation_waiting_for_worker_slot() -> None:
    service = MySQLService(Settings(max_workers=1))
    started = threading.Event()
    release = threading.Event()

    def blocked_connection_check(credentials: ConnectionCredentials) -> None:
        started.set()
        if not release.wait(timeout=2):
            raise TimeoutError("test operation was not released")

    service.repository.test_connection = blocked_connection_check
    active = asyncio.create_task(
        service.test_connection(ConnectionCredentials(host="localhost"))
    )
    assert await asyncio.to_thread(started.wait, 1)
    waiting = asyncio.create_task(
        service.test_connection(ConnectionCredentials(host="localhost"))
    )
    await asyncio.sleep(0)
    service.close()
    release.set()

    await active
    with pytest.raises(DatabaseOperationError, match="service is closed"):
        await waiting
