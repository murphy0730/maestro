from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CatalogSource(BaseModel):
    id: str
    kind: Literal["skill", "connector"]
    display_name: str
    owner: str
    repo: str
    ref: str = "main"
    source_url: str
    trust_tier: Literal["official", "verified"] = "official"
    paths: list[str] = Field(default_factory=list)
    enabled: bool = True


class ConnectorEnvSpec(BaseModel):
    name: str
    description: str = ""
    required: bool = False
    secret: bool = False


class CatalogSkill(BaseModel):
    catalog_id: str
    name: str
    display_name: str
    description: str
    summary_zh: str | None = None      # 大模型翻译的中文简介（一句话，卡片显示）
    description_zh: str | None = None   # 大模型翻译的中文描述（完整，详情显示）
    author: str | None = None
    license: str | None = None
    version: str | None = None
    source_id: str
    source_name: str
    source_url: str
    source_ref: str
    source_commit: str
    blob_sha: str | None = None
    package_sha256: str
    compatibility_status: Literal["ready", "degraded", "not_ready"]
    warnings: list[str] = Field(default_factory=list)
    has_scripts: bool = False
    synced_at: datetime = Field(default_factory=utcnow)
    last_checked_at: datetime = Field(default_factory=utcnow)
    withdrawn: bool = False
    installable: bool = True
    install_block_reason: str | None = None
    installed: bool = False
    installed_sha256: str | None = None
    update_available: bool = False


class CatalogConnector(BaseModel):
    catalog_id: str
    name: str
    display_name: str
    description: str                    # 从上游 manifest 提取的英文简介（回退用）
    summary_zh: str | None = None      # 大模型翻译的中文简介（卡片显示）
    author: str | None = None
    license: str | None = None
    version: str | None = None
    source_id: str
    source_name: str
    source_url: str
    source_ref: str
    source_commit: str
    blob_sha: str | None = None
    transport_type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env_schema: list[ConnectorEnvSpec] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    catalog_template_sha256: str
    synced_at: datetime = Field(default_factory=utcnow)
    last_checked_at: datetime = Field(default_factory=utcnow)
    withdrawn: bool = False
    installable: bool = True
    install_block_reason: str | None = None
    configured: bool = False
    configured_name: str | None = None
    configured_catalog_id: str | None = None
    configured_template_version: str | None = None
    update_available: bool = False


class SourceState(BaseModel):
    source_id: str
    last_synced_commit: str | None = None
    validation_fingerprint: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    stale: bool = False
    last_error: str | None = None


class SyncRun(BaseModel):
    run_id: str
    trigger: Literal["scheduled", "manual", "startup_recovery"]
    source_ids: list[str]
    status: Literal["running", "completed", "partial", "failed"] = "running"
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
