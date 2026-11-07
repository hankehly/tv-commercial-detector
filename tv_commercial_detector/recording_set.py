"""The recording set: recordings in the data folder and the list that describes them.

The list of recordings is a CSV file in the repository with one row per
recording: its file name, size in bytes, fingerprint (the SHA-256 hash of the
file, in hex) and length in seconds. The recordings themselves are every MP4
file directly inside the data folder's ``recordings/`` folder.
"""

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from tv_commercial_detector.media_probe import MediaProbe, ProbeError, ProbeResult

LIST_COLUMNS = ("file_name", "size_bytes", "fingerprint", "length_seconds")


@dataclass(frozen=True)
class ListEntry:
    """One row of the list of recordings."""

    file_name: str
    size_bytes: int
    fingerprint: str
    length_seconds: float

    def as_row(self) -> str:
        """Write this entry as a row of the list of recordings.

        Returns
        -------
        str
            The row, without a line ending, with the length to milliseconds.
        """
        return (
            f"{self.file_name},{self.size_bytes},{self.fingerprint},"
            f"{self.length_seconds:.3f}"
        )


@dataclass(frozen=True)
class Problem:
    """One error or warning, naming what it is about."""

    subject: str
    message: str


@dataclass
class ValidationReport:
    """The outcome of validating a recording set.

    ``recording_count`` and ``total_length_seconds`` cover the listed recordings
    found in the data folder; ``skipped_count`` counts the recordings skipped for
    not being listed.
    """

    errors: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)
    recording_count: int = 0
    skipped_count: int = 0
    total_length_seconds: float = 0.0

    @property
    def hours(self) -> float:
        """Total length of the checked recordings, in hours."""
        return self.total_length_seconds / 3600


class _ListError(Exception):
    """The list of recordings cannot be read."""


def validate(
    data_folder: Path, recording_list: Path, probe: MediaProbe
) -> ValidationReport:
    """Check the recordings in ``data_folder`` against ``recording_list``.

    Parameters
    ----------
    data_folder : Path
        The data folder; its ``recordings/`` folder holds the recordings.
    recording_list : Path
        The CSV list of recordings.
    probe : MediaProbe
        Reports each recording's tracks and length.

    Returns
    -------
    ValidationReport
        Every error and warning found, with a summary of the recordings.
    """
    report = ValidationReport()
    if not data_folder.is_dir():
        report.errors.append(Problem(str(data_folder), "data folder does not exist"))
        return report

    recordings_folder = data_folder / "recordings"
    recordings = _find_recordings(recordings_folder)
    if not recordings:
        report.errors.append(Problem(str(recordings_folder), "no MP4 recordings found"))
        return report

    try:
        rows = _read_list(recording_list)
    except _ListError as e:
        report.errors.append(Problem(str(recording_list), str(e)))
        return report
    entries = _unique_entries(rows, report)

    found = {path.name for path in recordings}
    for name in entries:
        if name not in found:
            report.errors.append(
                Problem(name, "listed but missing from the recordings folder")
            )

    for path in recordings:
        entry = entries.get(path.name)
        if entry is None:
            _warn_unlisted(path, probe, report)
        else:
            _check_listed(path, entry, probe, report)
    return report


def _unique_entries(
    rows: list[ListEntry], report: ValidationReport
) -> dict[str, ListEntry]:
    """Index rows by file name, reporting duplicate names and fingerprints.

    A row repeating an earlier file name is reported and ignored.

    Parameters
    ----------
    rows : list[ListEntry]
        Every row of the list of recordings, in order.
    report : ValidationReport
        Receives an error for each duplicate.

    Returns
    -------
    dict[str, ListEntry]
        The first row for each file name, keyed by file name.
    """
    entries: dict[str, ListEntry] = {}
    names_by_fingerprint: dict[str, str] = {}
    for entry in rows:
        if entry.file_name in entries:
            report.errors.append(
                Problem(
                    entry.file_name,
                    "file name listed more than once in the list of recordings",
                )
            )
            continue
        if entry.fingerprint in names_by_fingerprint:
            first = names_by_fingerprint[entry.fingerprint]
            report.errors.append(
                Problem(
                    entry.file_name,
                    f"same fingerprint as {first} in the list of recordings",
                )
            )
        else:
            names_by_fingerprint[entry.fingerprint] = entry.file_name
        entries[entry.file_name] = entry
    return entries


def _check_listed(
    path: Path, entry: ListEntry, probe: MediaProbe, report: ValidationReport
) -> None:
    """Check a listed recording's size and tracks, and count it in the summary.

    Parameters
    ----------
    path : Path
        The recording.
    entry : ListEntry
        Its row in the list of recordings.
    probe : MediaProbe
        Reports the recording's tracks.
    report : ValidationReport
        Receives any errors and the recording's length.
    """
    report.recording_count += 1
    report.total_length_seconds += entry.length_seconds

    size = path.stat().st_size
    if size != entry.size_bytes:
        report.errors.append(
            Problem(
                path.name,
                f"size changed: listed as {entry.size_bytes} bytes, now {size} bytes",
            )
        )

    result = _probe(path, probe, report)
    if result is None:
        return
    if not result.has_video:
        report.errors.append(Problem(path.name, "no video track"))
    if not result.has_audio:
        report.errors.append(Problem(path.name, "no audio track"))


def _warn_unlisted(path: Path, probe: MediaProbe, report: ValidationReport) -> None:
    """Skip an unlisted recording with a warning showing the row to add.

    Parameters
    ----------
    path : Path
        The recording.
    probe : MediaProbe
        Reports the recording's length for the row.
    report : ValidationReport
        Receives the warning, or an error if the probe fails.
    """
    report.skipped_count += 1
    result = _probe(path, probe, report)
    if result is None:
        return
    entry = ListEntry(
        file_name=path.name,
        size_bytes=path.stat().st_size,
        fingerprint=_fingerprint(path),
        length_seconds=result.length_seconds,
    )
    report.warnings.append(
        Problem(
            path.name,
            "not in the list of recordings, so skipped; "
            f"add this row: {entry.as_row()}",
        )
    )


def _probe(
    path: Path, probe: MediaProbe, report: ValidationReport
) -> ProbeResult | None:
    """Probe a recording, reporting an error if the probe can't read it.

    Parameters
    ----------
    path : Path
        The recording.
    probe : MediaProbe
        The media probe to ask.
    report : ValidationReport
        Receives an error if the probe fails.

    Returns
    -------
    ProbeResult | None
        The probe's answer, or ``None`` if it failed.
    """
    try:
        return probe.probe(path)
    except ProbeError as e:
        report.errors.append(Problem(path.name, f"media probe failed: {e}"))
        return None


def _fingerprint(path: Path) -> str:
    """Return the SHA-256 hash of a file, in hex.

    Parameters
    ----------
    path : Path
        The file to hash.

    Returns
    -------
    str
        The SHA-256 hash, as 64 hex digits.
    """
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _read_list(recording_list: Path) -> list[ListEntry]:
    """Read every row of the list of recordings.

    Parameters
    ----------
    recording_list : Path
        The CSV list of recordings.

    Returns
    -------
    list[ListEntry]
        Every row, in order; blank lines are ignored.

    Raises
    ------
    _ListError
        If the file is missing, its header is wrong, or a row can't be read.
    """
    if not recording_list.is_file():
        raise _ListError("list of recordings does not exist")
    with recording_list.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if tuple(header or ()) != LIST_COLUMNS:
            raise _ListError(f"header must be: {','.join(LIST_COLUMNS)}")
        return [_parse_row(values, reader.line_num) for values in reader if values]


def _parse_row(values: list[str], line: int) -> ListEntry:
    """Turn one CSV row into a list entry.

    Parameters
    ----------
    values : list[str]
        The row's values.
    line : int
        The row's line number, for error messages.

    Returns
    -------
    ListEntry
        The parsed row.

    Raises
    ------
    _ListError
        If the row has the wrong number of values or a value can't be read.
    """
    if len(values) != len(LIST_COLUMNS):
        raise _ListError(
            f"line {line}: expected {len(LIST_COLUMNS)} values, found {len(values)}"
        )
    file_name, size_bytes, fingerprint, length_seconds = values
    try:
        size = int(size_bytes)
    except ValueError:
        raise _ListError(
            f"line {line}: size_bytes {size_bytes!r} is not a whole number"
        ) from None
    try:
        length = float(length_seconds)
    except ValueError:
        raise _ListError(
            f"line {line}: length_seconds {length_seconds!r} is not a number"
        ) from None
    return ListEntry(file_name, size, fingerprint, length)


def _find_recordings(recordings_folder: Path) -> list[Path]:
    """Find the recordings: every MP4 file directly inside a folder.

    Parameters
    ----------
    recordings_folder : Path
        The data folder's ``recordings/`` folder.

    Returns
    -------
    list[Path]
        The recordings, sorted by name; empty if the folder doesn't exist.
    """
    if not recordings_folder.is_dir():
        return []
    return sorted(
        path
        for path in recordings_folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".mp4"
    )
