"""网页抓取工具。

提供 web_fetch 工具用于抓取 URL 内容并转为纯文本。
迁移自 Claude Code 的 WebFetchTool：http 自动升级 https，同主机重定向自动跟随，
跨主机重定向返回提示（由调用方决定是否二次抓取），HTML 做标签剥离。
依赖 httpx（随 openai 传递安装）；缺库时工具返回错误而非崩溃。
"""

import html as html_lib
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field

from ..base import (
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
)

MAX_CONTENT_CHARS = 100_000
MAX_SAME_HOST_REDIRECTS = 5
FETCH_TIMEOUT_SECONDS = 30.0


class WebFetchArgs(BaseModel):
    url: str = Field(description="The URL to fetch content from (http/https)")


def _validate_url(args: WebFetchArgs, context: dict) -> Optional[str]:
    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return f"Invalid URL: {args.url}. Only http/https URLs are supported."
    return None


def _html_to_text(content: str) -> str:
    """粗粒度 HTML → 纯文本: 去 script/style，剥标签，压空行。"""
    content = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", content)
    content = re.sub(r"(?s)<[^>]+>", " ", content)
    content = html_lib.unescape(content)
    lines = [ln.strip() for ln in content.splitlines()]
    return "\n".join(ln for ln in lines if ln)


async def web_fetch_execute(
    args: WebFetchArgs,
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        import httpx
    except ImportError:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message="httpx is not installed; web_fetch is unavailable"
        )

    # 与参考实现一致: http 升级为 https
    url = args.url
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS
        ) as client:
            for _ in range(MAX_SAME_HOST_REDIRECTS):
                response = await client.get(url)
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                location = response.headers.get("location")
                if not location:
                    break
                redirect_url = urljoin(url, location)
                # 跨主机重定向不自动跟随，返回提示让调用方显式二次抓取
                if urlparse(redirect_url).netloc != urlparse(url).netloc:
                    return ToolResult(
                        status=ToolResultStatus.SUCCESS,
                        content={
                            "url": url,
                            "status_code": response.status_code,
                            "redirect_url": redirect_url,
                            "content": (
                                "REDIRECT DETECTED: The URL redirects to a different host. "
                                f"Call web_fetch again with url: {redirect_url}"
                            ),
                        }
                    )
                url = redirect_url

        content_type = response.headers.get("content-type", "")
        text = response.text
        if "html" in content_type:
            text = _html_to_text(text)
        if len(text) > MAX_CONTENT_CHARS:
            text = text[:MAX_CONTENT_CHARS] + "\n\n[Content truncated]"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "content": text,
                "bytes": len(response.content),
            }
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=f"Fetch failed: {e}"
        )


WebFetchTool = build_tool(ToolDef(
    name="web_fetch",
    description=(
        "Fetch content from a URL and convert it to plain text. "
        "Fails for authenticated or private URLs."
    ),
    input_schema=WebFetchArgs,
    execute=web_fetch_execute,
    validate_input=_validate_url,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=True,
    is_concurrency_safe=True,
    max_result_size_chars=100_000,
    should_defer=True,
    search_hint="fetch and extract content from a URL web http"
))


def register_web_tools(tool_registry=None):
    from ..registry import registry

    (tool_registry or registry).register(WebFetchTool)
