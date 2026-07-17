from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import BaseModel, Field

from maestro.runtime.capabilities import CapabilityRegistry, CapabilitySnapshot, RiskLevel
from maestro.runtime.models import RunIntent, RunPath
from maestro.runtime.skills import SkillMetadata

ModelClassification = object
ModelClassifier = Callable[["IntentRequest"], ModelClassification]

_HIGH_RISK_WORDING = (
    "delete",
    "deploy",
    "execute",
    "publish",
    "update",
    "write",
    "删除",
    "发布",
    "执行",
    "更新",
    "写入",
)
_STRUCTURED_MODEL_SIGNALS = {"complex", "high", "structured"}
_KNOWN_MODEL_SIGNALS = _STRUCTURED_MODEL_SIGNALS | {"low", "medium"}
_COMPLEX_WORDING = ("complex", "multi-step", "复杂", "多步骤")


class IntentRequest(BaseModel):
    """The bounded request data used to select an initial Runtime path."""

    message: str = Field(min_length=1)
    source: Literal["chat", "expert", "event", "resume"] = "chat"
    principal_id: str = "local-user"
    tool_names: list[str] = Field(default_factory=list)
    requested_skills: list[str] = Field(default_factory=list)
    allow_background: bool = False
    external_wait: bool = False
    max_steps: int = Field(default=12, ge=1, le=100)
    max_seconds: int = Field(default=300, ge=1, le=86400)


class IntentClassifier:
    """Select FAST only when no deterministic or model complexity signal requires structure."""

    def __init__(
        self,
        capabilities: CapabilitySnapshot | CapabilityRegistry,
        *,
        skills: Mapping[str, SkillMetadata] | Callable[[], Mapping[str, SkillMetadata]] | None = None,
        model_classifier: ModelClassifier | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._skills = skills or {}
        self._model_classifier = model_classifier

    def build(self, request: IntentRequest) -> RunIntent:
        candidate_capabilities = self._candidate_capabilities(request)
        risk_signals, complexity_signals = self._deterministic_signals(
            request, candidate_capabilities
        )
        model_signals = self._model_signals(request)
        complexity_signals.extend(model_signals)

        path = RunPath.FAST
        if risk_signals or complexity_signals:
            path = RunPath.STRUCTURED

        return RunIntent(
            objective=request.message,
            source=request.source,
            principal_id=request.principal_id,
            requested_skills=request.requested_skills,
            candidate_capabilities=candidate_capabilities,
            risk_signals=risk_signals,
            complexity_signals=complexity_signals,
            max_steps=request.max_steps,
            max_seconds=request.max_seconds,
            allow_background=request.allow_background,
            path=path,
        )

    def _candidate_capabilities(self, request: IntentRequest) -> list[str]:
        names = list(request.tool_names)
        skills = self._skill_metadata()
        for skill_name in request.requested_skills:
            skill = skills.get(skill_name)
            if skill is not None:
                names.extend(skill.allowed_tools)
        return list(dict.fromkeys(names))

    def _deterministic_signals(
        self, request: IntentRequest, candidate_capabilities: list[str]
    ) -> tuple[list[str], list[str]]:
        risks: list[str] = []
        complexity: list[str] = []
        for name in candidate_capabilities:
            try:
                capability = self._snapshot().require(name)
            except KeyError:
                risks.append("unknown_capability")
                continue
            if capability.writes and capability.risk is RiskLevel.HIGH:
                risks.append("deterministic_high_risk_write")

        if len(candidate_capabilities) > 1:
            complexity.append("multiple_capabilities")
        if len(request.requested_skills) > 1:
            complexity.append("multiple_skills")
        if self._requests_fork(request):
            complexity.append("fork_context")
        if request.allow_background:
            complexity.append("background_requested")
        if request.external_wait:
            complexity.append("external_wait")
        if self._contains_high_risk_wording(request.message):
            risks.append("explicit_high_risk_wording")
        if self._contains_complex_wording(request.message):
            complexity.append("explicit_complex_wording")
        return list(dict.fromkeys(risks)), list(dict.fromkeys(complexity))

    def _snapshot(self) -> CapabilitySnapshot:
        if isinstance(self._capabilities, CapabilityRegistry):
            return self._capabilities.snapshot()
        return self._capabilities

    def _requests_fork(self, request: IntentRequest) -> bool:
        skills = self._skill_metadata()
        for name in request.requested_skills:
            skill = skills.get(name)
            if skill is not None and skill.context == "fork":
                return True
        return False

    def _skill_metadata(self) -> Mapping[str, SkillMetadata]:
        if callable(self._skills):
            return self._skills()
        return self._skills

    def _model_signals(self, request: IntentRequest) -> list[str]:
        if self._model_classifier is None:
            return []
        try:
            classification = self._model_classifier(request)
        except Exception:
            return ["model_unavailable"]
        if isinstance(classification, str):
            values = (classification,)
        elif isinstance(classification, (list, tuple)):
            values = classification
        else:
            return ["model_unknown_output"]
        if not all(isinstance(value, str) for value in values):
            return ["model_unknown_output"]
        normalized = [value.strip().lower() for value in values]
        if not normalized or any(value not in _KNOWN_MODEL_SIGNALS for value in normalized):
            return ["model_unknown_output"]
        return [f"model_{value}" for value in normalized if value in _STRUCTURED_MODEL_SIGNALS]

    @staticmethod
    def _contains_high_risk_wording(message: str) -> bool:
        normalized = message.lower()
        return any(word in normalized for word in _HIGH_RISK_WORDING)

    @staticmethod
    def _contains_complex_wording(message: str) -> bool:
        normalized = message.lower()
        return any(word in normalized for word in _COMPLEX_WORDING)
