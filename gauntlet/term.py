"""Terminal styling: status words in the same colors the HTML report uses.

Color is decoration, never information — every renderer produces plain text
and this module paints it afterwards. It only paints when the stream is a TTY,
honours NO_COLOR (https://no-color.org), and FORCE_COLOR overrides both.
"""
from __future__ import annotations

import os
import re
import sys
from typing import TextIO

_RESET = "\033[0m"
_STYLES = {
    "PASS": "\033[1;32m",       # bold green
    "WAIVED": "\033[1;33m",     # bold amber
    "FAIL": "\033[1;31m",       # bold red
    "TIMEOUT": "\033[1;35m",    # bold magenta
    "SKIPPED": "\033[2m",       # dim
    "REGRESSION": "\033[1;31m",
    "IMPROVED": "\033[1;32m",
    "CLEAN": "\033[1;32m",
    "NEW FAILURES": "\033[1;31m",
    "FIXED": "\033[1;32m",
    "STILL FAILING": "\033[1;33m",
}
_WORDS = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_STYLES, key=len, reverse=True)) + r")\b"
)
_TIMESTAMP = re.compile(r"^(\[\s*[\d.]+s\])")


def color_enabled(stream: TextIO | None = None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def paint(text: str, enabled: bool | None = None) -> str:
    """Color every status word in `text`; a no-op when color is off."""
    if enabled is None:
        enabled = color_enabled()
    if not enabled:
        return text
    lines = []
    for line in text.split("\n"):
        line = _TIMESTAMP.sub(lambda m: f"\033[2m{m.group(1)}{_RESET}", line)
        line = _WORDS.sub(lambda m: f"{_STYLES[m.group(1)]}{m.group(1)}{_RESET}", line)
        lines.append(line)
    return "\n".join(lines)
