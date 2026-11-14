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
Settling                   From the start of the run until the state first
                           matches the labels, and from 0.5 s before each
                           labeled edge until the state is first the new
                           labeled one. Every labeled edge counts, even in the
                           last 5 s.
False flip                 While settled, a change to any state other than the
                           labeled one, ``UNKNOWN`` included; the labeled one
                           changes 0.5 s before each edge. A return to it isn't
                           counted, nor is a change reported at or after the
                           recording's end. Counted per hour of recording
                           scored.
Processing speed           The full run's processing time divided by the
                           recording's length.
=========================  ====================================================

Startup delay comes from a trial run of 15 s of broadcast from each test start:

=========================  ====================================================
Rule                       How it is chosen or counted
=========================  ====================================================
In commercial breaks       One test start at the midpoint of each labeled
                           commercial break at least 30 s long, unless its
                           trial run would end past the recording's end.
In programs                As many again, at least one per recording, at random
                           positions at least 15 s from every labeled edge and
                           from the recording's end, seeded so every run picks
                           the same ones. A position drawn twice is tested
                           once; a recording with no such position gets none.
Startup delay              From the test start until the candidate first
                           reports what the labels say is on air, before the
                           trial run ends. If it never does, it counts as over
                           10 s.
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
Startup delay               At most 10 s for at least 95% of test starts.
False flips                 At most 1 per hour of recording scored.
Processing speed            At most 0.5 s to process each second of broadcast.
==========================  ===================================================

A measure with nothing to count, for example when the candidate failed on
every recording, fails. A candidate passes overall only if it passes every
measure.

Figures for several recordings pool every commercial break, test start and hour
across them; they aren't averages of per-recording figures.
"""

import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from tv_commercial_detector.detectors import CandidateReport, LookAheadReport, State
from tv_commercial_detector.labels import CommercialBreak
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
                _per_hour(self.false_flips, self.hours), {"hours": self.hours}
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

FALSE_FLIPS_PER_HOUR_LIMIT = 1.0
"""The most false flips per hour of recording scored that pass the bar."""

PROCESSING_SPEED_LIMIT = 0.5
"""The most seconds a candidate may take to process each second of broadcast."""

END_MARGIN_SECONDS = 5.0
"""How close to a recording's end an edge is too late to judge a delay on."""

STARTUP_LIMIT_SECONDS = 10.0
"""Startup delays pass the bar when they are at most this long."""

TRIAL_SECONDS = 15.0
"""How much broadcast each trial run gets, from its test start."""

TEST_START_BREAK_SECONDS = 30.0
"""How long a labeled commercial break must be to get a test start."""

TEST_START_MARGIN_SECONDS = 15.0
"""How far a test start inside a program stays from labeled edges and the end."""

TEST_START_SEED = "startup"
"""With a recording's fingerprint, seeds where its program test starts go."""


@dataclass(frozen=True)
class CandidateTally:
    """The raw counts behind a candidate's measures.

    ``entry_counted`` and ``exit_counted`` are how many commercial breaks each
    delay is counted over; ``entry_delays`` and ``exit_delays`` hold the delays
    that could be measured, so a missed commercial break counts towards
    ``entry_counted`` without a delay. ``hours`` is the length of the
    recordings scored and ``processing_seconds`` the time their full runs
    took. Tallies for several recordings add up, so overall figures pool
    them.
    """

    commercial_breaks: int = 0
    missed: int = 0
    entry_counted: int = 0
    entry_delays: tuple[float, ...] = ()
    exit_counted: int = 0
    exit_delays: tuple[float, ...] = ()
    test_starts: int = 0
    startup_delays: tuple[float, ...] = ()
    false_flips: int = 0
    hours: float = 0.0
    processing_seconds: float = 0.0

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
            test_starts=self.test_starts + other.test_starts,
            startup_delays=self.startup_delays + other.startup_delays,
            false_flips=self.false_flips + other.false_flips,
            hours=self.hours + other.hours,
            processing_seconds=self.processing_seconds + other.processing_seconds,
        )

    @property
    def false_flips_per_hour(self) -> float | None:
        """False flips per hour of recording scored, or ``None`` for no hours."""
        return _per_hour(self.false_flips, self.hours)

    @property
    def processing_speed(self) -> float | None:
        """Seconds of processing per second of broadcast, or ``None`` for none."""
        return self.processing_seconds / (self.hours * 3600) if self.hours else None

    @property
    def entry_within_limit(self) -> int:
        """How many commercial breaks were entered within the delay limit."""
        return _within_limit(self.entry_delays)

    @property
    def exit_within_limit(self) -> int:
        """How many commercial breaks were exited within the delay limit."""
        return _within_limit(self.exit_delays)

    @property
    def startup_within_limit(self) -> int:
        """How many test starts had the labeled state reported within the limit."""
        return _within_limit(self.startup_delays, STARTUP_LIMIT_SECONDS)

    def measures(self) -> dict[str, Measure]:
        """Turn the tally into the candidate measures.

        Returns
        -------
        dict[str, Measure]
            For entry and exit delay, the share of commercial breaks within the
            limit and the median of the delays that could be measured, in
            seconds; the number of missed commercial breaks; for startup
            delay, the share of test starts within the limit and the median
            of the delays that could be measured, in seconds; false flips per
            hour of recording scored; and processing speed, in seconds of
            processing per second of broadcast.
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
            "startup_delay_within_limit": Measure(
                _share(self.startup_within_limit, self.test_starts),
                {"test_starts": self.test_starts},
            ),
            "startup_delay_median": Measure(
                _median(self.startup_delays),
                {"test_starts": len(self.startup_delays)},
            ),
            "false_flips_per_hour": Measure(
                self.false_flips_per_hour, {"hours": self.hours}
            ),
            "processing_speed": Measure(self.processing_speed, {"hours": self.hours}),
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
            "startup_delay_within_limit": self.test_starts > 0
            and self.startup_within_limit * 100
            >= DELAY_SHARE_PERCENT * self.test_starts,
            "false_flips_per_hour": _at_most(
                self.false_flips_per_hour, FALSE_FLIPS_PER_HOUR_LIMIT
            ),
            "processing_speed": _at_most(self.processing_speed, PROCESSING_SPEED_LIMIT),
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
        if not timeline.ever(State.COMMERCIAL_BREAK, start, end):
            missed += 1
            continue
        entered = timeline.reached(State.COMMERCIAL_BREAK, start, end)
        if not under_way and entered is not None:
            entry_delays.append(_delay(entered, start))
        near_end = _near_end(end, length)
        exits = timeline.before(length) if near_end else timeline
        exited = exits.reached(State.PROGRAM, end, next_start)
        if exited is None and near_end:
            continue
        exit_counted += 1
        if exited is not None:
            exit_delays.append(_delay(exited, end))
    return CandidateTally(
        commercial_breaks=counted,
        missed=missed,
        entry_counted=entry_counted,
        entry_delays=tuple(entry_delays),
        exit_counted=exit_counted,
        exit_delays=tuple(exit_delays),
        false_flips=_false_flips(timeline, labeled, length),
        hours=recording.hours,
        processing_seconds=report.processing_seconds,
    )


def _false_flips(
    timeline: _Timeline, labeled: Sequence[CommercialBreak], length: float
) -> int:
    """Count a full run's false flips.

    The labels split the recording into stretches, each with one labeled
    state: from the start, and from ``LABELING_IMPRECISION_SECONDS`` before
    each labeled edge, until the next stretch or the recording's end. In each,
    the candidate settles at the first moment its state is the labeled one.
    Once settled, every change to another state is a false flip; a return to
    the labeled state isn't.

    Parameters
    ----------
    timeline : _Timeline
        The candidate's state over the run.
    labeled : Sequence[CommercialBreak]
        The labeled commercial breaks, sorted, not touching. Every one counts,
        even one starting in the last 5 s, since its edges still explain a
        change.
    length : float
        The recording's length, in seconds; changes reported at or after it
        fall outside the recording scored.

    Returns
    -------
    int
        How many false flips the run has.
    """
    under_way = bool(labeled) and labeled[0].start_seconds <= 0.0
    stretches = [(0.0, State.COMMERCIAL_BREAK if under_way else State.PROGRAM)]
    for labeled_break in labeled:
        edges = [(labeled_break.end_seconds, State.PROGRAM)]
        if labeled_break.start_seconds > 0.0:
            edges.insert(0, (labeled_break.start_seconds, State.COMMERCIAL_BREAK))
        stretches += [
            (_offset(edge, LABELING_IMPRECISION_SECONDS), state)
            for edge, state in edges
        ]
    ends = [start for start, _ in stretches[1:]] + [length]
    false_flips = 0
    for (start, state), end in zip(stretches, ends):
        settled = timeline.settles(state, start, end)
        if settled is not None:
            false_flips += timeline.changes_away(state, settled, end)
    return false_flips


@dataclass(frozen=True)
class TestStart:
    """Where a trial run starts, and what the labels say is on air there.

    Nothing labeled changes during the trial run, so ``state`` holds
    throughout it.
    """

    seconds: float
    state: State

    @property
    def end_seconds(self) -> float:
        """Where the trial run ends."""
        return self.seconds + TRIAL_SECONDS


def test_starts(recording: LabeledRecording) -> tuple[TestStart, ...]:
    """Choose a recording's test starts, the same ones on every run.

    Parameters
    ----------
    recording : LabeledRecording
        The recording and its labels.

    Returns
    -------
    tuple[TestStart, ...]
        One at the midpoint of each labeled commercial break at least
        ``TEST_START_BREAK_SECONDS`` long, in order, unless its trial run
        would end past the recording's end, which a label ending at the
        length rounded up to the next tenth allows; then as many again inside
        programs, at least one, at random positions at least
        ``TEST_START_MARGIN_SECONDS`` from every labeled edge and from the
        recording's end, in order. Positions drawn twice, which happens when
        the only room is a single moment, are tested once. The positions are
        drawn with a seed made from ``TEST_START_SEED`` and the recording's
        fingerprint, so they don't move when other recordings change. A
        recording with no such position gets no test start inside a program.
    """
    length = recording.entry.length_seconds
    midpoints = [
        (labeled.start_seconds + labeled.end_seconds) / 2
        for labeled in recording.label_file.commercial_breaks
        if _offset(labeled.end_seconds, labeled.start_seconds)
        >= TEST_START_BREAK_SECONDS
    ]
    in_breaks = [
        TestStart(midpoint, State.COMMERCIAL_BREAK)
        for midpoint in midpoints
        if _offset(length, midpoint) >= TRIAL_SECONDS
    ]
    room = _program_room(recording)
    if not room:
        return tuple(in_breaks)
    rng = random.Random(f"{TEST_START_SEED}:{recording.entry.fingerprint}")
    count = max(len(in_breaks), 1)
    in_programs = sorted({_draw(rng, room) for _ in range(count)})
    return (*in_breaks, *(TestStart(at, State.PROGRAM) for at in in_programs))


def _program_room(recording: LabeledRecording) -> list[tuple[float, float]]:
    """Return the stretches of program where a test start may go.

    Parameters
    ----------
    recording : LabeledRecording
        The recording and its labels.

    Returns
    -------
    list[tuple[float, float]]
        Each ``(earliest, latest)`` stretch, in order, at least
        ``TEST_START_MARGIN_SECONDS`` from every labeled edge and from the
        recording's end. A stretch may be a single moment.
    """
    margin = TEST_START_MARGIN_SECONDS
    length = recording.entry.length_seconds
    room = []
    program_from = 0.0
    edges = [
        (labeled.start_seconds, labeled.end_seconds)
        for labeled in recording.label_file.commercial_breaks
    ]
    for start, end in [*edges, (length, length)]:
        earliest = program_from + margin if program_from > 0.0 else 0.0
        latest = start - margin
        if _offset(latest, earliest) >= 0.0:
            room.append((earliest, latest))
        program_from = end
    return room


def _draw(rng: random.Random, room: list[tuple[float, float]]) -> float:
    """Draw a position evenly from some stretches of a recording.

    Parameters
    ----------
    rng : random.Random
        The seeded random numbers.
    room : list[tuple[float, float]]
        The ``(earliest, latest)`` stretches, at least one.

    Returns
    -------
    float
        A position in one of the stretches, to the millisecond. Longer
        stretches are likelier; if every stretch is a single moment, one of
        them is picked.
    """
    total = sum(latest - earliest for earliest, latest in room)
    if total <= 0.0:
        return rng.choice(room)[0]
    left = rng.uniform(0.0, total)
    for earliest, latest in room:
        if left <= latest - earliest:
            return min(max(round(earliest + left, 3), earliest), latest)
        left -= latest - earliest
    return room[-1][1]


def tally_startup(test_start: TestStart, report: CandidateReport) -> CandidateTally:
    """Compare a candidate's trial run from one test start with the labels.

    Parameters
    ----------
    test_start : TestStart
        Where the trial run started and what the labels say is on air.
    report : CandidateReport
        The candidate's report for the trial run.

    Returns
    -------
    CandidateTally
        One test start, with its startup delay: from the start until the
        candidate first reports the labeled state before the trial run ends.
        If it never does, there is no delay to measure and it counts as over
        the limit.
    """
    settled = next(
        (
            at
            for at, state in _Timeline.of(report).changes
            if state == test_start.state and at < test_start.end_seconds
        ),
        None,
    )
    delays = () if settled is None else (_delay(settled, test_start.seconds),)
    return CandidateTally(test_starts=1, startup_delays=delays)


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

    def before(self, time: float) -> _Timeline:
        """Return the timeline as it stood just before a moment.

        Parameters
        ----------
        time : float
            The moment, in seconds from the start of the recording.

        Returns
        -------
        _Timeline
            The timeline without the changes reported at or after it.
        """
        return _Timeline(tuple((at, s) for at, s in self.changes if at < time))

    def state_at(self, time: float) -> State:
        """Return the state at a moment.

        Parameters
        ----------
        time : float
            The moment, in seconds from the start of the recording.

        Returns
        -------
        State
            The state last reported at or before it, to the microsecond, or
            ``UNKNOWN``.
        """
        state = State.UNKNOWN
        for at, reported in self.changes:
            if _offset(at, time) > 0:
                break
            state = reported
        return state

    def ever(self, state: State, edge: float, before: float) -> bool:
        """Tell whether the state is a given one at any moment after a labeled edge.

        Parameters
        ----------
        state : State
            The state looked for.
        edge : float
            The labeled edge; looking starts ``LABELING_IMPRECISION_SECONDS``
            before it.
        before : float
            Where to stop looking, exclusive.

        Returns
        -------
        bool
            ``True`` if the state is the one looked for at some moment from
            ``LABELING_IMPRECISION_SECONDS`` before the edge until ``before``.
        """
        state_then = State.UNKNOWN
        for at, reported in self.changes:
            if at >= before:
                break
            if _offset(at, edge) <= -LABELING_IMPRECISION_SECONDS:
                state_then = reported
            elif reported == state:
                return True
        return state_then == state

    def settles(self, state: State, start: float, before: float) -> float | None:
        """Return the first moment in a stretch at which the state is a given one.

        Parameters
        ----------
        state : State
            The state looked for.
        start : float
            Where the stretch starts.
        before : float
            Where the stretch ends, exclusive.

        Returns
        -------
        float | None
            ``start`` itself if the state is already the one looked for there,
            otherwise the first change to it in the stretch; ``None`` if there
            is no such moment. Times are compared to the microsecond, so float
            noise can't move a change across either end.
        """
        if _offset(start, before) >= 0:
            return None
        if self.state_at(start) == state:
            return start
        return next(
            (
                at
                for at, reported in self.changes
                if _offset(at, start) > 0
                and _offset(at, before) < 0
                and reported == state
            ),
            None,
        )

    def changes_away(self, state: State, after: float, before: float) -> int:
        """Count the changes to any other state than a given one in a stretch.

        Parameters
        ----------
        state : State
            The state changes away from are counted.
        after : float
            Where the stretch starts, exclusive.
        before : float
            Where the stretch ends, exclusive.

        Returns
        -------
        int
            How many changes reported after ``after`` and before ``before``,
            to the microsecond, are to another state. Reporting the state the
            candidate is already in again isn't a change.
        """
        count = 0
        previous = State.UNKNOWN
        for at, reported in self.changes:
            if _offset(at, before) >= 0:
                break
            if _offset(at, after) > 0 and reported not in (state, previous):
                count += 1
            previous = reported
        return count

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
        return next(
            (
                at
                for at, reported in self.changes
                if _offset(at, edge) >= -LABELING_IMPRECISION_SECONDS
                and at < before
                and reported == state
            ),
            None,
        )


def _offset(time: float, edge: float) -> float:
    """Return how far a moment is from a labeled edge, without float noise.

    Parameters
    ----------
    time : float
        The moment, in seconds from the start of the recording.
    edge : float
        The labeled edge, in seconds from the start of the recording.

    Returns
    -------
    float
        ``time - edge``, to the microsecond, so float noise can't tip a
        boundary: 64.4 s - 0.5 s is 63.9 s, not 63.900000000000006 s.
        Negative is early.
    """
    return round(time - edge, 6)


def _delay(time: float, edge: float) -> float:
    """Return the delay from a labeled edge until a moment.

    Parameters
    ----------
    time : float
        The moment the state reached the labeled one.
    edge : float
        The labeled edge.

    Returns
    -------
    float
        The delay in seconds, to the microsecond, so 5.0004 s stays over a
        5 s limit; 0 for a moment before the edge.
    """
    return max(_offset(time, edge), 0.0) + 0.0


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


def _within_limit(delays: Sequence[float], limit: float = DELAY_LIMIT_SECONDS) -> int:
    """Count the delays that are within a limit.

    Parameters
    ----------
    delays : Sequence[float]
        The delays, in seconds, rounded to the microsecond.
    limit : float
        The limit, in seconds; entry and exit delays' by default.

    Returns
    -------
    int
        How many are at most ``limit``.
    """
    return sum(delay <= limit for delay in delays)


def _at_most(value: float | None, limit: float) -> bool:
    """Tell whether a measured value is within a limit.

    Parameters
    ----------
    value : float | None
        The value, or ``None`` when there was nothing to measure.
    limit : float
        The limit; a value exactly on it is within it.

    Returns
    -------
    bool
        ``True`` if the value is at most the limit, or differs from it only by
        float noise (a relative error of one in a billion); ``False`` when
        there is no value. A real excess, however small, is over the limit.
    """
    return value is not None and (
        value <= limit or math.isclose(value, limit, rel_tol=1e-9)
    )


def _per_hour(count: int, hours: float) -> float | None:
    """Return a count per hour.

    Parameters
    ----------
    count : int
        The count.
    hours : float
        The hours it was counted over.

    Returns
    -------
    float | None
        ``count / hours``, or ``None`` when there are no hours.
    """
    return count / hours if hours else None


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
