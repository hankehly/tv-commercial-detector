"""Detect whether a TV commercial is playing in a live audio/video stream."""

import sys

from tv_commercial_detector.cli import main as _cli_main


def main() -> None:
    """Run the commercial detector CLI."""
    sys.exit(_cli_main())
