"""The media probe: asks ffprobe what tracks a recording has and how long it is."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ProbeResult:
    """What the media probe reports about one recording."""

    has_video: bool
    has_audio: bool
    length_seconds: float


class ProbeError(Exception):
    """The media probe could not read a recording."""


class MediaProbe(Protocol):
    """Anything that can report a recording's tracks and length."""

    def probe(self, path: Path) -> ProbeResult:
        """Return the tracks and length of the recording at ``path``.

        Parameters
        ----------
        path : Path
            The recording to probe.

        Returns
        -------
        ProbeResult
            Whether it has a video and an audio track, and its length.

        Raises
        ------
        ProbeError
            If the recording cannot be read.
        """
        ...


class Ffprobe:
    """Media probe backed by the ``ffprobe`` command.

    Parameters
    ----------
    command : str
        The ffprobe executable to run.
    """

    def __init__(self, command: str = "ffprobe") -> None:
        self.command = command

    def probe(self, path: Path) -> ProbeResult:
        """Return the tracks and length of the recording at ``path``.

        Parameters
        ----------
        path : Path
            The recording to probe.

        Returns
        -------
        ProbeResult
            Whether it has a video and an audio track, and its length.

        Raises
        ------
        ProbeError
            If ffprobe is missing, fails, or reports no length.
        """
        try:
            completed = subprocess.run(
                [
                    self.command,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type:format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise ProbeError(f"{self.command} not found") from e
        if completed.returncode != 0:
            raise ProbeError(completed.stderr.strip() or f"exit {completed.returncode}")

        try:
            info = json.loads(completed.stdout)
            length_seconds = float(info["format"]["duration"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise ProbeError(f"could not read the length from ffprobe: {e}") from e
        codec_types = {stream.get("codec_type") for stream in info.get("streams", [])}
        return ProbeResult(
            has_video="video" in codec_types,
            has_audio="audio" in codec_types,
            length_seconds=length_seconds,
        )
