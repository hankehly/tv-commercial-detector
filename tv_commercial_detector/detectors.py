"""Detectors: anything the benchmark scores, in two kinds.

A look-ahead detector analyzes a whole recording at once and reports the
commercial breaks it found, in seconds from the start of the recording. A
candidate runs over a stretch of a recording as if it were live and reports
each change of state with the moment it would have reached a viewer.
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
    ``frame_rate`` is its video's frames per second as the media probe reported
    it, or ``None`` when the probe couldn't tell.
    """

    path: Path
    fingerprint: str
    length_seconds: float
    channel: str
    frame_rate: float | None = None


@dataclass(frozen=True)
class ReportedCommercialBreak:
    """One commercial break a look-ahead detector reports, in seconds."""

    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class LookAheadReport:
    """The commercial breaks a look-ahead detector found in one recording, any order."""

    commercial_breaks: tuple[ReportedCommercialBreak, ...]


class State(StrEnum):
    """What a candidate says is on air."""

    COMMERCIAL_BREAK = "COMMERCIAL_BREAK"
    PROGRAM = "PROGRAM"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class StateChange:
    """One change of a candidate's state.

    ``reported_at_seconds`` is the broadcast position, in seconds from the start
    of the recording, at which the change would have reached a viewer live: the
    position of the newest broadcast the candidate had used, plus the
    processing time it took to decide.
    """

    state: State
    reported_at_seconds: float


@dataclass(frozen=True)
class CandidateReport:
    """What a candidate reports for one run over a stretch of a recording.

    ``changes`` are in the order they were reported; before the first one the
    candidate's state is ``UNKNOWN``. ``processing_seconds`` is the run's total
    processing time, in seconds of wall-clock time.
    """

    changes: tuple[StateChange, ...]
    processing_seconds: float


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
            behind the detector is missing or fails. The benchmark records it
            as an error for that recording and carries on; any other
            exception is a bug and stops the run.
        """
        ...


class Candidate(Detector, Protocol):
    """A detector that runs over a stretch of a recording as if it were live.

    It never looks ahead (ADR 0004): each change uses only the broadcast up to
    the moment it reports. How it is fed the recording as if live is its own
    concern.
    """

    def run(
        self, recording: Recording, start_seconds: float, end_seconds: float
    ) -> CandidateReport:
        """Run over a stretch of a recording and report each change of state.

        Parameters
        ----------
        recording : Recording
            The recording.
        start_seconds : float
            Where the run starts, in seconds from the start of the recording.
        end_seconds : float
            Where the run ends, in seconds from the start of the recording.

        Returns
        -------
        CandidateReport
            The changes of state, in order, and the run's processing time.

        Raises
        ------
        DetectorError
            If the candidate can't run over the recording. The benchmark
            records it as an error for that recording and carries on; any
            other exception is a bug and stops the run.
        """
        ...
