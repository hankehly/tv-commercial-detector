"""Tests for ``tools/jlse-docker``, which runs join_logo_scp's pipeline in Docker.

A stand-in ``docker`` command, first on ``PATH``, takes Docker's place: it says
the image is built and, instead of running jlse, writes the files a test gives
it to the folder jlse writes its results to, then exits with the code the test
gives it. So the tests need neither Docker nor the image. They check how
jlse-docker judges what jlse left behind.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

JLSE_DOCKER = Path(__file__).parents[1] / "tools" / "jlse-docker"

STAND_IN_DOCKER = """\
#!/usr/bin/env bash
# Says every image is built. docker run copies the files in $JLSE_OUTPUTS to
# the folder shared as jlse's result folder, and exits with $JLSE_EXIT.
if [[ $1 == image ]]; then
  exit 0
fi
for argument in "$@"; do
  case $argument in
    *:/join_logo_scp_trial/result/recording) results=${argument%:*} ;;
  esac
done
shopt -s nullglob
outputs=("$JLSE_OUTPUTS"/*)
[[ ${#outputs[@]} -eq 0 ]] || cp "${outputs[@]}" "$results"
exit "$JLSE_EXIT"
"""

# What each step writes when it finishes. chapter_exe lists the silences and
# scene changes it found, then the last frame on a line of its own.
FINISHED = {
    "obs_chapterexe.txt": (
        "CHAPTER01=00:00:49.950\n"
        "CHAPTER01NAME=30フレーム ★ SCPos:1498 1497\n"
        "# SCPos:5404 5404\n"
    ),
    "obs_logoframe.txt": "(logoframe's output)\n",
    "obs_jlscp.txt": "(join_logo_scp's output)\n",
    "obs_cut.avs": "Trim(0,1497)\n",
}


@dataclass
class StandInDocker:
    """Runs jlse-docker with the stand-in ``docker`` first on ``PATH``."""

    folder: Path

    def run(
        self, outputs: dict[str, str], exit_code: int = 0
    ) -> subprocess.CompletedProcess[str]:
        """Run jlse-docker, as if jlse wrote some files and exited with a code.

        Parameters
        ----------
        outputs : dict[str, str]
            The files jlse writes, by name, and what each holds.
        exit_code : int
            The code jlse exits with.

        Returns
        -------
        subprocess.CompletedProcess[str]
            How jlse-docker ended, with what it wrote to standard error.
        """
        written = self.folder / "jlse-outputs"
        written.mkdir()
        for name, text in outputs.items():
            (written / name).write_text(text)
        recording = self.folder / "2026-11-01_17-01-22.mp4"
        recording.touch()
        logo = self.folder / "ntv.lgd"
        logo.touch()
        results = self.folder / "results"
        results.mkdir()
        environment = {
            **os.environ,
            "PATH": f"{self.folder}{os.pathsep}{os.environ['PATH']}",
            "JLSE_OUTPUTS": str(written),
            "JLSE_EXIT": str(exit_code),
        }
        return subprocess.run(
            [JLSE_DOCKER, recording, logo],
            cwd=results,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture
def docker(tmp_path: Path) -> StandInDocker:
    """Return the stand-in ``docker``, in its own folder."""
    command = tmp_path / "docker"
    command.write_text(STAND_IN_DOCKER)
    command.chmod(0o755)
    return StandInDocker(tmp_path)


def test_a_run_whose_steps_all_finished_succeeds(docker: StandInDocker) -> None:
    ended = docker.run(FINISHED)

    assert (ended.returncode, ended.stderr) == (0, "")


def test_a_step_that_wrote_nothing_is_named(docker: StandInDocker) -> None:
    outputs = {k: v for k, v in FINISHED.items() if k != "obs_logoframe.txt"}

    ended = docker.run(outputs, exit_code=1)

    assert ended.returncode == 1
    assert "logoframe wrote no obs_logoframe.txt" in ended.stderr


@pytest.mark.parametrize(
    "chapters",
    [
        "",
        "CHAPTER01=00:00:49.950\nCHAPTER01NAME=30フレーム ★ SCPos:1498 1497\n",
    ],
    ids=["nothing found yet", "some found"],
)
def test_chapter_exe_stopping_before_the_end_of_the_recording_is_an_error(
    docker: StandInDocker, chapters: str
) -> None:
    # chapter_exe writes as it goes, and jlse runs the later steps and exits
    # with 0 whatever chapter_exe's exit code, so its output is all there is
    # to go on.
    ended = docker.run({**FINISHED, "obs_chapterexe.txt": chapters})

    assert ended.returncode == 1
    assert "chapter_exe stopped before the end of the recording" in ended.stderr
