"""Fake detectors of both kinds, answering with scripted reports."""

from collections.abc import Callable
from dataclasses import dataclass, field

from tv_commercial_detector.detectors import (
    CandidateReport,
    DetectorError,
    DetectorKind,
    LookAheadReport,
    Recording,
    ReportedCommercialBreak,
    State,
    StateChange,
)


@dataclass
class FakeDetector:
    """Look-ahead detector answering with scripted commercial breaks per recording.

    A recording scripted with a string makes the detector fail on it with that
    message.
    """

    name: str
    reports: dict[str, list[tuple[float, float]] | str]
    seen: list[Recording] = field(default_factory=list)
    kind: DetectorKind = DetectorKind.LOOK_AHEAD

    def analyze(self, recording: Recording) -> LookAheadReport:
        """Return the scripted report for a recording.

        Parameters
        ----------
        recording : Recording
            The recording; only its file name is used to pick the script.

        Returns
        -------
        LookAheadReport
            The scripted commercial breaks.

        Raises
        ------
        DetectorError
            If the recording is scripted to fail.
        """
        self.seen.append(recording)
        script = self.reports[recording.path.name]
        if isinstance(script, str):
            raise DetectorError(script)
        return LookAheadReport(
            tuple(ReportedCommercialBreak(start, end) for start, end in script)
        )


def settles_at_once(file_name: str, start_seconds: float) -> float | None:
    """Settle the moment a trial run starts, whatever the recording and start.

    Parameters
    ----------
    file_name : str
        The recording's file name.
    start_seconds : float
        Where the trial run starts.

    Returns
    -------
    float | None
        0 s.
    """
    return 0.0


@dataclass
class FakeCandidate:
    """Candidate answering with scripted state changes per recording.

    Each script is a list of ``(state, reported_at)`` pairs for a full run over
    the recording; a script that is a string makes the candidate fail on that
    recording with that message.

    On a shorter run, the candidate first works out
    what is on air: ``settle`` says how many seconds after the run's start it
    reports the state its script has at that start, or ``None`` if it never
    does. After that it follows its script until the run's end. ``runs``
    records every stretch the candidate was asked to run over.
    """

    name: str
    scripts: dict[str, list[tuple[State, float]] | str]
    processing_seconds: float = 0.0
    settle: Callable[[str, float], float | None] = settles_at_once
    runs: list[tuple[str, float, float]] = field(default_factory=list)
    kind: DetectorKind = DetectorKind.CANDIDATE

    def run(
        self, recording: Recording, start_seconds: float, end_seconds: float
    ) -> CandidateReport:
        """Return the scripted state changes for a stretch of a recording.

        Parameters
        ----------
        recording : Recording
            The recording; only its file name is used to pick the script.
        start_seconds, end_seconds : float
            The stretch of the recording to run over.

        Returns
        -------
        CandidateReport
            The whole script for a full run; otherwise the state settled
            on and the script's changes after it, up to the run's end.

        Raises
        ------
        DetectorError
            If the recording is scripted to fail.
        """
        name = recording.path.name
        self.runs.append((name, start_seconds, end_seconds))
        script = self.scripts[name]
        if isinstance(script, str):
            raise DetectorError(script)
        if (start_seconds, end_seconds) != (0.0, recording.length_seconds):
            script = self._from(name, script, start_seconds, end_seconds)
        return CandidateReport(
            changes=tuple(StateChange(state, at) for state, at in script),
            processing_seconds=self.processing_seconds,
        )

    def _from(
        self,
        name: str,
        script: list[tuple[State, float]],
        start_seconds: float,
        end_seconds: float,
    ) -> list[tuple[State, float]]:
        """Return what the candidate reports on a run over part of a recording.

        Parameters
        ----------
        name : str
            The recording's file name.
        script : list[tuple[State, float]]
            The script for a full run over the recording.
        start_seconds, end_seconds : float
            The stretch of the recording to run over.

        Returns
        -------
        list[tuple[State, float]]
            The state the script has at the start, reported once the
            candidate settles, then the script's later changes until the end;
            nothing if it never settles.
        """
        settle = self.settle(name, start_seconds)
        if settle is None:
            return []
        settled_at = start_seconds + settle
        state_then = State.UNKNOWN
        for state, at in script:
            if at <= start_seconds:
                state_then = state
        later = [(s, at) for s, at in script if settled_at < at <= end_seconds]
        settled = [(state_then, settled_at)] if settled_at <= end_seconds else []
        return settled + later
