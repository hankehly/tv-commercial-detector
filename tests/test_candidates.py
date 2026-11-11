"""Tests for candidate scoring, driven through the benchmark as a whole.

Each test builds a small recording set in a temporary folder, plugs in fake
candidates that report scripted state changes, and reads the scorecard the run
saves. Expected numbers are worked out by hand in each test.
"""

import json
import re

import pytest
from fake_detectors import FakeCandidate, FakeDetector
from recording_sets import RecordingSet

from tv_commercial_detector import cli, settings
from tv_commercial_detector.cli import main
from tv_commercial_detector.detectors import State
from tv_commercial_detector.settings import DATA_FOLDER_VARIABLE


def clock(seconds: float) -> str:
    """Write a whole number of seconds as a label time, hh:mm:ss."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}:{secs:02d}"


CB = State.COMMERCIAL_BREAK
PROGRAM = State.PROGRAM
UNKNOWN = State.UNKNOWN


def test_worked_example_entry_3_s_and_exit_4_s_are_both_within_the_bar(
    recording_set: RecordingSet,
) -> None:
    # The example from #7: labels 60 to 180 s, the candidate reports a
    # commercial break at 63 s and the program at 184 s. On its two trial
    # runs, one from the middle of the commercial break and one inside the
    # program, it works out what is on air at once.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate(
        "fake", {"a.mp4": [(PROGRAM, 0.0), (CB, 63.0), (PROGRAM, 184.0)]}
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["kind"] == "candidate"
    assert candidate.runs[0] == ("a.mp4", 0.0, 3600.0)
    one = {"commercial_breaks": 1}
    two_starts = {"test_starts": 2}
    assert scored["overall"] == {
        "entry_delay_within_limit": {"value": 1.0, "based_on": one},
        "entry_delay_median": {"value": 3.0, "based_on": one},
        "exit_delay_within_limit": {"value": 1.0, "based_on": one},
        "exit_delay_median": {"value": 4.0, "based_on": one},
        "missed_commercial_breaks": {"value": 0, "based_on": one},
        "startup_delay_within_limit": {"value": 1.0, "based_on": two_starts},
        "startup_delay_median": {"value": 0.0, "based_on": two_starts},
    }
    assert scored["per_recording"]["a.mp4"] == scored["overall"]
    assert scored["verdicts"] == {
        "entry_delay_within_limit": "pass",
        "exit_delay_within_limit": "pass",
        "missed_commercial_breaks": "pass",
        "startup_delay_within_limit": "pass",
    }
    assert scored["verdict"] == "pass"
    assert scored["errors"] == {}


def test_a_change_up_to_half_a_second_before_a_labeled_start_is_on_time(
    recording_set: RecordingSet,
) -> None:
    # 60 to 180: a commercial break reported 0.5 s early, even briefly, counts
    # as entered on time, delay 0. 300 to 400: one reported 1 s early and
    # dropped 0.6 s before the labeled start is too early, so the commercial
    # break is missed.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:05:00", "00:06:40")]
    )
    candidate = FakeCandidate(
        "early",
        {
            "a.mp4": [
                (PROGRAM, 1.0),
                (CB, 59.5),
                (PROGRAM, 59.9),
                (CB, 299.0),
                (PROGRAM, 299.4),
            ]
        },
    )

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["missed_commercial_breaks"] == {
        "value": 1,
        "based_on": {"commercial_breaks": 2},
    }
    assert overall["entry_delay_within_limit"] == {
        "value": 0.5,
        "based_on": {"commercial_breaks": 2},
    }
    assert overall["entry_delay_median"] == {
        "value": 0.0,
        "based_on": {"commercial_breaks": 1},
    }


def test_a_change_up_to_half_a_second_before_a_labeled_end_is_on_time(
    recording_set: RecordingSet,
) -> None:
    # The program is reported at 179.5 s, 0.5 s before the labeled end, so the
    # exit is on time even though the candidate briefly goes back to the
    # commercial break. At 400 s it is reported 1 s early and dropped 0.6 s
    # early, so the exit counts from the next report of the program, at 410 s.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:05:00", "00:06:40")]
    )
    candidate = FakeCandidate(
        "early",
        {
            "a.mp4": [
                (CB, 60.0),
                (PROGRAM, 179.5),
                (CB, 179.9),
                (PROGRAM, 185.0),
                (CB, 300.0),
                (PROGRAM, 399.0),
                (CB, 399.4),
                (PROGRAM, 410.0),
            ]
        },
    )

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["exit_delay_within_limit"] == {
        "value": 0.5,
        "based_on": {"commercial_breaks": 2},
    }
    assert overall["exit_delay_median"] == {
        "value": 5.0,
        "based_on": {"commercial_breaks": 2},
    }


def test_exit_counts_as_over_the_limit_when_the_next_commercial_break_starts_first(
    recording_set: RecordingSet,
) -> None:
    # The candidate stays in a commercial break from 60 s to 705 s. The first
    # labeled one ends at 180 s, but the program is never reported before the
    # next starts at 600 s: over 5 s, with no delay to measure. The second
    # ends at 700 s and is left 5.0 s later, exactly on the limit.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:10:00", "00:11:40")]
    )
    candidate = FakeCandidate("slow", {"a.mp4": [(CB, 60.0), (PROGRAM, 705.0)]})

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["exit_delay_within_limit"] == {
        "value": 0.5,
        "based_on": {"commercial_breaks": 2},
    }
    assert overall["exit_delay_median"] == {
        "value": 5.0,
        "based_on": {"commercial_breaks": 1},
    }


def test_commercial_break_under_way_at_the_start_has_no_entry_delay(
    recording_set: RecordingSet,
) -> None:
    # a: the first commercial break is already on at 0 s. The candidate reports
    #    it at 4 s, which isn't an entry delay, and leaves it 3 s late. The
    #    second is entered 2 s late and left 1 s late.
    # b: the one under way at 0 s is never reported, so it is missed, and
    #    there is no entry delay to judge.
    recording_set.add(
        "a.mp4", 3600.0, [("00:00:00", "00:01:30"), ("00:05:00", "00:06:40")]
    )
    recording_set.add("b.mp4", 3600.0, [("00:00:00", "00:01:30")])
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [(CB, 4.0), (PROGRAM, 93.0), (CB, 302.0), (PROGRAM, 401.0)],
            "b.mp4": [(PROGRAM, 1.0)],
        },
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    a, b = scored["per_recording"]["a.mp4"], scored["per_recording"]["b.mp4"]
    assert a["entry_delay_within_limit"] == {
        "value": 1.0,
        "based_on": {"commercial_breaks": 1},
    }
    assert a["entry_delay_median"]["value"] == 2.0
    assert a["exit_delay_within_limit"] == {
        "value": 1.0,
        "based_on": {"commercial_breaks": 2},
    }
    assert a["exit_delay_median"]["value"] == 2.0
    assert b["entry_delay_within_limit"] == {
        "value": None,
        "based_on": {"commercial_breaks": 0},
    }
    assert b["missed_commercial_breaks"] == {
        "value": 1,
        "based_on": {"commercial_breaks": 1},
    }
    assert scored["overall"]["missed_commercial_breaks"] == {
        "value": 1,
        "based_on": {"commercial_breaks": 3},
    }


def test_commercial_break_starting_in_the_last_5_s_is_left_out_of_every_measure(
    recording_set: RecordingSet,
) -> None:
    # a is 600 s long. Its commercial break starting at 596 s, 4 s before the
    # end, is left out, so missing it doesn't count. b's starts at 595 s,
    # exactly 5 s before the end, so it counts: entered 1 s late.
    recording_set.add(
        "a.mp4", 600.0, [("00:01:00", "00:02:00"), ("00:09:56", "00:10:00")]
    )
    recording_set.add("b.mp4", 600.0, [("00:09:55", "00:09:58")])
    candidate = FakeCandidate(
        "fake",
        {"a.mp4": [(CB, 60.0), (PROGRAM, 120.0)], "b.mp4": [(CB, 596.0)]},
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    a, b = scored["per_recording"]["a.mp4"], scored["per_recording"]["b.mp4"]
    one = {"commercial_breaks": 1}
    assert a["missed_commercial_breaks"] == {"value": 0, "based_on": one}
    assert a["entry_delay_within_limit"] == {"value": 1.0, "based_on": one}
    assert a["exit_delay_within_limit"] == {"value": 1.0, "based_on": one}
    assert b["missed_commercial_breaks"] == {"value": 0, "based_on": one}
    assert b["entry_delay_median"] == {"value": 1.0, "based_on": one}


def test_commercial_break_ending_near_the_end_has_an_exit_delay_only_if_left_in_time(
    recording_set: RecordingSet,
) -> None:
    # Every recording is 600 s long, with a commercial break from 500 s.
    # a: it ends at 597 s and the program is reported at 599 s, before the end:
    #    exit delay 2 s.
    # b: it is still running at the end: no exit delay.
    # c: it ends at 597 s and the program is reported only at 601 s, after the
    #    end: no exit delay.
    # d: it ends at 595 s, exactly 5 s before the end, and the program is
    #    never reported: an exit delay over 5 s.
    for name, end in [("a", "00:09:57"), ("b", "00:10:00"), ("c", "00:09:57")]:
        recording_set.add(f"{name}.mp4", 600.0, [("00:08:20", end)])
    recording_set.add("d.mp4", 600.0, [("00:08:20", "00:09:55")])
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [(CB, 500.0), (PROGRAM, 599.0)],
            "b.mp4": [(CB, 500.0)],
            "c.mp4": [(CB, 500.0), (PROGRAM, 601.0)],
            "d.mp4": [(CB, 500.0)],
        },
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    exits = {
        name: measures["exit_delay_within_limit"]
        for name, measures in scored["per_recording"].items()
    }
    none = {"value": None, "based_on": {"commercial_breaks": 0}}
    assert exits == {
        "a.mp4": {"value": 1.0, "based_on": {"commercial_breaks": 1}},
        "b.mp4": none,
        "c.mp4": none,
        "d.mp4": {"value": 0.0, "based_on": {"commercial_breaks": 1}},
    }
    assert scored["overall"]["exit_delay_median"] == {
        "value": 2.0,
        "based_on": {"commercial_breaks": 1},
    }


@pytest.mark.parametrize(
    ("slow_entries", "verdict"), [(0, "pass"), (1, "pass"), (2, "fail")]
)
def test_entry_delay_passes_when_95_percent_are_within_5_s_counting_5_s_as_within(
    recording_set: RecordingSet, slow_entries: int, verdict: str
) -> None:
    # 20 labeled commercial breaks, each 60 s long and 150 s apart. Each is
    # entered exactly 5.0 s late, which is within, except the first
    # ``slow_entries``, entered 6 s late. 19 of 20 within is 95% and passes;
    # 18 of 20 is 90% and fails. Every exit is 1 s late.
    starts = [100.0 + 150.0 * i for i in range(20)]
    recording_set.add(
        "a.mp4", 3600.0, [(clock(start), clock(start + 60.0)) for start in starts]
    )
    script = [(PROGRAM, 1.0)]
    for i, start in enumerate(starts):
        script += [(CB, start + (6.0 if i < slow_entries else 5.0))]
        script += [(PROGRAM, start + 61.0)]
    candidate = FakeCandidate("fake", {"a.mp4": script})

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["overall"]["entry_delay_within_limit"] == {
        "value": (20 - slow_entries) / 20,
        "based_on": {"commercial_breaks": 20},
    }
    assert scored["verdicts"] == {
        "entry_delay_within_limit": verdict,
        "exit_delay_within_limit": "pass",
        "missed_commercial_breaks": "pass",
        "startup_delay_within_limit": "pass",
    }
    assert scored["verdict"] == verdict


@pytest.mark.parametrize(("missed", "verdict"), [(1, "pass"), (2, "fail")])
def test_missed_commercial_breaks_pass_up_to_2_percent(
    recording_set: RecordingSet, missed: int, verdict: str
) -> None:
    # 50 labeled commercial breaks, each 30 s long and 70 s apart, entered and
    # left on time except the first ``missed``, never reported. 1 of 50 is 2%
    # and passes; 2 of 50 is 4% and fails. Missed ones count as entered over
    # 5 s, but 48 of 50 within is still 96%. Their test starts never settle,
    # but 98 of 100 within is still 98%.
    starts = [10.0 + 70.0 * i for i in range(50)]
    recording_set.add(
        "a.mp4", 3600.0, [(clock(start), clock(start + 30.0)) for start in starts]
    )
    script = [(PROGRAM, 1.0)]
    for start in starts[missed:]:
        script += [(CB, start), (PROGRAM, start + 30.0)]
    candidate = FakeCandidate("fake", {"a.mp4": script})

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["overall"]["missed_commercial_breaks"] == {
        "value": missed,
        "based_on": {"commercial_breaks": 50},
    }
    assert scored["verdicts"] == {
        "entry_delay_within_limit": "pass",
        "exit_delay_within_limit": "pass",
        "missed_commercial_breaks": verdict,
        "startup_delay_within_limit": "pass",
    }
    assert scored["verdict"] == verdict


def test_exit_delay_fails_below_95_percent_of_entered_commercial_breaks(
    recording_set: RecordingSet,
) -> None:
    # Two commercial breaks, both entered on time; the second is left 5.1 s
    # late. 1 of 2 within is 50%.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:05:00", "00:06:40")]
    )
    candidate = FakeCandidate(
        "fake",
        {"a.mp4": [(CB, 60.0), (PROGRAM, 180.0), (CB, 300.0), (PROGRAM, 405.1)]},
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["verdicts"]["exit_delay_within_limit"] == "fail"
    assert scored["verdict"] == "fail"


def test_candidate_failing_on_one_recording_is_an_error_there_and_the_run_carries_on(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate(
        "fake", {"a.mp4": "model file not found", "b.mp4": [(CB, 60.0)]}
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {"a.mp4": "model file not found"}
    assert list(scored["per_recording"]) == ["b.mp4"]
    assert scored["overall"]["missed_commercial_breaks"] == {
        "value": 0,
        "based_on": {"commercial_breaks": 1},
    }


@pytest.mark.parametrize(
    ("changes", "processing_seconds", "error"),
    [
        (
            [(CB, 70.0), (PROGRAM, 65.0)],
            0.0,
            "state change 2 (PROGRAM at 65.0 s) is reported before the one before it",
        ),
        (
            [(CB, -1.0)],
            0.0,
            "state change 1 (COMMERCIAL_BREAK at -1.0 s) is reported before "
            "the run's start at 0.0 s",
        ),
        (
            [(CB, float("nan"))],
            0.0,
            "state change 1 (COMMERCIAL_BREAK at nan s) has a time that isn't "
            "a finite number",
        ),
        (
            [(CB, None)],
            0.0,
            "state change 1 (COMMERCIAL_BREAK at None s) has a time that "
            "isn't a finite number",
        ),
        (
            [("ADVERT", 60.0)],
            0.0,
            "state change 1 (ADVERT at 60.0 s) has a state that isn't "
            "COMMERCIAL_BREAK, PROGRAM or UNKNOWN",
        ),
        (
            [(CB, 60.0)],
            -2.0,
            "processing time -2.0 s isn't a finite number of seconds, 0 or more",
        ),
    ],
)
def test_report_that_cannot_be_scored_is_an_error(
    recording_set: RecordingSet,
    changes: list,
    processing_seconds: float,
    error: str,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate(
        "sloppy", {"a.mp4": changes}, processing_seconds=processing_seconds
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {"a.mp4": error}
    assert scored["per_recording"] == {}


def test_unknown_while_settling_is_covered_by_the_delays(
    recording_set: RecordingSet,
) -> None:
    # Labels 60 to 180 s. The candidate goes from the program to UNKNOWN at
    # 61 s and reports the commercial break at 63 s: entry delay 3 s. It goes
    # to UNKNOWN at 181 s and reports the program at 184 s: exit delay 4 s.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [
                (PROGRAM, 1.0),
                (UNKNOWN, 61.0),
                (CB, 63.0),
                (UNKNOWN, 181.0),
                (PROGRAM, 184.0),
            ]
        },
    )

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["entry_delay_median"]["value"] == 3.0
    assert overall["exit_delay_median"]["value"] == 4.0


def test_run_command_prints_candidates_with_pass_or_fail_and_look_ahead_without(
    recording_set: RecordingSet, monkeypatch: pytest.MonkeyPatch, log: list[str]
) -> None:
    # a: entered 3 s late and left 4 s late. b: missed. Overall, 1 of 2
    # entered within 5 s fails, the exit passes, and 1 of 2 missed fails.
    # Each has a test start mid-commercial break and one inside a program,
    # and the candidate settles at once on what its script says. That is
    # wrong for b's commercial break, so 3 of 4 within 10 s fails.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [(PROGRAM, 0.0), (CB, 63.0), (PROGRAM, 184.0)],
            "b.mp4": [(PROGRAM, 0.0)],
        },
    )
    look_ahead = FakeDetector("tool", {"a.mp4": [(60.0, 180.0)], "b.mp4": []})
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(recording_set.data_folder))
    monkeypatch.setattr(settings, "RECORDING_LIST", recording_set.recording_list)
    monkeypatch.setattr(settings, "LABELS_FOLDER", recording_set.labels_folder)
    monkeypatch.setattr(cli, "Ffprobe", recording_set.probe)
    monkeypatch.setattr(
        cli, "look_ahead_detectors", lambda data_folder, rerun: [look_ahead]
    )
    monkeypatch.setattr(cli, "candidates", lambda: [candidate])

    exit_code = main(["run"])

    assert exit_code == 0
    [saved] = (recording_set.data_folder / "runs").glob("*/scorecard.json")
    tool_scores, candidate_scores = json.loads(saved.read_text())["detectors"]
    assert "verdicts" not in tool_scores
    assert "verdict" not in tool_scores
    assert candidate_scores["verdict"] == "fail"
    lines = [line.removeprefix("INFO ") for line in log if line.startswith("INFO ")]
    assert "tool (look-ahead)" in lines
    assert "fake (candidate): fail" in lines
    table = lines[lines.index("fake (candidate): fail") + 1 :]
    rows = {
        cells[0]: cells[1:]
        for cells in (re.split(r" {2,}", line) for line in table)
        if len(cells) > 1
    }
    assert rows == {
        "Measure": ["Overall", "Verdict", "a.mp4", "b.mp4"],
        "Entry delay within 5 s": ["50.0% of 2", "fail", "100.0% of 1", "0.0% of 1"],
        "Entry delay, median": ["3.0 s (1)", "-", "3.0 s (1)", "- (0)"],
        "Exit delay within 5 s": ["100.0% of 1", "pass", "100.0% of 1", "- of 0"],
        "Exit delay, median": ["4.0 s (1)", "-", "4.0 s (1)", "- (0)"],
        "Missed commercial breaks": ["1 of 2", "fail", "0 of 1", "1 of 1"],
        "Startup delay within 10 s": [
            "75.0% of 4",
            "fail",
            "100.0% of 2",
            "50.0% of 2",
        ],
        "Startup delay, median": ["0.0 s (3)", "-", "0.0 s (2)", "0.0 s (1)"],
    }
    tool_table = lines[lines.index("tool (look-ahead)") + 1 : lines.index("")]
    assert tool_table[0].split() == ["Measure", "Overall", "a.mp4", "b.mp4"]


def test_already_in_a_commercial_break_at_the_labeled_start_is_delay_0(
    recording_set: RecordingSet,
) -> None:
    # Labels 300 to 400 s and 600 to 700 s. The first is entered at 200 s,
    # well before its start, and the state is still a commercial break at
    # 300 s: delay 0. Before the second, the candidate is in a commercial break
    # from 500 s but drops to UNKNOWN at 599.8 s, so at the labeled start it
    # isn't; it only reports a commercial break again at 607 s: delay 7 s, even
    # though the state 0.5 s before the start was a commercial break.
    recording_set.add(
        "a.mp4", 3600.0, [("00:05:00", "00:06:40"), ("00:10:00", "00:11:40")]
    )
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [
                (CB, 200.0),
                (PROGRAM, 400.0),
                (CB, 500.0),
                (UNKNOWN, 599.8),
                (CB, 607.0),
                (PROGRAM, 700.0),
            ]
        },
    )

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["entry_delay_within_limit"]["value"] == 0.5
    assert overall["entry_delay_median"] == {
        "value": 3.5,
        "based_on": {"commercial_breaks": 2},
    }


def test_program_before_the_labeled_end_that_is_dropped_by_the_end_is_not_an_exit(
    recording_set: RecordingSet,
) -> None:
    # Labels 60 to 180 s. The candidate reports the program early, at 170 s,
    # drops to UNKNOWN at 179.8 s, and reports the program again at 188 s:
    # exit delay 8 s.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate(
        "fake",
        {"a.mp4": [(CB, 60.0), (PROGRAM, 170.0), (UNKNOWN, 179.8), (PROGRAM, 188.0)]},
    )

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["exit_delay_median"]["value"] == 8.0
    assert overall["exit_delay_within_limit"]["value"] == 0.0


def test_recording_without_commercial_breaks_is_scored(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [])
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [(PROGRAM, 0.0), (CB, 60.0), (PROGRAM, 180.0)],
            "b.mp4": [(PROGRAM, 0.0)],
        },
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["per_recording"]["b.mp4"]["missed_commercial_breaks"] == {
        "value": 0,
        "based_on": {"commercial_breaks": 0},
    }
    assert scored["verdict"] == "pass"


def test_measure_with_nothing_to_count_fails(recording_set: RecordingSet) -> None:
    # The candidate fails on the only recording, so nothing is measured, and
    # nothing shows it is good enough for live use.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate("fake", {"a.mp4": "model file not found"})

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["verdicts"] == {
        "entry_delay_within_limit": "fail",
        "exit_delay_within_limit": "fail",
        "missed_commercial_breaks": "fail",
        "startup_delay_within_limit": "fail",
    }
    assert scored["verdict"] == "fail"


def test_half_a_second_allowance_holds_at_fractional_label_times(
    recording_set: RecordingSet,
) -> None:
    # Labels 64.4 to 180 s. A commercial break reported at 63.9 s, exactly
    # 0.5 s early, and dropped at 64.0 s is on time: delay 0.
    recording_set.add("a.mp4", 3600.0, [("00:01:04.4", "00:03:00")])
    candidate = FakeCandidate(
        "fake", {"a.mp4": [(CB, 63.9), (PROGRAM, 64.0), (CB, 70.0)]}
    )

    scorecard = recording_set.run(candidate)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["entry_delay_median"] == {
        "value": 0.0,
        "based_on": {"commercial_breaks": 1},
    }


def test_delay_a_fraction_of_a_millisecond_over_5_s_is_over_the_limit(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    candidate = FakeCandidate("fake", {"a.mp4": [(CB, 65.0004), (PROGRAM, 180.0)]})

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    assert scored["overall"]["entry_delay_within_limit"]["value"] == 0.0
    assert scored["verdicts"]["entry_delay_within_limit"] == "fail"


def test_exit_near_the_end_counts_only_reports_strictly_before_the_end(
    recording_set: RecordingSet,
) -> None:
    # a: 600 s long, labels 500 to 597 s; the program is reported exactly at
    #    600 s, the end, which isn't before it: no exit delay.
    # b: 599.95 s long, labeled to 600.0 s, the length rounded up to the next
    #    tenth. The program reported at 599.0 s, before the end, is an exit
    #    on time: delay 0.
    recording_set.add("a.mp4", 600.0, [("00:08:20", "00:09:57")])
    recording_set.add("b.mp4", 599.95, [("00:08:20", "00:10:00")])
    candidate = FakeCandidate(
        "fake",
        {
            "a.mp4": [(CB, 500.0), (PROGRAM, 600.0)],
            "b.mp4": [(CB, 500.0), (PROGRAM, 599.0)],
        },
    )

    scorecard = recording_set.run(candidate)

    [scored] = scorecard["detectors"]
    a, b = scored["per_recording"]["a.mp4"], scored["per_recording"]["b.mp4"]
    assert a["exit_delay_within_limit"] == {
        "value": None,
        "based_on": {"commercial_breaks": 0},
    }
    assert b["exit_delay_median"] == {
        "value": 0.0,
        "based_on": {"commercial_breaks": 1},
    }
