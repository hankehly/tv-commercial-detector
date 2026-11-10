"""Comskip as a look-ahead detector.

Comskip runs in its normal whole-recording mode with its default detection
settings; only where it writes its output is set. It writes the commercial
breaks it found to a ``.txt`` file named after the recording::

    FILE PROCESSING COMPLETE 160095 FRAMES AT  2997
    -------------------
    5738	11282
    160094	160095

The first line gives the number of the recording's last frame and the frame
rate times 100, and each line after the dashed one gives a commercial break's
first and last frames.
"""

import re
from pathlib import Path

from tv_commercial_detector.detectors import Recording
from tv_commercial_detector.external_tool import OutputError, ToolOutput

HEADER = re.compile(r"FILE PROCESSING COMPLETE +(\d+) FRAMES AT +(\d+)")
"""The ``.txt`` file's first line: the last frame's number and the frame rate × 100."""

DASHES = re.compile(r"-+")
"""The ``.txt`` file's second line."""

PAIR = re.compile(r"(\d+)\t(\d+)")
"""A commercial break's line: its first and last frames, separated by a tab."""


class ComskipAdapter:
    """How to call Comskip and read the ``.txt`` file it writes."""

    accepted_exit_codes = frozenset({0, 1})
    """Comskip exits with 0 when it finds commercial breaks and 1 when it finds none.

    Both write a complete ``.txt`` file. Any other code, such as 255 when it
    can't open the recording, is an error.
    """

    def arguments(self, recording: Recording, output_folder: Path) -> list[str]:
        """Return Comskip's arguments: where to write its output, then the recording.

        Parameters
        ----------
        recording : Recording
            The recording to analyze.
        output_folder : Path
            The folder Comskip writes its output to.

        Returns
        -------
        list[str]
            The arguments.
        """
        return [f"--output={output_folder}", str(recording.path)]

    def read_output(self, recording: Recording, output_folder: Path) -> ToolOutput:
        """Read the commercial breaks from Comskip's ``.txt`` file.

        Comskip numbers the frame at 0 s as frame 1, so each frame number is
        turned into frames from the start of the recording by taking 1 off.
        Unless its last commercial break runs to the end, Comskip adds a pair
        covering only the recording's last frame, which marks the end rather
        than a commercial break, so it is left out.

        Parameters
        ----------
        recording : Recording
            The recording Comskip analyzed.
        output_folder : Path
            The folder Comskip wrote its output to.

        Returns
        -------
        ToolOutput
            The commercial breaks in frames from the start of the recording,
            and the frame rate Comskip reported.

        Raises
        ------
        OutputError
            If the file is empty or a line isn't what Comskip writes.
        OSError
            If the file is missing or can't be opened.
        UnicodeDecodeError
            If the file isn't text.
        """
        path = output_folder / f"{recording.path.stem}.txt"
        lines = path.read_text().splitlines()
        if not lines:
            raise OutputError(f"{path.name} is empty")
        header = HEADER.fullmatch(lines[0])
        if header is None:
            raise OutputError(
                f"line 1 of {path.name} isn't Comskip's FILE PROCESSING COMPLETE "
                f"line: {lines[0]!r}"
            )
        if len(lines) < 2:
            raise OutputError(f"{path.name} stops before its dashed line")
        if DASHES.fullmatch(lines[1]) is None:
            raise OutputError(
                f"line 2 of {path.name} isn't Comskip's dashed line: {lines[1]!r}"
            )
        last_frame = int(header.group(1))
        frame_rate = int(header.group(2)) / 100
        frames = []
        for number, line in enumerate(lines[2:], start=3):
            pair = PAIR.fullmatch(line)
            if pair is None:
                raise OutputError(
                    f"line {number} of {path.name} isn't a pair of frame numbers: "
                    f"{line!r}"
                )
            frames.append((int(pair.group(1)), int(pair.group(2))))
        if frames and frames[-1][1] == last_frame and frames[-1][0] >= last_frame - 1:
            frames.pop()
        return ToolOutput(
            tuple((start - 1, end - 1) for start, end in frames), frame_rate
        )
