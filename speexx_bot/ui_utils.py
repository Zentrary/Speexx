"""Terminal color styling and East-Asian/Thai display-width helpers."""

import re
import unicodedata

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

    class _DummyColor:
        def __getattr__(self, name):
            return ""

    Fore = _DummyColor()
    Style = _DummyColor()

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _char_display_width(ch):
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(text):
    clean = _ANSI_ESCAPE_RE.sub("", str(text or ""))
    return sum(_char_display_width(ch) for ch in clean)


def truncate_display(text, max_width, ellipsis="..."):
    s = str(text or "")
    if display_width(s) <= max_width:
        return s
    ell_w = display_width(ellipsis)
    target = max(0, max_width - ell_w)
    out = []
    cur = 0
    for ch in s:
        w = _char_display_width(ch)
        if cur + w > target:
            break
        out.append(ch)
        cur += w
    return "".join(out) + ellipsis


def pad_display(text, width, align="left"):
    s = str(text or "")
    pad = max(0, width - display_width(s))
    if align == "right":
        return (" " * pad) + s
    if align == "center":
        left = pad // 2
        return (" " * left) + s + (" " * (pad - left))
    return s + (" " * pad)
