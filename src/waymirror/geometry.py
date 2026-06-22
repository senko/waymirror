"""Pure geometry helpers.

Deliberately free of GTK/GStreamer/portal imports so they can be unit-tested
without a display or the native stack.
"""

import re

_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?")


def parse_geometry(spec):
    """Parse an X-style geometry 'WxH+X+Y' (the +X+Y offset is optional/signed).

    Returns (w, h, x, y). Raises ValueError on malformed input.
    """
    m = _GEOMETRY_RE.fullmatch(spec.strip())
    if not m:
        raise ValueError(
            f"invalid geometry: {spec!r} (expected e.g. 800x600+100+100)"
        )
    w, h = int(m.group(1)), int(m.group(2))
    x = int(m.group(3)) if m.group(3) is not None else 0
    y = int(m.group(4)) if m.group(4) is not None else 0
    if w <= 0 or h <= 0:
        raise ValueError(
            f"invalid geometry: {spec!r} (width and height must be > 0)"
        )
    return w, h, x, y


def resolve_half(side, monitor_rect):
    """Resolve 'left'/'right' into a concrete (w, h, x, y) for a monitor.

    monitor_rect is (x, y, w, h) in logical coordinates. Odd widths split
    cleanly: left gets floor(w/2), right gets the remainder.
    """
    mx, my, mw, mh = monitor_rect
    half_w = mw // 2
    if side == "left":
        return (half_w, mh, mx, my)
    if side == "right":
        return (mw - half_w, mh, mx + half_w, my)
    raise ValueError(f"unknown side: {side!r} (expected 'left' or 'right')")


def normalize_rect(x0, y0, x1, y1, origin=(0, 0), bounds=None):
    """Turn two drag corners into a global region (w, h, x, y).

    x0,y0 / x1,y1: the drag's start/end in monitor-local logical coordinates;
        either drag direction works.
    origin: the monitor's (x, y) in global logical coordinates, added so the
        result is in the same global space as parse_geometry's output.
    bounds: the monitor's (w, h) to clamp the rectangle within, or None for no
        clamping.

    Returns (w, h, gx, gy). w/h may be 0 for a click (caller decides what that
    means).
    """
    left = round(min(x0, x1))
    top = round(min(y0, y1))
    right = round(max(x0, x1))
    bottom = round(max(y0, y1))
    if bounds is not None:
        bw, bh = bounds
        left = max(0, min(left, bw))
        right = max(0, min(right, bw))
        top = max(0, min(top, bh))
        bottom = max(0, min(bottom, bh))
    ox, oy = origin
    return right - left, bottom - top, left + ox, top + oy


def compute_crop(buffer_w, buffer_h, monitor_rect, geometry):
    """Crop (left, top, right, bottom) to extract `geometry` from a monitor buffer.

    buffer_w/buffer_h: negotiated pixel size of the captured monitor frame.
    monitor_rect: (x, y, w, h) logical monitor rect, or None (assume the region
        is already relative to the buffer at scale 1).
    geometry: (w, h, x, y) desired region in logical coordinates.

    The scale factor (buffer pixels / logical size) makes this HiDPI-aware.
    """
    gw, gh, gx, gy = geometry
    if monitor_rect:
        mx, my, mw, mh = monitor_rect
        sx = buffer_w / mw if mw else 1.0
        sy = buffer_h / mh if mh else 1.0
    else:
        mx = my = 0
        sx = sy = 1.0

    left = max(0, round((gx - mx) * sx))
    top = max(0, round((gy - my) * sy))
    right = max(0, buffer_w - round((gx - mx + gw) * sx))
    bottom = max(0, buffer_h - round((gy - my + gh) * sy))

    # keep at least 1px of picture in each dimension
    if left + right >= buffer_w:
        right = max(0, buffer_w - left - 1)
    if top + bottom >= buffer_h:
        bottom = max(0, buffer_h - top - 1)
    return left, top, right, bottom


def fit_within_bounds(desired_w, desired_h, bounds_w, bounds_h):
    """Largest (w, h) keeping desired_w:desired_h aspect ratio that fits bounds.

    A bound <= 0 means 'unconstrained' on that axis. Used to keep the window the
    right shape when the compositor caps it to the work area (no letterboxing).
    """
    if desired_h <= 0:
        return desired_w, desired_h
    ratio = desired_w / desired_h
    w = float(desired_w)
    h = float(desired_h)
    if bounds_w > 0 and w > bounds_w:
        w = bounds_w
        h = w / ratio
    if bounds_h > 0 and h > bounds_h:
        h = bounds_h
        w = h * ratio
    return max(1, round(w)), max(1, round(h))
