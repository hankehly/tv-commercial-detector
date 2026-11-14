"""Logo files: reading and writing the ``.lgd`` format join_logo_scp uses.

A logo file holds, for each pixel of a small box of the picture, how opaque the
channel's logo is there and how bright. join_logo_scp's logoframe compares that
with each frame to tell when the logo is on screen. The layout is the one in
logoframe's ``logo.h`` (version 0.1, from AviUtl's logo plugin):

======  ==========================================================
Bytes   Holds
======  ==========================================================
28      ``<logo data file ver0.1>``, padded with zero bytes
4       the number of logos, big-endian; always 1 here
32      the logo's name in Shift_JIS, padded with zero bytes
16      x, y, height, width, then four unused numbers
12 × n  one entry per pixel, row by row
======  ==========================================================

Numbers after the count are little-endian and 16 bits. A pixel's entry is its
opacity out of 1000 and its value, for brightness and then for each of the two
colour channels. Brightness runs from 0 at video black to 4096 at video white.
logoframe reads only the brightness pair, so the colour pairs are written as 0,
which means "no logo colour".
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_HEADER = b"<logo data file ver0.1>".ljust(28, b"\0")
_VERSION = _HEADER.rstrip(b">\0")
_NAME_BYTES = 32
_NAME_ENCODING = "cp932"
_NUMBERS = struct.Struct("<8h")
_START = len(_HEADER) + 4 + _NAME_BYTES + _NUMBERS.size
_PIXEL_NUMBERS = 6
_FULL_OPACITY = 1000
VIDEO_BLACK = 16
"""The 8-bit brightness level of black in video."""

VIDEO_WHITE = 235
"""The 8-bit brightness level of white in video."""

_WHITE_VALUE = 4096


class LogoFileError(Exception):
    """A logo file cannot be read."""


@dataclass(frozen=True)
class Logo:
    """One channel's logo, as it appears in our recordings.

    ``x`` and ``y`` are the top left corner of its box in the picture.
    ``opacity`` and ``brightness`` have one row per picture row of the box.
    ``opacity`` runs from 0 (no logo) to 1 (solid); ``brightness`` is the
    logo's own brightness as an 8-bit video level, 16 for black to 235 for
    white.
    """

    name: str
    x: int
    y: int
    opacity: np.ndarray
    brightness: np.ndarray

    @property
    def width(self) -> int:
        """The width of the logo's box, in pixels."""
        return self.opacity.shape[1]

    @property
    def height(self) -> int:
        """The height of the logo's box, in pixels."""
        return self.opacity.shape[0]


def write_logo_file(path: Path, logo: Logo) -> None:
    """Write a logo as a logo file, replacing any file already there.

    Parameters
    ----------
    path : Path
        Where to write it. Its folder must exist.
    logo : Logo
        The logo. A name longer than the file allows is cut short.
    """
    pixels = np.zeros((logo.height, logo.width, _PIXEL_NUMBERS), dtype="<i2")
    pixels[..., 0] = np.rint(np.clip(logo.opacity, 0, 1) * _FULL_OPACITY)
    scale = _WHITE_VALUE / (VIDEO_WHITE - VIDEO_BLACK)
    pixels[..., 1] = np.rint(
        (np.clip(logo.brightness, VIDEO_BLACK, VIDEO_WHITE) - VIDEO_BLACK) * scale
    )
    name = logo.name.encode(_NAME_ENCODING, errors="replace")[: _NAME_BYTES - 1]
    path.write_bytes(
        _HEADER
        + struct.pack(">I", 1)
        + name.ljust(_NAME_BYTES, b"\0")
        + _NUMBERS.pack(logo.x, logo.y, logo.height, logo.width, 0, 0, 0, 0)
        + pixels.tobytes()
    )


def read_logo_file(path: Path) -> Logo:
    """Read the first logo in a logo file.

    Parameters
    ----------
    path : Path
        The logo file.

    Returns
    -------
    Logo
        The logo, with its brightness as 8-bit video levels.

    Raises
    ------
    LogoFileError
        If the file isn't a version 0.1 logo file, gives its logo a negative
        size, or ends before its logo does.
    """
    content = path.read_bytes()
    if not content.startswith(_VERSION):
        raise LogoFileError(
            f"{path}: not a logo file: it doesn't start with {_VERSION.decode()}>"
        )
    if len(content) < _START:
        raise LogoFileError(f"{path}: the file ends before its logo does")
    name = content[len(_HEADER) + 4 :].split(b"\0", 1)[0][: _NAME_BYTES - 1]
    x, y, height, width, *_ = _NUMBERS.unpack_from(content, _START - _NUMBERS.size)
    if height < 0 or width < 0:
        raise LogoFileError(
            f"{path}: its logo's size isn't a size: {width} wide and {height} high"
        )
    count = height * width * _PIXEL_NUMBERS
    if len(content) < _START + count * 2:
        raise LogoFileError(f"{path}: the file ends before its logo does")
    pixels = np.frombuffer(content, dtype="<i2", count=count, offset=_START).reshape(
        height, width, _PIXEL_NUMBERS
    )
    scale = (VIDEO_WHITE - VIDEO_BLACK) / _WHITE_VALUE
    return Logo(
        name=name.decode(_NAME_ENCODING, errors="replace"),
        x=x,
        y=y,
        opacity=pixels[..., 0] / _FULL_OPACITY,
        brightness=pixels[..., 1] * scale + VIDEO_BLACK,
    )
