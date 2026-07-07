"""Electron 侧车入口：被 main.cjs 作为子进程拉起，从 env 读端口绑定 loopback。

打包后 (Plan 2) 由 PyInstaller 冻结为 MaestroBackend；本模块是其 entrypoint。
端口经 MAESTRO_BACKEND_PORT 注入 (Electron 动态挑选空闲端口)。
"""

import os

import uvicorn

from scheduling_platform.main import app


def resolve_bind() -> tuple[str, int]:
    """从 env 解析 (host, port)。仅绑 loopback，避免对外暴露。"""
    port = int(os.environ.get("MAESTRO_BACKEND_PORT", "8000"))
    return "127.0.0.1", port


def main() -> None:
    host, port = resolve_bind()
    uvicorn.run(app, host=host, port=port, workers=1, reload=False)


if __name__ == "__main__":
    main()
