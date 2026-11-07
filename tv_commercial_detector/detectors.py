"""Detectors: anything the benchmark scores, in two kinds.

A look-ahead detector analyzes a whole recording at once and reports the
commercial breaks it found, in seconds from the start of the recording. A
candidate runs over a stretch of a recording as if it were live; candidates are
scored in later work.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DetectorKind(StrEnum):
    """The two kinds of detector, as the scorecard names them."""

    LOOK_AHEAD = "look-ahead"
    CANDIDATE = "candidate"


@dataclass(frozen=True)
class Recording:
    """What a detector is told about the recording it analyzes.

    It holds no labels, so a detector can't see what it is scored against.
    """

    path: Path
    fingerprint: str
    length_seconds: float
    channel: str


@dataclass(frozen=True)
class ReportedCommercialBreak:
    """One commercial break a look-ahead detector reports, in seconds."""

    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class LookAheadReport:
    """The commercial breaks a look-ahead detector found in one recording, any order."""

    commercial_breaks: tuple[ReportedCommercialBreak, ...]


class DetectorError(Exception):
    """A detector could not analyze one recording; the message says why."""


class Detector(Protocol):
    """Anything the benchmark scores: it has a name and a kind."""

    @property
    def name(self) -> str:
        """The detector's name in the scorecard, unique within a run."""
        ...

    @property
    def kind(self) -> DetectorKind:
        """Which kind of detector it is."""
        ...


class LookAheadDetector(Detector, Protocol):
    """A detector that analyzes a whole recording at once."""

    def analyze(self, recording: Recording) -> LookAheadReport:
        """Find the commercial breaks in a whole recording.

        Parameters
        ----------
        recording : Recording
            The recording to analyze.

        Returns
        -------
        LookAheadReport
            The commercial breaks found.

        Raises
        ------
        DetectorError
            If the recording can't be analyzed, for example because the tool
            behind the detector is missing or fails.
        """
        ...
