"""Pytest fixtures for backend tests.

Unit tests use an in-memory SQLite database so they run without
any external infrastructure.  Integration tests targeting a live
PostgreSQL instance should be marked with @pytest.mark.integration.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.database as _db_module

# In-memory SQLite for unit tests
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


def override_get_db():
    """Yield a test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test and drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client():
    """FastAPI TestClient with database dependency overridden.

    Also mocks ``Base.metadata.create_all`` during startup since
    the tables are already created by the ``setup_database`` fixture.
    """
    from unittest.mock import patch
    app.dependency_overrides[get_db] = override_get_db
    with patch("app.main.Base.metadata.create_all"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session():
    """Raw database session for direct DB assertions."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Sample data fixtures ----

SAMPLE_INCIDENT = {
    "title": "Order Service high latency",
    "description": "Order requests are taking more than 3 seconds",
    "service": "order-service",
    "severity": "high",
    "start_time": "2026-08-23T10:00:00Z",
}

SAMPLE_INCIDENT_CRITICAL = {
    "title": "Database connection pool exhausted",
    "description": "PostgreSQL connections maxed out",
    "service": "user-service",
    "severity": "critical",
    "start_time": "2026-08-23T09:00:00Z",
}
