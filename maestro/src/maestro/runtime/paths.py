"""Confining model-supplied paths to a root directory.

Every path a model produces is untrusted input.  This module is the single
place that turns such a string into a real path, so skill resources and
filesystem tools cannot drift apart on what counts as safe.
"""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


class UnsafePathError(ValueError):
    """A model-supplied path escaped, or tried to escape, its root."""


def safe_join(root: Path, relative: str) -> Path:
    """Resolve `relative` under `root`, refusing anything that could escape.

    Rejects absolute paths, UNC paths, Windows drive letters, backslashes,
    Unicode control characters and `..` segments up front, then re-checks the
    resolved result against the resolved root so that a symlink pointing
    outside is caught too.
    """
    if (
        not relative
        or Path(relative).is_absolute()
        or relative.startswith(("//", "\\\\"))
        or _WINDOWS_DRIVE.match(relative)
        or "\\" in relative
    ):
        raise UnsafePathError(f"unsafe path: {relative!r}")
    if any(unicodedata.category(char) == "Cc" for char in relative):
        raise UnsafePathError(f"unsafe path: {relative!r}")
    if ".." in Path(relative).parts:
        raise UnsafePathError(f"unsafe path: {relative!r}")
    base = root.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise UnsafePathError(f"unsafe path: {relative!r}")
    return target
