"""`safe_join` is the single place a model-supplied path becomes a real path.

It had only indirect coverage through the filesystem tools, which left the
syntactic rejections — empty, UNC, drive letters, control characters — untested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maestro.runtime.paths import UnsafePathError, safe_join


@pytest.fixture
def root(tmp_path: Path) -> Path:
    base = tmp_path / "root"
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "file.txt").write_text("ok", "utf-8")
    return base


@pytest.mark.parametrize(
    "relative",
    [
        "",
        "..",
        "../outside.txt",
        "sub/../../outside.txt",
        "/etc/passwd",
        "//server/share",
        "\\\\server\\share",
        "C:/secret",
        "c:\\secret",
        "sub\\file.txt",
        "sub/\x00file",
        "sub/\x7ffile",
        "\x1bsub/file.txt",
    ],
)
def test_rejects_paths_that_escape_or_are_malformed(root: Path, relative: str) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(root, relative)


def test_accepts_a_path_inside_the_root(root: Path) -> None:
    assert safe_join(root, "sub/file.txt") == (root / "sub" / "file.txt").resolve()


def test_rejects_a_symlink_resolving_outside(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", "utf-8")
    (root / "link.txt").symlink_to(outside)

    with pytest.raises(UnsafePathError):
        safe_join(root, "link.txt")


def test_accepts_a_symlink_resolving_back_inside(root: Path) -> None:
    (root / "alias.txt").symlink_to(root / "sub" / "file.txt")

    assert safe_join(root, "alias.txt") == (root / "sub" / "file.txt").resolve()
