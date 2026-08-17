"""Small fixed capability surface used to discover lazy working content."""

from __future__ import annotations

from maestro.runtime.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySpec,
    RiskLevel,
)


def register_runtime_meta_capabilities(registry: CapabilityRegistry) -> None:
    definitions = [
        CapabilitySpec(
            name="tool_search",
            kind=CapabilityKind.TOOL,
            description="Search the capability index. Returned candidates become callable next turn.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "namespace": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            version="2.0.0",
        ),
        CapabilitySpec(
            name="load_skill",
            kind=CapabilityKind.TOOL,
            description="Activate one skill from the frozen session skill index.",
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "arguments": {"type": "string"},
                },
                "required": ["skill_id"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            version="2.0.0",
        ),
        CapabilitySpec(
            name="get_current_plan",
            kind=CapabilityKind.TOOL,
            description=(
                "Read the current persisted Maestro agent execution plan and task states. "
                "This is internal Runtime orchestration state. Never use this tool for a "
                "domain or business plan, schedule, or solution; use a listed skill or "
                "tool_search instead."
            ),
            input_schema={"type": "object", "properties": {}},
            risk=RiskLevel.LOW,
            writes=False,
            version="2.0.0",
        ),
        CapabilitySpec(
            name="get_result_detail",
            kind=CapabilityKind.TOOL,
            description=(
                "Read a bounded JSON chunk from a previously referenced tool result owned "
                "by this session. result_id accepts either a bare id or tool-result:// ref. "
                "Reuse source_result_id with next_offset to continue."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "result_id": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "max_chars": {"type": "integer", "minimum": 256, "maximum": 2500},
                },
                "required": ["result_id"],
            },
            risk=RiskLevel.LOW,
            writes=False,
            version="2.0.0",
        ),
    ]
    for definition in definitions:
        registry.register(definition, replace=True)
