"""The benchmark run: score detectors on the labeled recordings, save a scorecard."""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tv_commercial_detector.detectors import (
    DetectorError,
    LookAheadDetector,
    LookAheadReport,
    Recording,
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
from tv_commercial_detector.scorer import LookAheadTally, tally_look_ahead

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
    detectors: Sequence[LookAheadDetector],
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
    detectors : Sequence[LookAheadDetector]
        The detectors to score.
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
    scorecard = Scorecard(
        started_at=started_at,
        recordings=[_scored_recording(r) for r in validation.labeled],
        detectors=[_score(detector, validation.labeled) for detector in detectors],
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


def _score(
    detector: LookAheadDetector, recordings: list[LabeledRecording]
) -> DetectorScorecard:
    """Run a look-ahead detector on every labeled recording and score it.

    A recording the detector fails on, or reports nonsense for, is recorded as
    an error and left out of the detector's measures.

    Parameters
    ----------
    detector : LookAheadDetector
        The detector.
    recordings : list[LabeledRecording]
        The labeled recordings.

    Returns
    -------
    DetectorScorecard
        The detector's measures, overall and per recording, and its errors.
    """
    overall = LookAheadTally()
    per_recording = {}
    errors = {}
    for recording in recordings:
        try:
            report = detector.analyze(_for_detector(recording))
            _check_report(report)
        except DetectorError as e:
            errors[recording.path.name] = str(e)
            continue
        tally = tally_look_ahead(recording, report)
        overall += tally
        per_recording[recording.path.name] = tally.measures()
    return DetectorScorecard(
        name=detector.name,
        kind=detector.kind,
        overall=overall.measures(),
        per_recording=per_recording,
        errors=errors,
    )


def _check_report(report: LookAheadReport) -> None:
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
        Its path, fingerprint, length and channel.
    """
    return Recording(
        path=recording.path,
        fingerprint=recording.entry.fingerprint,
        length_seconds=recording.entry.length_seconds,
        channel=recording.label_file.channel,
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
