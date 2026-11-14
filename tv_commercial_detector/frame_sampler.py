"""Sampling frames from recordings with ffmpeg, to measure a logo from."""

import subprocess
from pathlib import Path

import numpy as np
from loguru import logger

from tv_commercial_detector.logo_maker import CornerFrames, LogoError

CORNER_WIDTH = 512
"""The width, in pixels, of the sampled corner: the top right of the picture,
where Japanese channels show their logo."""

CORNER_HEIGHT = 256
"""The height, in pixels, of the sampled corner."""


def sample_corner(recordings: list[Path]) -> CornerFrames:
    """Sample the top right corner of the picture throughout some recordings.

    Only keyframes are read, which our recordings have every two seconds or
    so. That takes about a minute and a half for a three-hour recording, and gives
    thousands of frames spread over everything it shows.

    Parameters
    ----------
    recordings : list[Path]
        Recordings of one channel, all with the same picture size.

    Returns
    -------
    CornerFrames
        The corner's brightness in every sampled frame of every recording.

    Raises
    ------
    LogoError
        If ffprobe or ffmpeg is missing or can't read a recording, a recording
        has no frames, or the recordings' pictures differ in size.
    """
    sizes = {recording: _picture_size(recording) for recording in recordings}
    if len(set(sizes.values())) > 1:
        listed = ", ".join(f"{r.name} is {w}×{h}" for r, (w, h) in sizes.items())
        raise LogoError(f"the recordings' pictures differ in size: {listed}")
    picture_width, picture_height = next(iter(sizes.values()))
    width = min(CORNER_WIDTH, picture_width)
    height = min(CORNER_HEIGHT, picture_height)
    x = picture_width - width

    sampled = []
    for recording in recordings:
        logger.info(f"Sampling {recording} (about a minute and a half for three hours)")
        output = _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-skip_frame",
                "nokey",
                "-i",
                str(recording),
                "-an",
                "-vf",
                f"crop={width}:{height}:{x}:0,extractplanes=y",
                "-fps_mode",
                "passthrough",
                "-pix_fmt",
                "gray",
                "-f",
                "rawvideo",
                "-",
            ],
            recording,
        )
        frames = np.frombuffer(output, dtype=np.uint8)
        frames = frames[: len(frames) // (width * height) * width * height]
        if not len(frames):
            raise LogoError(f"{recording}: ffmpeg read no frames from it")
        sampled.append(frames.reshape(-1, height, width))
        logger.info(f"Sampled {len(sampled[-1])} frames")
    return CornerFrames(
        pixels=np.concatenate(sampled) if len(sampled) > 1 else sampled[0],
        x=x,
        y=0,
        picture_width=picture_width,
        picture_height=picture_height,
    )


def _picture_size(recording: Path) -> tuple[int, int]:
    """Ask ffprobe for the width and height of a recording's picture.

    Parameters
    ----------
    recording : Path
        The recording.

    Returns
    -------
    tuple[int, int]
        The picture's width and height, in pixels.

    Raises
    ------
    LogoError
        If ffprobe is missing, fails, or reports no picture size.
    """
    output = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(recording),
        ],
        recording,
    )
    try:
        width, height = (int(v) for v in output.decode().split()[0].split(",")[:2])
    except (IndexError, ValueError) as e:
        raise LogoError(f"{recording}: ffprobe found no picture in it") from e
    return width, height


def _run(command: list[str], recording: Path) -> bytes:
    """Run ffmpeg or ffprobe on a recording and return what it wrote.

    Parameters
    ----------
    command : list[str]
        The command and its arguments.
    recording : Path
        The recording, for error messages.

    Returns
    -------
    bytes
        The command's standard output.

    Raises
    ------
    LogoError
        If the command isn't on the PATH or exits with an error.
    """
    try:
        completed = subprocess.run(command, capture_output=True, check=False)
    except FileNotFoundError as e:
        raise LogoError(f"{command[0]} not found on the PATH") from e
    if completed.returncode != 0:
        reason = completed.stderr.decode(errors="replace").strip()
        raise LogoError(
            f"{recording}: {command[0]} could not read it: "
            f"{reason or f'exit {completed.returncode}'}"
        )
    return completed.stdout
