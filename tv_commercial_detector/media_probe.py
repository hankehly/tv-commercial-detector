"""The media probe: asks ffprobe what tracks a recording has and how long it is."""

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ProbeResult:
    """What the media probe reports about one recording.

    ``frame_rate`` is the video's frames per second, or ``None`` when the probe
    can't tell.
    """

    has_video: bool
    has_audio: bool
    length_seconds: float
    frame_rate: float | None = None


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
    """Media probe backed by the ``ffprobe`` command on the PATH."""

    def probe(self, path: Path) -> ProbeResult:
        """Return the tracks and length of the recording at ``path``.

        Parameters
        ----------
        path : Path
            The recording to probe.

        Returns
        -------
        ProbeResult
            Whether it has a video and an audio track, its length, and the
            video's average frame rate.

        Raises
        ------
        ProbeError
            If ffprobe is missing, fails, or reports no length.
        """
        try:
            completed = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,avg_frame_rate:format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise ProbeError("ffprobe not found on the PATH") from e
        if completed.returncode != 0:
            raise ProbeError(completed.stderr.strip() or f"exit {completed.returncode}")

        try:
            info = json.loads(completed.stdout)
            length_seconds = float(info["format"]["duration"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise ProbeError(f"could not read the length from ffprobe: {e}") from e
        streams = info.get("streams", [])
        codec_types = {stream.get("codec_type") for stream in streams}
        video = [s for s in streams if s.get("codec_type") == "video"]
        return ProbeResult(
            has_video="video" in codec_types,
            has_audio="audio" in codec_types,
            length_seconds=length_seconds,
            frame_rate=_frame_rate(video[0].get("avg_frame_rate")) if video else None,
        )


def _frame_rate(value: object) -> float | None:
    """Read a frame rate as ffprobe writes it, such as ``30000/1001``.

    Parameters
    ----------
    value : object
        The ``avg_frame_rate`` ffprobe gave for the video stream.

    Returns
    -------
    float | None
        The frames per second, or ``None`` if ffprobe couldn't tell, which it
        writes as ``0/0``.
    """
    if not isinstance(value, str):
        return None
    try:
        frames, _, seconds = value.partition("/")
        rate = float(frames) / float(seconds or 1)
    except ValueError, ZeroDivisionError:
        return None
    return rate if math.isfinite(rate) and rate > 0 else None
