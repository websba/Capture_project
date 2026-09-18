"""Chrome ring geometry: overlap rails sit outside the capture hole."""

from __future__ import annotations

import tkinter as tk

import pytest
from PIL import Image

from app.long_snip import (
    DEFAULT_WHEEL_NOTCHES,
    FRAME_PX,
    OK_BAND_PX,
    OVERLAP_COLOR,
    SIDE_PX,
    _ChromeRing,
    _clamp_notches,
    _pack_lparam,
)
from app.snip_overlay import ScreenRect, Selection, VirtualMonitor
from app.vstitch import overlap_hint_rows


def test_overlap_rails_sit_outside_the_hole_and_match_hint_height() -> None:
    root = tk.Tk()
    root.withdraw()
    ring: _ChromeRing | None = None
    try:
        monitor = VirtualMonitor(0, 0, 1920, 1080)
        rect = ScreenRect(80, 80, 400, 300)
        seed = Image.new("RGB", (400, 300), (12, 24, 36))
        ring = _ChromeRing(root, Selection(monitor, rect, seed))
        ring._build()
        root.update_idletasks()

        hint = overlap_hint_rows(300)
        assert ring._size == (400 + 2 * SIDE_PX, 300 + 2 * FRAME_PX + OK_BAND_PX)
        assert ring._hole == (SIDE_PX, FRAME_PX, SIDE_PX + 400, FRAME_PX + 300)

        rails = [
            child
            for child in ring._top.winfo_children()
            if str(child.cget("bg")).lower() == OVERLAP_COLOR.lower()
        ]
        assert len(rails) == 4
        for rail in rails:
            assert int(str(rail.cget("width"))) == SIDE_PX
            assert int(str(rail.cget("height"))) == hint

        labels: list[str] = []

        def collect(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                if child.winfo_class() == "Button":
                    labels.append(str(child.cget("text")))
                collect(child)

        collect(ring._top)
        assert labels == ["OK", "↓", "↑"], labels

        spins: list[tk.Misc] = []

        def collect_spins(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                if child.winfo_class() == "Spinbox":
                    spins.append(child)
                collect_spins(child)

        collect_spins(ring._top)
        assert len(spins) == 1
        assert int(spins[0].get()) == DEFAULT_WHEEL_NOTCHES
    finally:
        if ring is not None and ring._top is not None:
            ring._on_cancel()
        root.destroy()


def test_pack_lparam_keeps_negative_virtual_desktop_coords() -> None:
    packed = _pack_lparam(-1820, 260) & 0xFFFFFFFF
    assert packed & 0xFFFF == (-1820 & 0xFFFF)
    assert (packed >> 16) & 0xFFFF == 260

    packed = _pack_lparam(40, -80) & 0xFFFFFFFF
    assert packed & 0xFFFF == 40
    assert (packed >> 16) & 0xFFFF == (-80 & 0xFFFF)


def test_clamp_notches_rejects_out_of_range_and_junk() -> None:
    assert _clamp_notches(3) == 3
    assert _clamp_notches(5) == 5
    assert _clamp_notches(0) == 1
    assert _clamp_notches(99) == 20
    assert _clamp_notches("") == DEFAULT_WHEEL_NOTCHES
    assert _clamp_notches("abc") == DEFAULT_WHEEL_NOTCHES


def test_scroll_buttons_use_the_notch_spinbox(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake_nudge(_rect: object, notches: int, _overlay: int = 0) -> None:
        seen.append(notches)

    monkeypatch.setattr("app.long_snip._nudge_target", fake_nudge)

    root = tk.Tk()
    root.withdraw()
    ring: _ChromeRing | None = None
    try:
        monitor = VirtualMonitor(0, 0, 1920, 1080)
        rect = ScreenRect(80, 80, 400, 300)
        seed = Image.new("RGB", (400, 300), (12, 24, 36))
        ring = _ChromeRing(root, Selection(monitor, rect, seed))
        ring._build()

        assert ring._notches() == DEFAULT_WHEEL_NOTCHES
        ring._on_scroll_down()
        ring._notches_var.set(5)
        ring._on_scroll_up()
        assert seen == [-DEFAULT_WHEEL_NOTCHES, 5]
    finally:
        if ring is not None and ring._top is not None:
            ring._on_cancel()
        root.destroy()
