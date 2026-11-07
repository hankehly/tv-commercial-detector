"""Tests for the ``validate`` command, driven through the recording set as a whole.

Each test builds a small recording set in a temporary folder: placeholder
recordings (a few bytes each), a list of recordings, and a fake media probe that
answers with scripted tracks and lengths.
"""

import hashlib
from pathlib import Path

import pytest

from tv_commercial_detector.media_probe import ProbeError, ProbeResult
from tv_commercial_detector.recording_set import validate

HEADER = "file_name,size_bytes,fingerprint,length_seconds\n"
BOTH_TRACKS = ProbeResult(has_video=True, has_audio=True, length_seconds=3600.0)


class FakeProbe:
    """Media probe answering from a dict of file name to result."""

    def __init__(self, results: dict[str, ProbeResult]) -> None:
        self.results = results

    def probe(self, path: Path) -> ProbeResult:
        """Return the scripted result for ``path``."""
        return self.results[path.name]


@pytest.fixture
def data_folder(tmp_path: Path) -> Path:
    """Return an empty data folder with a ``recordings/`` folder inside it."""
    folder = tmp_path / "data"
    (folder / "recordings").mkdir(parents=True)
    return folder


@pytest.fixture
def recording_list(tmp_path: Path) -> Path:
    """Return the path of a list of recordings holding only its header."""
    path = tmp_path / "recordings.csv"
    path.write_text(HEADER)
    return path


def add_recording(data_folder: Path, name: str, content: bytes = b"video") -> Path:
    """Write a placeholder recording into the data folder."""
    path = data_folder / "recordings" / name
    path.write_bytes(content)
    return path


def list_row(name: str, content: bytes = b"video", length: float = 3600.0) -> str:
    """Return the list row matching a placeholder recording with ``content``."""
    fingerprint = hashlib.sha256(content).hexdigest()
    return f"{name},{len(content)},{fingerprint},{length}\n"


def test_data_folder_that_does_not_exist_is_an_error(
    tmp_path: Path, recording_list: Path
) -> None:
    missing = tmp_path / "nowhere"

    report = validate(missing, recording_list, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(missing), "data folder does not exist")
    ]


def test_data_folder_without_recordings_is_an_error(
    data_folder: Path, recording_list: Path
) -> None:
    (data_folder / "recordings" / "notes.txt").write_text("not a recording")

    report = validate(data_folder, recording_list, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(data_folder / "recordings"), "no MP4 recordings found")
    ]


def test_data_folder_without_a_recordings_folder_is_an_error(
    tmp_path: Path, recording_list: Path
) -> None:
    folder = tmp_path / "data"
    folder.mkdir()

    report = validate(folder, recording_list, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(folder / "recordings"), "no MP4 recordings found")
    ]


def test_listed_recordings_with_both_tracks_pass_and_are_summarised(
    data_folder: Path, recording_list: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"first")
    add_recording(data_folder, "b.mp4", b"second")
    recording_list.write_text(
        HEADER
        + list_row("a.mp4", b"first", length=3600.0)
        + list_row("b.mp4", b"second", length=5400.0)
    )
    probe = FakeProbe({"a.mp4": BOTH_TRACKS, "b.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, probe)

    assert report.errors == []
    assert report.warnings == []
    assert report.recording_count == 2
    assert report.hours == 2.5


@pytest.mark.parametrize(
    ("probe_result", "message"),
    [
        (
            ProbeResult(has_video=False, has_audio=True, length_seconds=60.0),
            "no video track",
        ),
        (
            ProbeResult(has_video=True, has_audio=False, length_seconds=60.0),
            "no audio track",
        ),
    ],
)
def test_recording_missing_a_track_is_an_error(
    data_folder: Path, recording_list: Path, probe_result: ProbeResult, message: str
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4", length=60.0))

    report = validate(data_folder, recording_list, FakeProbe({"a.mp4": probe_result}))

    assert [(e.subject, e.message) for e in report.errors] == [("a.mp4", message)]


def test_listed_recording_missing_from_the_folder_is_an_error(
    data_folder: Path, recording_list: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(
        HEADER + list_row("a.mp4") + list_row("gone.mp4", b"gone")
    )

    report = validate(data_folder, recording_list, FakeProbe({"a.mp4": BOTH_TRACKS}))

    assert [(e.subject, e.message) for e in report.errors] == [
        ("gone.mp4", "listed but missing from the recordings folder")
    ]


def test_listed_recording_whose_size_changed_is_an_error(
    data_folder: Path, recording_list: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"trimmed")
    recording_list.write_text(HEADER + list_row("a.mp4", b"original recording"))

    report = validate(data_folder, recording_list, FakeProbe({"a.mp4": BOTH_TRACKS}))

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.mp4", "size changed: listed as 18 bytes, now 7 bytes")
    ]


def test_recording_not_in_the_list_is_skipped_with_the_row_to_add(
    data_folder: Path, recording_list: Path
) -> None:
    add_recording(data_folder, "listed.mp4", b"listed")
    add_recording(data_folder, "new.mp4", b"video")
    recording_list.write_text(HEADER + list_row("listed.mp4", b"listed", length=3600.0))
    probe = FakeProbe(
        {
            "listed.mp4": BOTH_TRACKS,
            "new.mp4": ProbeResult(
                has_video=True, has_audio=True, length_seconds=1800.25
            ),
        }
    )

    report = validate(data_folder, recording_list, probe)

    assert report.errors == []
    assert [(w.subject, w.message) for w in report.warnings] == [
        (
            "new.mp4",
            "not in the list of recordings, so skipped; add this row: "
            "new.mp4,5,"
            "0cab1c9617404faf2b24e221e189ca5945813e14d3f766345b09ca13bbe28ffc,"
            "1800.250",
        )
    ]
    assert report.recording_count == 1
    assert report.hours == 1.0


def test_duplicate_file_name_in_the_list_is_an_error(
    data_folder: Path, recording_list: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(
        HEADER + list_row("a.mp4") + list_row("a.mp4", b"other content")
    )

    report = validate(data_folder, recording_list, FakeProbe({"a.mp4": BOTH_TRACKS}))

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.mp4", "file name listed more than once in the list of recordings")
    ]


def test_duplicate_fingerprint_in_the_list_is_an_error(
    data_folder: Path, recording_list: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"same")
    add_recording(data_folder, "b.mp4", b"same")
    recording_list.write_text(
        HEADER + list_row("a.mp4", b"same") + list_row("b.mp4", b"same")
    )
    probe = FakeProbe({"a.mp4": BOTH_TRACKS, "b.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, probe)

    assert [(e.subject, e.message) for e in report.errors] == [
        ("b.mp4", "same fingerprint as a.mp4 in the list of recordings")
    ]


def test_missing_list_of_recordings_is_an_error(
    data_folder: Path, tmp_path: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    missing = tmp_path / "missing.csv"

    report = validate(data_folder, missing, FakeProbe({"a.mp4": BOTH_TRACKS}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(missing), "list of recordings does not exist")
    ]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "name,size\n",
            "header must be: file_name,size_bytes,fingerprint,length_seconds",
        ),
        (
            HEADER + "a.mp4,big,abc,60\n",
            "line 2: size_bytes 'big' is not a whole number",
        ),
        (
            HEADER + "a.mp4,5,abc,long\n",
            "line 2: length_seconds 'long' is not a number",
        ),
        (HEADER + "a.mp4,5\n", "line 2: expected 4 values, found 2"),
    ],
)
def test_unreadable_list_of_recordings_is_an_error(
    data_folder: Path, recording_list: Path, content: str, message: str
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(content)

    report = validate(data_folder, recording_list, FakeProbe({"a.mp4": BOTH_TRACKS}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(recording_list), message)
    ]


def test_recording_the_probe_cannot_read_is_an_error(
    data_folder: Path, recording_list: Path
) -> None:
    class FailingProbe:
        def probe(self, path: Path) -> ProbeResult:
            raise ProbeError("Invalid data found when processing input")

    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))

    report = validate(data_folder, recording_list, FailingProbe())

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.mp4", "media probe failed: Invalid data found when processing input")
    ]
