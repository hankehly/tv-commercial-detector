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
        }
      ]
    }

A recording a detector failed on appears under ``errors`` instead of
``per_recording``, and is left out of that detector's overall figures.

Printed, each detector gets a table with a row per measure and a column for the
overall figures and for each recording.
"""

from dataclasses import dataclass, field
from datetime import datetime

from tv_commercial_detector.detectors import DetectorKind
from tv_commercial_detector.scorer import Measure


@dataclass(frozen=True)
class ScoredRecording:
    """A labeled recording the run scored detectors on."""

    file_name: str
    channel: str
    hours: float
    commercial_break_count: int


@dataclass
class DetectorScorecard:
    """One detector's measures, overall and per recording, and its errors."""

    name: str
    kind: DetectorKind
    overall: dict[str, Measure]
    per_recording: dict[str, dict[str, Measure]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


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
            "detectors": [
                {
                    "name": detector.name,
                    "kind": str(detector.kind),
                    "overall": _measures_json(detector.overall),
                    "per_recording": {
                        file_name: _measures_json(measures)
                        for file_name, measures in detector.per_recording.items()
                    },
                    "errors": dict(detector.errors),
                }
                for detector in self.detectors
            ],
        }


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


MEASURE_LABELS = {
    "missed_commercial_breaks": "Missed commercial breaks",
    "false_flips_per_hour": "False flips per hour",
    "start_offset_median_size": "Start offset, median size",
    "start_offset_p95_size": "Start offset, 95th percentile size",
    "start_offset_median": "Start offset, median",
    "end_offset_median_size": "End offset, median size",
    "end_offset_p95_size": "End offset, 95th percentile size",
    "end_offset_median": "End offset, median",
}
"""How the printed table names each measure, in the order it shows them."""

_SIGNED = {"start_offset_median", "end_offset_median"}


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
        kind, and its cells are separated by at least two spaces. A recording
        the detector failed on shows ``error`` in every row.
    """
    file_names = [recording.file_name for recording in scorecard.recordings]
    lines: list[str] = []
    for detector in scorecard.detectors:
        rows = [["Measure", "Overall", *file_names]]
        for name, label in MEASURE_LABELS.items():
            row = [label, _cell(name, detector.overall[name])]
            for file_name in file_names:
                measures = detector.per_recording.get(file_name)
                row.append("error" if measures is None else _cell(name, measures[name]))
            rows.append(row)
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        if lines:
            lines.append("")
        lines.append(f"{detector.name} ({detector.kind})")
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
        For example ``2 of 12``, ``0.50 in 6.0 h``, ``1.5 s (10)`` or
        ``-0.3 s (10)``; ``-`` stands for a value there is nothing to measure.
    """
    if name == "missed_commercial_breaks":
        return f"{measure.value} of {measure.based_on['commercial_breaks']}"
    if name == "false_flips_per_hour":
        value = "-" if measure.value is None else f"{measure.value:.2f}"
        return f"{value} in {measure.based_on['hours']:.1f} h"
    count = measure.based_on["commercial_breaks"]
    if measure.value is None:
        return f"- ({count})"
    value = f"{measure.value:+.1f}" if name in _SIGNED else f"{measure.value:.1f}"
    return f"{value} s ({count})"
