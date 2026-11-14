"""Made-up frames of a corner of the picture, for tests that measure a logo.

The frames are plain backgrounds of many brightnesses, with a known
see-through logo blended in the way a broadcaster does it, plus the frames
that get in the way of measuring it: scenes without the logo, cluttered
scenes, and captions.
"""

from dataclasses import dataclass, field

import numpy as np

from tv_commercial_detector.logo_maker import CornerFrames

PICTURE = (1920, 1080)
CORNER = (1720, 0, 200, 120)
"""The corner the frames cover: x, y, width and height in the picture."""

LOGO_AT = (1800, 40)
"""Where the test logo's top left pixel sits in the picture."""


def letter_l(opacity: float = 0.2) -> np.ndarray:
    """Return the opacity of a 40 × 20 logo shaped like a fat letter L."""
    shape = np.zeros((20, 40))
    shape[:, :12] = opacity
    shape[12:, :] = opacity
    return shape


@dataclass
class Footage:
    """Made-up frames of the picture's corner, built up a stretch at a time."""

    logo: np.ndarray = field(default_factory=letter_l)
    logo_brightness: float = 230.0
    logo_at: tuple[int, int] = LOGO_AT
    dark_picture_edges: bool = False
    seed: int = 22
    frames: list[np.ndarray] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Seed the random numbers, so every run builds the same frames."""
        self.random = np.random.default_rng(self.seed)

    def plain(
        self, count: int, logo: bool, levels: tuple[float, float] = (20, 200)
    ) -> Footage:
        """Add frames of an evenly lit background, with or without the logo."""
        _, _, width, height = CORNER
        across, down = np.meshgrid(np.arange(width), np.arange(height))
        for _ in range(count):
            level = self.random.uniform(*levels)
            tilt_across, tilt_down = self.random.uniform(-0.02, 0.02, size=2)
            background = level + tilt_across * across + tilt_down * down
            self.frames.append(self._finish(background, logo))
        return self

    def busy(self, count: int, logo: bool, clutter: float = 110) -> Footage:
        """Add frames of a cluttered background, with or without the logo.

        Each pixel is mid grey give or take up to ``clutter`` 8-bit levels.
        """
        _, _, width, height = CORNER
        for _ in range(count):
            background = 125 + self.random.uniform(
                -clutter, clutter, size=(height, width)
            )
            self.frames.append(self._finish(background, logo))
        return self

    def plain_with_a_caption(self, count: int) -> Footage:
        """Add logo-less plain frames with a white caption where the logo goes."""
        left, top = self.logo_at[0] - CORNER[0], self.logo_at[1] - CORNER[1]
        for _ in range(count):
            background = np.full(CORNER[3:1:-1], self.random.uniform(20, 120))
            background[top + 4 : top + 14, left - 4 : left + 30] = 235
            self.frames.append(self._finish(background, logo=False))
        return self

    def plain_with_a_passing_object(self, count: int) -> Footage:
        """Add logo-less plain frames with a bright object somewhere in the box."""
        left, top = self.logo_at[0] - CORNER[0], self.logo_at[1] - CORNER[1]
        for _ in range(count):
            background = np.full(CORNER[3:1:-1], self.random.uniform(20, 120))
            x = left + int(self.random.integers(-6, 34))
            y = top + int(self.random.integers(-6, 14))
            background[y : y + 12, x : x + 12] = 235
            self.frames.append(self._finish(background, logo=False))
        return self

    def _finish(self, background: np.ndarray, logo: bool) -> np.ndarray:
        """Blend the logo over a background, then add noise and round."""
        frame = background.copy()
        if logo:
            left, top = self.logo_at[0] - CORNER[0], self.logo_at[1] - CORNER[1]
            rows, columns = self.logo.shape
            under = frame[top : top + rows, left : left + columns]
            frame[top : top + rows, left : left + columns] = (
                under * (1 - self.logo) + self.logo_brightness * self.logo
            )
        if self.dark_picture_edges:
            # What a window capture leaves along the top and right of the picture.
            frame[:2] *= 0.75
            frame[:, -1] = 7
        frame += self.random.normal(0, 0.7, size=frame.shape)
        return np.clip(np.rint(frame), 0, 255).astype(np.uint8)

    def corner(self) -> CornerFrames:
        """Return the frames as the corner of a 1920 × 1080 picture."""
        order = self.random.permutation(len(self.frames))
        return CornerFrames(
            pixels=np.stack(self.frames)[order],
            x=CORNER[0],
            y=CORNER[1],
            picture_width=PICTURE[0],
            picture_height=PICTURE[1],
        )
