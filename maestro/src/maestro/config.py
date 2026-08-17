"""Generic Runtime configuration."""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def runtime_data_root() -> Path:
    return Path(os.environ.get("MAESTRO_DATA_DIR", Path.home() / ".maestro"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 扁平 LLM 连接参数。settings.json 的 `model_providers` 里若存在启用的供应商，
    # 会在 bootstrap 覆盖这几项（见 foundation/model_config.py）。
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    # 嵌入模型；留空表示不启用。当前 Runtime 尚无嵌入消费方。
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = ""
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    sessions_dir: Path = Field(default_factory=lambda: runtime_data_root() / "sessions-v3")
    runs_dir: Path = Field(default_factory=lambda: runtime_data_root() / "runs")
    artifacts_dir: Path = Field(default_factory=lambda: runtime_data_root() / "artifacts")
    runtime_journal_file: Path = Field(
        default_factory=lambda: runtime_data_root() / "runtime" / "journal.jsonl"
    )
    runtime_v2_database: Path = Field(
        default_factory=lambda: runtime_data_root() / "runtime-v2" / "maestro.db"
    )
    skills_dir: Path = Field(default_factory=lambda: runtime_data_root() / "skills")
    # The only directory the filesystem capabilities can reach.
    workspace_root: Path = Field(default_factory=lambda: runtime_data_root() / "workspace")
    # Turns beyond the window are folded into a rolling summary, not discarded;
    # summarization costs a model call, so it waits for a batch to accumulate.
    history_max_messages: int = 20
    summary_enabled: bool = True
    summary_batch_messages: int = 8
    # One budget over system context + conversation + tool schemas. Set it below
    # the model's real window: the gap is the headroom, deliberately explicit
    # here rather than hidden as a fudge factor inside the estimator.
    # 48000 leaves a quarter of a 64K window for the reply. 0 disables budgeting.
    context_max_prompt_tokens: int = 48_000
    # Results above this are stored as an artifact and referenced instead of
    # inlined; the model reads them back with read_artifact.
    artifact_threshold_bytes: int = 4096
    # Skill package mutation is a host-administration operation, never a Runtime tool.
    privileged_api_token: str = ""
