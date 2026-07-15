from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field, replace as dataclass_replace
from enum import StrEnum
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, Field

from maestro.runtime.models import RuntimeErrorKind


class CapabilityKind(StrEnum):
    SKILL = "skill"
    TOOL = "tool"
    MCP = "mcp"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CapabilityCall(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class CapabilityResult(BaseModel):
    status: Literal["succeeded", "failed", "unknown"]
    content: object | None = None
    artifact_ref: str | None = None
    error_kind: RuntimeErrorKind | None = None
    error_message: str | None = None


CapabilityExecutor = Callable[[CapabilityCall, str | None], Awaitable[CapabilityResult]]


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    kind: CapabilityKind
    description: str = ""
    input_schema: dict[str, object] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    writes: bool = False
    idempotent: bool = True
    retryable_errors: frozenset[RuntimeErrorKind] = frozenset()
    version: str = "1"
    content_sha256: str = ""
    executor: CapabilityExecutor | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", _normalize_risk(self.risk))


def _content_hash(spec: CapabilitySpec) -> str:
    content = {
        "name": spec.name,
        "kind": spec.kind,
        "description": spec.description,
        "input_schema": spec.input_schema,
        "risk": spec.risk,
        "writes": spec.writes,
        "idempotent": spec.idempotent,
        "retryable_errors": sorted(spec.retryable_errors),
        "version": spec.version,
    }
    return sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _normalize_risk(risk: object) -> RiskLevel:
    if isinstance(risk, RiskLevel):
        return risk
    if isinstance(risk, str):
        try:
            return RiskLevel(risk)
        except ValueError as error:
            raise ValueError(f"invalid capability risk: {risk}") from error
    raise ValueError(f"invalid capability risk: {risk!r}")


class CapabilitySnapshot:
    """An immutable, deep-copied registry view pinned to a Run."""

    def __init__(self, specs: dict[str, CapabilitySpec]) -> None:
        self._specs = specs

    def require(self, name: str) -> CapabilitySpec:
        try:
            return deepcopy(self._specs[name])
        except KeyError as error:
            raise KeyError(f"unknown capability: {name}") from error

    def values(self) -> tuple[CapabilitySpec, ...]:
        return tuple(deepcopy(spec) for spec in self._specs.values())

    def versions(self) -> dict[str, str]:
        return {name: spec.content_sha256 for name, spec in self._specs.items()}


class CapabilityRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec, *, replace: bool = False) -> None:
        if spec.name in self._specs and not replace:
            raise ValueError(f"capability already registered: {spec.name}")
        stored = deepcopy(spec)
        stored = dataclass_replace(stored, risk=_normalize_risk(stored.risk))
        stored = dataclass_replace(stored, content_sha256=_content_hash(stored))
        self._specs[stored.name] = stored

    def require(self, name: str) -> CapabilitySpec:
        try:
            return deepcopy(self._specs[name])
        except KeyError as error:
            raise KeyError(f"unknown capability: {name}") from error

    def snapshot(self) -> CapabilitySnapshot:
        return CapabilitySnapshot(deepcopy(self._specs))
