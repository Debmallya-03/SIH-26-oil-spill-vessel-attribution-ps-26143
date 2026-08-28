from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from app.core.config import settings


class DatabaseUnavailableError(RuntimeError):
    pass


def get_database_url() -> str:
    try:
        return settings.resolved_database_url
    except ValueError as exc:
        raise DatabaseUnavailableError(str(exc)) from exc


def get_database_target() -> dict[str, str | int | None]:
    return settings.database_target


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    try:
        with psycopg.connect(get_database_url(), connect_timeout=settings.database_connect_timeout_seconds) as connection:
            yield connection
    except DatabaseUnavailableError:
        raise
    except psycopg.Error as exc:
        raise DatabaseUnavailableError(str(exc)) from exc


def check_database_status() -> tuple[str, str | None]:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return "connected", None
    except DatabaseUnavailableError as exc:
        return "unavailable", str(exc)
