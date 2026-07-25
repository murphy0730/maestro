from __future__ import annotations
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


class SkillValidationError(Exception):
    """技能包校验失败 → HTTP 422。"""


class RuntimeSkillFrontmatter(BaseModel):
    """Strict Runtime-facing Claude skill contract.

    This deliberately stays separate from ``SkillFrontmatter`` until the
    legacy SkillEngine is retired.  In particular, it has no Maestro action
    preconditions or script-execution fields.
    """

    name: str
    description: str
    allowed_tools: list[str] | None = None
    argument_hint: str | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    context: Literal["inline", "fork"] = "inline"
    agent: str | None = None
    model: str | None = None
    effort: str | None = None
    hooks: dict[str, Any] = Field(default_factory=dict)
    # Declared explicitly, or discovered from the package's scripts/ dir.
    scripts: list[str] = Field(default_factory=list)
    shell: str | list[str] | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _runtime_name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("name 必须匹配 ^[a-z][a-z0-9-]{1,31}$")
        return v

    @field_validator("description")
    @classmethod
    def _runtime_description(cls, v: str) -> str:
        if not (1 <= len(v) <= 1024):
            raise ValueError("description 长度需 1~1024 字符")
        return v


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
