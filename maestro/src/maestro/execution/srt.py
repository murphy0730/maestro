"""Anthropic Sandbox Runtime CLI 适配器。"""

import json
import asyncio
import os
import shutil
import tempfile
from pathlib import Path


class SrtRuntime:
    def __init__(self, executable: Path | None = None):
        self.executable = executable or self._discover()
        self._usable_cache: dict[tuple[str, tuple[str, ...]], bool] = {}

    @staticmethod
    def _discover() -> Path | None:
        found = shutil.which("srt")
        if found:
            return Path(found)
        root = Path(__file__).resolve().parents[4]
        candidate = root / "sandbox-runtime" / "node_modules" / ".bin" / (
            "srt.cmd" if __import__("os").name == "nt" else "srt"
        )
        return candidate if candidate.exists() else None

    @property
    def available(self) -> bool:
        return self.executable is not None

    def wrap(self, argv: list[str], cwd: Path, protected_paths: list[Path]) -> tuple[list[str], Path]:
        if self.executable is None:
            raise RuntimeError("SRT 未安装")
        config = {
            "network": {"allowedDomains": [], "deniedDomains": [], "allowLocalBinding": False},
            "filesystem": {
                "allowRead": [str(cwd)],
                "denyRead": [str(path) for path in protected_paths],
                "allowWrite": [str(cwd)],
                "denyWrite": [str(path) for path in protected_paths],
            },
        }
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="maestro-srt-", delete=False, encoding="utf-8"
        )
        with handle:
            json.dump(config, handle)
        settings_path = Path(handle.name)
        # "--" 终止 srt 自身的选项解析，否则命令里的 --help/--topic 等会被 srt 吃掉
        return [str(self.executable), "--settings", str(settings_path), "--", *argv], settings_path

    async def check_usable(self, cwd: Path, protected_paths: list[Path]) -> bool:
        """验证运行时，而不把“二进制存在”误报为“沙箱可用”。

        探针结果按 (cwd, protected) 记忆化: 沙箱可用性对同一目录是稳定的，
        无需每条命令都 spawn 一个探针子进程。
        """
        if self.executable is None:
            return False
        cache_key = (str(cwd), tuple(sorted(str(p) for p in protected_paths)))
        if cache_key in self._usable_cache:
            return self._usable_cache[cache_key]
        probe = ["cmd.exe", "/d", "/c", "exit", "0"] if os.name == "nt" else ["/bin/sh", "-c", ":"]
        argv, settings = self.wrap(probe, cwd, protected_paths)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            usable = await asyncio.wait_for(process.wait(), timeout=15) == 0
        except (OSError, TimeoutError):
            usable = False
        else:
            self._usable_cache[cache_key] = usable
        finally:
            settings.unlink(missing_ok=True)
        return usable
