"""stdio transport for MCP: newline-delimited JSON-RPC over a child process.

Two things the previous implementation of this got wrong are fixed here and
matter enough to name:

* the child inherited the whole environment, handing every MCP server the
  host's `LLM_API_KEY`.  It now gets the same allowlist `tools/sandbox.py`
  uses, plus whatever the server's own config declares.
* stderr was never drained, so a server that logs freely fills the pipe buffer
  and blocks forever.  It is now drained continuously and kept for diagnostics.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from maestro.mcp.types import MCPServerConfig

logger = logging.getLogger(__name__)

_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR")
_MAX_STDERR_BYTES = 64 * 1024
_MAX_LINE_BYTES = 8 * 1024 * 1024


class MCPTransportError(RuntimeError):
    """The transport could not carry a request to completion."""


def _child_environment(config: MCPServerConfig) -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env.update(config.env)
    return env


class StdioMCPTransport:
    """One JSON-RPC channel to a child process."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._stderr_reader: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._stderr = bytearray()

    @property
    def stderr(self) -> str:
        return self._stderr.decode("utf-8", "replace")

    async def connect(self) -> None:
        if self._process is not None:
            return
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._config.command,
                *self._config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_child_environment(self._config),
            )
        except (OSError, ValueError) as error:
            raise MCPTransportError(f"无法启动 MCP 服务器 {self._config.name}: {error}") from error
        self._reader = asyncio.create_task(self._read_loop())
        self._stderr_reader = asyncio.create_task(self._drain_stderr())

    async def disconnect(self) -> None:
        for task in (self._reader, self._stderr_reader):
            if task is not None:
                task.cancel()
        for task in (self._reader, self._stderr_reader):
            if task is not None:
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._reader = self._stderr_reader = None
        self._fail_pending(MCPTransportError("transport closed"))
        process, self._process = self._process, None
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except (TimeoutError, asyncio.TimeoutError):
                process.kill()
                await process.wait()

    async def request(self, request_id: int, message: dict, timeout: float) -> dict:
        """Send a request and wait for the response carrying the same id."""
        if self._process is None or self._process.stdin is None:
            raise MCPTransportError("not connected")
        future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write(message)
            return await asyncio.wait_for(future, timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError) as error:
            raise MCPTransportError(
                f"MCP 请求超时（>{timeout:.0f}s）: {message.get('method')}"
            ) from error
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, message: dict) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPTransportError("not connected")
        await self._write(message)

    async def _write(self, message: dict) -> None:
        assert self._process is not None and self._process.stdin is not None
        payload = json.dumps(message, ensure_ascii=False).encode() + b"\n"
        try:
            self._process.stdin.write(payload)
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as error:
            raise MCPTransportError(f"MCP 服务器已断开: {error}") from error

    async def _read_loop(self) -> None:
        # Buffered by hand rather than via `readline`, whose 64 KiB limit would
        # raise on a large but perfectly valid tool result.
        assert self._process is not None and self._process.stdout is not None
        stdout = self._process.stdout
        buffer = bytearray()
        try:
            while True:
                chunk = await stdout.read(65536)
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > _MAX_LINE_BYTES:
                    raise MCPTransportError(
                        f"MCP 响应超过 {_MAX_LINE_BYTES} 字节上限"
                    )
                while b"\n" in buffer:
                    raw, _, rest = buffer.partition(b"\n")
                    buffer = bytearray(rest)
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    try:
                        self._dispatch(json.loads(stripped))
                    except json.JSONDecodeError:
                        # A server writing non-JSON to stdout is misbehaving, but
                        # one bad line must not take the channel down.
                        logger.warning("[mcp] %s 输出了非 JSON 行，已忽略", self._config.name)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — surface as a transport failure
            self._fail_pending(MCPTransportError(f"MCP 读取失败: {error}"))
            return
        # stdout closed: nothing further can arrive, so waiters must not hang.
        self._fail_pending(MCPTransportError("MCP 服务器已关闭输出流"))

    def _dispatch(self, message: dict) -> None:
        message_id = message.get("id")
        future = self._pending.get(message_id) if isinstance(message_id, int) else None
        if future is not None and not future.done():
            future.set_result(message)

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                chunk = await self._process.stderr.read(4096)
                if not chunk:
                    return
                if len(self._stderr) < _MAX_STDERR_BYTES:
                    self._stderr.extend(chunk[: _MAX_STDERR_BYTES - len(self._stderr)])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — draining is best effort
            return

    def _fail_pending(self, error: Exception) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
