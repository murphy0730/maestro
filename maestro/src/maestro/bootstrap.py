"""Composition root for the generic agent runtime."""

from dataclasses import dataclass

from maestro.config import Settings
from maestro.foundation.llm import LLMClient
from maestro.foundation.session_store import SessionStore
from maestro.runtime.capabilities import CapabilityRegistry
from maestro.runtime.context import ContextProvider
from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.events import EventPublisher
from maestro.runtime.intent import IntentClassifier
from maestro.runtime.journal import JsonlJournal
from maestro.runtime.model import LLMRuntimeModel
from maestro.runtime.mcp import MCPConnector
from maestro.runtime.policy import PolicyGate
from maestro.runtime.skills import SkillCatalog
from maestro.runtime.store import ArtifactStore, RunStore


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
    session_store: SessionStore


def build_platform(settings: Settings | None = None, llm: LLMClient | None = None) -> Platform:
    settings = settings or Settings()
    llm = llm or LLMClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    capabilities = CapabilityRegistry()
    run_store = RunStore(settings.runs_dir)
    journal = JsonlJournal(settings.runtime_journal_file)
    artifact_store = ArtifactStore(settings.artifacts_dir)
    skill_catalog = SkillCatalog({"user": settings.skills_dir}, capabilities)
    skill_catalog.discover()
    runtime = RunCoordinator(
        model=LLMRuntimeModel(llm),
        capabilities=capabilities,
        intent_classifier=IntentClassifier(capabilities, skills=skill_catalog.discover),
        policy_gate=PolicyGate([]),
        context_provider=ContextProvider(max_chars=16_000),
        run_store=run_store,
        artifact_store=artifact_store,
        events=EventPublisher(journal),
        skill_catalog=skill_catalog,
    )
    return Platform(
        settings=settings,
        llm=llm,
        runtime=runtime,
        run_store=run_store,
        journal=journal,
        artifact_store=artifact_store,
        skill_catalog=skill_catalog,
        capabilities=capabilities,
        mcp=MCPConnector(capabilities),
        session_store=SessionStore(settings.sessions_dir),
    )
