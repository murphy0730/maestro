"""Capability descriptor search and exact-version resolution."""

from __future__ import annotations

from dataclasses import dataclass

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySnapshot,
    CapabilitySpec,
)


CORE_CAPABILITIES = frozenset(
    {
        "tool_search",
        "load_skill",
        "get_current_plan",
        "get_result_detail",
        "read_artifact",
        "knowledge_search",
        "memory_search",
    }
)

# These control-plane capabilities remain available while a Skill narrows the
# data/action capability allowlist. Read capabilities such as memory_search are
# core (eagerly loaded) but are still subject to the Skill allowlist.
SKILL_INDEPENDENT_CAPABILITIES = frozenset(
    {
        "tool_search",
        "load_skill",
        "get_current_plan",
        "get_result_detail",
    }
)


def capability_namespace(spec: CapabilitySpec) -> str:
    if spec.kind is CapabilityKind.MCP and spec.name.startswith("mcp__"):
        parts = spec.name.split("__", 2)
        return parts[1] if len(parts) > 2 else "MCP"
    if spec.kind is CapabilityKind.SKILL:
        return "SKILL"
    return "LOCAL"


@dataclass(frozen=True)
class ToolSearchResult:
    query: str
    namespace: str | None
    candidates: list[dict[str, object]]


class CapabilityResolver:
    def __init__(self, registry: CapabilityRegistry, store: SQLiteStore) -> None:
        self._registry = registry
        self._store = store

    def sync_index(self) -> None:
        for spec in self._registry.snapshot().values():
            if spec.kind is CapabilityKind.SKILL:
                continue
            self._store.sync_tool_definition(
                tool_id=spec.name,
                version=spec.version,
                name=spec.name,
                description=spec.description,
                namespace=capability_namespace(spec),
                input_schema=spec.input_schema,
                metadata={
                    "kind": spec.kind.value,
                    "risk": spec.risk.value,
                    "writes": spec.writes,
                },
            )

    def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        allowed: set[str] | None = None,
        top_k: int = 5,
    ) -> ToolSearchResult:
        stored_namespace = namespace
        capability_kind = None
        if namespace and namespace.upper() == "MCP":
            # The frozen Agent index advertises MCP as a top-level namespace,
            # while persisted definitions retain their server namespace (for
            # example, ``planning``). Filter by kind for the top-level alias.
            stored_namespace = None
            capability_kind = CapabilityKind.MCP.value
        return ToolSearchResult(
            query=query,
            namespace=namespace,
            candidates=self._store.search_tools(
                query,
                namespace=stored_namespace,
                capability_kind=capability_kind,
                allowed_tool_ids=allowed,
                top_k=top_k,
            ),
        )

    def resolve(
        self,
        active_versions: dict[str, str],
        *,
        include_core: bool = True,
        allowed: set[str] | None = None,
    ) -> list[CapabilitySpec]:
        snapshot = self._registry.snapshot()
        names = set(active_versions)
        if include_core:
            names.update(CORE_CAPABILITIES)
        result: list[CapabilitySpec] = []
        for name in sorted(names):
            try:
                spec = snapshot.require(name)
            except KeyError:
                continue
            expected = active_versions.get(name)
            if expected is not None and spec.version != expected:
                raise ValueError(f"capability_version_unavailable:{name}@{expected}")
            if (
                allowed is not None
                and name not in allowed
                and name not in SKILL_INDEPENDENT_CAPABILITIES
            ):
                continue
            result.append(spec)
        return result

    def snapshot(self) -> CapabilitySnapshot:
        return self._registry.snapshot()
