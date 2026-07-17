"""FastAPI application for the unified Run contract."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maestro.api.routes import artifacts, runs, sessions, skills
from maestro.bootstrap import build_platform
from maestro.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.platform = build_platform()
    app.state.run_tasks = set()
    app.state.skill_trust = {}
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Runtime", version="1", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(artifacts.router)
    app.include_router(runs.router)
    app.include_router(sessions.router)
    app.include_router(skills.router)
    return app
