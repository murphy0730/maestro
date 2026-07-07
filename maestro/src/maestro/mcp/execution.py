"""MCP 执行模块。

用于调用 MCP 工具和读取 MCP 资源。
"""

from typing import Any, Dict, List


async def call_mcp_tool(
    transport,
    tool_name: str,
    arguments: Dict[str, Any],
    request_id: int,
    timeout: float = 60.0
) -> Dict[str, Any]:
    """调用 MCP 工具。"""
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    await transport.send_message(request)
    response = await transport.receive_response(request_id, timeout=timeout)

    if response is None:
        raise TimeoutError("MCP tool call timed out")
    if 'error' in response:
        raise RuntimeError(f"MCP error: {response['error'].get('message', 'Unknown error')}")

    return response.get('result', {})


async def read_mcp_resource(
    transport,
    uri: str,
    request_id: int,
    timeout: float = 30.0
) -> List[Dict[str, Any]]:
    """读取 MCP 资源。"""
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "resources/read",
        "params": {
            "uri": uri
        }
    }

    await transport.send_message(request)
    response = await transport.receive_response(request_id, timeout=timeout)

    if response is None:
        raise TimeoutError("MCP resource read timed out")
    if 'error' in response:
        raise RuntimeError(f"MCP error: {response['error'].get('message', 'Unknown error')}")

    return response.get('result', {}).get('contents', [])
