"""Pictures for people to look at while making a logo file, saved as PNG."""

import struct
import zlib
from pathlib import Path

import numpy as np

from tv_commercial_detector.logo_file import Logo

RULER_STEP = 50
"""A ruler mark, and a dotted line across the picture, every this many pixels."""

_ZOOM = 2
_LEFT, _TOP = 44, 18
_PAPER, _INK, _LINE = 40, 255, 110
_DIGITS = {
    "0": "111101101101111",
    "1": "010110010010111",
    "2": "111001111100111",
    "3": "111001111001111",
    "4": "101101111001001",
    "5": "111100111001111",
    "6": "111100111101111",
    "7": "111001001001001",
    "8": "111101111101111",
    "9": "111101111001111",
}
_PREVIEW_ZOOM = 4
_PREVIEW_BACKGROUNDS = (16, 126, 235)
"""The preview shows a logo over black, mid grey and white, as 8-bit levels."""


def write_png(path: Path, picture: np.ndarray) -> None:
    """Save an 8-bit greyscale picture as a PNG file.

    Parameters
    ----------
    path : Path
        Where to save it. Its folder must exist.
    picture : np.ndarray
        The picture: one row per row of pixels, each pixel 0 to 255.
    """
    picture = np.ascontiguousarray(picture, dtype=np.uint8)
    height, width = picture.shape
    # Each row starts with a zero byte: "no filter".
    rows = np.zeros((height, width + 1), dtype=np.uint8)
    rows[:, 1:] = picture

    def chunk(kind: bytes, content: bytes) -> bytes:
        check = zlib.crc32(kind + content)
        return (
            struct.pack(">I", len(content)) + kind + content + struct.pack(">I", check)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows.tobytes(), 9))
        + chunk(b"IEND", b"")
    )


def with_rulers(picture: np.ndarray, x: int, y: int) -> np.ndarray:
    """Enlarge a part of the picture and mark its position along the top and left.

    Parameters
    ----------
    picture : np.ndarray
        An 8-bit greyscale picture of part of the whole picture.
    x : int
        Where its left column sits in the whole picture.
    y : int
        Where its top row sits in the whole picture.

    Returns
    -------
    np.ndarray
        The picture at twice the size, with a numbered mark and a dotted line
        every ``RULER_STEP`` pixels of the whole picture, so a box can be read
        off it as x, y, width and height.
    """
    height, width = picture.shape
    sheet = np.full((_TOP + height * _ZOOM, _LEFT + width * _ZOOM), _PAPER, np.uint8)
    body = sheet[_TOP:, _LEFT:]
    body[:] = np.repeat(np.repeat(picture, _ZOOM, axis=0), _ZOOM, axis=1)
    dots = np.arange(0, max(body.shape), 1) % 6 < 2
    for column in range(-x % RULER_STEP, width, RULER_STEP):
        line = body[:, column * _ZOOM]
        line[dots[: len(line)]] = np.maximum(line[dots[: len(line)]], _LINE)
        label = str(x + column)
        _write(sheet, label, _LEFT + column * _ZOOM - 4 * len(label), 3)
    for row in range(-y % RULER_STEP, height, RULER_STEP):
        line = body[row * _ZOOM, :]
        line[dots[: len(line)]] = np.maximum(line[dots[: len(line)]], _LINE)
        _write(sheet, str(y + row), 3, max(_TOP + row * _ZOOM - 5, _TOP))
    return sheet


def logo_preview(logo: Logo) -> np.ndarray:
    """Draw a logo as it looks over black, mid grey and white.

    Parameters
    ----------
    logo : Logo
        The logo.

    Returns
    -------
    np.ndarray
        An 8-bit greyscale picture: the logo three times side by side, at four
        times its size.
    """
    panels = [
        background * (1 - logo.opacity) + logo.brightness * logo.opacity
        for background in _PREVIEW_BACKGROUNDS
    ]
    gap = np.full((logo.height, 2), _LINE)
    strip = np.hstack([panels[0], gap, panels[1], gap, panels[2]])
    strip = np.clip(np.rint(strip), 0, 255).astype(np.uint8)
    return np.repeat(np.repeat(strip, _PREVIEW_ZOOM, axis=0), _PREVIEW_ZOOM, axis=1)


def _write(sheet: np.ndarray, number: str, left: int, top: int) -> None:
    """Write a number on a sheet in small digits, where it fits.

    Parameters
    ----------
    sheet : np.ndarray
        The picture to write on.
    number : str
        The digits to write.
    left : int
        The column of the first digit's left edge.
    top : int
        The row of the digits' top edge.
    """
    for place, digit in enumerate(number):
        dots = np.array(list(_DIGITS[digit]), dtype=np.uint8).reshape(5, 3)
        glyph = np.repeat(np.repeat(dots, 2, axis=0), 2, axis=1) * _INK
        column = max(left, 0) + place * 8
        patch = sheet[top : top + 10, column : column + 6]
        patch[:] = glyph[: patch.shape[0], : patch.shape[1]]
