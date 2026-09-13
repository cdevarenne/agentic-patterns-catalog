"""Shared fixtures. The real mirror is optional: tests that need it skip when it is absent."""
from __future__ import annotations

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
