"""On-disk skill package inspection.

A skill's identity is the content of every file in its directory, not just its
``SKILL.md``.  Trust records bind to this hash so that editing a script or a
reference invalidates the trust the user granted.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

_INSTALL_MARKER = ".maestro-install.json"
_IGNORED_NAMES = {".DS_Store", _INSTALL_MARKER}


def iter_package_files(root: Path) -> tuple[Path, ...]:
    """Every content file of a skill package, in a stable order."""
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and not any(part in _IGNORED_NAMES for part in path.parts)
        )
    )


def package_stats(root: Path) -> tuple[int, int]:
    """`(file_count, bytes)` for a skill package directory."""
    files = iter_package_files(root)
    return len(files), sum(path.stat().st_size for path in files)


def compute_package_hash(root: Path) -> str:
    """Content hash over every file in the package, path included.

    Paths are folded in so that renaming a file changes the hash even when the
    bytes are unchanged.
    """
    digest = sha256()
    for path in iter_package_files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
