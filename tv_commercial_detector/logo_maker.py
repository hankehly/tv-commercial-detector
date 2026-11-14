"""Making a logo file: measuring a channel's logo from our own recordings.

A broadcaster blends its logo over the picture: at each pixel the result is
``background × (1 − opacity) + logo brightness × opacity``. Whenever the
picture around the logo is plain (a dark scene, a sky, a wall), the background
under the logo is known too: it carries on from its surroundings. So over many
such frames, each pixel's brightness plotted against its background falls on a
straight line, whose slope gives the pixel's opacity and whose height gives the
logo's brightness. Frames without the logo, and frames with something else in
the box, don't fall on that line and are left out.
"""

from dataclasses import dataclass

import numpy as np

from tv_commercial_detector.logo_file import Logo

SURROUND = 12
"""Width, in pixels, of the band around the box that must be plain."""

PICTURE_EDGE = 4
"""Pixels along each edge of the picture left out of the surroundings: a window
capture leaves the outermost rows and columns darker than the broadcast."""

PLAIN_ROUGHNESS = 1.5
"""How far the surroundings may stray from an evenly lit background, as a
root-mean-square in 8-bit levels, for a frame to count as plain."""

PLAIN_TILT = 12.0
"""How much an evenly lit background may brighten from one side of the
surroundings to the other, in 8-bit levels, for a frame to count as plain."""

CHANGED_BY = 4.0
"""A pixel in the box differs from its background by more than this many 8-bit
levels when something, such as the logo, is drawn over it."""

CHANGED_SHARE = 0.02
"""The share of the box's pixels that must differ from their background for a
plain frame to have something in the box."""

OUTLIER_FLOOR = 2.0
"""A frame fits the logo if it strays from it by less than this, as a
root-mean-square in 8-bit levels, or by less than ``OUTLIER_SPREAD`` times what
is typical. If even the typical frame strays further, the frames don't show one
logo."""

OUTLIER_SPREAD = 2.5

MIN_FRAMES = 30
"""The fewest frames a logo can be measured from."""

MIN_BACKGROUND_RANGE = 40.0
"""The least the backgrounds must differ in brightness between the darker and
brighter frames used, in 8-bit levels. With less, a faint bright logo can't be
told from a solid dull one."""

LOGO_OPACITY = 0.04
"""A pixel is part of the logo when it is at least this opaque."""

NOISE_OPACITY = 0.02
"""Opacity below this is measurement noise, written as none."""

MARGIN = 6
"""Pixels kept around the logo on every side of the box written to the file."""


STILL_FRAMES = 1200
"""The most frames the still pictures are worked out from; more are thinned out."""

EDGE = 6
"""A step in brightness of more than this many 8-bit levels, between pixels two
apart, counts as an edge when judging how cluttered a frame is."""

CELL = 16
"""Frames are judged for clutter in square cells this many pixels wide."""

CLUTTERED_CELL = 0.10
"""A cell is cluttered when more than this share of its pixels are on edges."""

CALM_FRAME = 0.12
"""A frame is calm when fewer than this share of its cells are cluttered: a
logo fits in that, a caption doesn't."""

CALM_LEVELS = (20, 120)
"""Calm frames count towards their still picture when their typical brightness
is between these 8-bit levels: over a bright scene a white logo hardly shows."""

STILL_GAIN = 6
"""How much the still pictures brighten what they find, to make it easy to see."""


class LogoError(Exception):
    """A logo can't be measured from the frames given."""


@dataclass(frozen=True)
class Box:
    """A rectangle of the picture, by its top left corner and its size in pixels."""

    x: int
    y: int
    width: int
    height: int

    def __str__(self) -> str:
        """Write the box the way ``--box`` takes it."""
        return f"{self.x},{self.y},{self.width},{self.height}"


@dataclass(frozen=True)
class CornerFrames:
    """Frames sampled from one corner of the picture, brightness only.

    ``pixels`` holds one 8-bit brightness per frame, row and column. ``x`` and
    ``y`` say where the corner's top left pixel sits in the picture.
    """

    pixels: np.ndarray
    x: int
    y: int
    picture_width: int
    picture_height: int

    @property
    def box(self) -> Box:
        """The part of the picture the frames cover."""
        _, height, width = self.pixels.shape
        return Box(self.x, self.y, width, height)


@dataclass(frozen=True)
class MeasuredLogo:
    """A logo and how well founded it is.

    ``plain_frames`` counts the frames whose surroundings were plain, and
    ``frames_used`` those among them that showed the logo. ``darkest`` and
    ``brightest`` are the backgrounds of the frames used, as 8-bit levels.
    """

    logo: Logo
    plain_frames: int
    frames_used: int
    darkest: float
    brightest: float


def measure_logo(name: str, frames: CornerFrames, box: Box) -> MeasuredLogo:
    """Measure the logo inside a box of the picture.

    Parameters
    ----------
    name : str
        The logo's name: the channel.
    frames : CornerFrames
        Frames sampled from the corner of the picture holding the logo.
    box : Box
        A box drawn by hand around the logo, with some room to spare. Nothing
        else that stays on screen should be inside it.

    Returns
    -------
    MeasuredLogo
        The logo, in a box trimmed to it, and the frames it was measured from.

    Raises
    ------
    LogoError
        If the box isn't inside the frames, too few frames show the logo over
        plain surroundings, the frames disagree about what is in the box,
        their backgrounds are too alike, nothing in the box looks like a logo,
        or the logo reaches the edge of the box.
    """
    area, inside = _area_around(box, frames)
    left, top = area.x - frames.x, area.y - frames.y
    window = frames.pixels[:, top : top + area.height, left : left + area.width]
    plain, surfaces = _plain_surroundings(window, ~inside)
    pixels = window[plain].astype(np.float32)
    backgrounds = _backgrounds(surfaces[plain], inside.shape)
    changed = np.abs(pixels - backgrounds)[:, inside] > CHANGED_BY
    showing = changed.mean(axis=1) >= CHANGED_SHARE
    pixels, backgrounds = pixels[showing], backgrounds[showing]
    plain_frames = int(plain.sum())
    if len(pixels) < MIN_FRAMES:
        raise LogoError(
            f"only {len(pixels)} of the {len(frames.pixels)} frames show "
            f"something in the box {box} over plain surroundings "
            f"({plain_frames} have plain surroundings), and a logo needs at "
            f"least {MIN_FRAMES}. Check the box is around the logo and holds "
            "nothing else, or add more recordings of the channel."
        )

    slope, height, fits, stray = _fit(pixels, backgrounds, inside)
    if stray > OUTLIER_FLOOR or fits.sum() < MIN_FRAMES:
        raise LogoError(
            f"the {len(pixels)} frames with something in the box {box} don't "
            "agree on what it is, so it isn't a logo that stays put. Check the "
            "box is around the logo and holds nothing else."
        )
    levels = backgrounds[fits][:, inside].mean(axis=1)
    darkest, brightest = np.quantile(levels, [0.1, 0.9])
    if brightest - darkest < MIN_BACKGROUND_RANGE:
        raise LogoError(
            f"the {int(fits.sum())} frames that show the logo over plain "
            f"surroundings are all about as bright as each other (levels "
            f"{darkest:.0f} to {brightest:.0f}), so its opacity can't be told "
            "from its brightness. Add recordings with both dark and bright "
            "scenes."
        )

    opacity = np.clip(1 - slope, 0, 1)
    opacity[~inside | (opacity < NOISE_OPACITY)] = 0
    logo_pixels = opacity >= LOGO_OPACITY
    if not logo_pixels.any():
        raise LogoError(f"nothing in the box {box} looks like a logo")
    brightness = np.where(opacity > 0, height / np.maximum(opacity, 1e-6), 16.0)
    _check_room(logo_pixels, inside, box)

    rows, columns = np.nonzero(logo_pixels)
    trimmed = _trim(
        Box(
            area.x + int(columns.min()),
            area.y + int(rows.min()),
            int(columns.max() - columns.min()) + 1,
            int(rows.max() - rows.min()) + 1,
        ),
        area,
    )
    left, top = trimmed.x - area.x, trimmed.y - area.y
    kept = (slice(top, top + trimmed.height), slice(left, left + trimmed.width))
    return MeasuredLogo(
        logo=Logo(
            name=name,
            x=trimmed.x,
            y=trimmed.y,
            opacity=opacity[kept],
            brightness=np.clip(brightness[kept], 16, 235),
        ),
        plain_frames=plain_frames,
        frames_used=int(fits.sum()),
        darkest=float(darkest),
        brightest=float(brightest),
    )


def still_pictures(frames: CornerFrames) -> tuple[np.ndarray, np.ndarray]:
    """Draw what stays put in a corner of the picture, to find the logo by eye.

    Two pictures, since neither shows every logo. The first is bright along
    edges that are there in most frames: it shows a logo that is nearly always
    on, along with captions a program keeps on screen. The second is bright
    along edges that are there whenever the corner is otherwise calm and dark:
    it shows a logo however busy the programs' captions are, as long as some
    scenes are calm, along with anything else shown over calm scenes.

    Parameters
    ----------
    frames : CornerFrames
        Frames sampled from the corner of the picture holding the logo.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Two 8-bit pictures of the corner, one pixel per pixel: what is there in
        most frames, and what is there in calm frames.
    """
    step = max(1, -(-len(frames.pixels) // STILL_FRAMES))
    pixels = frames.pixels[::step].astype(np.int16)
    across = np.zeros_like(pixels)
    down = np.zeros_like(pixels)
    across[:, :, 1:-1] = pixels[:, :, 2:] - pixels[:, :, :-2]
    down[:, 1:-1, :] = pixels[:, 2:, :] - pixels[:, :-2, :]
    usually = np.abs(np.median(across, axis=0)) + np.abs(np.median(down, axis=0))

    steepness = np.abs(across) + np.abs(down)
    _, height, width = pixels.shape
    cells = (steepness > EDGE)[:, : height // CELL * CELL, : width // CELL * CELL]
    cells = cells.reshape(len(pixels), height // CELL, CELL, width // CELL, CELL)
    cluttered = (cells.mean(axis=(2, 4)) > CLUTTERED_CELL).mean(axis=(1, 2))
    level = np.median(pixels, axis=(1, 2))
    calm = (
        (cluttered < CALM_FRAME) & (level > CALM_LEVELS[0]) & (level < CALM_LEVELS[1])
    )
    when_calm = steepness[calm].mean(axis=0) if calm.any() else np.zeros_like(usually)

    def as_picture(strength: np.ndarray) -> np.ndarray:
        return np.clip(strength * STILL_GAIN, 0, 255).astype(np.uint8)

    return as_picture(usually), as_picture(when_calm)


def _area_around(box: Box, frames: CornerFrames) -> tuple[Box, np.ndarray]:
    """Return the box with its surroundings, and which of those pixels are the box.

    Parameters
    ----------
    box : Box
        The box drawn around the logo.
    frames : CornerFrames
        The sampled frames, which must cover the box.

    Returns
    -------
    tuple[Box, np.ndarray]
        The area to work on: the box plus its surroundings, as far as the
        frames cover them and short of the picture's edges. And a mask of that
        area, true inside the box.

    Raises
    ------
    LogoError
        If the box is empty or isn't inside the frames, or no surroundings are
        left around it.
    """
    covered = frames.box
    if box.width <= 0 or box.height <= 0:
        raise LogoError(f"the box {box} is empty: give it as x,y,width,height")
    if (
        box.x < covered.x
        or box.y < covered.y
        or box.x + box.width > covered.x + covered.width
        or box.y + box.height > covered.y + covered.height
    ):
        raise LogoError(
            f"the box {box} isn't inside the corner of the picture that was "
            f"sampled, {covered} (both as x,y,width,height)"
        )
    x0 = max(box.x - SURROUND, covered.x, PICTURE_EDGE)
    y0 = max(box.y - SURROUND, covered.y, PICTURE_EDGE)
    x1 = min(
        box.x + box.width + SURROUND,
        covered.x + covered.width,
        frames.picture_width - PICTURE_EDGE,
    )
    y1 = min(
        box.y + box.height + SURROUND,
        covered.y + covered.height,
        frames.picture_height - PICTURE_EDGE,
    )
    area = Box(x0, y0, x1 - x0, y1 - y0)
    inside = np.zeros((area.height, area.width), dtype=bool)
    inside[
        max(box.y - y0, 0) : box.y + box.height - y0,
        max(box.x - x0, 0) : box.x + box.width - x0,
    ] = True
    if (~inside).sum() < 2 * SURROUND * SURROUND:
        raise LogoError(
            f"the box {box} leaves no room around it: its surroundings tell "
            "what is behind the logo, so draw it closer around the logo"
        )
    return area, inside


def _terms(shape: tuple[int, int]) -> np.ndarray:
    """Return what an evenly lit surface is built from, at every pixel of an area.

    Parameters
    ----------
    shape : tuple[int, int]
        The area's rows and columns.

    Returns
    -------
    np.ndarray
        For each pixel: 1, its column and its row. A surface is a weighted sum
        of the three: a level, a tilt across and a tilt down.
    """
    rows, columns = np.indices(shape, dtype=np.float32)
    return np.stack([np.ones_like(rows), columns, rows], axis=-1)


def _plain_surroundings(
    window: np.ndarray, surroundings: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Find the frames whose surroundings are plain.

    Parameters
    ----------
    window : np.ndarray
        The frames, cut to the area being worked on.
    surroundings : np.ndarray
        A mask of the area, true around the box.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Which frames are plain: their surroundings stay close to an evenly lit
        surface, and that surface is nearly level. And each frame's surface,
        as its level, tilt across and tilt down.
    """
    terms = _terms(surroundings.shape)[surroundings]
    solve = np.linalg.pinv(terms).T
    height, width = surroundings.shape
    plain = np.zeros(len(window), dtype=bool)
    surfaces = np.zeros((len(window), 3), dtype=np.float32)
    # A thousand frames at a time, so sampled frames aren't all held twice.
    for start in range(0, len(window), 1000):
        around = window[start : start + 1000][:, surroundings].astype(np.float32)
        fitted = around @ solve
        stray = around - fitted @ terms.T
        roughness = np.sqrt((stray**2).mean(axis=1))
        tilt = np.abs(fitted[:, 1]) * width + np.abs(fitted[:, 2]) * height
        plain[start : start + 1000] = (roughness < PLAIN_ROUGHNESS) & (
            tilt < PLAIN_TILT
        )
        surfaces[start : start + 1000] = fitted
    return plain, surfaces


def _backgrounds(surfaces: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Draw frames' evenly lit surfaces over the whole area.

    Parameters
    ----------
    surfaces : np.ndarray
        Each frame's level, tilt across and tilt down.
    shape : tuple[int, int]
        The area's rows and columns.

    Returns
    -------
    np.ndarray
        Each frame's background at every pixel of the area: what would be
        there if nothing were drawn over it.
    """
    return np.einsum("fk,hwk->fhw", surfaces, _terms(shape))


def _fit(
    pixels: np.ndarray, backgrounds: np.ndarray, inside: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Fit each pixel's line of brightness against background.

    Frames that stray from the lines the others agree on, such as frames with
    a caption in the box, are dropped and the lines fitted again, until the
    same frames stay.

    Parameters
    ----------
    pixels : np.ndarray
        Plain frames with something in the box.
    backgrounds : np.ndarray
        Their backgrounds.
    inside : np.ndarray
        A mask of the area, true inside the box.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray, float]
        Each pixel's slope and its height where the background is 0, which
        frames the lines were fitted to, and how far the typical one of those
        frames strays from the lines, as a root-mean-square in 8-bit levels.
    """
    fits = np.ones(len(pixels), dtype=bool)
    for _ in range(10):
        seen, behind = pixels[fits], backgrounds[fits]
        mean_seen, mean_behind = seen.mean(axis=0), behind.mean(axis=0)
        spread = ((behind - mean_behind) ** 2).mean(axis=0)
        together = ((behind - mean_behind) * (seen - mean_seen)).mean(axis=0)
        slope = together / np.maximum(spread, 1e-6)
        height = mean_seen - slope * mean_behind
        stray = (pixels - (slope * backgrounds + height))[:, inside]
        distance = np.sqrt((stray**2).mean(axis=1))
        limit = max(OUTLIER_FLOOR, OUTLIER_SPREAD * float(np.median(distance[fits])))
        still_fits = distance < limit
        if (still_fits == fits).all() or still_fits.sum() < 2:
            break
        fits = still_fits
    return slope, height, fits, float(np.median(distance[fits]))


def _check_room(logo_pixels: np.ndarray, inside: np.ndarray, box: Box) -> None:
    """Check the logo stops short of the box's edges.

    Parameters
    ----------
    logo_pixels : np.ndarray
        A mask of the area, true where the logo is.
    inside : np.ndarray
        A mask of the area, true inside the box.
    box : Box
        The box, for the message.

    Raises
    ------
    LogoError
        If the logo reaches an edge of the box, naming the edges.
    """
    rows, columns = np.nonzero(inside)
    window = logo_pixels[rows.min() : rows.max() + 1, columns.min() : columns.max() + 1]
    edges = {
        "top": window[:2].any(),
        "bottom": window[-2:].any(),
        "left": window[:, :2].any(),
        "right": window[:, -2:].any(),
    }
    reached = [edge for edge, touched in edges.items() if touched]
    if reached:
        raise LogoError(
            f"the logo reaches the {' and '.join(reached)} of the box {box}, so "
            "part of it may be cut off. Make the box bigger on that side."
        )


def _trim(extent: Box, area: Box) -> Box:
    """Grow the logo's extent by the margin, to even numbers, within the area.

    Parameters
    ----------
    extent : Box
        The smallest box holding every logo pixel.
    area : Box
        The area that was worked on, which the result stays inside.

    Returns
    -------
    Box
        The box to write to the logo file, with an even position and size.
    """
    x0 = max(extent.x - MARGIN, area.x)
    y0 = max(extent.y - MARGIN, area.y)
    x1 = min(extent.x + extent.width + MARGIN, area.x + area.width)
    y1 = min(extent.y + extent.height + MARGIN, area.y + area.height)
    x0, y0 = x0 + x0 % 2, y0 + y0 % 2
    x1, y1 = x1 - (x1 - x0) % 2, y1 - (y1 - y0) % 2
    return Box(x0, y0, x1 - x0, y1 - y0)
