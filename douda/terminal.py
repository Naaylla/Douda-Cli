"""Terminal capability detection, plain mode, and visible-width helpers."""

from __future__ import annotations

import os
import re
import sys
import unicodedata

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_UNICODE_PROBE = "\u25a0\u25c6\u265b\u2728\u2500\u2502\u250c"

try:  # pragma: no cover - exercised only when the optional dependency exists
    from wcwidth import wcwidth as _wcwidth
except ImportError:  # pragma: no cover - fallback is used in the common case
    _wcwidth = None

_configured = False
_force_plain = False
_ansi_enabled = os.name != "nt"
_utf8_ok = True


def _is_tty(stream: object | None = None) -> bool:
    stream = sys.stdout if stream is None else stream
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _stdout_supports_utf8(stream: object | None = None) -> bool:
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True
    try:
        _UNICODE_PROBE.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _enable_windows_ansi() -> bool:
    try:
        import colorama

        colorama.just_fix_windows_console()
        return True
    except Exception:
        pass

    try:
        os.system("")
    except Exception:
        return False

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def configure(force_plain: bool = False) -> None:
    """Detect terminal capabilities once, at program startup."""
    global _configured, _force_plain, _ansi_enabled, _utf8_ok
    _configured = True
    _force_plain = bool(force_plain)
    _utf8_ok = _stdout_supports_utf8()
    if os.name == "nt" and _is_tty():
        _ansi_enabled = _enable_windows_ansi()
    else:
        _ansi_enabled = True


def plain_mode() -> bool:
    if _force_plain:
        return True
    if not _configured:
        return False
    return not _ansi_enabled or not _utf8_ok


def reset() -> None:
    """Reset detection state (mainly useful for tests)."""
    global _configured, _force_plain, _ansi_enabled, _utf8_ok
    _configured = False
    _force_plain = False
    _ansi_enabled = os.name != "nt"
    _utf8_ok = True


def color_enabled(stream: object | None = None) -> bool:
    if plain_mode() or "NO_COLOR" in os.environ:
        return False
    return _is_tty(stream)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def char_width(character: str) -> int:
    if _wcwidth is not None:
        width = _wcwidth(character)
        return width if width and width > 0 else 0
    if unicodedata.combining(character):
        return 0
    return 2 if unicodedata.east_asian_width(character) in ("W", "F") else 1


def visible_width(text: str) -> int:
    return sum(char_width(character) for character in strip_ansi(text))


def pad_visible(text: str, width: int, align: str = "left") -> str:
    gap = width - visible_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def truncate_visible(text: str, width: int) -> str:
    if width <= 0:
        return ""
    result = []
    used = 0
    for character in text:
        size = char_width(character)
        if used + size > width:
            break
        result.append(character)
        used += size
    return "".join(result)
