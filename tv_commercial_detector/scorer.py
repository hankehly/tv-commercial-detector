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

How candidates are scored, from one full run over each recording:

=========================  ====================================================
Rule                       How it is counted
=========================  ====================================================
Labeling imprecision       A change up to 0.5 s before a labeled edge counts as
                           on time, with a delay of 0.
Entry delay                From the labeled start until the state is first
                           ``COMMERCIAL_BREAK``; 0 if it already is.
Missed commercial break    The state is never ``COMMERCIAL_BREAK`` from 0.5 s
                           before the labeled start until the labeled end. It
                           counts as an entry delay over 5 s, and so does one
                           whose only ``COMMERCIAL_BREAK`` in that stretch was
                           dropped before the labeled start.
Exit delay                 For each commercial break not missed, from the
                           labeled end until the state is first ``PROGRAM``;
                           over 5 s if the next labeled one starts first.
Under way at the start     A commercial break labeled from 0 s has no entry
                           delay; it still counts for missed and exit delay.
Starting in the last 5 s   Left out of every measure.
Ending in the last 5 s,    No exit delay, unless ``PROGRAM`` is reported before
or still running at the    the recording ends.
end
=========================  ====================================================

The pass bar, judged on the overall figures, with a value exactly on a limit
counting as within it:

==========================  ===================================================
Measure                     Pass if
==========================  ===================================================
Entry delay                 At most 5 s for at least 95% of labeled commercial
                            breaks, missed ones counting as over 5 s.
Exit delay                  At most 5 s for at least 95% of the commercial
                            breaks the candidate entered.
Missed commercial breaks    At most 2% of labeled commercial breaks.
==========================  ===================================================

A measure with nothing to count, for example when the candidate failed on
every recording, fails. A candidate passes overall only if it passes every
measure.

Figures for several recordings pool every commercial break and hour across them;
they aren't averages of per-recording figures.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from tv_commercial_detector.detectors import CandidateReport, LookAheadReport, State
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


LABELING_IMPRECISION_SECONDS = 0.5
"""A change up to this long before a labeled edge counts as on time, delay 0."""

DELAY_LIMIT_SECONDS = 5.0
"""Entry and exit delays pass the bar when they are at most this long."""

DELAY_SHARE_PERCENT = 95
"""The share of commercial breaks whose delay must be within the limit."""

MISSED_PERCENT = 2
"""The largest share of labeled commercial breaks a candidate may miss."""

END_MARGIN_SECONDS = 5.0
"""How close to a recording's end an edge is too late to judge a delay on."""


@dataclass(frozen=True)
class CandidateTally:
    """The raw counts behind a candidate's measures.

    ``entry_counted`` and ``exit_counted`` are how many commercial breaks each
    delay is counted over; ``entry_delays`` and ``exit_delays`` hold the delays
    that could be measured, so a missed commercial break counts towards
    ``entry_counted`` without a delay. Tallies for several recordings add up,
    so overall figures pool them.
    """

    commercial_breaks: int = 0
    missed: int = 0
    entry_counted: int = 0
    entry_delays: tuple[float, ...] = ()
    exit_counted: int = 0
    exit_delays: tuple[float, ...] = ()

    def __add__(self, other: CandidateTally) -> CandidateTally:
        """Pool two tallies.

        Parameters
        ----------
        other : CandidateTally
            The tally to pool with this one.

        Returns
        -------
        CandidateTally
            The pooled tally.
        """
        return CandidateTally(
            commercial_breaks=self.commercial_breaks + other.commercial_breaks,
            missed=self.missed + other.missed,
            entry_counted=self.entry_counted + other.entry_counted,
            entry_delays=self.entry_delays + other.entry_delays,
            exit_counted=self.exit_counted + other.exit_counted,
            exit_delays=self.exit_delays + other.exit_delays,
        )

    @property
    def entry_within_limit(self) -> int:
        """How many commercial breaks were entered within the delay limit."""
        return _within_limit(self.entry_delays)

    @property
    def exit_within_limit(self) -> int:
        """How many commercial breaks were exited within the delay limit."""
        return _within_limit(self.exit_delays)

    def measures(self) -> dict[str, Measure]:
        """Turn the tally into the candidate measures.

        Returns
        -------
        dict[str, Measure]
            For entry and exit delay, the share of commercial breaks within the
            limit and the median of the delays that could be measured, in
            seconds; and the number of missed commercial breaks.
        """
        return {
            "entry_delay_within_limit": Measure(
                _share(self.entry_within_limit, self.entry_counted),
                {"commercial_breaks": self.entry_counted},
            ),
            "entry_delay_median": Measure(
                _median(self.entry_delays),
                {"commercial_breaks": len(self.entry_delays)},
            ),
            "exit_delay_within_limit": Measure(
                _share(self.exit_within_limit, self.exit_counted),
                {"commercial_breaks": self.exit_counted},
            ),
            "exit_delay_median": Measure(
                _median(self.exit_delays),
                {"commercial_breaks": len(self.exit_delays)},
            ),
            "missed_commercial_breaks": Measure(
                self.missed, {"commercial_breaks": self.commercial_breaks}
            ),
        }

    def verdicts(self) -> dict[str, bool]:
        """Judge the tally against the pass bar.

        A value exactly on a limit is within it. A measure with nothing to
        count fails, since nothing shows the candidate is good enough.

        Returns
        -------
        dict[str, bool]
            Whether each measure the bar covers passes, by measure name.
        """
        return {
            "entry_delay_within_limit": self.entry_counted > 0
            and self.entry_within_limit * 100
            >= DELAY_SHARE_PERCENT * self.entry_counted,
            "exit_delay_within_limit": self.exit_counted > 0
            and self.exit_within_limit * 100 >= DELAY_SHARE_PERCENT * self.exit_counted,
            "missed_commercial_breaks": self.commercial_breaks > 0
            and self.missed * 100 <= MISSED_PERCENT * self.commercial_breaks,
        }


def tally_candidate(
    recording: LabeledRecording, report: CandidateReport
) -> CandidateTally:
    """Compare a candidate's full run over one recording with its labels.

    Parameters
    ----------
    recording : LabeledRecording
        The recording and its labels.
    report : CandidateReport
        The candidate's report for a run over the whole recording.

    Returns
    -------
    CandidateTally
        The counts behind the recording's measures.
    """
    timeline = _Timeline.of(report)
    length = recording.entry.length_seconds
    labeled = recording.label_file.commercial_breaks
    counted = missed = entry_counted = exit_counted = 0
    entry_delays: list[float] = []
    exit_delays: list[float] = []
    next_starts = [later.start_seconds for later in labeled[1:]] + [math.inf]
    for labeled_break, next_start in zip(labeled, next_starts):
        start, end = labeled_break.start_seconds, labeled_break.end_seconds
        if _near_end(start, length):
            continue
        counted += 1
        under_way = start <= 0.0
        if not under_way:
            entry_counted += 1
        if not timeline.ever(
            State.COMMERCIAL_BREAK, start - LABELING_IMPRECISION_SECONDS, end
        ):
            missed += 1
            continue
        entered = timeline.reached(State.COMMERCIAL_BREAK, start, end)
        if not under_way and entered is not None:
            entry_delays.append(_milliseconds(max(entered - start, 0.0)))
        exited = timeline.reached(State.PROGRAM, end, next_start)
        if exited is not None and exited > length:
            exited = None
        if exited is None and _near_end(end, length):
            continue
        exit_counted += 1
        if exited is not None:
            exit_delays.append(_milliseconds(max(exited - end, 0.0)))
    return CandidateTally(
        commercial_breaks=counted,
        missed=missed,
        entry_counted=entry_counted,
        entry_delays=tuple(entry_delays),
        exit_counted=exit_counted,
        exit_delays=tuple(exit_delays),
    )


@dataclass(frozen=True)
class _Timeline:
    """A candidate's state over a run, as it changed.

    ``changes`` holds one ``(time, state)`` pair per distinct report time, with
    the last state reported at that time, in order. Before the first, the state
    is ``UNKNOWN``.
    """

    changes: tuple[tuple[float, State], ...]

    @classmethod
    def of(cls, report: CandidateReport) -> _Timeline:
        """Build the timeline of a report whose changes are in order.

        Parameters
        ----------
        report : CandidateReport
            The report.

        Returns
        -------
        _Timeline
            Its timeline.
        """
        latest: dict[float, State] = {}
        for change in report.changes:
            latest[change.reported_at_seconds] = State(change.state)
        return cls(tuple(latest.items()))

    def state_at(self, time: float) -> State:
        """Return the state at a moment.

        Parameters
        ----------
        time : float
            The moment, in seconds from the start of the recording.

        Returns
        -------
        State
            The state last reported at or before it, or ``UNKNOWN``.
        """
        state = State.UNKNOWN
        for at, reported in self.changes:
            if at > time:
                break
            state = reported
        return state

    def ever(self, state: State, start: float, before: float) -> bool:
        """Tell whether the state is a given one at any moment in a stretch.

        Parameters
        ----------
        state : State
            The state looked for.
        start : float
            The stretch's start.
        before : float
            The stretch's end, exclusive.

        Returns
        -------
        bool
            ``True`` if the state is the one looked for at some moment in
            ``[start, before)``.
        """
        return self.state_at(start) == state or any(
            start < at < before and reported == state for at, reported in self.changes
        )

    def reached(self, state: State, edge: float, before: float) -> float | None:
        """Return when the state reaches a given one at or after a labeled edge.

        Parameters
        ----------
        state : State
            The state the labels change to at the edge.
        edge : float
            The labeled edge.
        before : float
            Where to stop looking, exclusive.

        Returns
        -------
        float | None
            ``edge`` itself if the state is already the one looked for there.
            Otherwise the first change to it from ``LABELING_IMPRECISION_SECONDS``
            before the edge until ``before``, so a change that early counts as
            on time; a state reached long before the edge and dropped just
            before it doesn't. ``None`` if there is no such change.
        """
        if self.state_at(edge) == state:
            return edge
        earliest = edge - LABELING_IMPRECISION_SECONDS
        return next(
            (
                at
                for at, reported in self.changes
                if earliest <= at < before and reported == state
            ),
            None,
        )


def _near_end(time: float, length: float) -> bool:
    """Tell whether a moment falls in the last 5 s of a recording.

    Parameters
    ----------
    time : float
        The moment, in seconds from the start of the recording.
    length : float
        The recording's length, in seconds.

    Returns
    -------
    bool
        ``True`` if fewer than ``END_MARGIN_SECONDS`` are left after it.
    """
    return round(length - time, 6) < END_MARGIN_SECONDS


def _within_limit(delays: Sequence[float]) -> int:
    """Count the delays that are within the limit.

    Parameters
    ----------
    delays : Sequence[float]
        The delays, in seconds, rounded to the millisecond.

    Returns
    -------
    int
        How many are at most ``DELAY_LIMIT_SECONDS``.
    """
    return sum(delay <= DELAY_LIMIT_SECONDS for delay in delays)


def _share(count: int, total: int) -> float | None:
    """Return a count as a share of a total.

    Parameters
    ----------
    count : int
        The count.
    total : int
        The total.

    Returns
    -------
    float | None
        ``count / total``, or ``None`` when the total is 0.
    """
    return count / total if total else None
