import pytest
from PIL import Image

from server.framebuffer import (
    BUFFER_SIZE,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    X_ALIGNMENT,
    dirty_region,
    from_panel_buffer,
    to_monochrome,
    to_panel_buffer,
)


def test_buffer_is_exactly_one_bit_per_pixel(blank):
    assert len(to_panel_buffer(blank)) == BUFFER_SIZE == PANEL_WIDTH * PANEL_HEIGHT // 8


def test_buffer_survives_a_round_trip(blank):
    blank.putpixel((13, 7), 0)
    restored = from_panel_buffer(to_panel_buffer(blank))
    assert restored.getpixel((13, 7)) == 0
    assert restored.getpixel((14, 7)) == 255


def test_wrong_size_is_refused():
    with pytest.raises(ValueError, match="800x480"):
        to_panel_buffer(Image.new("1", (100, 100), 1))


def test_monochrome_leaves_no_grey():
    grey = Image.new("L", (PANEL_WIDTH, PANEL_HEIGHT), 130)
    assert set(to_monochrome(grey).convert("L").getdata()) <= {0, 255}


def test_identical_frames_need_no_update(blank):
    assert dirty_region(blank, blank.copy()) is None


def test_first_frame_redraws_everything(blank):
    assert dirty_region(None, blank) == (0, 0, PANEL_WIDTH, PANEL_HEIGHT)


def test_region_is_snapped_to_a_byte_boundary(blank):
    changed = blank.copy()
    changed.putpixel((100, 50), 0)
    x, y, width, height = dirty_region(blank, changed)
    assert x % X_ALIGNMENT == 0 and width % X_ALIGNMENT == 0
    assert x <= 100 < x + width
    assert (y, height) == (50, 1)


def test_region_never_runs_past_the_panel(blank):
    changed = blank.copy()
    changed.putpixel((PANEL_WIDTH - 1, 10), 0)
    x, _, width, _ = dirty_region(blank, changed)
    assert x + width <= PANEL_WIDTH


def test_large_changes_fall_back_to_a_full_redraw(blank):
    changed = Image.new("1", (PANEL_WIDTH, PANEL_HEIGHT), 0)
    assert dirty_region(blank, changed) == (0, 0, PANEL_WIDTH, PANEL_HEIGHT)
