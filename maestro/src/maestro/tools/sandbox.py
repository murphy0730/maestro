"""Containment for skill scripts (`run_script`) and shell commands (`run_command`).

This is defence in depth, **not** a security boundary.  The real gate is the
Policy Gate approval a human clicks — plus, for skill scripts, the content hash
the trust record binds to; this module only limits the blast radius of something
the user already approved.  `SandboxResult.isolation` reports what actually took
effect, so nothing downstream has to guess.

What always applies, on every platform:

- the process is spawned with `create_subprocess_exec`, so we never build a
  shell string ourselves (`run_command` hands the shell one opaque argument)
- the environment is rebuilt from an allowlist, so API keys are not inherited
- wall-clock and output-size limits are enforced
- `HOME`/`TMPDIR` point at a throwaway directory that is deleted afterwards

On macOS an additional `sandbox-exec` profile denies network access and
confines writes.  Windows has no equivalent, so only the baseline applies.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "TZ")
_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
_HOME_DIRECTORIES = ("Desktop", "Documents", "Downloads")
_INTERPRETERS = {".py": [sys.executable], ".sh": ["/bin/sh"]}

_probe_cache: bool | None = None


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    isolation: str
    artifacts: list[tuple[str, bytes]] = field(default_factory=list)


def _profile(run_root: Path, *extra_writable: Path) -> str:
    """A deny-by-default seatbelt profile allowing reads and scoped writes.

    Known gap: the whole `/private/var/folders` tree stays writable, because
    that is where macOS puts per-user temp state a sandboxed process still
    needs.  Writes elsewhere outside the named roots — `$HOME`, `/private/tmp`,
    the repository — are denied.  Reads are *not* restricted at all.
    """
    writable = "".join(
        f'(allow file-write* (subpath "{path}"))' for path in (run_root, *extra_writable)
    )
    return (
        "(version 1)"
        "(allow default)"
        "(deny network*)"
        f'(deny file-write* (subpath "/"))'
        f"{writable}"
        '(allow file-write* (subpath "/dev"))'
        '(allow file-write* (subpath "/private/var/folders"))'
    )


async def _seatbelt_available(run_root: Path) -> bool:
    """Probe once whether our profile is actually accepted by this host."""
    global _probe_cache
    if _probe_cache is not None:
        return _probe_cache
    if sys.platform != "darwin" or not _SANDBOX_EXEC.is_file():
        _probe_cache = False
        return False
    try:
        process = await asyncio.create_subprocess_exec(
            str(_SANDBOX_EXEC), "-p", _profile(run_root), "/usr/bin/true",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        _probe_cache = await process.wait() == 0
    except (OSError, ValueError):
        _probe_cache = False
    return _probe_cache


def _clip(raw: bytes) -> str:
    text = raw[:_MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    if len(raw) > _MAX_OUTPUT_BYTES:
        text += f"\n… 输出已截断（共 {len(raw)} 字节）"
    return text


def _collect(work: Path) -> list[tuple[str, bytes]]:
    """Copy anything the script produced out before the workspace is deleted."""
    produced: list[tuple[str, bytes]] = []
    for path in sorted(work.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            if path.stat().st_size > _MAX_ARTIFACT_BYTES:
                continue
            produced.append((path.relative_to(work).as_posix(), path.read_bytes()))
        except OSError:
            continue
    return produced


def _shell_argv(command: str) -> list[str]:
    """The interpreter that will read `command`.

    A shell is the whole point here, so unlike `run_script` the command string
    *is* interpreted.  What we still refuse to do is build that string ourselves
    from model input: the caller passes one opaque command and we hand it to the
    shell as a single argv element.
    """
    if sys.platform == "win32":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", command]
    return ["/bin/sh", "-c", command]


async def run_command(
    command: str, workdir: Path, timeout_seconds: float = 60.0
) -> SandboxResult:
    """Run one shell command with `workdir` as both cwd and the writable scope.

    Weaker than `run_script`: the command sees the real workspace rather than a
    throwaway copy, because operating on the workspace is the entire use.  It is
    also weaker than the filesystem capabilities, which can prove every path
    stays inside the workspace — a shell cannot offer that.  The real gate is the
    human approval the Policy Gate demands before each call; on macOS the
    seatbelt profile additionally denies network and confines writes to the
    workspace and the scratch root.
    """
    run_root = Path(tempfile.mkdtemp(prefix="maestro-shell-"))
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        for name in _HOME_DIRECTORIES:
            (run_root / name).mkdir(exist_ok=True)

        environment = {name: os.environ[name] for name in _ENV_ALLOWLIST if name in os.environ}
        environment["HOME"] = str(run_root)
        environment["TMPDIR"] = str(run_root)

        argv = _shell_argv(command)
        isolation = "baseline"
        if await _seatbelt_available(run_root):
            argv = [
                str(_SANDBOX_EXEC),
                "-p",
                _profile(run_root, workdir.resolve()),
                *argv,
            ]
            isolation = "seatbelt"

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(workdir),
                env=environment,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as error:
            return SandboxResult(
                exit_code=None, stdout="", stderr=f"无法执行命令: {error}",
                timed_out=False, isolation=isolation,
            )

        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            stdout, stderr = await process.communicate()

        return SandboxResult(
            exit_code=process.returncode,
            stdout=_clip(stdout or b""),
            stderr=_clip(stderr or b""),
            timed_out=timed_out,
            isolation=isolation,
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


async def run_script(
    package_root: Path, script: str, arguments: list[str], timeout_seconds: float = 60.0
) -> SandboxResult:
    """Run `script` from a copy of `package_root` inside a throwaway workspace."""
    suffix = Path(script).suffix.lower()
    interpreter = _INTERPRETERS.get(suffix)
    if interpreter is None:
        return SandboxResult(
            exit_code=None,
            stdout="",
            stderr=f"不支持的脚本类型: {suffix or script!r}（仅支持 .py / .sh）",
            timed_out=False,
            isolation="none",
        )

    run_root = Path(tempfile.mkdtemp(prefix="maestro-skill-"))
    try:
        # The script runs against a copy, so it can never mutate the installed
        # package that its own trust hash was computed over.
        package = run_root / "package"
        shutil.copytree(package_root, package, symlinks=False, ignore_dangling_symlinks=True)
        work = run_root / "work"
        work.mkdir()
        for name in _HOME_DIRECTORIES:
            (run_root / name).mkdir(exist_ok=True)

        environment = {name: os.environ[name] for name in _ENV_ALLOWLIST if name in os.environ}
        environment["HOME"] = str(run_root)
        environment["TMPDIR"] = str(run_root)
        environment["MAESTRO_SKILL_DIR"] = str(package)

        argv = [*interpreter, str(package / script), *arguments]
        isolation = "baseline"
        if await _seatbelt_available(run_root):
            argv = [str(_SANDBOX_EXEC), "-p", _profile(run_root), *argv]
            isolation = "seatbelt"

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(work),
                env=environment,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as error:
            return SandboxResult(
                exit_code=None, stdout="", stderr=f"无法启动脚本: {error}",
                timed_out=False, isolation=isolation,
            )

        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            stdout, stderr = await process.communicate()

        return SandboxResult(
            exit_code=process.returncode,
            stdout=_clip(stdout or b""),
            stderr=_clip(stderr or b""),
            timed_out=timed_out,
            isolation=isolation,
            # Must happen before the finally block removes run_root, or the
            # user sees "succeeded" with nothing to show for it.
            artifacts=_collect(work),
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
