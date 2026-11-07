"""Tests for the command-line entry point and its settings."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger

from tv_commercial_detector.cli import main
from tv_commercial_detector.settings import DATA_FOLDER_VARIABLE, data_folder


@pytest.fixture
def log() -> Iterator[list[str]]:
    """Collect every logged line as ``LEVEL message``."""
    lines: list[str] = []
    sink = logger.add(
        lambda m: lines.append(m.rstrip("\n")), format="{level} {message}"
    )
    yield lines
    logger.remove(sink)


def test_data_folder_defaults_to_data_at_the_repository_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATA_FOLDER_VARIABLE, raising=False)

    folder = data_folder()

    assert folder.name == "data"
    assert (folder.parent / "pyproject.toml").is_file()


def test_validate_checks_the_data_folder_named_by_the_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, log: list[str]
) -> None:
    missing = tmp_path / "elsewhere"
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(missing))

    exit_code = main(["validate"])

    assert exit_code == 1
    assert f"INFO Checking recordings in {missing / 'recordings'}" in log
    assert f"ERROR {missing}: data folder does not exist" in log
