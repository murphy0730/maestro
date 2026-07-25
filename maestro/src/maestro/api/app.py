"""FastAPI application for the unified Run contract."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maestro.api.routes import artifacts, mcp, runs, sessions, skills
from maestro.bootstrap import build_platform
from maestro.config import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    platform = build_platform()
    app.state.platform = platform
    app.state.run_tasks = set()
    # A server that will not start is reported through GET /mcp/servers, never
    # by refusing to serve the rest of the API.
    try:
        await platform.mcp_manager.connect_all(platform.mcp_config.load())
    except Exception:  # noqa: BLE001 — startup must survive any server defect
        logger.exception("[mcp] 启动时连接服务器失败")
    try:
        yield
    finally:
        await platform.mcp_manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Runtime", version="1", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(artifacts.router)
    app.include_router(mcp.router)
    app.include_router(runs.router)
    app.include_router(sessions.router)
    app.include_router(skills.router)
    return app
