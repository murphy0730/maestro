"""Execute trusted Skill scripts from an immutable per-run snapshot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# SRT 基础设施故障特征 (mux socket 建不起来等)，与"脚本自身失败"区分
_SRT_INFRA_ERROR = re.compile(r"srt-mux-.*\.sock|listen EINVAL")

from maestro.execution.srt import SrtRuntime
from maestro.skills.office_artifacts import artifact_metadata
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
            # LLM 常省略 scripts/ 前缀，先按声明列表归一化再拒绝
            prefixed = f"scripts/{script}"
            if prefixed in meta.scripts:
                script = prefixed
            else:
                raise SkillValidationError("只能执行 SKILL.md 声明或 scripts/ 下已识别的脚本")
        path = Path(script)
        if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in {".py", ".js"}:
            raise SkillValidationError("仅允许包内 .py/.js 脚本")
        return skill_id, script, list(args)

    def _collect_artifacts(self, workspace: Path, pre_existing: set[Path], run_id: str) -> list[dict]:
        # 工作区随 run_root 一起删除，脚本产物（如生成的 .pptx）必须先拷到持久目录才能交付用户
        saved: list[dict] = []
        keep_dir = self._output_dir / "artifacts" / run_id
        artifact_root = self._output_dir / "artifacts"
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or path in pre_existing:
                continue
            target = keep_dir / path.relative_to(workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            saved.append(artifact_metadata(target, artifact_root))
        return saved

    async def execute(self, params: dict) -> dict:
        skill_id, script, args = self._validate(params)
        files = self._store.snapshot_files(skill_id)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        result = await self._run_once(skill_id, script, args, files, allow_sandbox=True)
        if self._is_srt_infra_failure(result):
            # 契约承诺: SRT 不可用时可在宿主机受控执行。预检通过但运行期沙箱自身
            # 起不来 (如路径过长 mux socket EINVAL) 时按同一承诺回退重跑一次。
            logger.warning(
                "SRT 沙箱基础设施故障，回退宿主机受控执行: %s",
                (result.get("stderr") or "")[:200],
            )
            result = await self._run_once(skill_id, script, args, files, allow_sandbox=False)
            result["fallback_reason"] = "srt_infrastructure_failure"
        return result

    @staticmethod
    def _is_srt_infra_failure(result: dict) -> bool:
        """仅当 SRT 自身 (mux socket 等) 起不来时成立；脚本自身失败不重试。"""
        if result.get("execution_mode") != "srt" or result.get("status") != "failed":
            return False
        return bool(_SRT_INFRA_ERROR.search(result.get("stderr") or ""))

    async def _run_once(
        self, skill_id: str, script: str, args: list[str], files: dict, allow_sandbox: bool
    ) -> dict:
        # 执行现场放系统短路径 tmp: macOS unix socket 路径上限 ~104 字节，数据根
        # (MAESTRO_DATA_DIR / Electron userData) 可能很长。产物由 _collect_artifacts
        # 归档到数据根 artifacts 目录，现场随 finally 整树删除。
        run_root = Path(tempfile.mkdtemp(
            prefix=f"skill-{skill_id}-", dir="/tmp" if os.name != "nt" else None))
        workspace = run_root / "workspace"
        workspace.mkdir()
        # HOME 指向 workspace，脚本写 ~/Desktop 等常见目录时需要它们真实存在
        for home_dir in ("Desktop", "Documents", "Downloads"):
            (workspace / home_dir).mkdir()
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
            pre_existing = {path for path in workspace.rglob("*") if path.is_file()}
            interpreter = sys.executable if script_path.suffix.lower() == ".py" else shutil.which("node")
            if not interpreter:
                raise SkillValidationError("未安装 Node.js，无法执行 JavaScript Skill 脚本")
            argv = [str(interpreter), str(script_path), *args]
            protected = [self._skills_dir, Path.home() / ".ssh", Path.home() / ".aws"]
            sandboxed = (
                allow_sandbox
                and self._srt.available
                and await self._srt.check_usable(workspace, protected)
            )
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
                "stdout": captured["stdout"].decode("utf-8", "replace").replace(
                    str(workspace), "$WORKSPACE"
                ),
                "stderr": captured["stderr"].decode("utf-8", "replace").replace(
                    str(workspace), "$WORKSPACE"
                ),
                "output_truncated": truncated,
                "run_id": run_root.name,
                "artifacts": self._collect_artifacts(workspace, pre_existing, run_root.name),
            }
        finally:
            # Keep only the bounded JSON result in audit; never retain executable snapshots.
            shutil.rmtree(run_root, ignore_errors=True)


def result_detail(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)


def format_skill_result_markdown(result: dict) -> str:
    """把技能脚本执行结果 dict 渲染成可读 Markdown，用于确认后的用户回复。

    ``result_detail`` 保持机器可解析的 JSON（供 ReAct 观察与审计），
    面向用户的确认回复则走本函数，避免把裸 JSON 抛给前台。
    """
    ok = result.get("status") == "completed" and result.get("exit_code", 0) == 0
    icon = "✅" if ok else "⚠️"
    mode = result.get("execution_mode", "?")
    exit_code = result.get("exit_code", "?")
    duration = result.get("duration_ms", "?")
    parts = [
        f"{icon} 脚本执行{'完成' if ok else '结束'}"
        f"（{mode} · 退出码 {exit_code} · 耗时 {duration}ms）"
    ]
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        parts.append(f"\n```\n{stdout}\n```")
    stderr = (result.get("stderr") or "").strip()
    if stderr:
        parts.append(f"\n**stderr**\n```\n{stderr}\n```")
    artifacts = result.get("artifacts") or []
    if artifacts:
        listed = "\n".join(
            f"- [{a.get('name', '下载文件')}]({a['download_url']})"
            for a in artifacts
            if isinstance(a, dict) and a.get("download_url")
        )
        parts.append(f"\n**产物**\n{listed}")
    return "\n".join(parts)
