"""Composition root for the generic agent runtime."""

from dataclasses import dataclass, field
from pathlib import Path

from maestro.config import Settings
from maestro.foundation.llm import LLMClient
from maestro.foundation.session_store import SessionStore
from maestro.runtime.capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec
from maestro.runtime.context import ContextProvider
from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.events import EventPublisher
from maestro.runtime.intent import IntentClassifier
from maestro.runtime.journal import JsonlJournal
from maestro.runtime.model import LLMRuntimeModel
from maestro.foundation.mcp_config_store import MCPConfigStore
from maestro.mcp.manager import MCPManager
from maestro.runtime.mcp import MCPConnector
from maestro.runtime.policy import PolicyGate
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.store import ArtifactStore, RunStore
from maestro.skills.trust import SkillTrustStore
from maestro.tools import (
    register_artifact_capability,
    register_filesystem_capabilities,
    register_shell_capability,
    register_skill_resource_capability,
    register_skill_script_capability,
)
from maestro.runtime.summary import LLMHistorySummarizer


@dataclass
class Platform:
    settings: Settings
    llm: LLMClient
    runtime: RunCoordinator
    run_store: RunStore
    journal: JsonlJournal
    artifact_store: ArtifactStore
    skill_catalog: SkillCatalog
    capabilities: CapabilityRegistry
    mcp: MCPConnector
    mcp_manager: MCPManager
    mcp_config: MCPConfigStore
    session_store: SessionStore
    skill_trust: SkillTrustStore
    _registered_skill_names: set[str] = field(default_factory=set)

    def refresh_skills(self) -> dict:
        """Make discovered Claude Skills callable by the generic Runtime.

        Deliberately not memoised on skill file mtimes: the capability registry
        can gain a colliding Tool/MCP without any skill file changing, and that
        must still take effect.  The expensive part — reading frontmatter off
        disk — is cached inside ``SkillCatalog.discover``.
        """
        discovered = self.skill_catalog.discover()
        versions = {
            name: str(metadata.path.stat().st_mtime_ns)
            for name, metadata in discovered.items()
        }
        registered: dict = {}
        rejected: set[str] = set()
        for name in self._registered_skill_names - set(discovered):
            self.capabilities.unregister(name, kind=CapabilityKind.SKILL)
        for metadata in discovered.values():
            try:
                existing = self.capabilities.require(metadata.name)
            except KeyError:
                existing = None
            # A Skill package is never allowed to replace an operational
            # capability merely because it has the same display name.
            if existing is not None and existing.kind is not CapabilityKind.SKILL:
                rejected.add(metadata.name)
                continue
            self.capabilities.register(
                CapabilitySpec(
                    name=metadata.name,
                    kind=CapabilityKind.SKILL,
                    description=metadata.description,
                    version=versions[metadata.name],
                ),
                replace=True,
            )
            registered[metadata.name] = metadata
        self.skill_catalog.reject(rejected)
        self._registered_skill_names = set(registered)
        return registered


def build_platform(settings: Settings | None = None, llm: LLMClient | None = None) -> Platform:
    settings = settings or Settings()
    llm = llm or LLMClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    capabilities = CapabilityRegistry()
    run_store = RunStore(settings.runs_dir)
    journal = JsonlJournal(settings.runtime_journal_file)
    artifact_store = ArtifactStore(settings.artifacts_dir)
    project_skills_dir = Path(__file__).resolve().parents[3] / "skills"
    skill_catalog = SkillCatalog(
        {"user": settings.skills_dir, "project": project_skills_dir},
        capabilities,
    )
    session_store = SessionStore(settings.sessions_dir)
    skill_trust = SkillTrustStore(settings.skills_dir)
    runtime = RunCoordinator(
        model=LLMRuntimeModel(llm),
        capabilities=capabilities,
        intent_classifier=IntentClassifier(capabilities),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=16_000),
        run_store=run_store,
        artifact_store=artifact_store,
        events=EventPublisher(journal),
        skill_catalog=skill_catalog,
        history_provider=session_store.get_messages,
        max_history_messages=settings.history_max_messages,
        summarizer=LLMHistorySummarizer(llm) if settings.summary_enabled else None,
        summary_store=session_store if settings.summary_enabled else None,
        summary_batch_messages=settings.summary_batch_messages,
    )
    connector = MCPConnector(capabilities)
    platform = Platform(
        settings=settings,
        llm=llm,
        runtime=runtime,
        run_store=run_store,
        journal=journal,
        artifact_store=artifact_store,
        skill_catalog=skill_catalog,
        capabilities=capabilities,
        mcp=connector,
        # Servers are started by the host after construction (see
        # `api/app.py::lifespan`): connecting is async, and a slow or broken
        # server must not be able to stop the Runtime from coming up.
        mcp_manager=MCPManager(connector),
        mcp_config=MCPConfigStore(),
        session_store=session_store,
        skill_trust=skill_trust,
    )
    # 能力注册必须在 refresh_skills 之前：技能的 allowed_tools 会按注册表校验，
    # 工具缺席会让引用它的技能整个发现失败。
    # 这里只注册通用宿主原语；领域能力由宿主在 build_platform 之后自行注册。
    register_filesystem_capabilities(capabilities, settings.workspace_root)
    register_artifact_capability(capabilities, artifact_store)
    register_shell_capability(capabilities, settings.workspace_root)
    register_skill_resource_capability(capabilities, skill_catalog)
    register_skill_script_capability(capabilities, skill_catalog, skill_trust, artifact_store)
    runtime.set_intent_classifier(IntentClassifier(capabilities, skills=platform.refresh_skills))
    platform.refresh_skills()
    return platform
