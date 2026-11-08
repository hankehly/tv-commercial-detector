"""Settings, each read from an environment variable with a fallback default."""

import os
import shlex
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""The repository root, for files tracked alongside the code."""

DATA_FOLDER_VARIABLE = "TV_COMMERCIAL_DETECTOR_DATA_FOLDER"
"""Environment variable naming the data folder."""

COMSKIP_COMMAND_VARIABLE = "TV_COMMERCIAL_DETECTOR_COMSKIP_COMMAND"
"""Environment variable holding the command that runs Comskip."""

JOIN_LOGO_SCP_COMMAND_VARIABLE = "TV_COMMERCIAL_DETECTOR_JOIN_LOGO_SCP_COMMAND"
"""Environment variable holding the command that runs join_logo_scp's pipeline."""

RECORDING_LIST = REPOSITORY_ROOT / "benchmark" / "recordings.csv"
"""The list of recordings, tracked in the repository."""

LABELS_FOLDER = REPOSITORY_ROOT / "benchmark" / "labels"
"""The folder of label files, one per recording, tracked in the repository."""


def data_folder() -> Path:
    """Return the data folder: recordings, logo files and saved tool output.

    Returns
    -------
    Path
        The folder named by ``TV_COMMERCIAL_DETECTOR_DATA_FOLDER``, or the
        ``data/`` folder at the repository root when it is unset or empty.
    """
    configured = os.environ.get(DATA_FOLDER_VARIABLE)
    if configured:
        return Path(configured).expanduser()
    return REPOSITORY_ROOT / "data"


def comskip_command() -> list[str]:
    """Return the command that runs Comskip, before its arguments.

    Returns
    -------
    list[str]
        ``TV_COMMERCIAL_DETECTOR_COMSKIP_COMMAND`` split into words as a shell
        would, or ``comskip`` on the PATH when it is unset or empty.
    """
    return _command(COMSKIP_COMMAND_VARIABLE, "comskip")


def join_logo_scp_command() -> list[str]:
    """Return the command that runs join_logo_scp's pipeline, before its arguments.

    Returns
    -------
    list[str]
        ``TV_COMMERCIAL_DETECTOR_JOIN_LOGO_SCP_COMMAND`` split into words as a
        shell would, or ``jlse`` (the command from the JoinLogoScpTrialSetLinux
        setup) on the PATH when it is unset or empty. On macOS this is
        typically a wrapper that runs that setup in Docker.
    """
    return _command(JOIN_LOGO_SCP_COMMAND_VARIABLE, "jlse")


def _command(variable: str, default: str) -> list[str]:
    """Read a tool's command from an environment variable.

    Parameters
    ----------
    variable : str
        The environment variable.
    default : str
        The command to use when the variable is unset or holds no words.

    Returns
    -------
    list[str]
        The command, split into words as a shell would.
    """
    return shlex.split(os.environ.get(variable, "")) or [default]
