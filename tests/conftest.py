"""Shared fixtures. The real mirror is optional: tests that need it skip when it is absent."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MIRROR = Path("/opt/devel/DevMoi/agentic-design-mirror/pages/raw/patterns")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "mirror: needs the local agentic-design mirror")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if MIRROR.exists():
        return
    skip = pytest.mark.skip(reason=f"mirror not found at {MIRROR}")
    for item in items:
        if "mirror" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def mirror() -> Path:
    return MIRROR


@pytest.fixture
def pg_dsn() -> str:
    """The Postgres test DSN, or skip. Tests create their own schema and drop it (see `pg_schema`)."""
    dsn = os.environ.get("CATALOG_PG_TEST_DSN")
    if not dsn:
        pytest.skip("CATALOG_PG_TEST_DSN not set")
    return dsn


@pytest.fixture
def pg_schema(pg_dsn: str):
    psycopg = pytest.importorskip("psycopg")
    name = f"t_{uuid.uuid4().hex[:12]}"
    yield name
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(f'drop schema if exists "{name}" cascade')
