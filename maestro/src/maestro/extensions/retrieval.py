"""Local FTS-backed knowledge and memory capabilities.

Retrieval lives outside ``runtime/`` so the core remains domain-neutral and has
no built-in RAG behavior.  The host may replace these capabilities with MCP
providers without changing the agent loop.
"""

from __future__ import annotations

from maestro.foundation.sqlite_store import SQLiteStore
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityEvidence,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)


def register_local_retrieval_capabilities(
    registry: CapabilityRegistry, store: SQLiteStore
) -> None:
    async def knowledge(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        query = str(call.arguments.get("query") or "").strip()
        if not query:
            return CapabilityResult(status="failed", error_message="query is required")
        items = store.search_knowledge(
            query,
            max_chunks=int(call.arguments.get("max_chunks") or 5),
            max_tokens=int(call.arguments.get("max_tokens") or 4000),
        )
        return CapabilityResult(
            status="succeeded",
            content={
                "kind": "knowledge_recall",
                "items": items,
            },
            evidence=[
                CapabilityEvidence(
                    source_type="knowledge",
                    source_ref=f"knowledge://{item['document_id']}/{item['chunk_id']}",
                    content_digest=str(item["content"])[:1000],
                )
                for item in items
            ],
        )

    async def memory(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        query = str(call.arguments.get("query") or "").strip()
        if not query:
            return CapabilityResult(status="failed", error_message="query is required")
        items = store.search_memories(
            query, limit=int(call.arguments.get("limit") or 5)
        )
        return CapabilityResult(
            status="succeeded",
            content={
                "kind": "memory_recall",
                "items": items,
            },
            evidence=[
                CapabilityEvidence(
                    source_type="memory",
                    source_ref=f"memory://{item['memory_id']}",
                    content_digest=str(item["content"])[:1000],
                )
                for item in items
            ],
        )

    registry.register(
        CapabilitySpec(
            name="knowledge_search",
            kind=CapabilityKind.TOOL,
            description="Search the local knowledge base and return bounded evidence chunks.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_chunks": {"type": "integer", "minimum": 1, "maximum": 10},
                    "max_tokens": {"type": "integer", "minimum": 128, "maximum": 8000},
                },
                "required": ["query"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            version="2.0.0",
            executor=knowledge,
        ),
        replace=True,
    )
    registry.register(
        CapabilitySpec(
            name="memory_search",
            kind=CapabilityKind.TOOL,
            description="Search explicitly stored cross-session memory items.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            version="2.0.0",
            executor=memory,
        ),
        replace=True,
    )
