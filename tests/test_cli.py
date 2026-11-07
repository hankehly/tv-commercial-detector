"""Tests for the command-line entry point and its settings."""

import hashlib
from pathlib import Path

import pytest

from tv_commercial_detector import cli, settings
from tv_commercial_detector.cli import main
from tv_commercial_detector.media_probe import ProbeResult
from tv_commercial_detector.settings import DATA_FOLDER_VARIABLE, data_folder


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


def test_validate_summarises_labels_and_lists_channels_without_a_logo_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, log: list[str]
) -> None:
    class FakeProbe:
        def probe(self, path: Path) -> ProbeResult:
            return ProbeResult(has_video=True, has_audio=True, length_seconds=3600.0)

    data = tmp_path / "data"
    (data / "recordings").mkdir(parents=True)
    (data / "recordings" / "a.mp4").write_bytes(b"first")
    (data / "recordings" / "b.mp4").write_bytes(b"second")
    recording_list = tmp_path / "recordings.csv"
    recording_list.write_text(
        "file_name,size_bytes,fingerprint,length_seconds\n"
        f"a.mp4,5,{hashlib.sha256(b'first').hexdigest()},3600\n"
        f"b.mp4,6,{hashlib.sha256(b'second').hexdigest()},3600\n"
    )
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "a.toml").write_text(
        f'recording = "{hashlib.sha256(b"first").hexdigest()}"\n'
        'channel = "TBS"\n'
        'commercial_breaks = [{ start = "00:10:00", end = "00:12:00" }]\n'
    )
    (labels / "b.toml").write_text(
        f'recording = "{hashlib.sha256(b"second").hexdigest()}"\n'
        'channel = "NTV"\n'
        "commercial_breaks = [\n"
        '  { start = "00:20:00", end = "00:22:00" },\n'
        '  { start = "00:40:00", end = "00:42:30.5" },\n'
        "]\n"
    )
    (data / "logos").mkdir()
    (data / "logos" / "TBS.lgd").write_bytes(b"logo")
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(data))
    monkeypatch.setattr(settings, "RECORDING_LIST", recording_list)
    monkeypatch.setattr(settings, "LABELS_FOLDER", labels)
    monkeypatch.setattr(cli, "Ffprobe", FakeProbe)

    exit_code = main(["validate"])

    assert exit_code == 0
    assert f"INFO And the label files in {labels}" in log
    assert (
        "INFO Labeled 3 commercial breaks on 2 channels: NTV, TBS. "
        "Skipped 0 without a usable label file."
    ) in log
    assert (
        "WARNING No logo file for join_logo_scp on these channels: NTV. "
        f"Save each as {data / 'logos' / '<channel>.lgd'}."
    ) in log
