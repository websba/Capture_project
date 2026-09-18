"""Copy a PIL image to the Windows clipboard as CF_DIB."""

from __future__ import annotations

from io import BytesIO

import win32clipboard
from PIL import Image


def copy_image_to_clipboard(image: Image.Image) -> None:
    """Write *image* to the clipboard so it can be pasted into other apps."""
    rgb = image.convert("RGB")
    buffer = BytesIO()
    rgb.save(buffer, "BMP")
    data = buffer.getvalue()[14:]  # strip BITMAPFILEHEADER
    buffer.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()
