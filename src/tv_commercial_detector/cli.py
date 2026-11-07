"""The command-line entry point and its subcommands."""

import argparse

from loguru import logger

from tv_commercial_detector import settings
from tv_commercial_detector.media_probe import Ffprobe
from tv_commercial_detector.recording_set import validate


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv : list[str] | None
        The arguments after the program name; ``sys.argv`` when ``None``.

    Returns
    -------
    int
        The exit code: 0 on success, 1 when errors were found.
    """
    parser = argparse.ArgumentParser(prog="tv-commercial-detector")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "validate", help="Check the recording set without running any detector."
    )
    args = parser.parse_args(argv)

    if args.command == "validate":
        return _validate()
    parser.error(f"unknown command {args.command}")
    return 2


def _validate() -> int:
    """Validate the recording set and log what was found."""
    data_folder = settings.data_folder()
    logger.info(f"Checking recordings in {data_folder / 'recordings'}")
    logger.info(f"Against the list of recordings in {settings.RECORDING_LIST}")

    report = validate(data_folder, settings.RECORDING_LIST, Ffprobe())

    for warning in report.warnings:
        logger.warning(f"{warning.subject}: {warning.message}")
    for error in report.errors:
        logger.error(f"{error.subject}: {error.message}")
    hours, minutes = divmod(round(report.seconds / 60), 60)
    logger.info(
        f"Checked {report.recording_count} listed recordings: "
        f"{report.hours:.1f} hours ({hours} h {minutes} min). "
        f"Skipped {len(report.warnings)}, errors {len(report.errors)}."
    )
    return 1 if report.errors else 0
