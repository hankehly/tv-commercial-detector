"""Tests for the ``validate`` command, driven through the recording set as a whole.

Each test builds a small recording set in a temporary folder: placeholder
recordings (a few bytes each), a list of recordings, label files, and a fake
media probe that answers with scripted tracks and lengths.
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
        """Return the scripted result for a recording.

        Parameters
        ----------
        path : Path
            The recording; only its file name is used.

        Returns
        -------
        ProbeResult
            The result scripted for that file name.
        """
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


@pytest.fixture
def labels_folder(tmp_path: Path) -> Path:
    """Return an empty folder for label files."""
    folder = tmp_path / "labels"
    folder.mkdir()
    return folder


def fingerprint(content: bytes) -> str:
    """Return the fingerprint of a placeholder recording.

    Parameters
    ----------
    content : bytes
        The placeholder's bytes.

    Returns
    -------
    str
        The SHA-256 hash of ``content``, in hex.
    """
    return hashlib.sha256(content).hexdigest()


def write_labels(
    labels_folder: Path,
    name: str,
    content: bytes = b"video",
    channel: str = "TBS",
    commercial_breaks: str = "[]",
) -> Path:
    """Write a label file for a placeholder recording.

    Parameters
    ----------
    labels_folder : Path
        The folder for label files.
    name : str
        The label file's name.
    content : bytes
        The placeholder recording's bytes, which set the fingerprint written.
    channel : str
        The channel to write.
    commercial_breaks : str
        The TOML value written for ``commercial_breaks``.

    Returns
    -------
    Path
        The label file.
    """
    path = labels_folder / name
    path.write_text(
        f'recording = "{fingerprint(content)}"\n'
        f'channel = "{channel}"\n'
        f"commercial_breaks = {commercial_breaks}\n"
    )
    return path


def add_recording(data_folder: Path, name: str, content: bytes = b"video") -> Path:
    """Write a placeholder recording into the data folder.

    Parameters
    ----------
    data_folder : Path
        The data folder.
    name : str
        The recording's file name.
    content : bytes
        The placeholder's bytes, which set its size and fingerprint.

    Returns
    -------
    Path
        The placeholder recording.
    """
    path = data_folder / "recordings" / name
    path.write_bytes(content)
    return path


def list_row(name: str, content: bytes = b"video", length: float = 3600.0) -> str:
    """Build the list row matching a placeholder recording.

    Parameters
    ----------
    name : str
        The recording's file name.
    content : bytes
        The placeholder's bytes.
    length : float
        The length to list, in seconds.

    Returns
    -------
    str
        The row, with a line ending.
    """
    return f"{name},{len(content)},{fingerprint(content)},{length}\n"


def test_data_folder_that_does_not_exist_is_an_error(
    tmp_path: Path, recording_list: Path, labels_folder: Path
) -> None:
    missing = tmp_path / "nowhere"

    report = validate(missing, recording_list, labels_folder, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(missing), "data folder does not exist")
    ]


def test_data_folder_without_recordings_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    (data_folder / "recordings" / "notes.txt").write_text("not a recording")

    report = validate(data_folder, recording_list, labels_folder, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(data_folder / "recordings"), "no MP4 recordings found")
    ]


def test_data_folder_without_a_recordings_folder_is_an_error(
    tmp_path: Path, recording_list: Path, labels_folder: Path
) -> None:
    folder = tmp_path / "data"
    folder.mkdir()

    report = validate(folder, recording_list, labels_folder, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(folder / "recordings"), "no MP4 recordings found")
    ]


def test_listed_recordings_with_both_tracks_pass_and_are_summarised(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"first")
    add_recording(data_folder, "b.mp4", b"second")
    recording_list.write_text(
        HEADER
        + list_row("a.mp4", b"first", length=3600.0)
        + list_row("b.mp4", b"second", length=5400.0)
    )
    write_labels(labels_folder, "a.toml", b"first")
    write_labels(labels_folder, "b.toml", b"second")
    probe = FakeProbe(
        {
            "a.mp4": BOTH_TRACKS,
            "b.mp4": ProbeResult(has_video=True, has_audio=True, length_seconds=5400.0),
        }
    )

    report = validate(data_folder, recording_list, labels_folder, probe)

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
    data_folder: Path,
    recording_list: Path,
    probe_result: ProbeResult,
    message: str,
    labels_folder: Path,
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4", length=60.0))

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": probe_result})
    )

    assert [(e.subject, e.message) for e in report.errors] == [("a.mp4", message)]


def test_listed_recording_missing_from_the_folder_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(
        HEADER + list_row("a.mp4") + list_row("gone.mp4", b"gone")
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        ("gone.mp4", "listed but missing from the recordings folder")
    ]


def test_listed_recording_whose_size_changed_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"trimmed")
    recording_list.write_text(HEADER + list_row("a.mp4", b"original recording"))

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.mp4", "size changed: listed as 18 bytes, now 7 bytes")
    ]


def test_recording_not_in_the_list_is_skipped_with_the_row_to_add(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "listed.mp4", b"listed")
    add_recording(data_folder, "new.mp4", b"video")
    recording_list.write_text(HEADER + list_row("listed.mp4", b"listed", length=3600.0))
    write_labels(labels_folder, "listed.toml", b"listed")
    probe = FakeProbe(
        {
            "listed.mp4": BOTH_TRACKS,
            "new.mp4": ProbeResult(
                has_video=True, has_audio=True, length_seconds=1800.25
            ),
        }
    )

    report = validate(data_folder, recording_list, labels_folder, probe)

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
    assert report.skipped_count == 1
    assert report.hours == 1.0


def test_duplicate_file_name_in_the_list_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(
        HEADER + list_row("a.mp4") + list_row("a.mp4", b"other content")
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.mp4", "file name listed more than once in the list of recordings")
    ]


def test_duplicate_fingerprint_in_the_list_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"same")
    add_recording(data_folder, "b.mp4", b"same")
    recording_list.write_text(
        HEADER + list_row("a.mp4", b"same") + list_row("b.mp4", b"same")
    )
    probe = FakeProbe({"a.mp4": BOTH_TRACKS, "b.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert [(e.subject, e.message) for e in report.errors] == [
        ("b.mp4", "same fingerprint as a.mp4 in the list of recordings")
    ]


def test_missing_list_of_recordings_is_an_error(
    data_folder: Path, tmp_path: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    missing = tmp_path / "missing.csv"

    report = validate(
        data_folder, missing, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

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
        *[
            (
                HEADER + f"a.mp4,5,abc,{length}\n",
                f"line 2: length_seconds {length!r} is not a positive number",
            )
            for length in ["nan", "inf", "-60", "0"]
        ],
    ],
)
def test_unreadable_list_of_recordings_is_an_error(
    data_folder: Path,
    recording_list: Path,
    content: str,
    message: str,
    labels_folder: Path,
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(content)

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(recording_list), message)
    ]


def test_recording_the_probe_cannot_read_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    class FailingProbe:
        def probe(self, path: Path) -> ProbeResult:
            raise ProbeError("Invalid data found when processing input")

    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))

    report = validate(data_folder, recording_list, labels_folder, FailingProbe())

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.mp4", "media probe failed: Invalid data found when processing input")
    ]


def test_listed_length_far_from_the_probed_length_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "near.mp4", b"near")
    add_recording(data_folder, "far.mp4", b"far")
    recording_list.write_text(
        HEADER
        + list_row("near.mp4", b"near", length=3601.0)
        + list_row("far.mp4", b"far", length=3601.5)
    )
    probe = FakeProbe({"near.mp4": BOTH_TRACKS, "far.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert [(e.subject, e.message) for e in report.errors] == [
        ("far.mp4", "length changed: listed as 3601.500 s, media probe says 3600.000 s")
    ]


def test_unlisted_copy_of_a_listed_recording_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"same")
    add_recording(data_folder, "copy.mp4", b"same")
    recording_list.write_text(HEADER + list_row("a.mp4", b"same"))
    write_labels(labels_folder, "a.toml", b"same")
    probe = FakeProbe({"a.mp4": BOTH_TRACKS, "copy.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "copy.mp4",
            "not in the list of recordings, but has the same fingerprint as a.mp4",
        )
    ]
    assert report.warnings == []
    assert report.skipped_count == 1


def test_suggested_row_for_a_file_name_with_a_comma_can_be_pasted_in(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "news, late.mp4")
    probe = FakeProbe({"news, late.mp4": BOTH_TRACKS})
    [warning] = validate(data_folder, recording_list, labels_folder, probe).warnings
    suggested_row = warning.message.split("add this row: ")[1]

    recording_list.write_text(HEADER + suggested_row + "\n")
    write_labels(labels_folder, "news, late.toml")
    report = validate(data_folder, recording_list, labels_folder, probe)

    assert report.errors == []
    assert report.warnings == []
    assert report.recording_count == 1


def test_label_files_are_summarised_by_channel_and_commercial_break(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"first")
    add_recording(data_folder, "b.mp4", b"second")
    recording_list.write_text(
        HEADER + list_row("a.mp4", b"first") + list_row("b.mp4", b"second")
    )
    write_labels(
        labels_folder,
        "a.toml",
        b"first",
        channel="TV Asahi",
        commercial_breaks="""[
  { start = "00:30:00", end = "00:32:00" },
  { start = "00:12:03.2", end = "00:15:03" },
]""",
    )
    write_labels(labels_folder, "b.toml", b"second", channel="NTV")
    probe = FakeProbe({"a.mp4": BOTH_TRACKS, "b.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert report.errors == []
    assert report.warnings == []
    assert report.channels == ["NTV", "TV Asahi"]
    assert report.commercial_break_count == 2


def test_recording_without_a_label_file_is_skipped_with_a_warning(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "labeled.mp4", b"labeled")
    add_recording(data_folder, "unlabeled.mp4", b"unlabeled")
    recording_list.write_text(
        HEADER
        + list_row("labeled.mp4", b"labeled")
        + list_row("unlabeled.mp4", b"unlabeled")
    )
    write_labels(labels_folder, "labeled.toml", b"labeled")
    probe = FakeProbe({"labeled.mp4": BOTH_TRACKS, "unlabeled.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert report.errors == []
    assert [(w.subject, w.message) for w in report.warnings] == [
        (
            "unlabeled.mp4",
            f"no usable label file, so skipped; looked in {labels_folder}",
        )
    ]
    assert report.unlabeled_count == 1


def test_label_file_for_a_recording_not_in_the_list_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(labels_folder, "a.toml")
    write_labels(labels_folder, "stray.toml", b"never listed", channel="NTV")

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "stray.toml",
            f"recording {fingerprint(b'never listed')} is not in the list of "
            "recordings",
        )
    ]
    assert report.channels == ["TBS"]


def test_two_label_files_for_one_recording_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(labels_folder, "a.toml", channel="TBS")
    write_labels(labels_folder, "a copy.toml", channel="NTV")

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.toml", "same recording as a copy.toml; a recording has one label file")
    ]
    assert [(w.subject, w.message) for w in report.warnings] == [
        ("a.mp4", f"no usable label file, so skipped; looked in {labels_folder}")
    ]
    assert report.channels == []


@pytest.mark.parametrize(
    ("written", "shown"),
    [
        ('"00:61:00"', "00:61:00"),
        ('"12:03"', "12:03"),
        ('"00:12:03.25"', "00:12:03.25"),
        ('"00:12:03,2"', "00:12:03,2"),
        ("00:12:03", "00:12:03"),
        ("723", "723"),
        ('"0０:1２:03"', "0０:1２:03"),
    ],
)
def test_time_that_cannot_be_read_is_an_error(
    data_folder: Path,
    recording_list: Path,
    labels_folder: Path,
    written: str,
    shown: str,
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks=f"""[
  {{ start = "00:01:00", end = "00:02:00" }},
  {{ start = {written}, end = "00:15:00" }},
]""",
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            f"commercial break 2 ({shown} to 00:15:00): can't read the start "
            f"{shown}; write times in quotes as hh:mm:ss or hh:mm:ss.d",
        )
    ]
    assert report.commercial_break_count == 0


@pytest.mark.parametrize("end", ["00:14:59.9", "00:15:00"])
def test_commercial_break_that_does_not_end_after_its_start_is_an_error(
    data_folder: Path,
    recording_list: Path,
    labels_folder: Path,
    end: str,
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks=f'[{{ start = "00:15:00", end = "{end}" }}]',
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            f"commercial break 1 (00:15:00 to {end}): doesn't end after it starts",
        )
    ]


def test_overlapping_commercial_breaks_are_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks="""[
  { start = "00:30:00", end = "00:31:00" },
  { start = "00:10:00", end = "00:20:00" },
  { start = "00:12:00", end = "00:13:00" },
  { start = "00:19:59.9", end = "00:21:00" },
  { start = "00:40:00", end = "00:41:00" },
]""",
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            "commercial breaks 2 (00:10:00 to 00:20:00) and 3 (00:12:00 to 00:13:00) "
            "overlap",
        ),
        (
            "a.toml",
            "commercial breaks 2 (00:10:00 to 00:20:00) and 4 (00:19:59.9 to "
            "00:21:00) overlap",
        ),
    ]


def test_commercial_breaks_that_touch_are_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks="""[
  { start = "00:10:00", end = "00:12:00" },
  { start = "00:12:00", end = "00:13:00" },
]""",
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            "commercial breaks 1 (00:10:00 to 00:12:00) and 2 (00:12:00 to 00:13:00) "
            "touch; a commercial break is one continuous run, so join them",
        )
    ]


def test_time_past_the_end_of_the_recording_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4", length=3600.25))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks="""[
  { start = "00:50:00", end = "00:55:00" },
  { start = "00:58:00", end = "01:00:00.4" },
]""",
    )
    probe = FakeProbe(
        {"a.mp4": ProbeResult(has_video=True, has_audio=True, length_seconds=3600.25)}
    )

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            "commercial break 2 (00:58:00 to 01:00:00.4): runs past the end of the "
            "recording at 01:00:00.250",
        )
    ]


def test_commercial_break_can_end_at_the_last_tenth_of_the_recording(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4", length=3600.25))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks='[{ start = "00:58:00", end = "01:00:00.3" }]',
    )
    probe = FakeProbe(
        {"a.mp4": ProbeResult(has_video=True, has_audio=True, length_seconds=3600.25)}
    )

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert report.errors == []
    assert report.commercial_break_count == 1


FINGERPRINT_LINE = f'recording = "{fingerprint(b"video")}"\n'
RECORDING_HINT = (
    "recording must be the recording's fingerprint, in quotes, copied from the "
    "list of recordings"
)
BREAKS_HINT = (
    'commercial_breaks must be a list like [{ start = "00:12:03.2", end = "00:15:03" }]'
)


@pytest.mark.parametrize(
    ("content", "messages"),
    [
        ('channel = "TBS"\n', [RECORDING_HINT]),
        ('recording = 42\nchannel = "TBS"\n', [RECORDING_HINT]),
        (FINGERPRINT_LINE, ["channel must be the channel's name, in quotes"]),
        (
            FINGERPRINT_LINE + 'channel = ""\n',
            ["channel must be the channel's name, in quotes"],
        ),
        *[
            (
                FINGERPRINT_LINE + f'channel = "{channel}"\n',
                ["channel can't start or end with a space"],
            )
            for channel in [" TBS", "TBS ", "TBS\u3000"]
        ],
        (
            FINGERPRINT_LINE + 'channel = "BS/TBS"\n',
            ["channel can't contain / or \\, since it names the channel's logo file"],
        ),
        (
            FINGERPRINT_LINE + 'channel = "TBS"\ncommercial_break = []\n',
            [
                "unknown field commercial_break; the fields are recording, "
                "channel and commercial_breaks"
            ],
        ),
        (
            FINGERPRINT_LINE + 'channel = "TBS"\ncommercial_breaks = "none"\n',
            [BREAKS_HINT],
        ),
        (
            FINGERPRINT_LINE
            + 'channel = "TBS"\ncommercial_breaks = [{ start = "00:01:00" }, 5]\n',
            [
                "commercial break 1 must have a start and an end, and nothing else",
                "commercial break 2 must have a start and an end, and nothing else",
            ],
        ),
        (
            FINGERPRINT_LINE + 'channel = "TBS"\ncommercial_breaks = [{ start = '
            '"00:01:00", end = "00:02:00", note = "promo" }]\n',
            ["commercial break 1 must have a start and an end, and nothing else"],
        ),
    ],
)
def test_label_file_with_missing_or_wrong_fields_is_an_error(
    data_folder: Path,
    recording_list: Path,
    labels_folder: Path,
    content: str,
    messages: list[str],
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    (labels_folder / "a.toml").write_text(content)

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.toml", message) for message in messages
    ]
    assert report.channels == []


def test_label_file_that_is_not_valid_toml_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    (labels_folder / "a.toml").write_text("channel TBS\n")

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    [error] = report.errors
    assert error.subject == "a.toml"
    assert error.message.startswith("not valid TOML: ")
    assert [(w.subject, w.message) for w in report.warnings] == [
        ("a.mp4", f"no usable label file, so skipped; looked in {labels_folder}")
    ]


def test_channels_without_a_logo_file_are_listed(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4", b"first")
    add_recording(data_folder, "b.mp4", b"second")
    recording_list.write_text(
        HEADER + list_row("a.mp4", b"first") + list_row("b.mp4", b"second")
    )
    write_labels(labels_folder, "a.toml", b"first", channel="TV Asahi")
    write_labels(labels_folder, "b.toml", b"second", channel="NTV")
    (data_folder / "logos").mkdir()
    (data_folder / "logos" / "TV Asahi.lgd").write_bytes(b"logo")
    (data_folder / "logos" / "TBS.lgd").write_bytes(b"logo")
    probe = FakeProbe({"a.mp4": BOTH_TRACKS, "b.mp4": BOTH_TRACKS})

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert report.errors == []
    assert report.channels == ["NTV", "TV Asahi"]
    assert report.channels_without_logo == ["NTV"]


def test_label_file_with_a_bad_time_is_still_checked_against_the_others(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    write_labels(
        labels_folder,
        "a copy.toml",
        commercial_breaks='[{ start = "00:15:00", end = "00:14:00" }]',
    )
    write_labels(labels_folder, "a.toml")
    write_labels(
        labels_folder,
        "stray.toml",
        b"never listed",
        commercial_breaks='[{ start = "00:61:00", end = "01:02:00" }]',
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a copy.toml",
            "commercial break 1 (00:15:00 to 00:14:00): doesn't end after it starts",
        ),
        ("a.toml", "same recording as a copy.toml; a recording has one label file"),
        (
            "stray.toml",
            "commercial break 1 (00:61:00 to 01:02:00): can't read the start "
            "00:61:00; write times in quotes as hh:mm:ss or hh:mm:ss.d",
        ),
        (
            "stray.toml",
            f"recording {fingerprint(b'never listed')} is not in the list of "
            "recordings",
        ),
    ]


def test_recording_whose_label_file_has_errors_is_skipped_with_a_warning(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4", length=60.0))
    write_labels(
        labels_folder,
        "a.toml",
        commercial_breaks='[{ start = "00:00:30", end = "00:01:30" }]',
    )
    probe = FakeProbe(
        {"a.mp4": ProbeResult(has_video=True, has_audio=True, length_seconds=60.0)}
    )

    report = validate(data_folder, recording_list, labels_folder, probe)

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            "commercial break 1 (00:00:30 to 00:01:30): runs past the end of the "
            "recording at 00:01:00.000",
        )
    ]
    assert [(w.subject, w.message) for w in report.warnings] == [
        ("a.mp4", f"no usable label file, so skipped; looked in {labels_folder}")
    ]
    assert report.unlabeled_count == 1
    assert report.commercial_break_count == 0


def test_label_file_that_is_not_utf8_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    (labels_folder / "a.toml").write_bytes(
        f'recording = "{fingerprint(b"video")}"\nchannel = "テレビ朝日"\n'.encode(
            "shift_jis"
        )
    )
    write_labels(labels_folder, "b.toml", b"never listed")

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        ("a.toml", "not UTF-8 text; save it as UTF-8"),
        (
            "b.toml",
            f"recording {fingerprint(b'never listed')} is not in the list of "
            "recordings",
        ),
    ]


def test_label_files_are_checked_when_the_data_folder_is_missing(
    tmp_path: Path, recording_list: Path, labels_folder: Path
) -> None:
    missing = tmp_path / "unplugged drive"
    recording_list.write_text(
        HEADER + list_row("a.mp4", b"first") + list_row("b.mp4", b"second")
    )
    write_labels(labels_folder, "a.toml", b"first", channel="NTV")
    write_labels(
        labels_folder,
        "b.toml",
        b"second",
        commercial_breaks='[{ start = "00:15:00", end = "00:14:00" }]',
    )

    report = validate(missing, recording_list, labels_folder, FakeProbe({}))

    assert [(e.subject, e.message) for e in report.errors] == [
        (str(missing), "data folder does not exist"),
        (
            "b.toml",
            "commercial break 1 (00:15:00 to 00:14:00): doesn't end after it starts",
        ),
    ]
    assert report.warnings == []
    assert report.channels == ["NTV"]
    assert report.channels_without_logo == ["NTV"]


def test_label_file_that_cannot_be_opened_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    locked = write_labels(labels_folder, "a.toml")
    locked.chmod(0)
    write_labels(labels_folder, "b.toml", b"never listed")

    try:
        report = validate(
            data_folder,
            recording_list,
            labels_folder,
            FakeProbe({"a.mp4": BOTH_TRACKS}),
        )
    finally:
        locked.chmod(0o644)

    assert [(e.subject, e.message[:15]) for e in report.errors] == [
        ("a.toml", "can't be read: "),
        ("b.toml", "recording e51ef"),
    ]


@pytest.mark.parametrize(
    "written",
    [
        fingerprint(b"video").upper(),
        fingerprint(b"video") + " ",
        fingerprint(b"video")[:-1],
    ],
)
def test_recording_that_is_not_a_fingerprint_is_an_error(
    data_folder: Path, recording_list: Path, labels_folder: Path, written: str
) -> None:
    add_recording(data_folder, "a.mp4")
    recording_list.write_text(HEADER + list_row("a.mp4"))
    (labels_folder / "a.toml").write_text(
        f'recording = "{written}"\nchannel = "TBS"\ncommercial_breaks = []\n'
    )

    report = validate(
        data_folder, recording_list, labels_folder, FakeProbe({"a.mp4": BOTH_TRACKS})
    )

    assert [(e.subject, e.message) for e in report.errors] == [
        (
            "a.toml",
            f"recording {written!r} isn't a fingerprint: 64 lower-case hex digits, "
            "copied from the list of recordings",
        )
    ]
