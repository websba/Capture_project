"""Overlap cases for app.vstitch, driven from a synthetic tall page."""

from __future__ import annotations

import random

from PIL import Image

from app.vstitch import Detached, Edge, Frame, Grew, Reel, Unchanged, ingest

PAGE_HEIGHT = 1000
PAGE_WIDTH = 64
VIEW_HEIGHT = 200


def _page(seed: int) -> Image.Image:
    """A tall page whose every row is a unique flat colour."""
    rng = random.Random(seed)
    pixels = bytearray()
    for _ in range(PAGE_HEIGHT):
        row = bytes((rng.randrange(256), rng.randrange(256), rng.randrange(256)))
        pixels += row * PAGE_WIDTH
    return Image.frombytes("RGB", (PAGE_WIDTH, PAGE_HEIGHT), bytes(pixels))


def _view(page: Image.Image, top: int) -> Image.Image:
    return page.crop((0, top, PAGE_WIDTH, top + VIEW_HEIGHT))


def _frame(page: Image.Image, top: int) -> Frame:
    return Frame.of(_view(page, top))


def _span(page: Image.Image, top: int, bottom: int) -> bytes:
    return page.crop((0, top, PAGE_WIDTH, bottom)).tobytes()


def test_scroll_down_grows_the_bottom() -> None:
    page = _page(1)
    reel = Reel.started(_frame(page, 0))

    grown = ingest(reel, _frame(page, 150))

    assert isinstance(grown, Grew)
    assert grown.edge is Edge.BOTTOM
    assert grown.added_rows == 150
    assert grown.reel.strip.height == 350
    assert grown.reel.strip.tobytes() == _span(page, 0, 350)


def test_re_ingesting_the_same_frame_returns_the_same_reel() -> None:
    page = _page(1)
    reel = Reel.started(_frame(page, 0))
    frame = _frame(page, 150)

    grown = ingest(reel, frame)
    again = ingest(grown.reel, frame)

    assert isinstance(again, Unchanged)
    assert again.reel is grown.reel
    assert again.reel.strip.height == 350


def test_scroll_up_grows_the_top() -> None:
    page = _page(2)
    reel = Reel.started(_frame(page, 300))

    grown = ingest(reel, _frame(page, 180))

    assert isinstance(grown, Grew)
    assert grown.edge is Edge.TOP
    assert grown.added_rows == 120
    assert grown.reel.strip.height == 320
    assert grown.reel.strip.tobytes() == _span(page, 180, 500)


def test_the_seed_frame_again_is_a_no_op() -> None:
    page = _page(3)
    seed = _frame(page, 400)
    reel = Reel.started(seed)

    result = ingest(reel, seed)

    assert isinstance(result, Unchanged)
    assert result.reel is reel
    assert reel.strip.height == 200


def test_an_unrelated_frame_leaves_the_reel_untouched() -> None:
    page = _page(4)
    reel = Reel.started(_frame(page, 0))

    result = ingest(reel, _frame(_page(5), 0))

    assert isinstance(result, Detached)
    assert result.reel is reel
    assert reel.strip.height == 200


def test_scrolling_back_into_the_middle_then_further_up() -> None:
    page = _page(6)
    reel = Reel.started(_frame(page, 300))

    grown = ingest(reel, _frame(page, 450))
    assert isinstance(grown, Grew)
    assert grown.added_rows == 150
    assert grown.reel.strip.height == 350

    middle = ingest(grown.reel, _frame(page, 320))
    assert isinstance(middle, Unchanged)
    assert middle.reel.strip.height == 350

    higher = ingest(middle.reel, _frame(page, 260))
    assert isinstance(higher, Grew)
    assert higher.edge is Edge.TOP
    assert higher.added_rows == 40
    assert higher.reel.strip.height == 390
    assert higher.reel.strip.tobytes() == _span(page, 260, 650)
