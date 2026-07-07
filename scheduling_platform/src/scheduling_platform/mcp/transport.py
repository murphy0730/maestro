"""MCP 传输层。

提供与 MCP 服务器通信的传输实现。
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .types import MCPServerConfig


class MCPTransport(ABC):
    """MCP 传输层抽象基类。"""

    @abstractmethod
    async def connect(self) -> None:
        """连接到 MCP 服务器。"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """断开与 MCP 服务器的连接。"""
        pass

    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> None:
        """发送消息到 MCP 服务器。"""
        pass

    @abstractmethod
    async def receive_response(self, request_id: Any, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """接收针对特定请求 ID 的响应。"""
        pass


class StdioMCPTransport(MCPTransport):
    """stdio 传输层实现。"""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._read_task: Optional[asyncio.Task] = None
        self._pending_responses: Dict[Any, asyncio.Future[Dict[str, Any]]] = {}
        self._notification_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._running = False

    async def connect(self) -> None:
        if self._process:
            return

        env = dict(os.environ)
        if self.config.env:
            env.update(self.config.env)

        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args or [],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())

    async def disconnect(self) -> None:
        self._running = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Cancel all pending response futures
        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()
        self._pending_responses.clear()

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None

    async def send_message(self, message: Dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected")

        data = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(data.encode('utf-8'))
        await self._process.stdin.drain()

    async def receive_response(self, request_id: Any, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """接收针对特定请求 ID 的响应。"""
        future = asyncio.Future()
        self._pending_responses[request_id] = future

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            if request_id in self._pending_responses:
                del self._pending_responses[request_id]

    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return

        buffer = ""
        try:
            while self._running:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break

                buffer += chunk.decode('utf-8', errors='replace')

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            await self._handle_message(msg)
                        except json.JSONDecodeError:
                            continue
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """处理接收到的消息。"""
        msg_id = msg.get('id')
        
        if msg_id is not None and msg_id in self._pending_responses:
            # This is a response to a pending request
            future = self._pending_responses[msg_id]
            if not future.done():
                future.set_result(msg)
        elif 'method' in msg and msg.get('jsonrpc') == '2.0' and 'id' not in msg:
            # This is a notification
            await self._notification_queue.put(msg)
