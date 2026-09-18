"""Fullscreen mouse-drag region selection overlay (Snipping Tool style)."""

from __future__ import annotations

import tkinter as tk
import mss
from PIL import Image, ImageTk


def _virtual_monitor() -> dict:
    with mss.MSS() as sct:
        return dict(sct.monitors[0])


def _grab_virtual_screen() -> tuple[Image.Image, dict]:
    monitor = _virtual_monitor()
    with mss.MSS() as sct:
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return image, monitor


class SnipOverlay:
    """Modal fullscreen overlay that returns a cropped PIL image or None."""

    MIN_SIZE = 3

    def __init__(self, parent: tk.Misc) -> None:
        self._parent = parent
        self._result: Image.Image | None = None
        self._start: tuple[int, int] | None = None
        self._rect_id: int | None = None
        self._screen_image: Image.Image | None = None
        self._monitor: dict | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._top: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None

    def run(self) -> Image.Image | None:
        self._screen_image, self._monitor = _grab_virtual_screen()
        left = int(self._monitor["left"])
        top = int(self._monitor["top"])
        width = int(self._monitor["width"])
        height = int(self._monitor["height"])

        top_win = tk.Toplevel(self._parent)
        self._top = top_win
        top_win.withdraw()
        top_win.overrideredirect(True)
        top_win.attributes("-topmost", True)
        top_win.geometry(f"{width}x{height}+{left}+{top}")
        top_win.configure(cursor="crosshair", bg="black")

        canvas = tk.Canvas(
            top_win,
            width=width,
            height=height,
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
        self._rect_id = None

    def _on_drag(self, event: tk.Event) -> None:
        if self._start is None or self._canvas is None or self._screen_image is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)

        self._canvas.delete("selection")

        # Show the undimmed crop inside the selection rectangle.
        crop = self._screen_image.crop((left, top, right, bottom))
        if crop.width < 1 or crop.height < 1:
            return
        selection_photo = ImageTk.PhotoImage(crop)
        # Keep a reference so Tk does not garbage-collect the image.
        self._canvas._selection_photo = selection_photo  # type: ignore[attr-defined]
        self._rect_id = self._canvas.create_image(
            left, top, anchor=tk.NW, image=selection_photo, tags="selection"
        )
        self._canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline="#00B4FF",
            width=2,
            tags="selection",
        )

    def _on_release(self, event: tk.Event) -> None:
        if self._start is None or self._screen_image is None:
            self._finish(None)
            return

        x0, y0 = self._start
        x1, y1 = event.x, event.y
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        width = right - left
        height = bottom - top

        if width < self.MIN_SIZE or height < self.MIN_SIZE:
            self._finish(None)
            return

        cropped = self._screen_image.crop((left, top, right, bottom)).copy()
        self._finish(cropped)

    def _on_cancel(self, _event: tk.Event | None = None) -> None:
        self._finish(None)

    def _finish(self, image: Image.Image | None) -> None:
        self._result = image
        if self._top is not None:
            try:
                self._top.grab_release()
            except tk.TclError:
                pass
            self._top.destroy()
            self._top = None


def snip(parent: tk.Misc) -> Image.Image | None:
    """Run the snipping overlay and return the captured image, or None."""
    return SnipOverlay(parent).run()
