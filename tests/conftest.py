"""Fixtures shared by the tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger
from recording_sets import RecordingSet


@pytest.fixture
def log() -> Iterator[list[str]]:
    """Collect every logged line as ``LEVEL message``."""
    lines: list[str] = []
    sink = logger.add(
        lambda m: lines.append(m.rstrip("\n")), format="{level} {message}"
    )
    yield lines
    logger.remove(sink)


@pytest.fixture
def recording_set(tmp_path: Path) -> RecordingSet:
    """Return an empty recording set in a temporary folder."""
    return RecordingSet(tmp_path)
