"""The scorecard: every detector's measures, overall and per recording.

Saved as JSON, one file per run::

    {
      "started_at": "2026-11-08T14:03:22+09:00",
      "recordings": [
        {"file_name": "a.mp4", "channel": "TBS", "hours": 3.0,
         "commercial_breaks": 12}
      ],
      "detectors": [
        {
          "name": "comskip",
          "kind": "look-ahead",
          "overall": {"missed_commercial_breaks":
                        {"value": 1, "based_on": {"commercial_breaks": 12}}, ...},
          "per_recording": {"a.mp4": {...}},
          "errors": {"b.mp4": "comskip not found"}
        },
        {
          "name": "my-candidate",
          "kind": "candidate",
          "overall": {"entry_delay_within_limit":
                        {"value": 0.95, "based_on": {"commercial_breaks": 20}},
                      "startup_delay_within_limit":
                        {"value": 1.0, "based_on": {"test_starts": 24}},
                      ...},
          "per_recording": {"a.mp4": {...}},
          "errors": {},
          "verdicts": {"entry_delay_within_limit": "pass",
                       "exit_delay_within_limit": "pass",
                       "missed_commercial_breaks": "fail",
                       "startup_delay_within_limit": "pass",
                       "false_flips_per_hour": "pass",
                       "processing_speed": "pass"},
          "verdict": "fail"
        }
      ]
    }

A recording a detector failed on appears under ``errors`` instead of
``per_recording``, and is left out of that detector's overall figures. Only
candidates have ``verdicts`` and a ``verdict``: look-ahead detectors are never
judged against the pass bar (ADR 0004).

Printed, each detector gets a table with a row per measure and a column for the
overall figures and for each recording; a candidate's also has a column for its
verdicts, and its heading gives its overall verdict.
"""

from dataclasses import dataclass, field
from datetime import datetime

from tv_commercial_detector.detectors import DetectorKind
from tv_commercial_detector.scorer import (
    DELAY_LIMIT_SECONDS,
    STARTUP_LIMIT_SECONDS,
    Measure,
)


@dataclass(frozen=True)
class ScoredRecording:
    """A labeled recording the run scored detectors on."""

    file_name: str
    channel: str
    hours: float
    commercial_break_count: int


@dataclass
class DetectorScorecard:
    """One detector's measures, overall and per recording, and its errors.

    ``verdicts`` says whether each measure the pass bar covers passes, judged on
    the overall figures. Only candidates are judged; for a look-ahead detector
    it is ``None``.
    """

    name: str
    kind: DetectorKind
    overall: dict[str, Measure]
    per_recording: dict[str, dict[str, Measure]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    verdicts: dict[str, bool] | None = None

    @property
    def passes(self) -> bool | None:
        """Whether the detector passes every measure, or ``None`` if not judged."""
        return None if self.verdicts is None else all(self.verdicts.values())


@dataclass
class Scorecard:
    """The outcome of one run: the recordings scored and each detector's measures."""

    started_at: datetime
    recordings: list[ScoredRecording]
    detectors: list[DetectorScorecard]

    @property
    def hours(self) -> float:
        """The total length of the recordings scored, in hours."""
        return sum(recording.hours for recording in self.recordings)

    @property
    def commercial_break_count(self) -> int:
        """How many labeled commercial breaks the recordings scored have."""
        return sum(recording.commercial_break_count for recording in self.recordings)

    def to_json(self) -> dict:
        """Write the scorecard as plain JSON values.

        Returns
        -------
        dict
            The scorecard, in the shape this module's docstring shows.
        """
        return {
            "started_at": self.started_at.isoformat(),
            "recordings": [
                {
                    "file_name": recording.file_name,
                    "channel": recording.channel,
                    "hours": recording.hours,
                    "commercial_breaks": recording.commercial_break_count,
                }
                for recording in self.recordings
            ],
            "detectors": [_detector_json(detector) for detector in self.detectors],
        }


def _detector_json(detector: DetectorScorecard) -> dict:
    """Write one detector's scores as plain JSON values.

    Parameters
    ----------
    detector : DetectorScorecard
        The detector's scores.

    Returns
    -------
    dict
        Its name, kind, measures and errors, and for a candidate its verdicts
        as ``"pass"`` or ``"fail"``.
    """
    scores = {
        "name": detector.name,
        "kind": str(detector.kind),
        "overall": _measures_json(detector.overall),
        "per_recording": {
            file_name: _measures_json(measures)
            for file_name, measures in detector.per_recording.items()
        },
        "errors": dict(detector.errors),
    }
    if detector.verdicts is not None:
        scores["verdicts"] = {
            name: _verdict(passes) for name, passes in detector.verdicts.items()
        }
        scores["verdict"] = _verdict(bool(detector.passes))
    return scores


def _verdict(passes: bool) -> str:
    """Name a verdict.

    Parameters
    ----------
    passes : bool
        Whether it passes.

    Returns
    -------
    str
        ``"pass"`` or ``"fail"``.
    """
    return "pass" if passes else "fail"


def _measures_json(measures: dict[str, Measure]) -> dict:
    """Write measures as plain JSON values.

    Parameters
    ----------
    measures : dict[str, Measure]
        The measures, by name.

    Returns
    -------
    dict
        Each measure as ``{"value": ..., "based_on": {...}}``.
    """
    return {
        name: {"value": measure.value, "based_on": dict(measure.based_on)}
        for name, measure in measures.items()
    }


LOOK_AHEAD_MEASURE_LABELS = {
    "missed_commercial_breaks": "Missed commercial breaks",
    "false_flips_per_hour": "False flips per hour",
    "start_offset_median_size": "Start offset, median size",
    "start_offset_p95_size": "Start offset, 95th percentile size",
    "start_offset_median": "Start offset, median",
    "end_offset_median_size": "End offset, median size",
    "end_offset_p95_size": "End offset, 95th percentile size",
    "end_offset_median": "End offset, median",
}

CANDIDATE_MEASURE_LABELS = {
    "entry_delay_within_limit": f"Entry delay within {DELAY_LIMIT_SECONDS:g} s",
    "entry_delay_median": "Entry delay, median",
    "exit_delay_within_limit": f"Exit delay within {DELAY_LIMIT_SECONDS:g} s",
    "exit_delay_median": "Exit delay, median",
    "missed_commercial_breaks": "Missed commercial breaks",
    "startup_delay_within_limit": f"Startup delay within {STARTUP_LIMIT_SECONDS:g} s",
    "startup_delay_median": "Startup delay, median",
    "false_flips_per_hour": "False flips per hour",
    "processing_speed": "Processing speed",
}

MEASURE_LABELS = {
    DetectorKind.LOOK_AHEAD: LOOK_AHEAD_MEASURE_LABELS,
    DetectorKind.CANDIDATE: CANDIDATE_MEASURE_LABELS,
}
"""How the printed table names each kind's measures, in the order it shows them."""

_SIGNED = {"start_offset_median", "end_offset_median"}

_SHARES = {
    "entry_delay_within_limit",
    "exit_delay_within_limit",
    "startup_delay_within_limit",
}


def format_tables(scorecard: Scorecard) -> list[str]:
    """Lay out the scorecard as one table per detector, for printing.

    Parameters
    ----------
    scorecard : Scorecard
        The scorecard.

    Returns
    -------
    list[str]
        The lines of the tables. Each table starts with the detector's name and
        kind, followed for a candidate by its overall verdict, and its cells
        are separated by at least two spaces. A candidate's table has a
        ``Verdict`` column after the overall figures, with ``pass`` or ``fail``
        for each measure the bar covers and ``-`` for the others. A recording
        the detector failed on shows ``error`` in every row.
    """
    file_names = [recording.file_name for recording in scorecard.recordings]
    lines: list[str] = []
    for detector in scorecard.detectors:
        verdicts = detector.verdicts
        labels = MEASURE_LABELS[detector.kind]
        verdict_column = [] if verdicts is None else ["Verdict"]
        rows = [["Measure", "Overall", *verdict_column, *file_names]]
        for name, label in labels.items():
            row = [label, _cell(name, detector.overall[name])]
            if verdicts is not None:
                row.append(_verdict(verdicts[name]) if name in verdicts else "-")
            for file_name in file_names:
                measures = detector.per_recording.get(file_name)
                row.append("error" if measures is None else _cell(name, measures[name]))
            rows.append(row)
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        if lines:
            lines.append("")
        heading = f"{detector.name} ({detector.kind})"
        if detector.passes is not None:
            heading += f": {_verdict(detector.passes)}"
        lines.append(heading)
        lines.extend(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
            for row in rows
        )
    return lines


def _cell(name: str, measure: Measure) -> str:
    """Write one measure as a table cell, with the count it is based on.

    Parameters
    ----------
    name : str
        The measure's name, which decides how it is written.
    measure : Measure
        The measure.

    Returns
    -------
    str
        For example ``2 of 12``, ``95.0% of 20``, ``0.50 in 6.0 h``,
        ``0.120 s/s in 6.0 h``, ``1.5 s (10)`` or ``-0.3 s (10)``; ``-``
        stands for a value there is nothing to measure.
    """
    if name == "missed_commercial_breaks":
        return f"{measure.value} of {measure.based_on['commercial_breaks']}"
    if name in _SHARES:
        value = "-" if measure.value is None else f"{measure.value:.1%}"
        return f"{value} of {_count(measure)}"
    if name == "false_flips_per_hour":
        value = "-" if measure.value is None else f"{measure.value:.2f}"
        return f"{value} in {measure.based_on['hours']:.1f} h"
    if name == "processing_speed":
        value = "-" if measure.value is None else f"{measure.value:.3f}"
        return f"{value} s/s in {measure.based_on['hours']:.1f} h"
    count = _count(measure)
    if measure.value is None:
        return f"- ({count})"
    value = f"{measure.value:+.1f}" if name in _SIGNED else f"{measure.value:.1f}"
    return f"{value} s ({count})"


def _count(measure: Measure) -> int:
    """Return the count a delay measure is based on.

    Parameters
    ----------
    measure : Measure
        The measure, based on commercial breaks or on test starts.

    Returns
    -------
    int
        How many it is counted over.
    """
    [count] = measure.based_on.values()
    return int(count)
