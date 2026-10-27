"""Shrinking options shared by the image and video engines.

--width / --height / --max describe a box the picture must fit into: images and
videos are only ever scaled down, never up, and keep their aspect ratio.
--small asks every encoder for a smaller file; --target-size aims a video at a
file size.
"""

import re

_UNITS = {"": 1, "b": 1, "k": 10 ** 3, "kb": 10 ** 3, "m": 10 ** 6, "mb": 10 ** 6,
          "g": 10 ** 9, "gb": 10 ** 9, "kib": 2 ** 10, "mib": 2 ** 20, "gib": 2 ** 30}


def parse_size(text):
    """'50MB', '1.5 GB', '700k', '2GiB' → bytes (MB = 1,000,000 bytes, like Finder)."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*", str(text))
    if not m or m.group(2).lower() not in _UNITS:
        raise ValueError(f"not a file size: {text!r} (examples: 50MB, 1.5GB, 700k)")
    value = float(m.group(1).replace(",", ".")) * _UNITS[m.group(2).lower()]
    if value <= 0:
        raise ValueError("the file size must be greater than zero")
    return int(value)


def box(opts):
    """(max width, max height) from --width/--height/--max; None means unlimited.

    Returns None when no size limit was asked for.
    """
    width = getattr(opts, "width", None)
    height = getattr(opts, "height", None)
    longest = getattr(opts, "max", None)
    if not (width or height or longest):
        return None
    w = min(v for v in (width, longest) if v) if (width or longest) else None
    h = min(v for v in (height, longest) if v) if (height or longest) else None
    return w, h


def fit(size, limit):
    """Size (w, h) scaled down into the box limit, aspect ratio kept, never enlarged."""
    w, h = size
    if not limit:
        return w, h
    bw, bh = limit
    scale = min(1.0, (bw / w) if bw else 1.0, (bh / h) if bh else 1.0)
    return max(1, round(w * scale)), max(1, round(h * scale))


def small(opts):
    return bool(getattr(opts, "small", False))


def target_size(opts):
    return getattr(opts, "target_size", None)


def shrinking(opts):
    """True when any shrink option is set."""
    return bool(box(opts) or small(opts) or target_size(opts))

