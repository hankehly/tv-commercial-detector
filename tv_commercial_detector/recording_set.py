"""The recording set: recordings in the data folder and the list that describes them.

The list of recordings is a CSV file in the repository with one row per
recording: its file name, size in bytes, fingerprint (the SHA-256 hash of the
file, in hex) and length in seconds. The recordings themselves are every MP4
file directly inside the data folder's ``recordings/`` folder.
"""

import csv
import hashlib
import io
import math
from dataclasses import dataclass, field
from pathlib import Path

from tv_commercial_detector.labels import find_label_files, read_label_file
from tv_commercial_detector.media_probe import MediaProbe, ProbeError, ProbeResult

LIST_COLUMNS = ("file_name", "size_bytes", "fingerprint", "length_seconds")

LOGO_SUFFIX = ".lgd"
"""The extension of logo files, which live in the data folder's ``logos/`` folder."""

LENGTH_TOLERANCE_SECONDS = 1.0
"""How far a listed length may be from the probed length before it's an error."""


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
        row = io.StringIO()
        csv.writer(row, lineterminator="").writerow(
            [
                self.file_name,
                self.size_bytes,
                self.fingerprint,
                f"{self.length_seconds:.3f}",
            ]
        )
        return row.getvalue()


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
    not being listed, and ``unlabeled_count`` those skipped for having no usable
    label file. ``channels`` and ``commercial_break_count`` cover the
    label files without errors; ``channels_without_logo`` lists those channels
    with no logo file.
    """

    errors: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)
    recording_count: int = 0
    skipped_count: int = 0
    unlabeled_count: int = 0
    total_length_seconds: float = 0.0
    channels: list[str] = field(default_factory=list)
    commercial_break_count: int = 0
    channels_without_logo: list[str] = field(default_factory=list)

    @property
    def hours(self) -> float:
        """Total length of the checked recordings, in hours."""
        return self.total_length_seconds / 3600


class _ListError(Exception):
    """The list of recordings cannot be read."""


def validate(
    data_folder: Path, recording_list: Path, labels_folder: Path, probe: MediaProbe
) -> ValidationReport:
    """Check the recordings in ``data_folder`` and their labels.

    Parameters
    ----------
    data_folder : Path
        The data folder; its ``recordings/`` folder holds the recordings.
    recording_list : Path
        The CSV list of recordings.
    labels_folder : Path
        The folder holding the label files.
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
            _warn_unlisted(path, entries, probe, report)
        else:
            _check_listed(path, entry, probe, report)

    _check_labels(labels_folder, list(entries.values()), found, report)
    report.channels_without_logo = [
        channel
        for channel in report.channels
        if not logo_file(data_folder, channel).is_file()
    ]
    return report


def logo_file(data_folder: Path, channel: str) -> Path:
    """Return where a channel's logo file belongs for join_logo_scp.

    Parameters
    ----------
    data_folder : Path
        The data folder.
    channel : str
        The channel, as written in the label files.

    Returns
    -------
    Path
        ``logos/<channel>.lgd`` inside the data folder.
    """
    return data_folder / "logos" / f"{channel}{LOGO_SUFFIX}"


def _check_labels(
    labels_folder: Path,
    listed: list[ListEntry],
    found: set[str],
    report: ValidationReport,
) -> None:
    """Check every label file against the list and summarise the usable ones.

    Only label files without errors count towards the channels and commercial
    breaks in the summary. A listed recording in the recordings folder without a
    label file is skipped with a warning.

    Parameters
    ----------
    labels_folder : Path
        The folder holding the label files.
    listed : list[ListEntry]
        Every listed recording.
    found : set[str]
        The file names of the recordings in the recordings folder.
    report : ValidationReport
        Receives any errors and warnings, the channels and the commercial break
        count.
    """
    by_fingerprint = {entry.fingerprint: entry for entry in listed}
    channels: set[str] = set()
    labeled: dict[str, str] = {}
    for path in find_label_files(labels_folder):
        errors_before = len(report.errors)
        label_file, problems = read_label_file(path)
        report.errors.extend(Problem(path.name, message) for message in problems)
        if label_file is None:
            continue
        first = labeled.setdefault(label_file.recording, path.name)
        if first != path.name:
            report.errors.append(
                Problem(
                    path.name,
                    f"same recording as {first}; a recording has one label file",
                )
            )
        elif label_file.recording not in by_fingerprint:
            report.errors.append(
                Problem(
                    path.name,
                    f"recording {label_file.recording} is not in the list of "
                    "recordings",
                )
            )
        else:
            length = by_fingerprint[label_file.recording].length_seconds
            report.errors.extend(
                Problem(path.name, message)
                for message in label_file.problems_against(length)
            )
        if len(report.errors) == errors_before:
            channels.add(label_file.channel)
            report.commercial_break_count += len(label_file.commercial_breaks)
    report.channels = sorted(channels)

    for entry in listed:
        if entry.file_name in found and entry.fingerprint not in labeled:
            report.unlabeled_count += 1
            report.warnings.append(
                Problem(
                    entry.file_name,
                    f"no usable label file, so skipped; looked in {labels_folder}",
                )
            )


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
        Reports the recording's tracks and length.
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
    if abs(result.length_seconds - entry.length_seconds) > LENGTH_TOLERANCE_SECONDS:
        report.errors.append(
            Problem(
                path.name,
                f"length changed: listed as {entry.length_seconds:.3f} s, "
                f"media probe says {result.length_seconds:.3f} s",
            )
        )


def _warn_unlisted(
    path: Path,
    listed: dict[str, ListEntry],
    probe: MediaProbe,
    report: ValidationReport,
) -> None:
    """Skip an unlisted recording with a warning showing the row to add.

    If the recording has the same fingerprint as a listed one, that is an error
    instead, since its row could never be added.

    Parameters
    ----------
    path : Path
        The recording.
    listed : dict[str, ListEntry]
        The listed recordings, keyed by file name.
    probe : MediaProbe
        Reports the recording's length for the row.
    report : ValidationReport
        Receives the warning, or an error if the probe fails or the recording
        duplicates a listed one.
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
    same = [e.file_name for e in listed.values() if e.fingerprint == entry.fingerprint]
    if same:
        report.errors.append(
            Problem(
                path.name,
                "not in the list of recordings, but has the same fingerprint as "
                f"{same[0]}",
            )
        )
        return
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
    if not (math.isfinite(length) and length > 0):
        raise _ListError(
            f"line {line}: length_seconds {length_seconds!r} is not a positive number"
        )
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
