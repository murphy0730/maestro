"""延迟工具检索。

提供 tool_search 工具，按名称或关键词检索延迟加载（should_defer）的工具，
返回其完整定义供 Agent 后续调用。迁移自 Claude Code 的 SearchExtraToolsTool
（简化版：关键词计分，不做 TF-IDF）。

查询形式：
- "select:tool_a,tool_b"  按名称精确选取
- "keyword one two"       关键词检索（命中 name/description/search_hint 计分）
- "+must other"           前缀 + 的词必须命中
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from ..base import (
    Tool,
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
    tool_matches_name,
)


class ToolSearchArgs(BaseModel):
    query: str = Field(
        description=(
            'Query to find deferred tools. Use "select:<tool_name>[,<tool_name>...]" '
            "for direct selection, or keywords to search; prefix a keyword with + to require it."
        )
    )
    max_results: Optional[int] = Field(default=5, description="Maximum number of results (default 5)")


def _tool_brief(tool: Tool) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema.model_json_schema(),
    }


def _search_text(tool: Tool) -> str:
    return " ".join(
        filter(None, [tool.name, tool.description, tool.search_hint or ""])
    ).lower()


async def tool_search_execute(
    args: ToolSearchArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    from ..registry import registry

    deferred = registry.list_deferred()
    loaded = registry.list_initial_load()
    max_results = args.max_results or 5
    query = args.query.strip()

    matches: List[dict] = []
    already_loaded: List[str] = []

    if query.startswith("select:"):
        names = [n.strip() for n in query[len("select:"):].split(",") if n.strip()]
        for name in names:
            tool = next((t for t in deferred if tool_matches_name(t, name)), None)
            if tool:
                matches.append(_tool_brief(tool))
            elif any(tool_matches_name(t, name) for t in loaded):
                already_loaded.append(name)
    else:
        terms = [t.lower() for t in query.split() if t]
        required = [t[1:] for t in terms if t.startswith("+") and len(t) > 1]
        optional = [t for t in terms if not t.startswith("+")]
        scored = []
        for tool in deferred:
            text = _search_text(tool)
            if any(term not in text for term in required):
                continue
            score = sum(1 for term in optional if term in text) + len(required)
            if score > 0:
                scored.append((score, tool))
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        matches = [_tool_brief(t) for _, t in scored[:max_results]]

    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        content={
            "query": args.query,
            "matches": matches,
            "total_deferred_tools": len(deferred),
            "already_loaded": already_loaded,
        }
    )


ToolSearchTool = build_tool(ToolDef(
    name="tool_search",
    description=(
        "Search deferred tools by name or keywords and return their full definitions "
        "so they can be called. Deferred tools are not in the initial tool list."
    ),
    input_schema=ToolSearchArgs,
    execute=tool_search_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    max_result_size_chars=100_000,
    always_load=True,
))


def register_tool_search_tools():
    from ..registry import registry
    registry.register(ToolSearchTool)
