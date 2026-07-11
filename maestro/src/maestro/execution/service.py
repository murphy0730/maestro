import asyncio
import os
import platform
import shutil
import signal
import time
from pathlib import Path

from .models import ExecutionMode, SecurityCapabilities
from .output_store import FileOutputStore
from .risk import classify_command
from .srt import SrtRuntime


class ShellExecutionService:
    def __init__(
        self,
        store: FileOutputStore,
        allowed_roots: list[Path],
        srt: SrtRuntime | None = None,
        protected_paths: list[Path] | None = None,
    ):
        self.store = store
        self.allowed_roots = [Path(root).resolve() for root in allowed_roots]
        self.srt = srt or SrtRuntime()
        self.protected_paths = [Path(path).resolve() for path in (protected_paths or [])]

    def _cwd(self, value: Path) -> Path:
        cwd = Path(value).resolve(strict=True)
        if not cwd.is_dir() or not any(cwd == root or cwd.is_relative_to(root) for root in self.allowed_roots):
            raise ValueError("工作目录不在允许范围内")
        return cwd

    @staticmethod
    def _security(mode: ExecutionMode) -> SecurityCapabilities:
        if mode == ExecutionMode.SANDBOXED:
            return SecurityCapabilities(mode, True, "srt", "srt", True)
        return SecurityCapabilities(
            mode,
            False,
            "account_acl_only" if platform.system() == "Windows" else "none",
            "none",
            platform.system() != "Windows",
        )

    @staticmethod
    def _argv(shell: str, command: str) -> list[str]:
        if shell == "bash":
            executable = shutil.which("bash")
            if not executable:
                raise RuntimeError("未找到 bash")
            return [executable, "-lc", command]
        if shell == "powershell":
            executable = shutil.which("pwsh") or shutil.which("powershell")
            if not executable:
                raise RuntimeError("未找到 PowerShell")
            import base64
            encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
            return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
        raise ValueError("shell 必须是 bash 或 powershell")

    async def execute(
        self,
        *,
        command: str,
        shell: str,
        cwd: Path,
        timeout_ms: int,
        session_id: str,
        authorized: bool = False,
        force_mode: ExecutionMode | None = None,
        on_progress=None,
    ) -> dict:
        cwd = self._cwd(cwd)
        risk = classify_command(command, shell)
        # 硬性底线: deny 永不执行; ask 级命令只有经确认授权 (authorized=True) 才放行，
        # 使任何入口 (含未经桥接/ActionGate 的调用) 都无法绕过人工确认执行高危命令。
        if risk.effect == "deny":
            return {"status": "blocked", "risk": risk.to_dict()}
        if risk.effect == "ask" and not authorized:
            return {"status": "blocked", "risk": risk.to_dict()}
        if force_mode is not None:
            mode = force_mode
        elif self.srt.available and await self.srt.check_usable(cwd, self.protected_paths):
            mode = ExecutionMode.SANDBOXED
        elif platform.system() == "Windows":
            mode = ExecutionMode.GUARDED
        else:
            raise RuntimeError("SRT 不可用；当前平台默认禁止无沙箱执行")
        writer = self.store.create(session_id)
        started = time.monotonic()
        kwargs = {"cwd": cwd, "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        argv = self._argv(shell, command)
        srt_settings: Path | None = None
        if mode == ExecutionMode.SANDBOXED:
            argv, srt_settings = self.srt.wrap(argv, cwd, self.protected_paths)
        process = await asyncio.create_subprocess_exec(*argv, **kwargs)

        async def pump(stream, name: str):
            while chunk := await stream.read(4096):
                writer.write(name, chunk)
                if on_progress is not None:
                    await on_progress({"phase": "progress", "message": f"{name} +{len(chunk)} bytes"})

        pumps = [asyncio.create_task(pump(process.stdout, "stdout")), asyncio.create_task(pump(process.stderr, "stderr"))]
        status = "completed"
        try:
            await asyncio.wait_for(process.wait(), timeout=max(1, timeout_ms) / 1000)
        except TimeoutError:
            status = "timed_out"
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        finally:
            await asyncio.gather(*pumps)
            if srt_settings is not None:
                srt_settings.unlink(missing_ok=True)
        handle = writer.finish({"status": status, "exit_code": process.returncode})
        return {
            **handle,
            "status": status if process.returncode == 0 or status == "timed_out" else "failed",
            "exit_code": process.returncode,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "risk": risk.to_dict(),
            "security": self._security(mode).to_dict(),
        }
