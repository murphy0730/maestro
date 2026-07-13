"""FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.api.routes import artifacts, chat, extensions, knowledge, mcp, models, operations, sessions, skills

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    platform = build_platform()
    app.state.platform = platform
    await platform.connect_mcp()
    bus_task = asyncio.create_task(platform.bus.run())
    patrol_task = asyncio.create_task(platform.patrol.run())
    catalog_task = asyncio.create_task(platform.catalog_scheduler.run())
    logger.info("平台已启动: 事件总线 + 定时巡检运行中")
    try:
        yield
    finally:
        for task in (bus_task, patrol_task, catalog_task):
            task.cancel()
        await platform.disconnect_mcp()


def create_app() -> FastAPI:
    """Create the HTTP application used by Uvicorn, Electron, and tests."""
    app = FastAPI(title="生产调度与排产 Agent 平台", version="0.1.0", lifespan=lifespan)
    allowed_origins = Settings().cors_allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat.router)
    app.include_router(artifacts.router)
    app.include_router(operations.router)
    app.include_router(sessions.router)
    app.include_router(knowledge.router)
    app.include_router(skills.router)
    app.include_router(models.router)
    app.include_router(mcp.router)
    app.include_router(extensions.router)
    return app
