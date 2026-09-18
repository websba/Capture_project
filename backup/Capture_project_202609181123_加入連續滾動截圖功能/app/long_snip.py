"""Long screenshot. A chrome ring around a locked rect, wheel goes to the target.

The overlay is only the cyan frame and the OK band. SetWindowRgn cuts the
capture interior out of the HWND, so every wheel notch and click inside it
belongs to whatever window sits below.
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes

import mss
from PIL import Image

from app.snip_overlay import ScreenRect, Selection, select_region
from app.vstitch import Detached, Frame, FrameHash, Reel, ingest

FRAME_PX = 3
OK_BAND_PX = 36
POLL_MS = 60
RING_COLOR = "#00E5FF"
BAND_COLOR = "#101010"

GWL_EXSTYLE = -20
RGN_DIFF = 4
VK_ESCAPE = 0x1B
WS_EX_NOACTIVATE = 0x08000000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

_user32.GetParent.argtypes = (wintypes.HWND,)
_user32.GetParent.restype = wintypes.HWND
_user32.SetWindowRgn.argtypes = (wintypes.HWND, wintypes.HRGN, wintypes.BOOL)
_user32.SetWindowRgn.restype = ctypes.c_int
_user32.WindowFromPoint.argtypes = (wintypes.POINT,)
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short

_gdi32.CreateRectRgn.argtypes = (ctypes.c_int,) * 4
_gdi32.CreateRectRgn.restype = wintypes.HRGN
_gdi32.CombineRgn.argtypes = (
    wintypes.HRGN,
    wintypes.HRGN,
    wintypes.HRGN,
    ctypes.c_int,
)
_gdi32.CombineRgn.restype = ctypes.c_int
_gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
_gdi32.DeleteObject.restype = wintypes.BOOL

# 32-bit builds only export the non-Ptr spelling.
_get_window_long = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
_set_window_long = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
_get_window_long.argtypes = (wintypes.HWND, ctypes.c_int)
_get_window_long.restype = ctypes.c_ssize_t
_set_window_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
_set_window_long.restype = ctypes.c_ssize_t


def _window_handle(win: tk.Toplevel) -> int:
    """Tk hangs a toplevel inside a wrapper HWND, and the wrapper owns the region."""
    child = int(win.winfo_id())
    wrapper = _user32.GetParent(child)
    return int(wrapper) if wrapper else child


def _open_hole(hwnd: int, size: tuple[int, int], hole: tuple[int, int, int, int]) -> None:
    width, height = size
    ring = _gdi32.CreateRectRgn(0, 0, width, height)
    cut = _gdi32.CreateRectRgn(*hole)
    _gdi32.CombineRgn(ring, ring, cut, RGN_DIFF)
    _gdi32.DeleteObject(cut)
    # Windows takes ownership of the region once SetWindowRgn accepts it.
    if not _user32.SetWindowRgn(hwnd, ring, True):
        _gdi32.DeleteObject(ring)


def _stop_stealing_focus(hwnd: int) -> None:
    style = _get_window_long(hwnd, GWL_EXSTYLE)
    _set_window_long(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)


def _focus_target_under(rect: ScreenRect) -> None:
    """The wheel follows keyboard focus when Windows hover-scroll is off."""
    centre = wintypes.POINT(
        rect.left + rect.width // 2, rect.top + rect.height // 2
    )
    target = _user32.WindowFromPoint(centre)
    if target:
        _user32.SetForegroundWindow(target)


def _escape_held() -> bool:
    return bool(_user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


class _ChromeRing:
    """Cyan frame plus an OK band around a locked rect whose interior is a hole."""

    def __init__(self, parent: tk.Misc, selection: Selection) -> None:
        seed = Frame.of(selection.frame)
        self._parent = parent
        self._rect = selection.rect
        self._monitor = selection.monitor
        self._reel = Reel.started(seed)
        self._result: Image.Image | None = None
        self._status = tk.StringVar()
        self._top: tk.Toplevel | None = None
        self._size = (0, 0)
        self._hole = (0, 0, 0, 0)
        self._after_id: str | None = None
        self._wheel_script = ""
        # Digest of the previous grab, and of the last one handed to ingest. A
        # Detached frame never enters reel.seen, so without the second the same
        # rejected view would be re-searched on every tick.
        self._previous: FrameHash | None = None
        self._ingested: FrameHash | None = seed.digest
        self._shots = mss.MSS()

    def run(self) -> Image.Image | None:
        self._build()
        self._arm()
        self._report()
        self._tick()
        win = self._top
        if win is not None:
            self._parent.wait_window(win)
        return self._result

    def _build(self) -> None:
        rect = self._rect
        below = (
            rect.top + rect.height + FRAME_PX + OK_BAND_PX
            <= self._monitor.top + self._monitor.height
        )
        band_above = 0 if below else OK_BAND_PX
        width = rect.width + 2 * FRAME_PX
        height = rect.height + 2 * FRAME_PX + OK_BAND_PX
        left = rect.left - FRAME_PX
        top = rect.top - FRAME_PX - band_above

        win = tk.Toplevel(self._parent)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=RING_COLOR)
        win.geometry(f"{width}x{height}+{left}+{top}")

        band = tk.Frame(win, bg=BAND_COLOR, height=OK_BAND_PX)
        band.pack(side=tk.BOTTOM if below else tk.TOP, fill=tk.X)
        band.pack_propagate(False)

        tk.Label(
            band,
            textvariable=self._status,
            bg=BAND_COLOR,
            fg="#FFFFFF",
            anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(10, 0))
        tk.Button(
            band,
            text="OK",
            width=6,
            bd=0,
            bg="#00B4FF",
            fg="#FFFFFF",
            activebackground="#0090CC",
            activeforeground="#FFFFFF",
            cursor="hand2",
            command=self._on_ok,
        ).pack(side=tk.RIGHT, padx=10, pady=5)

        win.bind("<Escape>", self._on_cancel)
        win.bind("<ButtonPress-3>", self._on_cancel)

        # The gallery scrolls on <MouseWheel> through bind_all, which would
        # swallow notches aimed at the target. Tk hands the script back so it
        # can be reinstated verbatim.
        self._wheel_script = self._parent.bind_all("<MouseWheel>")
        self._parent.unbind_all("<MouseWheel>")

        self._top = win
        self._size = (width, height)
        self._hole = (
            FRAME_PX,
            FRAME_PX + band_above,
            FRAME_PX + rect.width,
            FRAME_PX + band_above + rect.height,
        )

    def _arm(self) -> None:
        win = self._top
        if win is None:
            return
        win.deiconify()
        win.lift()
        win.update_idletasks()
        hwnd = _window_handle(win)
        _stop_stealing_focus(hwnd)
        _open_hole(hwnd, self._size, self._hole)
        _focus_target_under(self._rect)

    def _tick(self) -> None:
        self._after_id = None
        win = self._top
        if win is None:
            return
        if _escape_held():
            self._on_cancel()
            return

        frame = Frame.of(self._grab())
        # Two equal grabs in a row mean the target is not mid-animation.
        if frame.digest == self._previous and frame.digest != self._ingested:
            self._ingested = frame.digest
            self._absorb(frame)
        self._previous = frame.digest

        if self._top is not None:
            self._after_id = win.after(POLL_MS, self._tick)

    def _grab(self) -> Image.Image:
        rect = self._rect
        shot = self._shots.grab(
            {
                "left": rect.left,
                "top": rect.top,
                "width": rect.width,
                "height": rect.height,
            }
        )
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def _absorb(self, frame: Frame) -> None:
        result = ingest(self._reel, frame)
        self._reel = result.reel
        if isinstance(result, Detached):
            self._status.set("請往回捲一點再試")
        else:
            self._report()

    def _report(self) -> None:
        self._status.set(f"已接 {self._reel.strip.height} 列")

    def _on_ok(self) -> None:
        self._finish(self._reel.strip)

    def _on_cancel(self, _event: tk.Event | None = None) -> None:
        self._finish(None)

    def _finish(self, image: Image.Image | None) -> None:
        win = self._top
        if win is None:
            return
        self._top = None
        self._result = image
        if self._after_id is not None:
            win.after_cancel(self._after_id)
            self._after_id = None
        if self._wheel_script:
            self._parent.bind_all("<MouseWheel>", self._wheel_script)
        self._shots.close()
        win.destroy()


def long_snip(parent: tk.Misc) -> Image.Image | None:
    """Frame a rect, scroll the window under it, return one tall image.

    None only on cancel. Committing without scrolling yields the seed frame.
    Signature matches snip so MainWindow drives both buttons through one path.
    """
    selection = select_region(parent)
    if selection is None:
        return None
    return _ChromeRing(parent, selection).run()
