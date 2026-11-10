"""Tests for the Comskip adapter, fed real output saved from running Comskip.

A stand-in takes Comskip's place: called with Comskip's arguments, it writes the
``.txt`` file scripted for the recording where Comskip would, and exits with
the scripted code. The scripted files in ``fixtures/comskip/`` are real
Comskip 0.83.001 output, with its default detection settings:

- ``no-breaks.txt``: the 89-minute pilot recording ``2026-11-01_17-01-22.mp4``,
  in which Comskip found no commercial breaks and exited with code 1.
- ``break-in-the-middle.txt``: a 10-minute recording made by joining a
  3-minute stretch of program, a 4-minute stretch of commercial break and the
  same stretch of program again. Comskip exited with code 0.
- ``break-to-the-end.txt``: the 4-minute stretch of commercial break on its
  own, which Comskip found to be one commercial break from its second frame to
  its last. Comskip exited with code 0.
"""

import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from recording_sets import RecordingSet

from tv_commercial_detector import cli, settings
from tv_commercial_detector.cli import main
from tv_commercial_detector.comskip import ComskipAdapter
from tv_commercial_detector.detectors import (
    DetectorError,
    Recording,
)
from tv_commercial_detector.external_tool import ExternalTool
from tv_commercial_detector.settings import (
    COMSKIP_COMMAND_VARIABLE,
    DATA_FOLDER_VARIABLE,
)

FIXTURES = Path(__file__).parent / "fixtures" / "comskip"

STAND_IN = """\
import json
import shlex
import sys
from pathlib import Path

answers = Path({answers!r})
arguments = sys.argv[1:]
with (answers / "calls.jsonl").open("a") as f:
    f.write(json.dumps(arguments) + "\\n")
output = Path(next(a for a in arguments if a.startswith("--output=")).split("=", 1)[1])
recording = Path(arguments[-1])
answer = answers / (recording.name + ".txt")
if answer.exists():
    (output / (recording.stem + ".txt")).write_bytes(answer.read_bytes())
exit_code = answers / (recording.name + ".exit")
if exit_code.exists():
    sys.stderr.write("stand-in: exiting as scripted\\n")
    sys.exit(int(exit_code.read_text()))
"""


@dataclass
class StandIn:
    """A stand-in for Comskip and the answers it gives."""

    folder: Path
    data_folder: Path

    @property
    def command(self) -> list[str]:
        """The command that runs the stand-in."""
        return [sys.executable, str(self.folder / "stand_in.py")]

    def answer(self, recording: str, output: str | bytes, exit_code: int) -> None:
        """Script the ``.txt`` file the stand-in writes for a recording, and its exit.

        Parameters
        ----------
        recording : str
            The recording's file name.
        output : str | bytes
            The ``.txt`` file's content.
        exit_code : int
            The code the stand-in exits with.
        """
        content = output.encode() if isinstance(output, str) else output
        (self.folder / f"{recording}.txt").write_bytes(content)
        (self.folder / f"{recording}.exit").write_text(str(exit_code))

    def answer_with_fixture(self, recording: str, fixture: str, exit_code: int) -> None:
        """Script one of the saved real Comskip outputs for a recording.

        Parameters
        ----------
        recording : str
            The recording's file name.
        fixture : str
            The fixture's file name in ``fixtures/comskip/``.
        exit_code : int
            The code Comskip exited with when it wrote that output.
        """
        self.answer(recording, (FIXTURES / fixture).read_bytes(), exit_code)

    def fail(self, recording: str, exit_code: int) -> None:
        """Script the stand-in to exit with a code and write no ``.txt`` file.

        Parameters
        ----------
        recording : str
            The recording's file name.
        exit_code : int
            The code it exits with.
        """
        (self.folder / f"{recording}.exit").write_text(str(exit_code))

    @property
    def calls(self) -> list[list[str]]:
        """The arguments of each call to the stand-in, in order."""
        log = self.folder / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def analyze(self, name: str, rerun: bool = False) -> list[tuple[float, float]]:
        """Run the Comskip detector on a placeholder recording.

        Parameters
        ----------
        name : str
            The recording's file name.
        rerun : bool
            Whether to analyze afresh instead of reusing saved output.

        Returns
        -------
        list[tuple[float, float]]
            The start and end, in seconds, of each commercial break found.
        """
        path = self.data_folder / "recordings" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        detector = ExternalTool(
            name="comskip",
            command=self.command,
            adapter=ComskipAdapter(),
            data_folder=self.data_folder,
            rerun=rerun,
        )
        report = detector.analyze(
            Recording(
                path=path,
                fingerprint="0" * 64,
                length_seconds=3600.0,
                channel="NTV",
                frame_rate=30000 / 1001,
            )
        )
        return [(b.start_seconds, b.end_seconds) for b in report.commercial_breaks]


@pytest.fixture
def comskip(tmp_path: Path) -> StandIn:
    """Return a stand-in for Comskip with no answers scripted yet."""
    folder = tmp_path / "stand-in"
    folder.mkdir()
    (folder / "stand_in.py").write_text(STAND_IN.format(answers=str(folder)))
    return StandIn(folder, tmp_path / "data")


def test_a_commercial_break_in_the_middle_is_turned_into_seconds(
    comskip: StandIn,
) -> None:
    # Comskip numbers the frame at 0 s as frame 1, so frames 5738 and 11282 at
    # the 29.97 fps it reports are 5737 / 29.97 s and 11281 / 29.97 s. The
    # pair after it, 17980 to 17981, only marks the last frame.
    comskip.answer_with_fixture("a.mp4", "break-in-the-middle.txt", exit_code=0)

    breaks = comskip.analyze("a.mp4")

    assert breaks == [
        (pytest.approx(191.4247, abs=1e-4), pytest.approx(376.4097, abs=1e-4))
    ]


def test_no_commercial_breaks_found_is_a_result_not_an_error(
    comskip: StandIn,
) -> None:
    # Comskip exits with code 1 when it finds none; its only pair, 160094 to
    # 160095, marks the last frame.
    comskip.answer_with_fixture("a.mp4", "no-breaks.txt", exit_code=1)

    assert comskip.analyze("a.mp4") == []


def test_empty_output_is_an_error(comskip: StandIn) -> None:
    comskip.answer("a.mp4", "", exit_code=0)

    with pytest.raises(DetectorError) as error:
        comskip.analyze("a.mp4")

    assert str(error.value) == "could not read the output of comskip: a.txt is empty"


@pytest.mark.parametrize(
    ("output", "reason"),
    [
        (
            "Commercials were not found.\n",
            "line 1 of a.txt isn't Comskip's FILE PROCESSING COMPLETE line: "
            "'Commercials were not found.'",
        ),
        (
            "FILE PROCESSING COMPLETE 17981 FRAMES AT  2997\n",
            "a.txt stops before its dashed line",
        ),
        (
            "FILE PROCESSING COMPLETE 17981 FRAMES AT  2997\n5738\t11282\n",
            "line 2 of a.txt isn't Comskip's dashed line: '5738\\t11282'",
        ),
        (
            "FILE PROCESSING COMPLETE 17981 FRAMES AT  2997\n"
            "-------------------\n5738 to 11282\n",
            "line 3 of a.txt isn't a pair of frame numbers: '5738 to 11282'",
        ),
    ],
    ids=["no header", "no dashed line", "pair for dashed line", "bad pair"],
)
def test_malformed_output_is_an_error(
    comskip: StandIn, output: str, reason: str
) -> None:
    comskip.answer("a.mp4", output, exit_code=0)

    with pytest.raises(DetectorError) as error:
        comskip.analyze("a.mp4")

    assert str(error.value) == f"could not read the output of comskip: {reason}"


def test_a_commercial_break_running_to_the_end_is_kept(comskip: StandIn) -> None:
    # It ends on the last frame, 7181, so Comskip adds no pair to mark it.
    # Frames 2 and 7181 are 1 / 29.97 s and 7180 / 29.97 s.
    comskip.answer_with_fixture("a.mp4", "break-to-the-end.txt", exit_code=0)

    breaks = comskip.analyze("a.mp4")

    assert breaks == [
        (pytest.approx(0.0334, abs=1e-4), pytest.approx(239.5729, abs=1e-4))
    ]


def test_a_recording_comskip_cannot_open_is_an_error(comskip: StandIn) -> None:
    # Comskip exits with 255 and leaves its .txt file empty.
    comskip.answer("a.mp4", "", exit_code=255)

    with pytest.raises(DetectorError) as error:
        comskip.analyze("a.mp4")

    assert str(error.value) == (
        "comskip exited with code 255: stand-in: exiting as scripted"
    )


def test_comskip_is_given_only_where_to_write_and_the_recording(
    comskip: StandIn,
) -> None:
    # Its default detection settings, in its normal whole-recording mode.
    comskip.answer_with_fixture("a.mp4", "no-breaks.txt", exit_code=1)

    comskip.analyze("a.mp4")

    output_folder = comskip.data_folder / "tool-output" / "comskip" / "a"
    recording = comskip.data_folder / "recordings" / "a.mp4"
    assert comskip.calls == [[f"--output={output_folder}", str(recording)]]


def test_run_scores_comskip_with_the_command_its_setting_names(
    recording_set: RecordingSet,
    comskip: StandIn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Comskip found 191.4247 s to 376.4097 s in a.mp4, labeled 180 s to 360 s,
    # and nothing in b.mp4, which has no commercial breaks. The scorecard keeps
    # offsets to the millisecond.
    recording_set.add("a.mp4", 600.0, [("00:03:00", "00:06:00")])
    recording_set.add("b.mp4", 600.0, [])
    comskip.answer_with_fixture("a.mp4", "break-in-the-middle.txt", exit_code=0)
    comskip.answer_with_fixture("b.mp4", "no-breaks.txt", exit_code=1)
    monkeypatch.setenv(COMSKIP_COMMAND_VARIABLE, shlex.join(comskip.command))
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(recording_set.data_folder))
    monkeypatch.setattr(settings, "RECORDING_LIST", recording_set.recording_list)
    monkeypatch.setattr(settings, "LABELS_FOLDER", recording_set.labels_folder)
    monkeypatch.setattr(cli, "Ffprobe", recording_set.probe)

    main(["run"])

    [saved] = (recording_set.data_folder / "runs").glob("*/scorecard.json")
    detectors = {d["name"]: d for d in json.loads(saved.read_text())["detectors"]}
    scored = detectors["comskip"]
    assert scored["kind"] == "look-ahead"
    assert scored["errors"] == {}
    a = scored["per_recording"]["a.mp4"]
    assert a["start_offset_median"]["value"] == 11.425
    assert a["end_offset_median"]["value"] == 16.41
    b = scored["per_recording"]["b.mp4"]
    assert b["false_flips_per_hour"]["value"] == 0.0
