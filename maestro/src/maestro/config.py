"""Generic Runtime configuration."""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def runtime_data_root() -> Path:
    return Path(os.environ.get("MAESTRO_DATA_DIR", Path.home() / ".maestro"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    sessions_dir: Path = Field(default_factory=lambda: runtime_data_root() / "sessions-v3")
    runs_dir: Path = Field(default_factory=lambda: runtime_data_root() / "runs")
    artifacts_dir: Path = Field(default_factory=lambda: runtime_data_root() / "artifacts")
    runtime_journal_file: Path = Field(
        default_factory=lambda: runtime_data_root() / "runtime" / "journal.jsonl"
    )
    skills_dir: Path = Field(default_factory=lambda: runtime_data_root() / "skills")
    # Skill package mutation is a host-administration operation, never a Runtime tool.
    privileged_api_token: str = ""
