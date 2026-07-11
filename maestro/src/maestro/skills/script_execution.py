"""Execute trusted Skill scripts from an immutable per-run snapshot."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

from maestro.execution.srt import SrtRuntime
from maestro.skills.schemas import SkillValidationError
from maestro.skills.store import SkillStore


class SkillScriptExecutionService:
    def __init__(
        self,
        store: SkillStore,
        output_dir: Path,
        skills_dir: Path,
        timeout_seconds: int = 15,
        max_output_bytes: int = 65536,
        srt: SrtRuntime | None = None,
    ):
        self._store = store
        self._output_dir = Path(output_dir)
        self._skills_dir = Path(skills_dir)
        self._timeout = timeout_seconds
        self._max_output = max_output_bytes
        self._srt = srt or SrtRuntime()

    def _validate(self, params: dict) -> tuple[str, str, list[str]]:
        skill_id = str(params.get("skill_id", ""))
        script = str(params.get("script", ""))
        package_hash = str(params.get("package_sha256", ""))
        args = params.get("args", [])
        if not isinstance(args, list) or len(args) > 32 or not all(isinstance(arg, str) for arg in args):
            raise SkillValidationError("脚本参数必须是最多 32 项的字符串数组")
        if any(len(arg) > 2048 or "\x00" in arg for arg in args):
            raise SkillValidationError("脚本参数非法或过长")
        meta = self._store.get(skill_id)
        if meta is None:
            raise SkillValidationError(f"技能 {skill_id} 不存在")
        if not self._store.is_trusted(skill_id, package_hash):
            raise SkillValidationError("技能当前版本未被本地用户信任")
        if script not in meta.scripts:
            raise SkillValidationError("只能执行 SKILL.md 声明或 scripts/ 下已识别的脚本")
        path = Path(script)
        if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in {".py", ".js"}:
            raise SkillValidationError("仅允许包内 .py/.js 脚本")
        return skill_id, script, list(args)

    async def execute(self, params: dict) -> dict:
        skill_id, script, args = self._validate(params)
        files = self._store.snapshot_files(skill_id)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        run_root = Path(tempfile.mkdtemp(prefix=f"skill-{skill_id}-", dir=self._output_dir))
        workspace = run_root / "workspace"
        workspace.mkdir()
        snapshot = workspace / "input"
        snapshot.mkdir()
        try:
            for rel, content in files.items():
                target = snapshot / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            script_path = (snapshot / script).resolve()
            if not script_path.is_relative_to(snapshot.resolve()) or not script_path.is_file():
                raise SkillValidationError("脚本文件不存在于可信快照")
            interpreter = sys.executable if script_path.suffix.lower() == ".py" else shutil.which("node")
            if not interpreter:
                raise SkillValidationError("未安装 Node.js，无法执行 JavaScript Skill 脚本")
            argv = [str(interpreter), str(script_path), *args]
            protected = [self._skills_dir, Path.home() / ".ssh", Path.home() / ".aws"]
            sandboxed = self._srt.available and await self._srt.check_usable(workspace, protected)
            settings_path: Path | None = None
            if sandboxed:
                argv, settings_path = self._srt.wrap(argv, workspace, protected)
            started = time.monotonic()
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(workspace),
                "USERPROFILE": str(workspace),
                "TMP": str(workspace),
                "TEMP": str(workspace),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            if os.name == "nt" and os.environ.get("SystemRoot"):
                env["SystemRoot"] = os.environ["SystemRoot"]
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workspace,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=os.name != "nt",
            )
            captured = {"stdout": bytearray(), "stderr": bytearray()}
            total_seen = 0
            truncated = False

            async def pump(stream, name: str) -> None:
                nonlocal total_seen, truncated
                while chunk := await stream.read(4096):
                    total_seen += len(chunk)
                    remaining = self._max_output - sum(len(value) for value in captured.values())
                    if remaining > 0:
                        captured[name].extend(chunk[:remaining])
                    if total_seen > self._max_output:
                        truncated = True

            pumps = [
                asyncio.create_task(pump(process.stdout, "stdout")),
                asyncio.create_task(pump(process.stderr, "stderr")),
            ]
            try:
                await asyncio.wait_for(process.wait(), timeout=self._timeout)
                await asyncio.gather(*pumps)
            except TimeoutError:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
                await asyncio.gather(*pumps)
                return {
                    "status": "timed_out",
                    "execution_mode": "srt" if sandboxed else "guarded_host",
                    "timeout_seconds": self._timeout,
                }
            finally:
                if settings_path is not None:
                    settings_path.unlink(missing_ok=True)
            return {
                "status": "completed" if process.returncode == 0 else "failed",
                "execution_mode": "srt" if sandboxed else "guarded_host",
                "exit_code": process.returncode,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "stdout": captured["stdout"].decode("utf-8", "replace"),
                "stderr": captured["stderr"].decode("utf-8", "replace"),
                "output_truncated": truncated,
                "run_id": run_root.name,
            }
        finally:
            # Keep only the bounded JSON result in audit; never retain executable snapshots.
            shutil.rmtree(run_root, ignore_errors=True)


def result_detail(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)
