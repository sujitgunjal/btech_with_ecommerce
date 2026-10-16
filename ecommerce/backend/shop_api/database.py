"""Database engine and session factory."""

from __future__ import annotations

import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from shop_platform.faults import controller
from shop_platform.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
        )
    return create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(engine, "before_cursor_execute")
def _delay_database_statements(conn, cursor, statement, parameters, context, executemany):
    context._query_started = time.perf_counter()
    delay = controller.database_delay_seconds()
    if delay > 0:
        time.sleep(delay)


@event.listens_for(engine, "after_cursor_execute")
def _record_database_statement(conn, cursor, statement, parameters, context, executemany):
    started = getattr(context, "_query_started", None)
    if started is None:
        return
    from shop_platform.telemetry import record_db_query

    record_db_query(time.perf_counter() - started)


@event.listens_for(engine, "connect")
def _sqlite_busy_timeout(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def init_db() -> None:
    from shop_api import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    statement = (
        "ALTER TABLE experiments ADD COLUMN IF NOT EXISTS investigation_incident_id INTEGER"
        if engine.dialect.name == "postgresql"
        else "ALTER TABLE experiments ADD COLUMN investigation_incident_id INTEGER"
    )
    try:
        with engine.begin() as connection:
            connection.execute(text(statement))
    except Exception:
        return


def database_ready() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
