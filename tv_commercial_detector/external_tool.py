"""Look-ahead detectors that run an external tool, such as Comskip or join_logo_scp.

An :class:`ExternalTool` does the work every such tool shares: it runs the
tool's configured command on a recording, keeps the raw output in the data
folder, and turns the commercial breaks the tool found, in frames, into seconds.
A :class:`ToolAdapter` says only how to call one tool and how to read its output.
"""

import json
import math
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from loguru import logger

from tv_commercial_detector.detectors import (
    DetectorError,
    DetectorKind,
    LookAheadReport,
    Recording,
    ReportedCommercialBreak,
)

TOOL_OUTPUT_FOLDER = "tool-output"
"""The data folder's folder of saved tool output, one folder per tool inside it."""

STDOUT_FILE_NAME = "stdout.log"
"""The file, among a recording's saved output, holding what the tool printed."""

STDERR_FILE_NAME = "stderr.log"
"""The file, among a recording's saved output, holding the tool's error output."""

SOURCE_FILE_NAME = "source.json"
"""The file, among a recording's saved output, naming what the output came from.

It holds the recording's fingerprint and the tool's command, and nothing that
depends on where the data folder is, so saved output moves with the recordings.
"""


@dataclass(frozen=True)
class ToolOutput:
    """What an adapter read from a tool's output.

    ``commercial_breaks`` holds each commercial break's start and end in frames
    from the start of the recording; ``frame_rate`` is the frames per second the
    tool reported, or ``None`` if it reported none.
    """

    commercial_breaks: tuple[tuple[float, float], ...]
    frame_rate: float | None = None


class OutputError(Exception):
    """A tool's output can't be read; the message says why."""


class ToolAdapter(Protocol):
    """How to call one external tool and how to read what it wrote."""

    accepted_exit_codes: frozenset[int]
    """The non-zero exit codes after which the tool's output is still read.

    0 is always accepted; any code not here is an error. Most tools need only
    0. A tool that reports what it found through its exit
    code, as Comskip exits with 1 when it finds no commercial breaks, names
    those codes too.
    """

    def arguments(self, recording: Recording, output_folder: Path) -> list[str]:
        """Return the arguments that follow the tool's command.

        Parameters
        ----------
        recording : Recording
            The recording to analyze, with an absolute path.
        output_folder : Path
            The absolute path of the folder the tool must write its output to.
            It is emptied, or
            created, after this returns, and the tool runs with it as its
            working folder.

        Returns
        -------
        list[str]
            The arguments.

        Raises
        ------
        DetectorError
            If the tool can't be run on this recording, for example because a
            file it needs is missing.
        """
        ...

    def read_output(self, recording: Recording, output_folder: Path) -> ToolOutput:
        """Read the commercial breaks the tool found from its output.

        Parameters
        ----------
        recording : Recording
            The recording the tool analyzed, for output that needs its
            length, such as a list of the parts to keep.
        output_folder : Path
            The folder the tool wrote its output to.

        Returns
        -------
        ToolOutput
            The commercial breaks in frames, and the frame rate if the tool
            reported one.

        Raises
        ------
        OutputError
            If the output can't be read.
        OSError
            If an output file is missing or can't be opened.
        UnicodeDecodeError
            If an output file isn't text in the expected encoding.

        Any other exception is a bug in the adapter and stops the run.
        """
        ...


class ExternalTool:
    """A look-ahead detector that runs an external tool on each recording.

    The tool's raw output is kept in ``tool-output/<name>/<recording>/`` inside
    the data folder, where ``<recording>`` is the recording's file name without
    its extension.

    Parameters
    ----------
    name : str
        The detector's name in the scorecard, which also names its folder of
        saved output.
    command : list[str]
        The configured command that runs the tool, before its arguments.
    adapter : ToolAdapter
        How to call the tool and read its output.
    data_folder : Path
        The data folder.
    rerun : bool
        Whether to analyze every recording afresh instead of reusing saved
        output.
    """

    kind = DetectorKind.LOOK_AHEAD

    def __init__(
        self,
        name: str,
        command: list[str],
        adapter: ToolAdapter,
        data_folder: Path,
        rerun: bool = False,
    ) -> None:
        self.name = name
        self.command = command
        self.adapter = adapter
        self.data_folder = data_folder
        self.rerun = rerun

    def analyze(self, recording: Recording) -> LookAheadReport:
        """Run the tool on a recording and return the commercial breaks it found.

        Parameters
        ----------
        recording : Recording
            The recording to analyze.

        Returns
        -------
        LookAheadReport
            The commercial breaks found, in seconds.

        Raises
        ------
        DetectorError
            If the tool can't be called on the recording, its command is
            missing or exits with an error, or its output can't be read or
            turned into seconds. Output from a command that exited with an
            error isn't reused, so the next run tries again; output that exited
            cleanly is reused even if it can't be read, so a fixed adapter can
            read it again without rerunning the tool. Output after a non-zero
            exit code the adapter accepts is reused only once it has been read,
            since a wrapper that couldn't start the tool may exit with the
            same code.
        """
        # The tool runs inside its output folder, so it is given absolute
        # paths: ones relative to where the benchmark started would point
        # nowhere from there.
        recording = replace(recording, path=recording.path.absolute())
        folder = (
            self.data_folder / TOOL_OUTPUT_FOLDER / self.name / recording.path.stem
        ).absolute()
        source = {"fingerprint": recording.fingerprint, "command": self.command}
        accepted_exit = None
        if not self.rerun and _saved_source(folder) == source:
            logger.info(f"{self.name}: reusing saved output for {recording.path.name}")
        else:
            accepted_exit = self._run_tool(recording, folder)
            if accepted_exit is None:
                _save_source(folder, source)
        try:
            output = self.adapter.read_output(recording, folder)
        except (OutputError, OSError, UnicodeDecodeError) as e:
            if accepted_exit is None:
                raise DetectorError(
                    f"could not read the output of {self.name}: {e}"
                ) from e
            raise DetectorError(
                f"{accepted_exit}; could not read its output: {e}"
            ) from e
        if accepted_exit is not None:
            _save_source(folder, source)
        return self._in_seconds(output, recording)

    def _run_tool(self, recording: Recording, folder: Path) -> str | None:
        """Run the tool on a recording, into an emptied folder.

        Parameters
        ----------
        recording : Recording
            The recording to analyze.
        folder : Path
            The recording's folder of saved output for this tool. Once the
            adapter has given the tool's arguments, anything already in it is
            removed, so output saved earlier survives a tool that can't be
            called.

        Returns
        -------
        str | None
            ``None`` if the tool exited with 0; otherwise, for a non-zero exit
            code the adapter accepts, a message giving the code and the last
            line of the tool's error output.

        Raises
        ------
        DetectorError
            If the adapter can't give the tool's arguments, or the command
            can't be found or run, or exits with a code the adapter doesn't
            accept.
        """
        arguments = self.adapter.arguments(recording, folder)
        logger.info(f"{self.name}: analyzing {recording.path.name}")
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        stderr = folder / STDERR_FILE_NAME
        try:
            with (
                (folder / STDOUT_FILE_NAME).open("w") as out,
                stderr.open("w") as err,
            ):
                completed = subprocess.run(
                    [*_runnable(self.command), *arguments],
                    cwd=folder,
                    stdout=out,
                    stderr=err,
                    check=False,
                )
        except FileNotFoundError as e:
            raise DetectorError(f"command not found: {self.command[0]}") from e
        except OSError as e:
            raise DetectorError(f"could not run {self.command[0]}: {e}") from e
        if completed.returncode == 0:
            return None
        lines = stderr.read_text(errors="replace").strip().splitlines()
        reason = f": {lines[-1].strip()}" if lines else ""
        message = f"{self.name} exited with code {completed.returncode}{reason}"
        if completed.returncode not in self.adapter.accepted_exit_codes:
            raise DetectorError(message)
        return message

    def _in_seconds(self, output: ToolOutput, recording: Recording) -> LookAheadReport:
        """Turn the commercial breaks a tool found, in frames, into seconds.

        Parameters
        ----------
        output : ToolOutput
            What the adapter read from the tool's output.
        recording : Recording
            The recording, whose probed frame rate is used when the tool
            reports none.

        Returns
        -------
        LookAheadReport
            The commercial breaks, in seconds.

        Raises
        ------
        DetectorError
            If the tool reported a frame rate that isn't a positive number, or
            there are commercial breaks to convert but neither the tool nor the
            media probe gave a frame rate.
        """
        frame_rate = output.frame_rate
        if frame_rate is not None and not (
            math.isfinite(frame_rate) and frame_rate > 0
        ):
            raise DetectorError(
                f"{self.name} reported a frame rate of {frame_rate}, which isn't a "
                "positive number"
            )
        if frame_rate is None:
            frame_rate = recording.frame_rate
        if frame_rate is None:
            if not output.commercial_breaks:
                return LookAheadReport(())
            raise DetectorError(
                f"{self.name} reported frames but no frame rate, and the media "
                "probe found none"
            )
        return LookAheadReport(
            tuple(
                ReportedCommercialBreak(start / frame_rate, end / frame_rate)
                for start, end in output.commercial_breaks
            )
        )


def _saved_source(folder: Path) -> dict | None:
    """Return what a recording's saved output came from.

    Parameters
    ----------
    folder : Path
        The recording's folder of saved output for one tool.

    Returns
    -------
    dict | None
        The fingerprint and command the output came from, or ``None`` if
        nothing usable is saved there.
    """
    try:
        return json.loads((folder / SOURCE_FILE_NAME).read_text())
    except OSError, json.JSONDecodeError:
        return None


def _save_source(folder: Path, source: dict) -> None:
    """Note what a recording's saved output came from, so it can be reused.

    Parameters
    ----------
    folder : Path
        The recording's folder of saved output for one tool.
    source : dict
        The fingerprint and command the output came from.
    """
    (folder / SOURCE_FILE_NAME).write_text(json.dumps(source, indent=2) + "\n")


def _runnable(command: list[str]) -> list[str]:
    """Make a command's program findable from inside the tool's output folder.

    Parameters
    ----------
    command : list[str]
        The configured command, before its arguments.

    Returns
    -------
    list[str]
        The command with its program made absolute when it is a relative path
        with a folder in it, such as ``./tools/comskip-wrapper``, so it is
        found from where the run started. A bare name such as ``comskip`` is
        left for the PATH to find.
    """
    program, *rest = command
    if "/" in program:
        program = str(Path(program).absolute())
    return [program, *rest]
