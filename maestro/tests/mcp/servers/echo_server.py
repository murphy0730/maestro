"""A minimal stdio MCP server, just complete enough to exercise the client.

Behaviour is steered by environment variables so one script covers the failure
modes too:

  ECHO_FAIL_TOOL=1   `tools/call` answers with a JSON-RPC error
  ECHO_HANG_TOOL=1   `tools/call` never answers, to exercise the timeout
  ECHO_IS_ERROR=1    `tools/call` returns an MCP result with `isError=true`
  ECHO_STRUCTURED=1  return text plus structuredContent
  ECHO_BUSINESS_ERROR=1 return `{ok:false}` as an ordinary successful result
  ECHO_EXIT_TOOL=1   exit while a tool call is pending
  ECHO_NOISY=1       write a lot to stderr, to prove stderr is drained
  ECHO_BAD_LINE=1    emit a non-JSON line before responding
"""

import json
import os
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "回显传入的 text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "leak_env",
        "description": "回显本进程可见的环境变量名",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def send(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    if os.environ.get("ECHO_NOISY"):
        sys.stderr.write("x" * 200_000)
        sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        method = request.get("method")
        request_id = request.get("id")

        if method == "notifications/initialized":
            continue

        if os.environ.get("ECHO_BAD_LINE"):
            sys.stdout.write("not json at all\n")
            sys.stdout.flush()

        if method == "initialize":
            send({
                "jsonrpc": "2.0", "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "echo", "version": "1"},
                },
            })
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            if os.environ.get("ECHO_EXIT_TOOL"):
                return
            if os.environ.get("ECHO_HANG_TOOL"):
                continue
            if os.environ.get("ECHO_FAIL_TOOL"):
                send({
                    "jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32000, "message": "工具执行失败"},
                })
                continue
            if os.environ.get("ECHO_IS_ERROR"):
                send({
                    "jsonrpc": "2.0", "id": request_id,
                    "result": {
                        "isError": True,
                        "content": [{
                            "type": "text",
                            "text": os.environ.get(
                                "ECHO_IS_ERROR_TEXT", "远端工具拒绝了本次调用"
                            ),
                        }],
                    },
                })
                continue
            params = request.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name == "leak_env":
                payload = sorted(os.environ)
            else:
                payload = arguments.get("text", "")
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            if os.environ.get("ECHO_STRUCTURED"):
                result = {
                    "content": [{"type": "text", "text": "查询到 1 条结果"}],
                    "structuredContent": {"ok": True, "value": payload},
                }
            if os.environ.get("ECHO_BUSINESS_ERROR"):
                result = {
                    "content": [{"type": "text", "text": "匹配到多个订单"}],
                    "structuredContent": {
                        "ok": False,
                        "error": {"code": "AMBIGUOUS_ORDER", "suggestions": ["O-1", "O-2"]},
                    },
                }
            send({
                "jsonrpc": "2.0", "id": request_id,
                "result": result,
            })
        elif request_id is not None:
            send({
                "jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            })


if __name__ == "__main__":
    main()
