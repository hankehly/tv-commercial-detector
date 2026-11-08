"""Tests for the ``run`` command, driven through the benchmark as a whole.

Each test builds a small recording set in a temporary folder (placeholder
recordings, a list of recordings, label files and a fake media probe), plugs in
fake look-ahead detectors that return scripted reports, and reads the scorecard
the run saves. Expected numbers are worked out by hand in each test.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest
from fake_detectors import FakeDetector
from recording_sets import STARTED_AT, RecordingSet

from tv_commercial_detector import cli, settings
from tv_commercial_detector.benchmark import run
from tv_commercial_detector.cli import main
from tv_commercial_detector.detectors import Recording
from tv_commercial_detector.settings import DATA_FOLDER_VARIABLE


def test_detector_that_finds_every_commercial_break_exactly_misses_none(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    detector = FakeDetector("exact", {"a.mp4": [(60.0, 180.0)]})

    scorecard = recording_set.run(detector)

    [scored] = scorecard["detectors"]
    assert scored["name"] == "exact"
    assert scored["kind"] == "look-ahead"
    assert scored["overall"] == {
        "missed_commercial_breaks": {
            "value": 0,
            "based_on": {"commercial_breaks": 1},
        },
        "false_flips_per_hour": {"value": 0.0, "based_on": {"hours": 1.0}},
        "start_offset_median_size": {
            "value": 0.0,
            "based_on": {"commercial_breaks": 1},
        },
        "start_offset_p95_size": {"value": 0.0, "based_on": {"commercial_breaks": 1}},
        "start_offset_median": {"value": 0.0, "based_on": {"commercial_breaks": 1}},
        "end_offset_median_size": {"value": 0.0, "based_on": {"commercial_breaks": 1}},
        "end_offset_p95_size": {"value": 0.0, "based_on": {"commercial_breaks": 1}},
        "end_offset_median": {"value": 0.0, "based_on": {"commercial_breaks": 1}},
    }
    assert scored["errors"] == {}


def test_detector_is_told_the_recording_but_not_its_labels(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")], channel="NTV")
    detector = FakeDetector("exact", {"a.mp4": []})

    recording_set.run(detector)

    assert detector.seen == [
        Recording(
            path=recording_set.data_folder / "recordings" / "a.mp4",
            fingerprint=hashlib.sha256(b"a.mp4").hexdigest(),
            length_seconds=3600.0,
            channel="NTV",
        )
    ]


def test_matching_needs_more_than_half_a_second_of_overlap(
    recording_set: RecordingSet,
) -> None:
    # 179.5 to 300 overlaps 60 to 180 by exactly 0.5 s, so it doesn't match:
    # the labeled one is missed and the reported one is a false flip.
    # 699.4 to 800 overlaps 600 to 700 by 0.6 s, so it matches.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:10:00", "00:11:40")]
    )
    detector = FakeDetector("edge", {"a.mp4": [(179.5, 300.0), (699.4, 800.0)]})

    scorecard = recording_set.run(detector)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["missed_commercial_breaks"] == {
        "value": 1,
        "based_on": {"commercial_breaks": 2},
    }
    assert overall["false_flips_per_hour"] == {"value": 1.0, "based_on": {"hours": 1.0}}
    assert overall["start_offset_median"] == {
        "value": 99.4,
        "based_on": {"commercial_breaks": 1},
    }
    assert overall["end_offset_median"]["value"] == 100.0


def test_unmatched_reports_and_extra_pieces_are_both_false_flips(
    recording_set: RecordingSet,
) -> None:
    # 60 to 180 is reported in two pieces: one extra piece. 1000 to 1030 matches
    # nothing. Two false flips in two hours. The pieces together span the
    # labeled commercial break, so both edges are on time.
    recording_set.add("a.mp4", 7200.0, [("00:01:00", "00:03:00")])
    detector = FakeDetector(
        "split", {"a.mp4": [(60.0, 100.0), (100.2, 180.0), (1000.0, 1030.0)]}
    )

    scorecard = recording_set.run(detector)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["missed_commercial_breaks"]["value"] == 0
    assert overall["false_flips_per_hour"] == {"value": 1.0, "based_on": {"hours": 2.0}}
    assert overall["start_offset_median"]["value"] == 0.0
    assert overall["end_offset_median"]["value"] == 0.0


def test_one_reported_commercial_break_spanning_two_labeled_ones_matches_both(
    recording_set: RecordingSet,
) -> None:
    # 50 to 420 overlaps both 60 to 180 and 300 to 400, so neither is missed and
    # it is no false flip. Its start is 10 s early for the first, 250 s early
    # for the second; its end is 240 s late for the first, 20 s late for the
    # second.
    recording_set.add(
        "a.mp4", 3600.0, [("00:01:00", "00:03:00"), ("00:05:00", "00:06:40")]
    )
    detector = FakeDetector("merged", {"a.mp4": [(50.0, 420.0)]})

    scorecard = recording_set.run(detector)

    overall = scorecard["detectors"][0]["overall"]
    assert overall["missed_commercial_breaks"]["value"] == 0
    assert overall["false_flips_per_hour"]["value"] == 0.0
    assert overall["start_offset_median"] == {
        "value": -130.0,
        "based_on": {"commercial_breaks": 2},
    }
    assert overall["end_offset_median"]["value"] == 130.0


def test_edge_offsets_give_median_and_95th_percentile_sizes_and_signed_medians(
    recording_set: RecordingSet,
) -> None:
    # Start offsets -2, +1, +3, -0.5, +4: sizes sorted 0.5, 1, 2, 3, 4, so the
    # median size is 2 and the 95th percentile sits 0.8 of the way from 3 to 4.
    # The signed values sorted are -2, -0.5, 1, 3, 4: median 1.
    # End offsets +1, -3, +2, 0, -6: sizes sorted 0, 1, 2, 3, 6, so the median
    # size is 2 and the 95th percentile is 3 + 0.8 * 3. Signed median 0.
    recording_set.add(
        "a.mp4",
        3600.0,
        [
            ("00:01:40", "00:03:20"),
            ("00:06:40", "00:08:20"),
            ("00:11:40", "00:13:20"),
            ("00:16:40", "00:18:20"),
            ("00:21:40", "00:23:20"),
        ],
    )
    detector = FakeDetector(
        "offsets",
        {
            "a.mp4": [
                (98.0, 201.0),
                (401.0, 497.0),
                (703.0, 802.0),
                (999.5, 1100.0),
                (1304.0, 1394.0),
            ]
        },
    )

    scorecard = recording_set.run(detector)

    overall = scorecard["detectors"][0]["overall"]
    values = {name: measure["value"] for name, measure in overall.items()}
    assert values == {
        "missed_commercial_breaks": 0,
        "false_flips_per_hour": 0.0,
        "start_offset_median_size": 2.0,
        "start_offset_p95_size": pytest.approx(3.8),
        "start_offset_median": 1.0,
        "end_offset_median_size": 2.0,
        "end_offset_p95_size": pytest.approx(5.4),
        "end_offset_median": 0.0,
    }
    assert overall["start_offset_p95_size"]["based_on"] == {"commercial_breaks": 5}


def test_overall_figures_pool_recordings_instead_of_averaging_them(
    recording_set: RecordingSet,
) -> None:
    # a: 1 hour, its one commercial break found 2 s late and 1 s late, plus one
    #    false flip.
    # b: 3 hours, all three commercial breaks missed.
    # c: 1 hour and commercial-free, with one false flip.
    # Overall: 3 of 4 missed, and 2 false flips in 5 hours is 0.4 per hour (the
    # average of the per-recording rates would be 0.67).
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add(
        "b.mp4",
        10800.0,
        [
            ("00:10:00", "00:12:00"),
            ("01:10:00", "01:12:00"),
            ("02:10:00", "02:12:00"),
        ],
    )
    recording_set.add("c.mp4", 3600.0, [])
    detector = FakeDetector(
        "pooled",
        {
            "a.mp4": [(62.0, 181.0), (2000.0, 2030.0)],
            "b.mp4": [],
            "c.mp4": [(500.0, 530.0)],
        },
    )

    scorecard = recording_set.run(detector)

    [scored] = scorecard["detectors"]
    a, b, c = (scored["per_recording"][name] for name in ("a.mp4", "b.mp4", "c.mp4"))
    assert a["missed_commercial_breaks"] == {
        "value": 0,
        "based_on": {"commercial_breaks": 1},
    }
    assert a["false_flips_per_hour"] == {"value": 1.0, "based_on": {"hours": 1.0}}
    assert a["start_offset_median"]["value"] == 2.0
    assert a["end_offset_median"]["value"] == 1.0
    assert b["missed_commercial_breaks"] == {
        "value": 3,
        "based_on": {"commercial_breaks": 3},
    }
    assert b["false_flips_per_hour"] == {"value": 0.0, "based_on": {"hours": 3.0}}
    assert b["start_offset_median"] == {
        "value": None,
        "based_on": {"commercial_breaks": 0},
    }
    assert c["missed_commercial_breaks"] == {
        "value": 0,
        "based_on": {"commercial_breaks": 0},
    }
    assert c["false_flips_per_hour"]["value"] == 1.0
    overall = scored["overall"]
    assert overall["missed_commercial_breaks"] == {
        "value": 3,
        "based_on": {"commercial_breaks": 4},
    }
    assert overall["false_flips_per_hour"] == {
        "value": pytest.approx(0.4),
        "based_on": {"hours": 5.0},
    }
    assert overall["start_offset_median"] == {
        "value": 2.0,
        "based_on": {"commercial_breaks": 1},
    }
    assert [r["file_name"] for r in scorecard["recordings"]] == [
        "a.mp4",
        "b.mp4",
        "c.mp4",
    ]


def test_detector_failing_on_one_recording_is_an_error_there_and_the_run_carries_on(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    broken = FakeDetector(
        "broken", {"a.mp4": [(60.0, 180.0)], "b.mp4": "comskip not found"}
    )
    fine = FakeDetector("fine", {"a.mp4": [], "b.mp4": [(60.0, 180.0)]})

    scorecard = recording_set.run(broken, fine)

    broken_scores, fine_scores = scorecard["detectors"]
    assert broken_scores["errors"] == {"b.mp4": "comskip not found"}
    assert list(broken_scores["per_recording"]) == ["a.mp4"]
    assert broken_scores["overall"]["missed_commercial_breaks"] == {
        "value": 0,
        "based_on": {"commercial_breaks": 1},
    }
    assert broken_scores["overall"]["false_flips_per_hour"]["based_on"] == {
        "hours": 1.0
    }
    assert fine_scores["errors"] == {}
    assert fine_scores["overall"]["missed_commercial_breaks"] == {
        "value": 1,
        "based_on": {"commercial_breaks": 2},
    }


def test_report_with_a_commercial_break_that_does_not_end_after_it_starts_is_an_error(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    detector = FakeDetector("backwards", {"a.mp4": [(60.0, 180.0), (300.0, 290.0)]})

    scorecard = recording_set.run(detector)

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {
        "a.mp4": "reported commercial break 300.0 to 290.0 s doesn't end after "
        "it starts"
    }
    assert scored["per_recording"] == {}
    assert scored["overall"]["missed_commercial_breaks"] == {
        "value": 0,
        "based_on": {"commercial_breaks": 0},
    }
    assert scored["overall"]["false_flips_per_hour"] == {
        "value": None,
        "based_on": {"hours": 0.0},
    }


@pytest.mark.parametrize("bad_time", [None, "60", float("nan"), True])
def test_report_with_a_time_that_is_not_a_finite_number_is_an_error(
    recording_set: RecordingSet, bad_time: object
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    detector = FakeDetector(
        "sloppy",
        {"a.mp4": [(bad_time, 180.0)], "b.mp4": [(60.0, 180.0)]},  # ty: ignore[invalid-argument-type]
    )

    scorecard = recording_set.run(detector)

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {
        "a.mp4": f"reported commercial break {bad_time} to 180.0 s has a time "
        "that isn't a finite number"
    }
    assert list(scored["per_recording"]) == ["b.mp4"]


def test_each_run_saves_its_scorecard_in_a_new_folder_named_after_its_start(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    runs = recording_set.data_folder / "runs"

    def run_once(detector: FakeDetector) -> Path | None:
        return run(
            recording_set.data_folder,
            recording_set.recording_list,
            recording_set.labels_folder,
            recording_set.probe(),
            [detector],
            STARTED_AT,
        ).scorecard_path

    first = run_once(FakeDetector("first", {"a.mp4": []}))
    first_content = first.read_text() if first else ""
    second = run_once(FakeDetector("second", {"a.mp4": []}))

    assert first == runs / "2026-11-08_14-03-22" / "scorecard.json"
    assert second == runs / "2026-11-08_14-03-22_2" / "scorecard.json"
    assert first.read_text() == first_content
    assert json.loads(first_content)["started_at"] == "2026-11-08T14:03:22+09:00"
    assert json.loads(second.read_text())["detectors"][0]["name"] == "second"


def test_run_with_validation_errors_scores_nothing_and_saves_nothing(
    recording_set: RecordingSet,
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    (recording_set.labels_folder / "a.toml").write_text("not = [valid")
    detector = FakeDetector("never", {"a.mp4": []})

    result = run(
        recording_set.data_folder,
        recording_set.recording_list,
        recording_set.labels_folder,
        recording_set.probe(),
        [detector],
        STARTED_AT,
    )

    assert [e.subject for e in result.validation.errors] == ["a.toml"]
    assert result.scorecard is None
    assert result.scorecard_path is None
    assert detector.seen == []
    assert not (recording_set.data_folder / "runs").exists()


def test_run_command_prints_the_scorecard_as_a_table_and_reports_errors(
    recording_set: RecordingSet, monkeypatch: pytest.MonkeyPatch, log: list[str]
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 7200.0, [("00:01:00", "00:03:00")])
    detector = FakeDetector(
        "fake", {"a.mp4": [(62.0, 179.0), (900.0, 930.0)], "b.mp4": "tool exited 1"}
    )
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(recording_set.data_folder))
    monkeypatch.setattr(settings, "RECORDING_LIST", recording_set.recording_list)
    monkeypatch.setattr(settings, "LABELS_FOLDER", recording_set.labels_folder)
    monkeypatch.setattr(cli, "Ffprobe", recording_set.probe)
    monkeypatch.setattr(
        cli, "look_ahead_detectors", lambda data_folder, rerun: [detector]
    )

    exit_code = main(["run"])

    assert exit_code == 1
    saved = sorted((recording_set.data_folder / "runs").glob("*/scorecard.json"))
    assert len(saved) == 1
    table = [line.removeprefix("INFO ") for line in log if line.startswith("INFO ")]
    assert "Scored 2 recordings: 3.0 hours, 2 labeled commercial breaks" in table
    assert f"Saved the scorecard to {saved[0]}" in table
    assert "fake (look-ahead)" in table
    rows = {
        cells[0]: cells[1:]
        for cells in (re.split(r" {2,}", line) for line in table)
        if len(cells) > 1
    }
    assert rows == {
        "Measure": ["Overall", "a.mp4", "b.mp4"],
        "Missed commercial breaks": ["0 of 1", "0 of 1", "error"],
        "False flips per hour": ["1.00 in 1.0 h", "1.00 in 1.0 h", "error"],
        "Start offset, median size": ["2.0 s (1)", "2.0 s (1)", "error"],
        "Start offset, 95th percentile size": ["2.0 s (1)", "2.0 s (1)", "error"],
        "Start offset, median": ["+2.0 s (1)", "+2.0 s (1)", "error"],
        "End offset, median size": ["1.0 s (1)", "1.0 s (1)", "error"],
        "End offset, 95th percentile size": ["1.0 s (1)", "1.0 s (1)", "error"],
        "End offset, median": ["-1.0 s (1)", "-1.0 s (1)", "error"],
    }
    assert "ERROR fake on b.mp4: tool exited 1" in log


def test_run_command_stops_when_the_recording_set_has_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log: list[str]
) -> None:
    missing = tmp_path / "elsewhere"
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(missing))

    exit_code = main(["run"])

    assert exit_code == 1
    assert f"ERROR {missing}: data folder does not exist" in log
    assert "ERROR Fix the errors above before running the benchmark." in log
    assert not missing.exists()
