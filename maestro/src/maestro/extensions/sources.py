from .schemas import CatalogSource


SOURCES = [
    CatalogSource(id="openai-skills-curated", kind="skill", display_name="OpenAI Skills", owner="openai", repo="skills", source_url="https://github.com/openai/skills", paths=["skills/.curated"]),
    CatalogSource(id="anthropics-skills", kind="skill", display_name="Anthropic Skills", owner="anthropics", repo="skills", source_url="https://github.com/anthropics/skills", paths=["skills/pdf", "skills/docx", "skills/pptx", "skills/xlsx"]),
    CatalogSource(id="mcp-reference-servers", kind="connector", display_name="MCP Reference Servers", owner="modelcontextprotocol", repo="servers", source_url="https://github.com/modelcontextprotocol/servers", paths=["src/filesystem", "src/memory", "src/sequentialthinking", "src/fetch", "src/git", "src/time"]),
    CatalogSource(id="github-mcp-server", kind="connector", display_name="GitHub MCP Server", owner="github", repo="github-mcp-server", source_url="https://github.com/github/github-mcp-server", paths=["."]),
    CatalogSource(id="playwright-mcp", kind="connector", display_name="Playwright MCP", owner="microsoft", repo="playwright-mcp", source_url="https://github.com/microsoft/playwright-mcp", paths=["."]),
]

SOURCE_BY_ID = {source.id: source for source in SOURCES}
