"""Tests for the ``make-logo`` command, as a whole.

Made-up frames (see ``logo_footage``) stand in for sampling a recording with
ffmpeg, so the tests need neither ffmpeg nor a real recording. They check what
the command saves in the data folder and what it tells the user.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from logo_footage import Footage

from tv_commercial_detector import cli
from tv_commercial_detector.cli import main
from tv_commercial_detector.logo_file import read_logo_file
from tv_commercial_detector.logo_maker import CornerFrames, LogoError
from tv_commercial_detector.recording_set import logo_file
from tv_commercial_detector.settings import DATA_FOLDER_VARIABLE

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class FakeSampler:
    """Stands in for sampling recordings: hands back made-up frames."""

    footage: Footage
    asked_for: list[Path] = field(default_factory=list)
    error: str | None = None

    def __call__(self, recordings: list[Path]) -> CornerFrames:
        """Note which recordings were asked for, and return the footage."""
        self.asked_for.extend(recordings)
        if self.error:
            raise LogoError(self.error)
        return self.footage.corner()


@pytest.fixture
def data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Return a data folder holding one placeholder recording, ``tbs.mp4``."""
    folder = tmp_path / "data"
    (folder / "recordings").mkdir(parents=True)
    (folder / "recordings" / "tbs.mp4").write_bytes(b"a recording")
    monkeypatch.setenv(DATA_FOLDER_VARIABLE, str(folder))
    return folder


@pytest.fixture
def sampler(monkeypatch: pytest.MonkeyPatch) -> FakeSampler:
    """Replace sampling with footage that shows the test logo well."""
    fake = FakeSampler(Footage().plain(200, logo=True).plain(100, logo=False))
    monkeypatch.setattr(cli, "sample_corner", fake)
    return fake


def test_without_a_box_it_saves_a_picture_to_find_the_logo_in(
    data: Path, sampler: FakeSampler, log: list[str]
) -> None:
    exit_code = main(["make-logo", "TBS", str(data / "recordings" / "tbs.mp4")])

    picture = data / "logos" / "TBS.still.png"
    assert exit_code == 0
    assert picture.read_bytes().startswith(PNG_SIGNATURE)
    assert not logo_file(data, "TBS").exists()
    assert f"INFO Saved a picture of what stays put in the corner to {picture}" in log
    assert (
        "INFO Find the logo in it, read a box around it off the rulers, and run "
        "this again with --box X,Y,WIDTH,HEIGHT"
    ) in log


def test_with_a_box_it_saves_the_logo_file_where_validate_looks(
    data: Path, sampler: FakeSampler, log: list[str]
) -> None:
    recording = str(data / "recordings" / "tbs.mp4")

    exit_code = main(["make-logo", "TBS", recording, "--box", "1790,30,60,40"])

    assert exit_code == 0
    logo = read_logo_file(logo_file(data, "TBS"))
    assert (logo.name, logo.x, logo.y, logo.width, logo.height) == (
        "TBS",
        1794,
        34,
        52,
        32,
    )
    assert logo.opacity.max() == pytest.approx(0.2, abs=0.02)
    preview = data / "logos" / "TBS.png"
    assert preview.read_bytes().startswith(PNG_SIGNATURE)
    assert (
        "INFO Measured the logo from 200 frames that show it over plain surroundings"
    ) in log
    assert (
        "INFO Its box is 1794,34,52,32 (x,y,width,height) and it is up to 20% opaque"
    ) in log
    assert f"INFO Saved the logo file to {logo_file(data, 'TBS')}" in log
    assert (
        f"INFO Saved a picture of it to {preview}: check that it shows the "
        "channel's whole logo and nothing else"
    ) in log


def test_recordings_are_found_by_name_in_the_recordings_folder(
    data: Path, sampler: FakeSampler, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.mp4"
    elsewhere.write_bytes(b"another recording")

    exit_code = main(["make-logo", "TBS", "tbs.mp4", str(elsewhere)])

    assert exit_code == 0
    assert sampler.asked_for == [data / "recordings" / "tbs.mp4", elsewhere]


def test_a_recording_that_does_not_exist_is_an_error(
    data: Path, sampler: FakeSampler, log: list[str]
) -> None:
    exit_code = main(["make-logo", "TBS", "nope.mp4"])

    assert exit_code == 1
    assert (
        f"ERROR no such recording: nope.mp4 (also looked in {data / 'recordings'})"
    ) in log
    assert sampler.asked_for == []


def test_a_logo_that_cannot_be_measured_is_an_error_and_saves_nothing(
    data: Path, monkeypatch: pytest.MonkeyPatch, log: list[str]
) -> None:
    footage = Footage().plain(12, logo=True).plain(50, logo=False)
    monkeypatch.setattr(cli, "sample_corner", FakeSampler(footage))

    exit_code = main(["make-logo", "TBS", "tbs.mp4", "--box", "1790,30,60,40"])

    assert exit_code == 1
    assert any(line.startswith("ERROR only 12 of the 62 frames") for line in log)
    assert not logo_file(data, "TBS").exists()


def test_a_recording_that_cannot_be_sampled_is_an_error(
    data: Path, monkeypatch: pytest.MonkeyPatch, log: list[str]
) -> None:
    broken = FakeSampler(Footage(), error="tbs.mp4: ffmpeg could not read it")
    monkeypatch.setattr(cli, "sample_corner", broken)

    exit_code = main(["make-logo", "TBS", "tbs.mp4"])

    assert exit_code == 1
    assert "ERROR tbs.mp4: ffmpeg could not read it" in log


@pytest.mark.parametrize(
    ("channel", "message"),
    [
        (
            "TV/Asahi",
            "channel can't contain / or \\, since it names the channel's logo file",
        ),
        (" TBS", "channel can't start or end with a space"),
    ],
)
def test_a_channel_that_cannot_name_a_logo_file_is_an_error(
    data: Path, sampler: FakeSampler, log: list[str], channel: str, message: str
) -> None:
    exit_code = main(["make-logo", channel, "tbs.mp4"])

    assert exit_code == 1
    assert f"ERROR {message}" in log
    assert sampler.asked_for == []


@pytest.mark.parametrize("box", ["1790,30,60", "1790,30,60,forty", "around the logo"])
def test_a_box_that_is_not_four_numbers_is_refused(
    data: Path, sampler: FakeSampler, capsys: pytest.CaptureFixture[str], box: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["make-logo", "TBS", "tbs.mp4", "--box", box])

    assert stopped.value.code == 2
    assert "--box takes four whole numbers: X,Y,WIDTH,HEIGHT" in capsys.readouterr().err
