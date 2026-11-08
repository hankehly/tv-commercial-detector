"""Fixtures shared by the tests."""

from collections.abc import Iterator

import pytest
from loguru import logger


@pytest.fixture
def log() -> Iterator[list[str]]:
    """Collect every logged line as ``LEVEL message``."""
    lines: list[str] = []
    sink = logger.add(
        lambda m: lines.append(m.rstrip("\n")), format="{level} {message}"
    )
    yield lines
    logger.remove(sink)
