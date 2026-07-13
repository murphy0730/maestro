from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


class SkillValidationError(Exception):
    """技能包校验失败 → HTTP 422。"""


class SkillFrontmatter(BaseModel):
    name: str
    display_name: str | None = None
    description: str
    when_to_use: list[str] = []
    allowed_tools: list[str] | None = None  # None = 不授予任何引擎工具 (文件/脚本工具由 SkillEngine 按需追加)
    user_invocable: bool = True
    disable_model_invocation: bool = False
    tool_preconditions: dict[str, list[str]] = {}
    version: str | None = None
    author: str | None = None
    license: str | None = None
    compatibility: str | None = None
    argument_hint: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)
    scripts: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("name 必须匹配 ^[a-z][a-z0-9-]{1,31}$")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        if not (1 <= len(v) <= 1024):
            raise ValueError("description 长度需 1~1024 字符")
        return v

    @field_validator("display_name")
    @classmethod
    def _display(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 32:
            raise ValueError("display_name 需 ≤32 字符")
        return v

    @field_validator("when_to_use")
    @classmethod
    def _when(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("when_to_use 需 ≤10 条")
        for s in v:
            if len(s) > 100:
                raise ValueError("when_to_use 每条需 ≤100 字符")
        return v

    @field_validator("version")
    @classmethod
    def _ver(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 16:
            raise ValueError("version 需 ≤16 字符")
        return v

    @field_validator("author")
    @classmethod
    def _author(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 32:
            raise ValueError("author 需 ≤32 字符")
        return v

    @model_validator(mode="after")
    def _precond_types(self):
        for tool, names in self.tool_preconditions.items():
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise ValueError(f"tool_preconditions['{tool}'] 必须为 list[str]")
        return self

    @property
    def effective_display_name(self) -> str:
        return self.display_name or self.name


class SkillMeta(SkillFrontmatter):
    summary_zh: str | None = None
    description_zh: str | None = None
    file_count: int = 0
    bytes: int = 0
    archive_bytes: int | None = None
    added_at: str = ""
    compatibility_status: Literal["ready", "degraded", "not_ready", "disabled"] = "ready"
    warnings: list[str] = Field(default_factory=list)
    package_sha256: str = ""


class SkillTrustRecord(BaseModel):
    skill_name: str
    package_sha256: str
    principal_id: str = "local-user"
    trusted_at: datetime = Field(default_factory=datetime.now)


class SkillCapabilityReport(BaseModel):
    prompt: bool = True
    attachments: bool = False
    scripts: bool = False


class SkillValidationReport(BaseModel):
    compatible: bool
    normalized_name: str | None = None
    compatibility_status: Literal["ready", "degraded", "not_ready", "disabled"] = "ready"
    capabilities: SkillCapabilityReport = Field(default_factory=SkillCapabilityReport)
    tool_mapping: dict[str, str] = Field(default_factory=dict)
    normalized_frontmatter: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
