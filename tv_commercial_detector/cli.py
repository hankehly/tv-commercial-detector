"""The command-line entry point and its subcommands."""

import argparse

from loguru import logger

from tv_commercial_detector import settings
from tv_commercial_detector.media_probe import Ffprobe
from tv_commercial_detector.recording_set import LOGO_SUFFIX, validate


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
    parser.parse_args(argv)
    return _validate()


def _validate() -> int:
    """Validate the recording set and log what was found.

    Returns
    -------
    int
        The exit code: 0 if no errors were found, otherwise 1.
    """
    data_folder = settings.data_folder()
    logger.info(f"Checking recordings in {data_folder / 'recordings'}")
    logger.info(f"Against the list of recordings in {settings.RECORDING_LIST}")
    logger.info(f"And the label files in {settings.LABELS_FOLDER}")

    report = validate(
        data_folder, settings.RECORDING_LIST, settings.LABELS_FOLDER, Ffprobe()
    )

    for warning in report.warnings:
        logger.warning(f"{warning.subject}: {warning.message}")
    for error in report.errors:
        logger.error(f"{error.subject}: {error.message}")
    hours, minutes = divmod(round(report.total_length_seconds / 60), 60)
    logger.info(
        f"Checked {report.recording_count} listed recordings: "
        f"{report.hours:.1f} hours ({hours} h {minutes} min). "
        f"Skipped {report.skipped_count} not in the list, "
        f"errors {len(report.errors)}."
    )
    logger.info(
        f"Labeled {report.commercial_break_count} commercial breaks on "
        f"{len(report.channels)} channels: {', '.join(report.channels) or 'none'}. "
        f"Skipped {report.unlabeled_count} without a usable label file."
    )
    if report.channels_without_logo:
        logger.warning(
            "No logo file for join_logo_scp on these channels: "
            f"{', '.join(report.channels_without_logo)}. "
            f"Put each in {data_folder / 'logos'}, named <channel>{LOGO_SUFFIX}."
        )
    return 1 if report.errors else 0
