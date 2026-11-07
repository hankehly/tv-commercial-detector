"""Label files: one recording's channel and commercial breaks, written by hand.

A label file is TOML, tracked in the repository and named after its recording
for people's convenience. It belongs to its recording by fingerprint::

    recording = "a24b31a34ad5c13200e232abee93f71390f1b71d468464719e85f26221ed91fd"
    channel = "TBS"
    commercial_breaks = [
      { start = "00:12:03.2", end = "00:15:03" },
    ]

Times are written ``hh:mm:ss``, optionally with tenths, in any order.
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_TIME = re.compile(r"(\d{1,2}):([0-5]\d):([0-5]\d)(\.\d)?")

_TIME_HINT = "write times in quotes as hh:mm:ss or hh:mm:ss.d"

_FIELDS = ("recording", "channel", "commercial_breaks")


@dataclass(frozen=True)
class CommercialBreak:
    """One labeled commercial break, as written and in seconds.

    ``number`` is its position in the label file, counting from 1, and the
    ``*_text`` fields are its times as written, so messages can point to it.
    """

    number: int
    start_text: str
    end_text: str
    start_seconds: float
    end_seconds: float

    @property
    def span(self) -> str:
        """Its start and end as written, for messages."""
        return f"{self.start_text} to {self.end_text}"

    @property
    def name(self) -> str:
        """How messages refer to this commercial break."""
        return f"commercial break {self.number} ({self.span})"


@dataclass(frozen=True)
class LabelFile:
    """A label file that could be read: its recording, channel and labels.

    ``commercial_breaks`` holds the commercial breaks whose times could be read,
    sorted by start.
    """

    path: Path
    recording: str
    channel: str
    commercial_breaks: tuple[CommercialBreak, ...]

    def problems_against(self, length_seconds: float) -> list[str]:
        """Check the commercial breaks against the recording's length.

        Parameters
        ----------
        length_seconds : float
            The recording's length, from the list of recordings.

        Returns
        -------
        list[str]
            A message for each commercial break running past the end.
        """
        return [
            f"{b.name}: runs past the end of the recording at {_clock(length_seconds)}"
            for b in sorted(self.commercial_breaks, key=lambda b: b.number)
            if b.end_seconds > length_seconds
        ]


def find_label_files(labels_folder: Path) -> list[Path]:
    """Find the label files: every TOML file directly inside a folder.

    Parameters
    ----------
    labels_folder : Path
        The folder holding the label files.

    Returns
    -------
    list[Path]
        The label files, sorted by name; empty if the folder doesn't exist.
    """
    if not labels_folder.is_dir():
        return []
    return sorted(
        path
        for path in labels_folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".toml"
    )


def read_label_file(path: Path) -> tuple[LabelFile | None, list[str]]:
    """Read a label file, collecting every problem found inside it.

    Parameters
    ----------
    path : Path
        The label file.

    Returns
    -------
    tuple[LabelFile | None, list[str]]
        The label file, or ``None`` if its fields can't be read, and a message
        for each problem found in it.
    """
    try:
        with path.open("rb") as f:
            fields = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return None, [f"not valid TOML: {e}"]

    problems = [
        f"unknown field {name}; the fields are recording, channel and commercial_breaks"
        for name in fields
        if name not in _FIELDS
    ]
    recording = _read_recording(fields.get("recording"), problems)
    channel = _read_channel(fields.get("channel"), problems)
    entries = fields.get("commercial_breaks", [])
    if not isinstance(entries, list):
        problems.append(
            'commercial_breaks must be a list like [{ start = "00:12:03.2", '
            'end = "00:15:03" }]'
        )
        entries = []

    breaks = []
    for number, entry in enumerate(entries, start=1):
        commercial_break = _read_break(number, entry, problems)
        if commercial_break is not None:
            breaks.append(commercial_break)
    breaks.sort(key=lambda b: b.start_seconds)
    problems.extend(_overlaps(breaks))
    if problems or recording is None or channel is None:
        return None, problems
    label_file = LabelFile(
        path=path,
        recording=recording,
        channel=channel,
        commercial_breaks=tuple(breaks),
    )
    return label_file, problems


def _read_recording(value: object, problems: list[str]) -> str | None:
    """Read the ``recording`` field: the recording's fingerprint.

    Parameters
    ----------
    value : object
        The field as TOML gave it, or ``None`` if it is missing.
    problems : list[str]
        Receives a message if it isn't a fingerprint in quotes.

    Returns
    -------
    str | None
        The fingerprint, or ``None`` if it can't be read.
    """
    if isinstance(value, str) and value:
        return value
    problems.append(
        "recording must be the recording's fingerprint, in quotes, copied from "
        "the list of recordings"
    )
    return None


def _read_channel(value: object, problems: list[str]) -> str | None:
    """Read the ``channel`` field, which also names the channel's logo file.

    Parameters
    ----------
    value : object
        The field as TOML gave it, or ``None`` if it is missing.
    problems : list[str]
        Receives a message if it isn't a name in quotes, or can't name a file.

    Returns
    -------
    str | None
        The channel, or ``None`` if it can't be read.
    """
    if not isinstance(value, str) or not value.strip():
        problems.append("channel must be the channel's name, in quotes")
        return None
    if "/" in value or "\\" in value:
        problems.append(
            "channel can't contain / or \\, since it names the channel's logo file"
        )
        return None
    return value


def _overlaps(breaks: list[CommercialBreak]) -> list[str]:
    """Find commercial breaks that overlap or touch.

    Parameters
    ----------
    breaks : list[CommercialBreak]
        The commercial breaks, sorted by start.

    Returns
    -------
    list[str]
        A message for each commercial break that overlaps or touches an earlier
        one, naming the earlier one that ends last.
    """
    problems = []
    latest: CommercialBreak | None = None
    for commercial_break in breaks:
        if latest is not None and commercial_break.start_seconds <= latest.end_seconds:
            pair = (
                f"commercial breaks {latest.number} ({latest.span}) and "
                f"{commercial_break.number} ({commercial_break.span})"
            )
            if commercial_break.start_seconds < latest.end_seconds:
                problems.append(f"{pair} overlap")
            else:
                problems.append(
                    f"{pair} touch; a commercial break is one continuous run, "
                    "so join them"
                )
        if latest is None or commercial_break.end_seconds > latest.end_seconds:
            latest = commercial_break
    return problems


def _read_break(
    number: int, entry: object, problems: list[str]
) -> CommercialBreak | None:
    """Read one commercial break from a label file.

    Parameters
    ----------
    number : int
        Its position in the label file, counting from 1.
    entry : object
        Its fields as TOML gave them; anything but a table with a start and an
        end is a problem.
    problems : list[str]
        Receives a message for each time that can't be read, or for an end
        that isn't after the start.

    Returns
    -------
    CommercialBreak | None
        The commercial break, or ``None`` if it has a problem.
    """
    if not isinstance(entry, dict) or set(entry) != {"start", "end"}:
        problems.append(
            f"commercial break {number} must have a start and an end, and nothing else"
        )
        return None
    start, end = entry["start"], entry["end"]
    start_text, end_text = str(start), str(end)
    name = f"commercial break {number} ({start_text} to {end_text})"
    seconds = {}
    for field_name, value in (("start", start), ("end", end)):
        seconds[field_name] = _seconds(value)
        if seconds[field_name] is None:
            problems.append(
                f"{name}: can't read the {field_name} {value}; {_TIME_HINT}"
            )
    if seconds["start"] is None or seconds["end"] is None:
        return None
    if seconds["end"] <= seconds["start"]:
        problems.append(f"{name}: doesn't end after it starts")
        return None
    return CommercialBreak(
        number, start_text, end_text, seconds["start"], seconds["end"]
    )


def _seconds(value: object) -> float | None:
    """Turn a time written ``hh:mm:ss`` or ``hh:mm:ss.d`` into seconds.

    Parameters
    ----------
    value : object
        The time as TOML gave it; only a string can be read.

    Returns
    -------
    float | None
        The time in seconds, or ``None`` if it can't be read.
    """
    match = _TIME.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    hours, minutes, seconds, tenths = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + float(tenths or 0)


def _clock(seconds: float) -> str:
    """Write a length in seconds as ``hh:mm:ss.fff``.

    Parameters
    ----------
    seconds : float
        The length in seconds.

    Returns
    -------
    str
        The length, to the millisecond.
    """
    milliseconds = round(seconds * 1000)
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours:02d}:{minutes:02d}:{rest / 1000:06.3f}"
