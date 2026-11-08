"""The scorer: measures how far a detector's reports are from the labels.

How look-ahead detectors are scored:

=========================  ====================================================
Rule                       How it is counted
=========================  ====================================================
Match                      A reported and a labeled commercial break overlap by
                           more than 0.5 s. One reported commercial break may
                           match several labeled ones.
Missed commercial break    A labeled one that no reported one matches.
False flip                 A reported one that matches no labeled one, plus each
                           extra piece when several reported ones match one
                           labeled one.
Start offset               Earliest matching reported start minus the labeled
                           start, for each matched labeled one. Negative is
                           early.
End offset                 Latest matching reported end minus the labeled end.
                           Negative is early.
=========================  ====================================================

Figures for several recordings pool every commercial break and hour across them;
they aren't averages of per-recording figures.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from tv_commercial_detector.detectors import LookAheadReport
from tv_commercial_detector.recording_set import LabeledRecording

MATCH_OVERLAP_SECONDS = 0.5
"""Reported and labeled commercial breaks match if they overlap by more than this."""


@dataclass(frozen=True)
class Measure:
    """One measure's value and what it is based on.

    ``value`` is ``None`` when there is nothing to measure, for example an edge
    offset when no commercial break was matched. ``based_on`` says what the value
    is counted over, such as ``{"commercial_breaks": 12}`` or ``{"hours": 3.0}``.
    """

    value: float | None
    based_on: dict[str, float]


@dataclass(frozen=True)
class LookAheadTally:
    """The raw counts behind a look-ahead detector's measures.

    Tallies for several recordings add up, so overall figures pool them.
    """

    commercial_breaks: int = 0
    missed: int = 0
    false_flips: int = 0
    hours: float = 0.0
    start_offsets: tuple[float, ...] = ()
    end_offsets: tuple[float, ...] = ()

    def __add__(self, other: LookAheadTally) -> LookAheadTally:
        """Pool two tallies.

        Parameters
        ----------
        other : LookAheadTally
            The tally to pool with this one.

        Returns
        -------
        LookAheadTally
            The pooled tally.
        """
        return LookAheadTally(
            commercial_breaks=self.commercial_breaks + other.commercial_breaks,
            missed=self.missed + other.missed,
            false_flips=self.false_flips + other.false_flips,
            hours=self.hours + other.hours,
            start_offsets=self.start_offsets + other.start_offsets,
            end_offsets=self.end_offsets + other.end_offsets,
        )

    def measures(self) -> dict[str, Measure]:
        """Turn the tally into the look-ahead measures.

        Returns
        -------
        dict[str, Measure]
            Missed commercial breaks, false flips per hour, and the median and
            95th-percentile size and the median signed value of start and end
            offsets, in seconds.
        """
        labeled = {"commercial_breaks": self.commercial_breaks}
        matched = {"commercial_breaks": len(self.start_offsets)}
        start_sizes = [abs(offset) for offset in self.start_offsets]
        end_sizes = [abs(offset) for offset in self.end_offsets]
        return {
            "missed_commercial_breaks": Measure(self.missed, labeled),
            "false_flips_per_hour": Measure(
                self.false_flips / self.hours if self.hours else None,
                {"hours": self.hours},
            ),
            "start_offset_median_size": Measure(_median(start_sizes), matched),
            "start_offset_p95_size": Measure(_percentile(start_sizes, 95), matched),
            "start_offset_median": Measure(_median(self.start_offsets), matched),
            "end_offset_median_size": Measure(_median(end_sizes), matched),
            "end_offset_p95_size": Measure(_percentile(end_sizes, 95), matched),
            "end_offset_median": Measure(_median(self.end_offsets), matched),
        }


def tally_look_ahead(
    recording: LabeledRecording, report: LookAheadReport
) -> LookAheadTally:
    """Compare a look-ahead detector's report on one recording with its labels.

    Parameters
    ----------
    recording : LabeledRecording
        The recording and its labels.
    report : LookAheadReport
        The commercial breaks the detector reported.

    Returns
    -------
    LookAheadTally
        The counts behind the recording's measures.
    """
    reported = report.commercial_breaks
    matched_reported: set[int] = set()
    missed = extra_pieces = 0
    start_offsets: list[float] = []
    end_offsets: list[float] = []
    for labeled in recording.label_file.commercial_breaks:
        matches = [
            index
            for index, reported_break in enumerate(reported)
            if _overlap(
                labeled.start_seconds,
                labeled.end_seconds,
                reported_break.start_seconds,
                reported_break.end_seconds,
            )
            > MATCH_OVERLAP_SECONDS
        ]
        if not matches:
            missed += 1
            continue
        matched_reported.update(matches)
        extra_pieces += len(matches) - 1
        earliest = min(reported[index].start_seconds for index in matches)
        latest = max(reported[index].end_seconds for index in matches)
        start_offsets.append(_milliseconds(earliest - labeled.start_seconds))
        end_offsets.append(_milliseconds(latest - labeled.end_seconds))
    return LookAheadTally(
        commercial_breaks=len(recording.label_file.commercial_breaks),
        missed=missed,
        false_flips=len(reported) - len(matched_reported) + extra_pieces,
        hours=recording.hours,
        start_offsets=tuple(start_offsets),
        end_offsets=tuple(end_offsets),
    )


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    """Return how long two stretches of a recording overlap, in seconds.

    Parameters
    ----------
    start_a, end_a : float
        The first stretch.
    start_b, end_b : float
        The second stretch.

    Returns
    -------
    float
        The overlap, to the microsecond so float noise can't tip a boundary;
        negative if they don't overlap.
    """
    return round(min(end_a, end_b) - max(start_a, start_b), 6)


def _milliseconds(seconds: float) -> float:
    """Round a time to the millisecond, below which offsets mean nothing.

    Parameters
    ----------
    seconds : float
        The time, in seconds.

    Returns
    -------
    float
        The time, rounded to three decimal places.
    """
    return round(seconds, 3) + 0.0


def _median(values: Sequence[float]) -> float | None:
    """Return the median of some values.

    Parameters
    ----------
    values : Sequence[float]
        The values.

    Returns
    -------
    float | None
        The median, or ``None`` if there are no values.
    """
    return statistics.median(values) if values else None


def _percentile(values: Sequence[float], percent: float) -> float | None:
    """Return a percentile, interpolating linearly between the closest values.

    This is the usual definition (NumPy's default): with ``n`` sorted values,
    the percentile sits at position ``percent / 100 * (n - 1)``, counting from 0.

    Parameters
    ----------
    values : Sequence[float]
        The values.
    percent : float
        The percentile, from 0 to 100.

    Returns
    -------
    float | None
        The percentile, or ``None`` if there are no values.
    """
    if not values:
        return None
    ordered = sorted(values)
    position = percent / 100 * (len(ordered) - 1)
    below = math.floor(position)
    above = min(below + 1, len(ordered) - 1)
    return ordered[below] + (ordered[above] - ordered[below]) * (position - below)
