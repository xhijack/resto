"""ESC/POS helpers for raw-printing Print Format templates.

Helpers return Latin-1 strings (bytes 0-255 preserved 1:1 via decode("latin-1")).
Templates concatenate these with regular text; the dispatcher does the final
`.encode("latin-1")` to obtain raw bytes for CUPS.

Why strings (not bytes): Frappe `render_template` returns str. Latin-1 round-trip
preserves all ESC/POS control bytes (\x1b, \x1d, etc.) without corruption.

Exposed to Jinja via `jinja.methods` in hooks.py.
"""
from __future__ import annotations

from typing import Iterable

ESC = "\x1b"
GS = "\x1d"


# ---------- ESC/POS primitives ----------

def esc_init() -> str:
    return ESC + "@"


def esc_align_left() -> str:
    return ESC + "a" + "\x00"


def esc_align_center() -> str:
    return ESC + "a" + "\x01"


def esc_align_right() -> str:
    return ESC + "a" + "\x02"


def esc_bold(on: bool = True) -> str:
    return ESC + "E" + ("\x01" if on else "\x00")


def esc_font_a() -> str:
    return ESC + "M" + "\x00"


def esc_font_b() -> str:
    return ESC + "M" + "\x01"


def esc_cut_full() -> str:
    """GS V 0 — full cut. Widely supported."""
    return GS + "V" + "\x00"


def esc_cut_full_with_feed() -> str:
    """GS V 65 — full cut with feed (Epson Function B)."""
    return GS + "V" + "\x41"


def esc_feed(n: int = 1) -> str:
    """Feed n lines (0-255)."""
    n = max(0, min(int(n), 255))
    return ESC + "d" + chr(n)


def esc_drawer() -> str:
    """Open cash drawer (ESC p 0 25 250)."""
    return ESC + "p" + "\x00" + "\x19" + "\xFA"


def esc_char_size(width_mul: int = 0, height_mul: int = 0) -> str:
    """Character size via GS ! n. Multipliers 0..7 → 1x..8x.

    Match the legacy private `_esc_char_size` API in printing.py (0-indexed).
    """
    w = max(0, min(7, int(width_mul)))
    h = max(0, min(7, int(height_mul)))
    return GS + "!" + chr((w << 4) | h)


def esc_char_size_dotmatrix(width_mul: int = 1, height_mul: int = 1) -> str:
    """Character size for dot-matrix printers via ESC ! n.

    width_mul, height_mul: 1 = normal, 2 = double. Bit 3 = double-height,
    bit 4 = double-width. Mirror of legacy `_esc_char_size_dotmatrix`.
    """
    w = 1 if int(width_mul) <= 1 else 2
    h = 1 if int(height_mul) <= 1 else 2
    n = ((h - 1) << 3) | ((w - 1) << 4)
    return ESC + "!" + chr(n)


def esc_qr(data: str) -> str:
    """ESC/POS QR (Model 2, size 4, error correction M)."""
    raw = (data or "").encode("utf-8")
    store_pL = (len(raw) + 3) & 0xFF
    store_pH = (len(raw) + 3) >> 8
    out = ""
    # Select model 2
    out += GS + "(" + "k" + "\x04\x00" + "1A" + "\x02\x00"
    # Size 4
    out += GS + "(" + "k" + "\x03\x00" + "1C" + "\x04"
    # Error correction M (0x31)
    out += GS + "(" + "k" + "\x03\x00" + "1E" + "\x31"
    # Store data
    out += GS + "(" + "k" + chr(store_pL) + chr(store_pH) + "1P0" + raw.decode("latin-1")
    # Print
    out += GS + "(" + "k" + "\x03\x00" + "1Q" + "\x30"
    return out


# ---------- Text layout helpers ----------

def line_separator(char: str = "-", width: int = 32) -> str:
    """Repeat `char` `width` times. Defaults to 32-col thermal width."""
    if not char:
        return ""
    return (char * width)[:width]


def pad_right(text: str, width: int, fill: str = " ") -> str:
    """Left-justify `text` in `width` columns."""
    text = "" if text is None else str(text)
    if len(text) >= width:
        return text[:width]
    return text + (fill or " ") * (width - len(text))


def pad_left(text: str, width: int, fill: str = " ") -> str:
    """Right-justify `text` in `width` columns."""
    text = "" if text is None else str(text)
    if len(text) >= width:
        return text[:width]
    return (fill or " ") * (width - len(text)) + text


def two_col(left: str, right: str, width: int = 32) -> str:
    """Single line `left ........ right` justified to `width` columns."""
    left = "" if left is None else str(left)
    right = "" if right is None else str(right)
    gap = width - len(left) - len(right)
    if gap < 1:
        return (left + " " + right)[:width]
    return left + " " * gap + right


def wrap_text(text: str, width: int) -> list[str]:
    """Greedy word wrap to `width` columns. Returns list of lines."""
    text = "" if text is None else str(text)
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + (1 if cur else 0) + len(w) <= width:
            cur = (cur + " " + w) if cur else w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, width: int) -> str:
    """Truncate to one line of exactly `width` (or fewer) cols."""
    text = "" if text is None else str(text)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def fmt_idr(value: float) -> str:
    """Indonesian Rupiah formatting: `Rp 12.345`."""
    try:
        n = int(round(float(value or 0)))
    except (TypeError, ValueError):
        n = 0
    s = f"{n:,}".replace(",", ".")
    return f"Rp {s}"


# ---------- Convenience aggregations ----------

def join_bytes(*parts: Iterable[str]) -> str:
    """Concatenate variadic string parts. Helper for Jinja {{ join_bytes(...) }}."""
    return "".join(str(p or "") for p in parts)
