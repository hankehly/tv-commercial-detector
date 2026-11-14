"""Tests for measuring a channel's logo from frames of our own recordings.

The frames are made up (see ``logo_footage``). A test passes when the logo
measured back matches the one blended in.
"""

import numpy as np
import pytest
from logo_footage import Footage, letter_l

from tv_commercial_detector.logo_maker import (
    Box,
    LogoError,
    measure_logo,
    still_pictures,
)


def test_a_logo_is_measured_from_frames_with_plain_surroundings() -> None:
    footage = Footage().plain(200, logo=True)

    measured = measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40))

    logo = measured.logo
    assert logo.name == "TBS"
    # The box is trimmed to the logo plus 6 pixels on every side.
    assert (logo.x, logo.y, logo.width, logo.height) == (1794, 34, 52, 32)
    inside = np.zeros((32, 52), dtype=bool)
    inside[6:26, 6:46] = letter_l() > 0
    np.testing.assert_allclose(logo.opacity[inside], 0.2, atol=0.02)
    np.testing.assert_allclose(logo.brightness[inside], 230, atol=8)
    assert (logo.opacity[~inside] == 0).all()
    assert measured.frames_used == 200


def test_frames_without_the_logo_or_with_clutter_do_not_spoil_the_logo() -> None:
    footage = (
        Footage()
        .plain(120, logo=True)
        .plain(300, logo=False)  # commercials over plain backgrounds
        .busy(200, logo=True)
        .busy(100, logo=False)
        .plain_with_a_caption(25)
    )

    measured = measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40))

    logo = measured.logo
    assert (logo.x, logo.y, logo.width, logo.height) == (1794, 34, 52, 32)
    inside = np.zeros((32, 52), dtype=bool)
    inside[6:26, 6:46] = letter_l() > 0
    np.testing.assert_allclose(logo.opacity[inside], 0.2, atol=0.02)
    np.testing.assert_allclose(logo.brightness[inside], 230, atol=8)
    assert (logo.opacity[~inside] == 0).all()
    assert (measured.plain_frames, measured.frames_used) == (445, 120)


def test_the_dark_edges_of_a_captured_picture_do_not_count_as_surroundings() -> None:
    footage = Footage(logo_at=(1866, 12), dark_picture_edges=True)
    footage.plain(200, logo=True)

    measured = measure_logo("NTV", footage.corner(), Box(1856, 4, 58, 38))

    logo = measured.logo
    assert (logo.x, logo.y, logo.width, logo.height) == (1860, 6, 52, 32)
    inside = np.zeros((32, 52), dtype=bool)
    inside[6:26, 6:46] = letter_l() > 0
    np.testing.assert_allclose(logo.opacity[inside], 0.2, atol=0.02)
    assert measured.frames_used == 200


def test_too_few_frames_showing_the_logo_is_an_error_saying_what_to_do() -> None:
    footage = Footage().plain(12, logo=True).plain(50, logo=False)

    with pytest.raises(LogoError) as error:
        measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40))

    assert str(error.value) == (
        "only 12 of the 62 frames show something in the box 1790,30,60,40 over "
        "plain surroundings (62 have plain surroundings), and a logo needs at "
        "least 30. Check the box is around the logo and holds nothing else, or "
        "add more recordings of the channel."
    )


def test_a_logo_reaching_the_edge_of_the_box_is_an_error_naming_the_edge() -> None:
    footage = Footage().plain(200, logo=True)

    with pytest.raises(LogoError) as error:
        measure_logo("TBS", footage.corner(), Box(1790, 30, 49, 40))

    assert str(error.value) == (
        "the logo reaches the right of the box 1790,30,49,40, so part of it may "
        "be cut off. Make the box bigger on that side."
    )


def test_frames_that_disagree_about_what_is_in_the_box_are_an_error() -> None:
    footage = Footage().plain_with_a_passing_object(80)

    with pytest.raises(LogoError) as error:
        measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40))

    assert str(error.value) == (
        "the 80 frames with something in the box 1790,30,60,40 don't agree on "
        "what it is, so it isn't a logo that stays put. Check the box is around "
        "the logo and holds nothing else."
    )


def test_a_mark_too_faint_to_be_a_logo_is_an_error() -> None:
    footage = Footage(logo=letter_l(opacity=0.03)).plain(200, True, levels=(16, 90))

    with pytest.raises(LogoError) as error:
        measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40))

    assert str(error.value) == "nothing in the box 1790,30,60,40 looks like a logo"


def test_backgrounds_all_alike_are_an_error_asking_for_dark_and_bright() -> None:
    footage = Footage().plain(200, logo=True, levels=(16, 30))

    with pytest.raises(LogoError) as error:
        measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40))

    assert str(error.value) == (
        "the 200 frames that show the logo over plain surroundings are all "
        "about as bright as each other (levels 17 to 29), so its opacity can't "
        "be told from its brightness. Add recordings with both dark and bright "
        "scenes."
    )


@pytest.mark.parametrize(
    ("box", "message"),
    [
        (
            Box(1700, 30, 60, 40),
            "the box 1700,30,60,40 isn't inside the corner of the picture that "
            "was sampled, 1720,0,200,120 (both as x,y,width,height)",
        ),
        (
            Box(1790, 100, 60, 40),
            "the box 1790,100,60,40 isn't inside the corner of the picture that "
            "was sampled, 1720,0,200,120 (both as x,y,width,height)",
        ),
        (
            Box(1790, 30, 0, 40),
            "the box 1790,30,0,40 is empty: give it as x,y,width,height",
        ),
    ],
)
def test_a_box_outside_the_sampled_corner_is_an_error(box: Box, message: str) -> None:
    footage = Footage().plain(40, logo=True)

    with pytest.raises(LogoError) as error:
        measure_logo("TBS", footage.corner(), box)

    assert str(error.value) == message


ON_THE_LOGO_S_EDGE = (50, 80)
"""Row and column, within the corner, of a pixel on the test logo's left edge."""

AWAY_FROM_THE_LOGO = (100, 20)


def test_a_logo_shown_over_calm_scenes_stands_out_in_the_calm_picture() -> None:
    footage = Footage().plain(100, logo=True, levels=(20, 110))
    footage.busy(300, logo=False, clutter=30)

    usually, when_calm = still_pictures(footage.corner())

    assert usually.shape == when_calm.shape == (120, 200)
    assert when_calm[ON_THE_LOGO_S_EDGE] > 100
    assert when_calm[AWAY_FROM_THE_LOGO] < 40


def test_a_logo_never_shown_over_calm_scenes_stands_out_in_the_usual_picture() -> None:
    footage = Footage().busy(300, logo=True, clutter=30).plain(60, logo=False)

    usually, when_calm = still_pictures(footage.corner())

    assert usually[ON_THE_LOGO_S_EDGE] > 100
    assert usually[AWAY_FROM_THE_LOGO] < 40
    assert when_calm[ON_THE_LOGO_S_EDGE] < 40


def test_a_faint_fringe_keeps_the_brightness_of_the_logo() -> None:
    # A solid block with a faint row along its top, as a scaled logo's soft
    # edge is: 3% opaque, too faint to count as logo but still written.
    shape = np.zeros((20, 40))
    shape[1:] = 0.2
    shape[0] = 0.03
    footage = Footage(logo=shape).plain(300, logo=True)

    logo = measure_logo("TBS", footage.corner(), Box(1790, 30, 60, 40)).logo

    # The box starts at row 36 of the picture, so the fringe, at row 40, is
    # its fifth row.
    assert (logo.x, logo.y, logo.width, logo.height) == (1794, 36, 52, 30)
    fringe = logo.opacity[4, 6:46]
    assert ((fringe > 0) & (fringe < 0.04)).all()
    np.testing.assert_allclose(logo.brightness[4, 6:46], 230, atol=40)
