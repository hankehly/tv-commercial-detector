"""Tests for ``tools/comskip-docker``, which runs Comskip in Docker.

A stand-in ``docker`` command, first on ``PATH``, takes Docker's place: it says
the image is built and, instead of running anything, notes the arguments
``docker run`` was given. So the tests need neither Docker nor the image. They
check which folders the wrapper shares with the container, each at the path it
has on the Mac, and that Comskip gets its arguments unchanged.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

COMSKIP_DOCKER = Path(__file__).parents[1] / "tools" / "comskip-docker"
IMAGE = "tv-commercial-detector/comskip"

STAND_IN_DOCKER = """\
#!/usr/bin/env bash
# Says every image is built, and writes the arguments of docker run, each
# followed by a NUL, to $DOCKER_ARGUMENTS instead of running anything.
if [[ $1 == image ]]; then
  exit 0
fi
printf '%s\\0' "$@" >"$DOCKER_ARGUMENTS"
"""


@dataclass
class DockerRun:
    """What comskip-docker asked Docker to run.

    Attributes
    ----------
    shared : list[str]
        The folders shared with the container, as ``--volume`` gave them:
        ``SOURCE:TARGET``, in order.
    comskip_arguments : list[str]
        The arguments Comskip was given.
    """

    shared: list[str]
    comskip_arguments: list[str]


@dataclass
class StandInDocker:
    """Runs comskip-docker with the stand-in ``docker`` first on ``PATH``."""

    folder: Path

    def run(self, arguments: list[str], working_folder: Path) -> DockerRun:
        """Run comskip-docker and return what it asked Docker to run.

        Parameters
        ----------
        arguments : list[str]
            Comskip's arguments.
        working_folder : Path
            The folder to run it in.

        Returns
        -------
        DockerRun
            What it asked Docker to run.
        """
        noted = self.folder / "docker-arguments"
        environment = {
            **os.environ,
            "PATH": f"{self.folder}{os.pathsep}{os.environ['PATH']}",
            "DOCKER_ARGUMENTS": str(noted),
        }
        subprocess.run(
            [COMSKIP_DOCKER, *arguments],
            cwd=working_folder,
            env=environment,
            check=True,
        )
        docker_arguments = noted.read_text().split("\0")[:-1]
        image = docker_arguments.index(IMAGE)
        options = docker_arguments[:image]
        shared = [
            value for option, value in zip(options, options[1:]) if option == "--volume"
        ]
        return DockerRun(shared, docker_arguments[image + 1 :])


@pytest.fixture
def docker(tmp_path: Path) -> StandInDocker:
    """Return the stand-in ``docker``, alone in its folder."""
    folder = tmp_path / "bin"
    folder.mkdir()
    command = folder / "docker"
    command.write_text(STAND_IN_DOCKER)
    command.chmod(0o755)
    return StandInDocker(folder)


def new_file(path: Path) -> Path:
    """Create an empty file, and the folders it is in.

    Parameters
    ----------
    path : Path
        The file.

    Returns
    -------
    Path
        The file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def new_link(path: Path, target: Path) -> Path:
    """Create a symbolic link, and the folders it is in.

    Parameters
    ----------
    path : Path
        The link.
    target : Path
        Where it leads: an absolute path, or one relative to the link's folder.

    Returns
    -------
    Path
        The link.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)
    return path


def at_same_paths(*folders: Path) -> list[str]:
    """Return how ``--volume`` shares each folder at the path it has on the Mac.

    Parameters
    ----------
    *folders : Path
        The folders.

    Returns
    -------
    list[str]
        ``FOLDER:FOLDER`` for each folder, sorted.
    """
    return sorted(f"{folder}:{folder}" for folder in folders)


@pytest.fixture
def output(tmp_path: Path) -> Path:
    """Return an empty output folder, which Comskip is run in, as the benchmark does."""
    folder = tmp_path / "output"
    folder.mkdir()
    return folder


def test_the_current_folder_and_the_folder_of_each_file_named_are_shared(
    tmp_path: Path, docker: StandInDocker, output: Path
) -> None:
    recording = new_file(tmp_path / "recordings" / "2026-11-01_17-01-22.mp4")
    arguments = [f"--output={output}", str(recording)]

    run = docker.run(arguments, output)

    assert sorted(run.shared) == at_same_paths(output, recording.parent)
    assert run.comskip_arguments == arguments


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_a_linked_recording_also_shares_the_folder_the_link_leads_to(
    tmp_path: Path, docker: StandInDocker, output: Path, relative: bool
) -> None:
    recording = new_file(tmp_path / "recordings" / "2026-11-01_17-01-22.mp4")
    target = Path("..", "recordings", recording.name) if relative else recording
    link = new_link(tmp_path / "pilot" / "pilot.mp4", target)
    arguments = [f"--output={output}", str(link)]

    run = docker.run(arguments, output)

    assert sorted(run.shared) == at_same_paths(output, link.parent, recording.parent)
    # Comskip is still given the link, and so names its output after the link,
    # and without --output writes it next to the link, as it would on the Mac.
    assert run.comskip_arguments == arguments


def test_a_chain_of_links_shares_the_folder_of_each_file_along_it(
    tmp_path: Path, docker: StandInDocker, output: Path
) -> None:
    recording = new_file(tmp_path / "recordings" / "2026-11-01_17-01-22.mp4")
    middle = new_link(tmp_path / "by-channel" / "ntv.mp4", recording)
    link = new_link(
        tmp_path / "pilot" / "pilot.mp4", Path("..", "by-channel", "ntv.mp4")
    )

    run = docker.run([f"--output={output}", str(link)], output)

    assert sorted(run.shared) == at_same_paths(
        output, link.parent, middle.parent, recording.parent
    )


def test_a_linked_ini_file_also_shares_the_folder_the_link_leads_to(
    tmp_path: Path, docker: StandInDocker, output: Path
) -> None:
    # Comskip runs with its default settings, without an error, when it can't
    # open the --ini file.
    recording = new_file(tmp_path / "recordings" / "2026-11-01_17-01-22.mp4")
    settings = new_file(tmp_path / "settings" / "comskip.ini")
    link = new_link(tmp_path / "pilot" / "comskip.ini", settings)
    arguments = [f"--ini={link}", f"--output={output}", str(recording)]

    run = docker.run(arguments, output)

    assert sorted(run.shared) == at_same_paths(
        output, link.parent, settings.parent, recording.parent
    )


def test_a_linked_folder_is_shared_at_its_own_path_only(
    tmp_path: Path, docker: StandInDocker, output: Path
) -> None:
    # Docker follows a linked folder it is asked to share, so the folder it
    # leads to doesn't need sharing as well.
    recording = new_file(tmp_path / "recordings" / "2026-11-01_17-01-22.mp4")
    linked = new_link(tmp_path / "linked", tmp_path / "recordings")

    run = docker.run([f"--output={output}", str(linked / recording.name)], output)

    assert sorted(run.shared) == at_same_paths(output, linked)
