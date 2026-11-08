"""Fake detectors of both kinds, answering with scripted reports."""

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


@dataclass
class FakeCandidate:
    """Candidate answering with scripted state changes per recording.

    Each script is a list of ``(state, reported_at)`` pairs; a script that is a
    string makes the candidate fail on that recording with that message.
    ``runs`` records every stretch the candidate was asked to run over.
    """

    name: str
    scripts: dict[str, list[tuple[State, float]] | str]
    processing_seconds: float = 0.0
    runs: list[tuple[str, float, float]] = field(default_factory=list)
    kind: DetectorKind = DetectorKind.CANDIDATE

    def run(
        self, recording: Recording, start_seconds: float, end_seconds: float
    ) -> CandidateReport:
        """Return the scripted state changes for a recording.

        Parameters
        ----------
        recording : Recording
            The recording; only its file name is used to pick the script.
        start_seconds, end_seconds : float
            The stretch of the recording to run over.

        Returns
        -------
        CandidateReport
            The scripted state changes.

        Raises
        ------
        DetectorError
            If the recording is scripted to fail.
        """
        self.runs.append((recording.path.name, start_seconds, end_seconds))
        script = self.scripts[recording.path.name]
        if isinstance(script, str):
            raise DetectorError(script)
        return CandidateReport(
            changes=tuple(StateChange(state, at) for state, at in script),
            processing_seconds=self.processing_seconds,
        )
