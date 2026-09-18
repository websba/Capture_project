"""Fold repeated views of one locked rect into a single tall strip.

Pure image math. No tkinter, no mss, no ctypes, so every case here is
reproducible from a synthetic page in a test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from hashlib import blake2b
from operator import sub
from typing import NewType, TypeAlias

from PIL import Image

ANCHOR_ROWS = 48
SIG_COLS = 8
OVERLAP_COLS = 32
MATCH_TOLERANCE = 6.0
OVERLAP_TOLERANCE = 8.0
REFINE_RADIUS = 16
SHIFT_AGREE = 2

FrameHash = NewType("FrameHash", bytes)


@dataclass(frozen=True)
class Frame:
    """One view of the locked rect.

    digest is derived from image, so Frame.of is the only legitimate
    constructor.
    """

    image: Image.Image
    digest: FrameHash

    @classmethod
    def of(cls, image: Image.Image) -> Frame:
        rgb = image if image.mode == "RGB" else image.convert("RGB")
        return cls(rgb, FrameHash(blake2b(rgb.tobytes(), digest_size=16).digest()))


class Edge(Enum):
    TOP = auto()
    BOTTOM = auto()


@dataclass(frozen=True)
class Camera:
    """Where the last accepted frame sits in the strip.

    height is the locked rect's height, so it never changes for one reel.
    """

    top: int
    height: int


@dataclass(frozen=True)
class Reel:
    """The accumulated column plus the camera that last matched it.

    last_view is a crop of strip rather than a second stored image, so the
    two cannot disagree about the pixels the next incremental match reads.
    """

    strip: Image.Image
    camera: Camera
    seen: frozenset[FrameHash]

    @classmethod
    def started(cls, seed: Frame) -> Reel:
        return cls(
            seed.image.copy(),
            Camera(0, seed.image.height),
            frozenset({seed.digest}),
        )

    @property
    def last_view(self) -> Image.Image:
        top = self.camera.top
        return self.strip.crop((0, top, self.strip.width, top + self.camera.height))


@dataclass(frozen=True)
class Unchanged:
    """Frame adds no rows."""

    reel: Reel


@dataclass(frozen=True)
class Grew:
    reel: Reel
    edge: Edge
    added_rows: int


@dataclass(frozen=True)
class Detached:
    """No overlap anywhere. Frame discarded, reel untouched."""

    reel: Reel


IngestResult: TypeAlias = Unchanged | Grew | Detached


def overlap_hint_rows(frame_height: int) -> int:
    """How tall the left/right overlap marks should be for this locked rect."""
    if frame_height < 1:
        return 1
    return min(ANCHOR_ROWS, max(1, frame_height // 3))


def ingest(reel: Reel, frame: Frame) -> IngestResult:
    """Fold one view of the locked rect into the reel.

    Pure and idempotent. Ingesting any frame already in reel.seen returns
    Unchanged carrying the same reel object.
    """
    if frame.digest in reel.seen:
        return Unchanged(reel)
    if frame.image.size != (reel.strip.width, reel.camera.height):
        return Detached(reel)

    target = _rows(frame.image)

    settled = _camera_inside_strip(reel, target)
    if settled is not None:
        return Unchanged(Reel(reel.strip, settled, reel.seen | {frame.digest}))

    seam = _seam(reel, frame.image, target)
    if seam is None:
        return Detached(reel)

    edge, added_rows, camera = seam
    strip = _grow(reel.strip, frame.image, edge, added_rows)
    return Grew(Reel(strip, camera, reel.seen | {frame.digest}), edge, added_rows)


def _rows(image: Image.Image, cols: int = SIG_COLS) -> bytes:
    """Every row reduced to *cols* averaged grayscale buckets, row-major.

    Row resolution is kept so a seam lands on an exact row. Columns collapse
    because the row search compares one band against every candidate row, and
    at full column width that scan costs hundreds of milliseconds per grab.
    """
    gray = image.convert("L")
    buckets = gray.resize((cols, gray.height), Image.Resampling.BOX)
    return buckets.tobytes()


def _band(rows: bytes, top: int, count: int) -> bytes:
    return rows[top * SIG_COLS : (top + count) * SIG_COLS]


def _locate(rows: bytes, band: bytes, still_row: int) -> tuple[int, float] | None:
    """Row of rows where band matches best, with its mean absolute error.

    still_row is the row that would mean the camera did not move. Ties go to
    the row nearest it, so a flat band cannot fabricate a scroll.
    """
    span = len(rows) // SIG_COLS - len(band) // SIG_COLS
    if span < 0:
        return None

    width = len(band)
    best: tuple[int, int, int] | None = None
    for row in range(span + 1):
        start = row * SIG_COLS
        error = sum(map(abs, map(sub, rows[start : start + width], band)))
        key = (error, abs(row - still_row), row)
        if best is None or key < best:
            best = key
            if error == 0 and row == still_row:
                break

    if best is None or best[0] > MATCH_TOLERANCE * width:
        return None
    return best[2], best[0] / width


def _camera_inside_strip(reel: Reel, target: bytes) -> Camera | None:
    """Where the frame lands when it is an incremental move that adds no rows.

    None when the move cannot be read off last_view, or when it spills past an
    edge of the strip. Spilling is growth, and _seam owns every seam.
    """
    height = reel.camera.height
    view = _rows(reel.last_view)
    anchor = min(ANCHOR_ROWS, height)
    floor = height - anchor

    shifts: list[tuple[float, int]] = []
    found = _locate(target, _band(view, 0, anchor), 0)
    if found is not None:
        shifts.append((found[1], -found[0]))
    found = _locate(target, _band(view, floor, anchor), floor)
    if found is not None:
        shifts.append((found[1], floor - found[0]))
    if not shifts:
        return None
    if len(shifts) == 2 and abs(shifts[0][1] - shifts[1][1]) > SHIFT_AGREE:
        return None

    _, shift = min(shifts)
    top = reel.camera.top + shift
    if top < 0 or top + height > reel.strip.height:
        return None
    return Camera(top, height)


def _seam(
    reel: Reel, view: Image.Image, target: bytes
) -> tuple[Edge, int, Camera] | None:
    """Which strip edge the frame extends, by how many rows, and where it lands."""
    strip = reel.strip
    height = reel.camera.height
    anchor = min(ANCHOR_ROWS, height, strip.height)
    floor = height - anchor
    head = strip.crop((0, 0, strip.width, anchor))
    tail = strip.crop((0, strip.height - anchor, strip.width, strip.height))

    seams: list[tuple[float, Edge, int, Camera]] = []
    found = _locate(target, _rows(head), 0)
    if found is not None and found[0] > 0:
        seams.append((found[1], Edge.TOP, found[0], Camera(0, height)))
    found = _locate(target, _rows(tail), floor)
    if found is not None and floor - found[0] > 0:
        camera = Camera(strip.height - anchor - found[0], height)
        seams.append((found[1], Edge.BOTTOM, floor - found[0], camera))
    if not seams:
        return None

    for _, edge, added_rows, camera in sorted(seams, key=lambda seam: seam[0]):
        refined = _refine_added(strip, view, edge, added_rows)
        if refined is not None:
            return edge, refined[0], refined[1]
    return None


def _overlap_mae(
    strip: Image.Image, view: Image.Image, edge: Edge, added_rows: int
) -> float | None:
    """Mean absolute error of the implied overlap after growing by added_rows."""
    overlap = view.height - added_rows
    if added_rows < 1 or overlap < 1:
        return None
    if edge is Edge.BOTTOM:
        old = strip.crop((0, strip.height - overlap, strip.width, strip.height))
        new = view.crop((0, 0, view.width, overlap))
    else:
        old = strip.crop((0, 0, strip.width, overlap))
        new = view.crop((0, added_rows, view.width, view.height))
    left = _rows(old, OVERLAP_COLS)
    right = _rows(new, OVERLAP_COLS)
    if len(left) != len(right) or not left:
        return None
    return sum(map(abs, map(sub, left, right))) / len(left)


def _refine_added(
    strip: Image.Image, view: Image.Image, edge: Edge, added_rows: int
) -> tuple[int, Camera] | None:
    """Walk nearby row counts and keep the one whose overlap actually matches.

    The coarse locator can land a few rows off on similar content. That extra
    delta is the duplicate band at the seam.
    """
    height = view.height
    lo = max(1, added_rows - REFINE_RADIUS)
    hi = min(height - 1, added_rows + REFINE_RADIUS)
    best: tuple[float, int, int] | None = None
    for added in range(lo, hi + 1):
        mae = _overlap_mae(strip, view, edge, added)
        if mae is None:
            continue
        key = (mae, abs(added - added_rows), added)
        if best is None or key < best:
            best = key
    if best is None or best[0] > OVERLAP_TOLERANCE:
        return None
    added = best[2]
    if edge is Edge.BOTTOM:
        camera = Camera(strip.height - height + added, height)
    else:
        camera = Camera(0, height)
    return added, camera


def _grow(
    strip: Image.Image, view: Image.Image, edge: Edge, added_rows: int
) -> Image.Image:
    """Extend strip at edge and paste the whole view over its matched span.

    Pasting the whole view, not only the novel rows, keeps Reel.last_view
    pixel-identical to the frame that produced it.
    """
    grown = Image.new("RGB", (strip.width, strip.height + added_rows))
    if edge is Edge.TOP:
        grown.paste(strip, (0, added_rows))
        grown.paste(view, (0, 0))
    else:
        grown.paste(strip, (0, 0))
        grown.paste(view, (0, grown.height - view.height))
    return grown
