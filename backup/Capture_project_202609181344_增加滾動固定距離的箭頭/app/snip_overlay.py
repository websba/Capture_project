"""Fullscreen mouse-drag region selection overlay (Snipping Tool style)."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

import mss
from PIL import Image, ImageTk

MIN_SIZE = 3


@dataclass(frozen=True)
class CanvasRect:
    """Overlay-canvas pixels. The overlay's own top-left is always (0, 0)."""

    left: int
    top: int
    width: int
    height: int

    @classmethod
    def spanning(cls, a: tuple[int, int], b: tuple[int, int]) -> CanvasRect:
        """Only producer of a CanvasRect, so width and height are never negative."""
        left, right = sorted((a[0], b[0]))
        top, bottom = sorted((a[1], b[1]))
        return cls(left, top, right - left, bottom - top)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.left + self.width, self.top + self.height)


@dataclass(frozen=True)
class ScreenRect:
    """Virtual-desktop pixels. Produced only by VirtualMonitor.to_screen."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class VirtualMonitor:
    """mss monitors[0]. left and top are negative when a monitor sits up or left."""

    left: int
    top: int
    width: int
    height: int

    @classmethod
    def current(cls) -> VirtualMonitor:
        with mss.MSS() as sct:
            area = sct.monitors[0]
        return cls(
            int(area["left"]),
            int(area["top"]),
            int(area["width"]),
            int(area["height"]),
        )

    def to_screen(self, rect: CanvasRect) -> ScreenRect:
        return ScreenRect(
            self.left + rect.left, self.top + rect.top, rect.width, rect.height
        )


@dataclass(frozen=True)
class Selection:
    """What the user drew, plus the pixels that were under it at that moment.

    frame.size == (rect.width, rect.height).
    """

    monitor: VirtualMonitor
    rect: ScreenRect
    frame: Image.Image


def _grab_virtual_screen() -> tuple[Image.Image, VirtualMonitor]:
    monitor = VirtualMonitor.current()
    area = {
        "left": monitor.left,
        "top": monitor.top,
        "width": monitor.width,
        "height": monitor.height,
    }
    with mss.MSS() as sct:
        shot = sct.grab(area)
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return image, monitor


class SnipOverlay:
    """Modal fullscreen overlay that returns a Selection or None."""

    def __init__(self, parent: tk.Misc) -> None:
        self._parent = parent
        self._result: Selection | None = None
        self._start: tuple[int, int] | None = None
        self._screen_image: Image.Image | None = None
        self._monitor: VirtualMonitor | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._top: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None

    def run(self) -> Selection | None:
        self._screen_image, self._monitor = _grab_virtual_screen()
        monitor = self._monitor

        top_win = tk.Toplevel(self._parent)
        self._top = top_win
        top_win.withdraw()
        top_win.overrideredirect(True)
        top_win.attributes("-topmost", True)
        top_win.geometry(
            f"{monitor.width}x{monitor.height}+{monitor.left}+{monitor.top}"
        )
        top_win.configure(cursor="crosshair", bg="black")

        canvas = tk.Canvas(
            top_win,
            width=monitor.width,
            height=monitor.height,
            highlightthickness=0,
            cursor="crosshair",
            bg="black",
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas = canvas

        # Dimmed full-screen background so the selection area stands out.
        dimmed = self._screen_image.point(lambda p: int(p * 0.45))
        self._photo = ImageTk.PhotoImage(dimmed)
        canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        top_win.bind("<Escape>", self._on_cancel)
        top_win.bind("<ButtonPress-3>", self._on_cancel)

        top_win.deiconify()
        top_win.lift()
        top_win.focus_force()
        top_win.grab_set()
        self._parent.wait_window(top_win)
        return self._result

    def _on_press(self, event: tk.Event) -> None:
        self._start = (event.x, event.y)
        if self._canvas is not None:
            self._canvas.delete("selection")

    def _on_drag(self, event: tk.Event) -> None:
        if self._start is None or self._canvas is None or self._screen_image is None:
            return
        rect = CanvasRect.spanning(self._start, (event.x, event.y))

        self._canvas.delete("selection")
        if rect.width < 1 or rect.height < 1:
            return

        # Show the undimmed crop inside the selection rectangle.
        selection_photo = ImageTk.PhotoImage(self._screen_image.crop(rect.box))
        # Keep a reference so Tk does not garbage-collect the image.
        self._canvas._selection_photo = selection_photo  # type: ignore[attr-defined]
        self._canvas.create_image(
            rect.left, rect.top, anchor=tk.NW, image=selection_photo, tags="selection"
        )
        self._canvas.create_rectangle(
            rect.left,
            rect.top,
            rect.left + rect.width,
            rect.top + rect.height,
            outline="#00B4FF",
            width=2,
            tags="selection",
        )

    def _on_release(self, event: tk.Event) -> None:
        if (
            self._start is None
            or self._screen_image is None
            or self._monitor is None
        ):
            self._finish(None)
            return

        rect = CanvasRect.spanning(self._start, (event.x, event.y))
        if rect.width < MIN_SIZE or rect.height < MIN_SIZE:
            self._finish(None)
            return

        frame = self._screen_image.crop(rect.box).copy()
        self._finish(Selection(self._monitor, self._monitor.to_screen(rect), frame))

    def _on_cancel(self, _event: tk.Event | None = None) -> None:
        self._finish(None)

    def _finish(self, selection: Selection | None) -> None:
        self._result = selection
        if self._top is not None:
            try:
                self._top.grab_release()
            except tk.TclError:
                pass
            self._top.destroy()
            self._top = None


def select_region(parent: tk.Misc) -> Selection | None:
    """Run the dimmed fullscreen overlay and return what the user framed.

    None on Esc, right-click, or a rect smaller than MIN_SIZE in either axis.
    """
    return SnipOverlay(parent).run()


def snip(parent: tk.Misc) -> Image.Image | None:
    """Run the snipping overlay and return the captured image, or None."""
    selection = select_region(parent)
    return None if selection is None else selection.frame
