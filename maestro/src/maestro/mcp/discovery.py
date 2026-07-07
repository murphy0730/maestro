"""MCP 发现模块。

用于从 MCP 服务器发现工具和资源。
"""

from typing import Any, Dict, List

from .types import MCPTool, MCPResource


def parse_input_schema(tool_def: Dict[str, Any]) -> Dict[str, Any]:
    """解析工具输入模式。"""
    if 'inputSchema' in tool_def:
        return tool_def['inputSchema']

    return {
        "type": "object",
        "properties": {},
        "required": []
    }


def discover_tools_from_response(
    server_name: str,
    response: Dict[str, Any]
) -> List[MCPTool]:
    """从 tools/list 响应中发现工具。"""
    tools = []
    tool_defs = response.get('result', {}).get('tools', [])

    for tool_def in tool_defs:
        tool = MCPTool(
            name=tool_def['name'],
            description=tool_def.get('description', ''),
            input_schema=parse_input_schema(tool_def),
            server_name=server_name,
            metadata={}
        )

        if '_meta' in tool_def:
            tool.metadata = tool_def['_meta']

        tools.append(tool)

    return tools


def discover_resources_from_response(
    response: Dict[str, Any]
) -> List[MCPResource]:
    """从 resources/list 响应中发现资源。"""
    resources = []
    resource_defs = response.get('result', {}).get('resources', [])

    for resource_def in resource_defs:
        resource = MCPResource(
            uri=resource_def['uri'],
            name=resource_def.get('name', ''),
            description=resource_def.get('description', ''),
            mime_type=resource_def.get('mimeType', 'text/plain')
        )
        resources.append(resource)

    return resources
