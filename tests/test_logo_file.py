"""Tests for logo files, checked against the layout join_logo_scp's logoframe reads.

logoframe's ``logo.h`` gives the layout: a 28-byte header string, the number
of logos as 4 big-endian bytes, then for each logo a 32-byte name, eight
little-endian 16-bit numbers (x, y, height, width and four it ignores), and six
little-endian 16-bit numbers per pixel, row by row: opacity out of 1000 and
value for brightness, then the same for the two colour channels. Brightness
runs from 0 for video black to 4096 for video white.
"""

from pathlib import Path

import numpy as np
import pytest

from tv_commercial_detector.logo_file import (
    Logo,
    LogoFileError,
    read_logo_file,
    write_logo_file,
)


def test_a_logo_is_written_in_the_layout_logoframe_reads(tmp_path: Path) -> None:
    logo = Logo(
        name="TBS",
        x=1764,
        y=22,
        opacity=np.array([[0.0, 0.2, 0.2], [0.0, 0.05, 1.0]]),
        brightness=np.array([[16.0, 235.0, 125.5], [16.0, 16.0, 235.0]]),
    )

    write_logo_file(tmp_path / "TBS.lgd", logo)

    no_colour = b"\0" * 8
    assert (tmp_path / "TBS.lgd").read_bytes() == b"".join(
        [
            b"<logo data file ver0.1>\0\0\0\0\0",
            b"\x00\x00\x00\x01",  # one logo
            b"TBS" + b"\0" * 29,  # its name
            b"\xe4\x06\x16\x00",  # x 1764, y 22
            b"\x02\x00\x03\x00",  # 2 high, 3 wide
            b"\0" * 8,  # no fade in or out, no start or end
            # First row: nothing; 20% of video white; 20% of mid grey.
            b"\x00\x00\x00\x00" + no_colour,
            b"\xc8\x00\x00\x10" + no_colour,
            b"\xc8\x00\x00\x08" + no_colour,
            # Second row: nothing; 5% of video black; solid video white.
            b"\x00\x00\x00\x00" + no_colour,
            b"\x32\x00\x00\x00" + no_colour,
            b"\xe8\x03\x00\x10" + no_colour,
        ]
    )


def test_a_logo_read_back_matches_the_one_written(tmp_path: Path) -> None:
    opacity = np.array([[0.0, 0.181, 0.21], [0.07, 0.0, 0.155]])
    brightness = np.array([[16.0, 233.0, 228.0], [120.0, 16.0, 225.0]])
    path = tmp_path / "TV Asahi.lgd"

    write_logo_file(path, Logo("TV Asahi", 1722, 40, opacity, brightness))
    logo = read_logo_file(path)

    assert (logo.name, logo.x, logo.y) == ("TV Asahi", 1722, 40)
    assert (logo.width, logo.height) == (3, 2)
    np.testing.assert_allclose(logo.opacity, opacity, atol=0.0005)
    np.testing.assert_allclose(logo.brightness, brightness, atol=0.05)


def test_a_japanese_name_is_written_as_logoframe_tools_expect(tmp_path: Path) -> None:
    path = tmp_path / "テレ東.lgd"

    write_logo_file(path, Logo("テレ東", 0, 0, np.zeros((1, 1)), np.zeros((1, 1))))

    assert path.read_bytes()[32:64] == "テレ東".encode("cp932") + b"\0" * 26
    assert read_logo_file(path).name == "テレ東"


def test_a_name_too_long_for_the_file_is_cut_short(tmp_path: Path) -> None:
    path = tmp_path / "long.lgd"
    name = "A channel with a name longer than the file allows"

    write_logo_file(path, Logo(name, 0, 0, np.zeros((1, 1)), np.zeros((1, 1))))

    assert read_logo_file(path).name == "A channel with a name longer th"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "not a logo file"),
        (b"GIF89a" + b"\0" * 200, "not a logo file"),
        (
            b"<logo data file ver0.1>\0\0\0\0\0\0\0\0\x01" + b"\0" * 20,
            "the file ends before its logo does",
        ),
        (
            b"<logo data file ver0.1>\0\0\0\0\0\0\0\0\x01"
            + b"TBS".ljust(32, b"\0")
            + b"\x00\x00\x00\x00\x02\x00\x03\x00"
            + b"\0" * 8
            + b"\0" * 60,
            "the file ends before its logo does",
        ),
    ],
)
def test_a_file_that_is_not_a_whole_logo_file_is_rejected(
    tmp_path: Path, content: bytes, message: str
) -> None:
    path = tmp_path / "broken.lgd"
    path.write_bytes(content)

    with pytest.raises(LogoFileError, match=message):
        read_logo_file(path)
