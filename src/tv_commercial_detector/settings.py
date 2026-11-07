"""Settings, each read from an environment variable with a fallback default."""

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
"""The repository root, for files tracked alongside the code."""

DATA_FOLDER_VARIABLE = "TV_COMMERCIAL_DETECTOR_DATA_FOLDER"
"""Environment variable naming the data folder."""

RECORDING_LIST = REPOSITORY_ROOT / "benchmark" / "recordings.csv"
"""The list of recordings, tracked in the repository."""


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
