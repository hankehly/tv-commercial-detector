"""Tests for look-ahead detectors that run an external tool, driven through ``run``.

Each test puts a stand-in command in place of a real tool: a small Python
script that answers with output scripted per recording, writes nothing for a
recording with no answer scripted, or fails when told to, and notes each
recording it is run on. A stand-in adapter says how to call it
and how to read its output, which lists commercial breaks in frames, one
``start end`` pair per line, after an optional ``fps <rate>`` line.
"""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from recording_sets import RecordingSet

from tv_commercial_detector import cli, settings
from tv_commercial_detector.cli import main
from tv_commercial_detector.detectors import DetectorError, Recording
from tv_commercial_detector.external_tool import (
    ExternalTool,
    OutputError,
    ToolOutput,
)
from tv_commercial_detector.settings import DATA_FOLDER_VARIABLE

STAND_IN = """\
import shutil
import sys
from pathlib import Path

recording, output_folder = Path(sys.argv[-2]), Path(sys.argv[-1])
answers = Path({answers!r})
with (answers / "calls.log").open("a") as f:
    f.write(recording.name + "\\n")
exit_code = answers / (recording.name + ".exit")
if exit_code.exists():
    sys.stderr.write("stand-in: could not open the recording\\n")
    sys.exit(int(exit_code.read_text()))
answer = answers / recording.name
if answer.exists():
    (output_folder / "breaks.txt").write_bytes(answer.read_bytes())
"""


class StandInAdapter:
    """Says how to call the stand-in and how to read its output."""

    def arguments(self, recording: Recording, output_folder: Path) -> list[str]:
        """Return the stand-in's arguments: the recording, then the output folder.

        Parameters
        ----------
        recording : Recording
            The recording to analyze.
        output_folder : Path
            Where the stand-in writes its output.

        Returns
        -------
        list[str]
            The arguments.
        """
        return [str(recording.path), str(output_folder)]

    def read_output(self, recording: Recording, output_folder: Path) -> ToolOutput:
        """Read the commercial breaks, in frames, from ``breaks.txt``.

        Parameters
        ----------
        recording : Recording
            The recording the stand-in analyzed; unused.
        output_folder : Path
            The folder the stand-in wrote to.

        Returns
        -------
        ToolOutput
            The commercial breaks in frames and the frame rate, if given.

        Raises
        ------
        OutputError
            If a line isn't a frame rate or a pair of frame numbers.
        """
        frame_rate = None
        commercial_breaks = []
        for line in (output_folder / "breaks.txt").read_text().splitlines():
            try:
                if line.startswith("fps "):
                    frame_rate = float(line.removeprefix("fps "))
                else:
                    start, end = line.split()
                    commercial_breaks.append((int(start), int(end)))
            except ValueError as e:
                raise OutputError(f"bad line {line!r}") from e
        return ToolOutput(tuple(commercial_breaks), frame_rate)


@dataclass
class StandIn:
    """A stand-in tool and the answers it gives, kept outside the data folder."""

    folder: Path

    @property
    def command(self) -> list[str]:
        """The command that runs the stand-in."""
        return [sys.executable, str(self.folder / "stand_in.py")]

    def answer(self, recording: str, output: str | bytes) -> None:
        """Script the output the stand-in writes for a recording.

        Parameters
        ----------
        recording : str
            The recording's file name.
        output : str | bytes
            The content of the output file.
        """
        content = output.encode() if isinstance(output, str) else output
        (self.folder / recording).write_bytes(content)

    def fail(self, recording: str, exit_code: int) -> None:
        """Script the stand-in to fail on a recording.

        Parameters
        ----------
        recording : str
            The recording's file name.
        exit_code : int
            The exit code it fails with.
        """
        (self.folder / f"{recording}.exit").write_text(str(exit_code))

    @property
    def calls(self) -> list[str]:
        """The file names of the recordings the stand-in was run on, in order."""
        log = self.folder / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def detector(
        self,
        data_folder: Path,
        command: list[str] | None = None,
        rerun: bool = False,
    ) -> ExternalTool:
        """Return a look-ahead detector that runs the stand-in.

        Parameters
        ----------
        data_folder : Path
            The data folder, where the detector saves the stand-in's output.
        command : list[str] | None
            The command to run; the stand-in's own when ``None``.
        rerun : bool
            Whether to analyze afresh instead of reusing saved output.

        Returns
        -------
        ExternalTool
            The detector, named ``stand-in``.
        """
        return ExternalTool(
            name="stand-in",
            command=self.command if command is None else command,
            adapter=StandInAdapter(),
            data_folder=data_folder,
            rerun=rerun,
        )


@pytest.fixture
def stand_in(tmp_path: Path) -> StandIn:
    """Return a stand-in tool with no answers scripted yet."""
    folder = tmp_path / "stand-in"
    folder.mkdir()
    (folder / "stand_in.py").write_text(STAND_IN.format(answers=str(folder)))
    return StandIn(folder)


def offsets(scorecard: dict, recording: str) -> tuple[float, float]:
    """Return a recording's median signed start and end offsets for the only detector.

    Parameters
    ----------
    scorecard : dict
        The saved scorecard.
    recording : str
        The recording's file name.

    Returns
    -------
    tuple[float, float]
        The median start offset and median end offset, in seconds.
    """
    [scored] = scorecard["detectors"]
    measures = scored["per_recording"][recording]
    return (
        measures["start_offset_median"]["value"],
        measures["end_offset_median"]["value"],
    )


def test_frames_are_converted_with_the_frame_rate_the_tool_reports_and_output_saved(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    # 1860 and 5340 frames at 30 fps are 62 s and 178 s, against labels of
    # 60 s and 180 s; the probe's 25 fps is ignored when the tool reports one.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")], frame_rate=25.0)
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    assert scorecard["detectors"][0]["errors"] == {}
    assert offsets(scorecard, "a.mp4") == (2.0, -2.0)
    saved = recording_set.data_folder / "tool-output" / "stand-in" / "a" / "breaks.txt"
    assert saved.read_text() == "fps 30\n1860 5340\n"


def test_frames_are_converted_with_the_probed_frame_rate_when_the_tool_reports_none(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    # 1550 and 4450 frames at the probed 25 fps are 62 s and 178 s.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")], frame_rate=25.0)
    stand_in.answer("a.mp4", "1550 4450\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    assert scorecard["detectors"][0]["errors"] == {}
    assert offsets(scorecard, "a.mp4") == (2.0, -2.0)


def test_frames_without_a_frame_rate_from_the_tool_or_the_probe_are_an_error(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "1550 4450\n")
    stand_in.answer("b.mp4", "fps 25\n1550 4450\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {
        "a.mp4": "stand-in reported frames but no frame rate, and the media probe "
        "found none"
    }
    assert offsets(scorecard, "b.mp4") == (2.0, -2.0)


def test_saved_output_is_reused_on_a_second_run(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    recording_set.run(stand_in.detector(recording_set.data_folder))
    stand_in.answer("a.mp4", "fps 30\n1800 5400\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    assert stand_in.calls == ["a.mp4"]
    assert offsets(scorecard, "a.mp4") == (2.0, -2.0)


def test_saved_output_is_not_reused_when_the_command_changes(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    recording_set.run(stand_in.detector(recording_set.data_folder))
    stand_in.answer("a.mp4", "fps 30\n1800 5400\n")
    changed = [*stand_in.command, "--some-option"]

    scorecard = recording_set.run(
        stand_in.detector(recording_set.data_folder, command=changed)
    )

    assert stand_in.calls == ["a.mp4", "a.mp4"]
    assert offsets(scorecard, "a.mp4") == (0.0, 0.0)


def test_saved_output_is_not_reused_when_the_recording_changes(
    tmp_path: Path, stand_in: StandIn
) -> None:
    before = RecordingSet(tmp_path / "before")
    before.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    before.run(stand_in.detector(before.data_folder))
    # The same file name, re-recorded: new content, so a new fingerprint, with
    # the first recording's saved output alongside it.
    after = RecordingSet(tmp_path / "after")
    after.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")], content=b"re-recorded")
    shutil.copytree(
        before.data_folder / "tool-output", after.data_folder / "tool-output"
    )
    stand_in.answer("a.mp4", "fps 30\n1800 5400\n")

    scorecard = after.run(stand_in.detector(after.data_folder))

    assert stand_in.calls == ["a.mp4", "a.mp4"]
    assert offsets(scorecard, "a.mp4") == (0.0, 0.0)


def test_saved_output_moves_with_the_data_folder(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    recording_set.run(stand_in.detector(recording_set.data_folder))
    moved = recording_set.root / "external-drive"
    recording_set.data_folder.rename(moved)
    recording_set.data_folder_name = moved.name

    scorecard = recording_set.run(stand_in.detector(moved))

    assert stand_in.calls == ["a.mp4"]
    assert offsets(scorecard, "a.mp4") == (2.0, -2.0)


def test_saved_output_is_not_reused_when_asked_to_rerun(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    recording_set.run(stand_in.detector(recording_set.data_folder))
    stand_in.answer("a.mp4", "fps 30\n1800 5400\n")

    scorecard = recording_set.run(
        stand_in.detector(recording_set.data_folder, rerun=True)
    )

    assert stand_in.calls == ["a.mp4", "a.mp4"]
    assert offsets(scorecard, "a.mp4") == (0.0, 0.0)


def test_a_missing_command_is_an_error_on_each_recording_and_the_run_carries_on(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    missing = stand_in.detector(
        recording_set.data_folder, command=["no-such-tool-for-tests", "--flag"]
    )

    scorecard = recording_set.run(missing)

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {
        "a.mp4": "command not found: no-such-tool-for-tests",
        "b.mp4": "command not found: no-such-tool-for-tests",
    }
    assert scored["per_recording"] == {}


def test_a_non_zero_exit_is_an_error_there_and_is_tried_again_next_run(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.fail("a.mp4", exit_code=3)
    stand_in.answer("b.mp4", "fps 30\n1860 5340\n")

    first = recording_set.run(stand_in.detector(recording_set.data_folder))
    second = recording_set.run(stand_in.detector(recording_set.data_folder))

    [scored] = first["detectors"]
    assert scored["errors"] == {
        "a.mp4": "stand-in exited with code 3: stand-in: could not open the recording"
    }
    assert offsets(first, "b.mp4") == (2.0, -2.0)
    assert second["detectors"][0]["errors"] == scored["errors"]
    assert stand_in.calls == ["a.mp4", "b.mp4", "a.mp4"]


def test_output_that_cannot_be_read_is_an_error_there_and_the_run_carries_on(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 to 5340\n")
    stand_in.answer("b.mp4", "fps 30\n1860 5340\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    [scored] = scorecard["detectors"]
    assert scored["errors"] == {
        "a.mp4": "could not read the output of stand-in: bad line '1860 to 5340'"
    }
    assert offsets(scorecard, "b.mp4") == (2.0, -2.0)


def test_output_that_cannot_be_read_is_kept_and_read_again_without_rerunning(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    # The tool finished, so its output is reused: rerunning hours of analysis
    # wouldn't change it, while a fixed adapter can read it again.
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 to 5340\n")
    first = recording_set.run(stand_in.detector(recording_set.data_folder))

    second = recording_set.run(stand_in.detector(recording_set.data_folder))

    assert stand_in.calls == ["a.mp4"]
    assert second["detectors"][0]["errors"] == first["detectors"][0]["errors"]


def test_output_that_is_not_text_is_an_error(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", b"fps 30\n\xff\xfe\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    [error] = scorecard["detectors"][0]["errors"].values()
    assert error.startswith("could not read the output of stand-in: 'utf-8' codec")


def test_a_tool_that_cannot_be_called_keeps_the_output_saved_earlier(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    recording_set.run(stand_in.detector(recording_set.data_folder))

    class MissingFile(StandInAdapter):
        def arguments(self, recording: Recording, output_folder: Path) -> list[str]:
            raise DetectorError("a file the tool needs is missing")

    detector = ExternalTool(
        name="stand-in",
        command=stand_in.command,
        adapter=MissingFile(),
        data_folder=recording_set.data_folder,
        rerun=True,
    )

    scorecard = recording_set.run(detector)

    assert scorecard["detectors"][0]["errors"] == {
        "a.mp4": "a file the tool needs is missing"
    }
    saved = recording_set.data_folder / "tool-output" / "stand-in" / "a" / "breaks.txt"
    assert saved.read_text() == "fps 30\n1860 5340\n"


def test_missing_output_is_an_error(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    [error] = scorecard["detectors"][0]["errors"].values()
    assert error.startswith("could not read the output of stand-in: ")
    assert "breaks.txt" in error


def test_a_frame_rate_that_is_not_a_positive_number_is_an_error(
    recording_set: RecordingSet, stand_in: StandIn
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")], frame_rate=30.0)
    recording_set.add("b.mp4", 3600.0, [("00:01:00", "00:03:00")], frame_rate=30.0)
    stand_in.answer("a.mp4", "fps 0\n1860 5340\n")
    stand_in.answer("b.mp4", "fps nan\n1860 5340\n")

    scorecard = recording_set.run(stand_in.detector(recording_set.data_folder))

    assert scorecard["detectors"][0]["errors"] == {
        "a.mp4": "stand-in reported a frame rate of 0.0, which isn't a positive number",
        "b.mp4": "stand-in reported a frame rate of nan, which isn't a positive number",
    }


def test_run_command_reuses_saved_output_unless_given_the_rerun_option(
    recording_set: RecordingSet,
    stand_in: StandIn,
    monkeypatch: pytest.MonkeyPatch,
    log: list[str],
) -> None:
    recording_set.add("a.mp4", 3600.0, [("00:01:00", "00:03:00")])
    stand_in.answer("a.mp4", "fps 30\n1860 5340\n")
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(recording_set.data_folder))
    monkeypatch.setattr(settings, "RECORDING_LIST", recording_set.recording_list)
    monkeypatch.setattr(settings, "LABELS_FOLDER", recording_set.labels_folder)
    monkeypatch.setattr(cli, "Ffprobe", recording_set.probe)
    monkeypatch.setattr(
        cli,
        "look_ahead_detectors",
        lambda data_folder, rerun: [stand_in.detector(data_folder, rerun=rerun)],
    )

    exit_codes = [main(["run"]), main(["run"]), main(["run", "--rerun"])]

    assert exit_codes == [0, 0, 0]
    assert stand_in.calls == ["a.mp4", "a.mp4"]
    assert log.count("INFO stand-in: analyzing a.mp4") == 2
    assert log.count("INFO stand-in: reusing saved output for a.mp4") == 1
