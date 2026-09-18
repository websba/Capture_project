"""Compose captured images into a single collage by column count."""

from __future__ import annotations

from PIL import Image


def build_collage(images: list[Image.Image], columns: int) -> Image.Image:
    """Tile images left-to-right, top-to-bottom using *columns* per row.

    Each cell keeps the source image's native size. Cell width/height are the
    max width/height among images that fall in that column/row. Empty trailing
    cells in the last row remain white.
    """
    if not images:
        raise ValueError("images must not be empty")
    if columns < 1:
        raise ValueError("columns must be >= 1")

    rgb_images = [img.convert("RGB") for img in images]
    n = len(rgb_images)
    row_count = (n + columns - 1) // columns

    col_widths = [0] * columns
    row_heights = [0] * row_count

    for index, image in enumerate(rgb_images):
        row = index // columns
        col = index % columns
        col_widths[col] = max(col_widths[col], image.width)
        row_heights[row] = max(row_heights[row], image.height)

    total_width = sum(col_widths)
    total_height = sum(row_heights)
    canvas = Image.new("RGB", (total_width, total_height), color=(255, 255, 255))

    x_offsets = [0]
    for width in col_widths[:-1]:
        x_offsets.append(x_offsets[-1] + width)

    y_offsets = [0]
    for height in row_heights[:-1]:
        y_offsets.append(y_offsets[-1] + height)

    for index, image in enumerate(rgb_images):
        row = index // columns
        col = index % columns
        canvas.paste(image, (x_offsets[col], y_offsets[row]))

    return canvas
