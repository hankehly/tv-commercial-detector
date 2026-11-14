"""The benchmark run: score detectors on the labeled recordings, save a scorecard."""

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from loguru import logger

from tv_commercial_detector.detectors import (
    Candidate,
    CandidateReport,
    DetectorError,
    DetectorKind,
    LookAheadDetector,
    LookAheadReport,
    Recording,
    State,
)
from tv_commercial_detector.media_probe import MediaProbe
from tv_commercial_detector.recording_set import (
    LabeledRecording,
    ValidationReport,
    validate,
)
from tv_commercial_detector.scorecard import (
    DetectorScorecard,
    Scorecard,
    ScoredRecording,
)
from tv_commercial_detector.scorer import (
    TEST_START_MARGIN_SECONDS,
    CandidateTally,
    LookAheadTally,
    Measure,
    TestStart,
    tally_candidate,
    tally_look_ahead,
    tally_startup,
    test_starts,
)

SCORECARD_FILE_NAME = "scorecard.json"

RUN_FOLDER_FORMAT = "%Y-%m-%d_%H-%M-%S"
"""How a run's folder is named after its start, like the recordings' file names."""


@dataclass(frozen=True)
class RunResult:
    """The outcome of a run.

    When validation finds errors, nothing is scored or saved, and
    ``scorecard`` and ``scorecard_path`` are ``None``.
    """

    validation: ValidationReport
    scorecard: Scorecard | None
    scorecard_path: Path | None


def run(
    data_folder: Path,
    recording_list: Path,
    labels_folder: Path,
    probe: MediaProbe,
    detectors: Sequence[LookAheadDetector | Candidate],
    started_at: datetime,
) -> RunResult:
    """Validate the recording set, score each detector on it and save the scorecard.

    Parameters
    ----------
    data_folder : Path
        The data folder. Each run saves its scorecard in a new folder inside
        its ``runs/`` folder, named after the run's start, and never
        overwrites an earlier run's.
    recording_list : Path
        The CSV list of recordings.
    labels_folder : Path
        The folder holding the label files.
    probe : MediaProbe
        Reports each recording's tracks and length.
    detectors : Sequence[LookAheadDetector | Candidate]
        The detectors to score, of either kind.
    started_at : datetime
        When the run started; it names the run's folder.

    Returns
    -------
    RunResult
        The validation report, the scorecard and where it was saved.
    """
    validation = validate(data_folder, recording_list, labels_folder, probe)
    if validation.errors:
        return RunResult(validation, None, None)
    recordings = validation.labeled
    starts = (
        _choose_test_starts(recordings)
        if any(detector.kind == DetectorKind.CANDIDATE for detector in detectors)
        else {}
    )
    scorecard = Scorecard(
        started_at=started_at,
        recordings=[_scored_recording(r) for r in recordings],
        detectors=[_score(detector, recordings, starts) for detector in detectors],
    )
    path = _new_run_folder(data_folder / "runs", started_at) / SCORECARD_FILE_NAME
    path.write_text(json.dumps(scorecard.to_json(), indent=2) + "\n")
    return RunResult(validation, scorecard, path)


def _new_run_folder(runs_folder: Path, started_at: datetime) -> Path:
    """Create a folder for a run that no earlier run has used.

    Parameters
    ----------
    runs_folder : Path
        The folder holding every run's folder; created if missing.
    started_at : datetime
        When the run started.

    Returns
    -------
    Path
        The new folder, named after the start, such as
        ``2026-11-08_14-03-22``, with ``_2``, ``_3`` and so on added when
        another run started in the same second.
    """
    runs_folder.mkdir(parents=True, exist_ok=True)
    name = started_at.strftime(RUN_FOLDER_FORMAT)
    attempt = 1
    while True:
        folder = runs_folder / (name if attempt == 1 else f"{name}_{attempt}")
        try:
            folder.mkdir()
        except FileExistsError:
            attempt += 1
            continue
        return folder


def _choose_test_starts(
    recordings: list[LabeledRecording],
) -> dict[str, tuple[TestStart, ...]]:
    """Choose every recording's test starts, warning about any without room.

    Parameters
    ----------
    recordings : list[LabeledRecording]
        The labeled recordings.

    Returns
    -------
    dict[str, tuple[TestStart, ...]]
        Each recording's test starts, by file name. A recording too short or
        too busy for a test start inside a program is logged as a warning.
    """
    starts = {}
    for recording in recordings:
        name = recording.path.name
        starts[name] = test_starts(recording)
        if all(start.state != State.PROGRAM for start in starts[name]):
            logger.warning(
                f"{name} has no program at least {TEST_START_MARGIN_SECONDS:g} s "
                "from every labeled edge and from its end, so it has no test "
                "start inside a program"
            )
    return starts


def _score(
    detector: LookAheadDetector | Candidate,
    recordings: list[LabeledRecording],
    starts: dict[str, tuple[TestStart, ...]],
) -> DetectorScorecard:
    """Score a detector of either kind on every labeled recording.

    A look-ahead detector analyzes each recording; a candidate gets one full
    run over each, plus a trial run from each of its test starts. A recording
    the detector fails on, or reports nonsense for, is recorded as an error
    and left out of the detector's measures.

    Parameters
    ----------
    detector : LookAheadDetector | Candidate
        The detector.
    recordings : list[LabeledRecording]
        The labeled recordings.
    starts : dict[str, tuple[TestStart, ...]]
        Each recording's test starts, by file name, for a candidate's trial
        runs.

    Returns
    -------
    DetectorScorecard
        The detector's measures, overall and per recording, its errors and,
        for a candidate, its verdicts on the overall figures.
    """
    if detector.kind == DetectorKind.CANDIDATE:
        candidate = cast(Candidate, detector)
        overall, per_recording, errors = _tally_each(
            recordings,
            lambda r: _tally_runs(candidate, r, starts[r.path.name]),
            CandidateTally(),
        )
        verdicts = overall.verdicts()
    else:
        look_ahead = cast(LookAheadDetector, detector)
        overall, per_recording, errors = _tally_each(
            recordings, lambda r: _tally_analysis(look_ahead, r), LookAheadTally()
        )
        verdicts = None
    return DetectorScorecard(
        name=detector.name,
        kind=detector.kind,
        overall=overall.measures(),
        per_recording=per_recording,
        errors=errors,
        verdicts=verdicts,
    )


def _tally_each[T: (CandidateTally, LookAheadTally)](
    recordings: list[LabeledRecording],
    tally_one: Callable[[LabeledRecording], T],
    empty: T,
) -> tuple[T, dict[str, dict[str, Measure]], dict[str, str]]:
    """Tally a detector on every recording, pooling what it could be scored on.

    Parameters
    ----------
    recordings : list[LabeledRecording]
        The labeled recordings.
    tally_one : Callable[[LabeledRecording], T]
        Runs the detector on one recording and tallies its report; raises
        ``DetectorError`` if the detector fails on it or reports nonsense.
    empty : T
        The tally of no recordings, to pool from.

    Returns
    -------
    tuple[T, dict[str, dict[str, Measure]], dict[str, str]]
        The pooled tally, the measures per recording, and the error per
        recording the detector failed on, both by file name.
    """
    overall = empty
    per_recording = {}
    errors = {}
    for recording in recordings:
        try:
            tally = tally_one(recording)
        except DetectorError as e:
            errors[recording.path.name] = str(e)
            continue
        overall += tally
        per_recording[recording.path.name] = tally.measures()
    return overall, per_recording, errors


def _tally_runs(
    candidate: Candidate,
    recording: LabeledRecording,
    starts: tuple[TestStart, ...],
) -> CandidateTally:
    """Give a candidate a full run and its trial runs on a recording, and tally them.

    Parameters
    ----------
    candidate : Candidate
        The candidate.
    recording : LabeledRecording
        The labeled recording.
    starts : tuple[TestStart, ...]
        The recording's test starts.

    Returns
    -------
    CandidateTally
        The counts behind the recording's measures.

    Raises
    ------
    DetectorError
        If the candidate fails on the recording or reports nonsense, in its
        full run or in any trial run.
    """
    described = _for_detector(recording)
    report = candidate.run(described, 0.0, recording.entry.length_seconds)
    _check_candidate_report(report, start_seconds=0.0)
    tally = tally_candidate(recording, report)
    for test_start in starts:
        tally += _tally_trial_run(candidate, described, test_start)
    return tally


def _tally_trial_run(
    candidate: Candidate, recording: Recording, test_start: TestStart
) -> CandidateTally:
    """Give a candidate a trial run from a test start and tally its report.

    Parameters
    ----------
    candidate : Candidate
        The candidate.
    recording : Recording
        The recording, as the candidate is told about it.
    test_start : TestStart
        Where the trial run starts and what is on air there.

    Returns
    -------
    CandidateTally
        The test start and its startup delay.

    Raises
    ------
    DetectorError
        If the candidate fails on the trial run or reports nonsense; the
        message says which trial run.
    """
    try:
        report = candidate.run(recording, test_start.seconds, test_start.end_seconds)
        _check_candidate_report(report, start_seconds=test_start.seconds)
    except DetectorError as e:
        raise DetectorError(f"trial run from {test_start.seconds} s: {e}") from e
    return tally_startup(test_start, report)


def _tally_analysis(
    detector: LookAheadDetector, recording: LabeledRecording
) -> LookAheadTally:
    """Have a look-ahead detector analyze a recording and tally its report.

    Parameters
    ----------
    detector : LookAheadDetector
        The detector.
    recording : LabeledRecording
        The labeled recording.

    Returns
    -------
    LookAheadTally
        The counts behind the recording's measures.

    Raises
    ------
    DetectorError
        If the detector fails on the recording or reports nonsense.
    """
    report = detector.analyze(_for_detector(recording))
    _check_look_ahead_report(report)
    return tally_look_ahead(recording, report)


def _check_candidate_report(report: CandidateReport, start_seconds: float) -> None:
    """Check that a candidate's report can be scored.

    Parameters
    ----------
    report : CandidateReport
        The report.
    start_seconds : float
        Where the run started; no change can be reported before it.

    Raises
    ------
    DetectorError
        If a change has a state that isn't one of the three, or a time that
        isn't a finite number, comes before the run's start or comes before the
        change before it; or if the processing time isn't a finite number of
        seconds, 0 or more.
    """
    previous = start_seconds
    for number, change in enumerate(report.changes, start=1):
        at = change.reported_at_seconds
        described = f"state change {number} ({change.state} at {at} s)"
        if change.state not in list(State):
            raise DetectorError(
                f"{described} has a state that isn't COMMERCIAL_BREAK, PROGRAM "
                "or UNKNOWN"
            )
        if not _is_finite_number(at):
            raise DetectorError(f"{described} has a time that isn't a finite number")
        if at < start_seconds:
            raise DetectorError(
                f"{described} is reported before the run's start at {start_seconds} s"
            )
        if at < previous:
            raise DetectorError(f"{described} is reported before the one before it")
        previous = at
    processing = report.processing_seconds
    if not (_is_finite_number(processing) and processing >= 0):
        raise DetectorError(
            f"processing time {processing} s isn't a finite number of seconds, "
            "0 or more"
        )


def _check_look_ahead_report(report: LookAheadReport) -> None:
    """Check that every commercial break in a report is a stretch of time.

    Parameters
    ----------
    report : LookAheadReport
        The report.

    Raises
    ------
    DetectorError
        If a commercial break has a time that isn't a finite number, such as
        ``None``, text, ``True`` or NaN, or doesn't end after it starts.
    """
    for reported in report.commercial_breaks:
        span = f"{reported.start_seconds} to {reported.end_seconds} s"
        if not (
            _is_finite_number(reported.start_seconds)
            and _is_finite_number(reported.end_seconds)
        ):
            raise DetectorError(
                f"reported commercial break {span} has a time that isn't a "
                "finite number"
            )
        if reported.end_seconds <= reported.start_seconds:
            raise DetectorError(
                f"reported commercial break {span} doesn't end after it starts"
            )


def _is_finite_number(value: object) -> bool:
    """Tell whether a reported time is a finite number of seconds.

    Parameters
    ----------
    value : object
        The time, as the detector gave it; detectors parse tool output, so it
        may not be the number the report's type promises.

    Returns
    -------
    bool
        ``True`` for a finite ``int`` or ``float`` that isn't a ``bool``.
    """
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _for_detector(recording: LabeledRecording) -> Recording:
    """Describe a labeled recording to a detector, without its labels.

    Parameters
    ----------
    recording : LabeledRecording
        The labeled recording.

    Returns
    -------
    Recording
        Its path, fingerprint, length, channel and frame rate.
    """
    return Recording(
        path=recording.path,
        fingerprint=recording.entry.fingerprint,
        length_seconds=recording.entry.length_seconds,
        channel=recording.label_file.channel,
        frame_rate=recording.frame_rate,
    )


def _scored_recording(recording: LabeledRecording) -> ScoredRecording:
    """Summarise a labeled recording for the scorecard.

    Parameters
    ----------
    recording : LabeledRecording
        The labeled recording.

    Returns
    -------
    ScoredRecording
        Its file name, channel, hours and number of labeled commercial breaks.
    """
    return ScoredRecording(
        file_name=recording.path.name,
        channel=recording.label_file.channel,
        hours=recording.hours,
        commercial_break_count=len(recording.label_file.commercial_breaks),
    )
