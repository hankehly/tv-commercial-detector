"""Tests for candidate startup delay, driven through the benchmark as a whole.

Each candidate gets a short trial run from every test start: one at the
midpoint of each labeled commercial break at least 30 s long, and as many
again inside programs, chosen with a fixed seed. Each test builds a small
recording set in a temporary folder, plugs in fake candidates and reads the
scorecard the run saves.
"""

import pytest
from fake_detectors import FakeCandidate
from recording_sets import RecordingSet, clock

from tv_commercial_detector.detectors import State

CB = State.COMMERCIAL_BREAK
PROGRAM = State.PROGRAM
UNKNOWN = State.UNKNOWN


def trial_runs(candidate: FakeCandidate) -> list[tuple[str, float, float]]:
    """Return the stretches of the candidate's 15 s trial runs, in order."""
    return [run for run in candidate.runs if run[2] - run[1] == 15.0]


def test_test_starts_sit_mid_commercial_break_and_as_many_again_in_programs(
    recording_set: RecordingSet,
) -> None:
    # Labels 60 to 180 s and 1000 to 1020 s. Only the first is at least 30 s
    # long, so it gets a test start at its midpoint, 120 s, and one more goes
    # inside a program. The candidate settles at once on its script's state.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:16:40", "00:17:00")]
    )
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [
                (PROGRAM, 0.0),
                (CB, 60.0),
                (PROGRAM, 180.0),
                (CB, 1000.0),
                (PROGRAM, 1020.0),
            ]
        },
    )

    scorecard = recording_set.run(candidate)

    in_break, in_program = trial_runs(candidate)
    assert in_break == ("a.mp4", 120.0, 135.0)
    name, start, end = in_program
    assert name == "a.mp4"
    assert end == start + 15.0
    assert (
        0.0 <= start <= 45.0 or 195.0 <= start <= 985.0 or (1035.0 <= start <= 3585.0)
    )
    [scored] = scorecard["detectors"]
    two = {"test_starts": 2}
    assert scored["overall"]["startup_delay_within_limit"] == {
        "value": 1.0,
        "based_on": two,
    }
    assert scored["overall"]["startup_delay_median"] == {
        "value": 0.0,
        "based_on": two,
    }
    assert scored["per_recording"]["a.mp4"]["startup_delay_within_limit"] == {
        "value": 1.0,
        "based_on": two,
    }
    assert scored["verdicts"]["startup_delay_within_limit"] == "pass"


def in_room(start: float, room: list[tuple[float, float]]) -> bool:
    """Tell whether a test start lies in one of the allowed stretches."""
    return any(earliest <= start <= latest for earliest, latest in room)


def test_as_many_program_test_starts_as_commercial_break_ones_all_in_program(
    recording_set: RecordingSet,
) -> None:
    # Labels 300 to 400 s, 1000 to 1100 s and 2000 to 2020 s in a 3600 s
    # recording. Two are at least 30 s long, so two test starts go inside
    # programs, at least 15 s from every labeled edge and from the end.
    recording_set.add(
        "a.mp4",
        3600.0,
        [("00:05:00", "00:06:40"), ("00:16:40", "00:18:20"), ("00:33:20", "00:33:40")],
    )
    candidate = FakeCandidate("fake", {"a.mp4": [(PROGRAM, 0.0)]})

    recording_set.run(candidate)

    runs = trial_runs(candidate)
    assert [start for _, start, _ in runs[:2]] == [350.0, 1050.0]
    in_programs = [start for _, start, _ in runs[2:]]
    assert len(in_programs) == 2
    room = [(0.0, 285.0), (415.0, 985.0), (1115.0, 1985.0), (2035.0, 3585.0)]
    assert all(in_room(start, room) for start in in_programs)


def test_test_starts_are_the_same_on_every_run(recording_set: RecordingSet) -> None:
    recording_set.add(
        "a.mp4", 3600.0, [("00:05:00", "00:06:40"), ("00:16:40", "00:18:20")]
    )
    recording_set.add("b.mp4", 1800.0, [])
    script = {"a.mp4": [(PROGRAM, 0.0)], "b.mp4": [(PROGRAM, 0.0)]}
    first, second = FakeCandidate("fake", script), FakeCandidate("fake", script)

    first_scorecard = recording_set.run(first)
    second_scorecard = recording_set.run(second)

    # a: 2 test starts in commercial breaks and 2 inside programs; b: none in
    # commercial breaks, so 1 inside a program.
    assert trial_runs(first) == trial_runs(second)
    assert len(trial_runs(first)) == 5
    assert first_scorecard["detectors"] == second_scorecard["detectors"]


def test_recording_too_short_or_too_busy_gets_no_program_test_start(
    recording_set: RecordingSet, log: list[str]
) -> None:
    # short: 10 s long, so no start is 15 s from its end: no test start.
    # busy: commercial breaks leave only 20 s of program between them, so it
    #   gets one test start mid-commercial break and none inside a program.
    # tight: the program between its commercial breaks is exactly 30 s, so
    #   its middle, 15 s from both edges, is the only place for a test start
    #   inside a program. Its two commercial breaks ask for two there, but one
    #   moment is only tested once.
    recording_set.add("short.mp4", 10.0, [])
    recording_set.add(
        "busy.mp4", 300.0, [("00:00:00", "00:02:00"), ("00:02:20", "00:05:00")]
    )
    recording_set.add(
        "tight.mp4", 300.0, [("00:00:00", "00:02:00"), ("00:02:30", "00:05:00")]
    )
    candidate = FakeCandidate(
        "fake",
        {
            "short.mp4": [(PROGRAM, 0.0)],
            "busy.mp4": [(CB, 0.0), (PROGRAM, 120.0), (CB, 140.0)],
            "tight.mp4": [(CB, 0.0), (PROGRAM, 120.0), (CB, 150.0)],
        },
    )

    scorecard = recording_set.run(candidate)

    assert trial_runs(candidate) == [
        ("busy.mp4", 60.0, 75.0),
        ("busy.mp4", 220.0, 235.0),
        ("tight.mp4", 60.0, 75.0),
        ("tight.mp4", 225.0, 240.0),
        ("tight.mp4", 135.0, 150.0),
    ]
    per_recording = scorecard["detectors"][0]["per_recording"]
    starts = {
        name: measures["startup_delay_within_limit"]["based_on"]["test_starts"]
        for name, measures in per_recording.items()
    }
    assert starts == {"short.mp4": 0, "busy.mp4": 2, "tight.mp4": 3}
    warnings = [line for line in log if line.startswith("WARNING")]
    assert warnings == [
        "WARNING busy.mp4 has no program at least 15 s from every labeled edge "
        "and from its end, so it has no test start inside a program",
        "WARNING short.mp4 has no program at least 15 s from every labeled edge "
        "and from its end, so it has no test start inside a program",
    ]


def test_candidate_that_never_settles_within_the_trial_counts_as_over_10_s(
    recording_set: RecordingSet,
) -> None:
    # Labels 60 to 180 s: one test start at 120 s, one inside a program.
    # a: from 120 s the candidate never reports anything; inside the program
    #    it reports the program only at the trial run's end, 15 s in, which is
    #    too late. Neither has a delay to measure.
    # b: from 120 s it reports the program, which is wrong, then UNKNOWN,
    #    then the commercial break 7 s in: delay 7 s. Inside the program it
    #    settles at once.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    script = [(PROGRAM, 0.0), (CB, 60.0), (PROGRAM, 180.0)]
    b_script = [
        (PROGRAM, 0.0),
        (CB, 60.0),
        (PROGRAM, 110.0),
        (UNKNOWN, 122.0),
        (CB, 127.0),
        (PROGRAM, 180.0),
    ]

    def settle(name: str, start: float) -> float | None:
        if name == "b.mp4":
            return 0.0
        return None if start == 120.0 else 15.0

    candidate = FakeCandidate(
        "fake", {"a.mp4": script, "b.mp4": b_script}, settle=settle
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    a, b = scored["per_recording"]["a.mp4"], scored["per_recording"]["b.mp4"]
    assert a["startup_delay_within_limit"] == {
        "value": 0.0,
        "based_on": {"test_starts": 2},
    }
    assert a["startup_delay_median"] == {
        "value": None,
        "based_on": {"test_starts": 0},
    }
    assert b["startup_delay_within_limit"]["value"] == 1.0
    assert b["startup_delay_median"] == {
        "value": 3.5,
        "based_on": {"test_starts": 2},
    }
    assert scored["overall"]["startup_delay_within_limit"] == {
        "value": 0.5,
        "based_on": {"test_starts": 4},
    }
    assert scored["verdicts"]["startup_delay_within_limit"] == "fail"
    assert scored["verdict"] == "fail"


@pytest.mark.parametrize(
    ("slow_starts", "verdict"), [(0, "pass"), (1, "pass"), (2, "fail")]
)
def test_startup_delay_passes_when_95_percent_are_within_10_s_counting_10_s_as_within(
    recording_set: RecordingSet, slow_starts: int, verdict: str
) -> None:
    # 10 labeled commercial breaks, each 60 s long and 150 s apart, give 10
    # test starts in them and 10 inside programs. The candidate settles
    # exactly 10.0 s after each start, which is within, except on the trial
    # runs from the first ``slow_starts`` commercial breaks, where it takes
    # 10.5 s. 19 of 20 within is 95% and passes; 18 of 20 is 90% and fails.
    starts = [100.0 + 150.0 * i for i in range(10)]
    recording_set.add(
        "a.mp4", 3600.0, [(clock(start), clock(start + 60.0)) for start in starts]
    )
    script = [(PROGRAM, 0.0)]
    for start in starts:
        script += [(CB, start), (PROGRAM, start + 60.0)]
    slow = {start + 30.0 for start in starts[:slow_starts]}
    candidate = FakeCandidate(
        "fake",
        {"a.mp4": script},
        settle=lambda name, start: 10.5 if start in slow else 10.0,
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["overall"]["startup_delay_within_limit"] == {
        "value": (20 - slow_starts) / 20,
        "based_on": {"test_starts": 20},
    }
    assert scored["verdicts"] == {
        "entry_delay_within_limit": "pass",
        "exit_delay_within_limit": "pass",
        "missed_commercial_breaks": "pass",
        "startup_delay_within_limit": verdict,
    }
    assert scored["verdict"] == verdict


def test_trial_run_that_cannot_be_scored_is_an_error_for_its_recording(
    recording_set: RecordingSet,
) -> None:
    # The candidate reports its settled state 1 s before the trial run from
    # 120 s starts.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [])
    script = [(PROGRAM, 0.0), (CB, 60.0), (PROGRAM, 180.0)]
    candidate = FakeCandidate(
        "fake",
        {"a.mp4": script, "b.mp4": [(PROGRAM, 0.0)]},
        settle=lambda name, start: -1.0 if start == 120.0 else 0.0,
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {
        "a.mp4": "trial run from 120.0 s: state change 1 (COMMERCIAL_BREAK at "
        "119.0 s) is reported before the run's start at 120.0 s"
    }
    assert list(scored["per_recording"]) == ["b.mp4"]
    assert scored["overall"]["startup_delay_within_limit"] == {
        "value": 1.0,
        "based_on": {"test_starts": 1},
    }
