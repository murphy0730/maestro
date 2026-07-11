"""Persistent editable MCP configurations with revision and secret redaction."""

from __future__ import annotations

from maestro.config import MCPServerSettings, runtime_data_root
from maestro.foundation.settings_json_store import SettingsJsonStore


class MCPConfigStore:
    def __init__(self, store: SettingsJsonStore | None = None):
        self.settings = store or SettingsJsonStore(runtime_data_root() / "settings.json")

    def list(self) -> tuple[list[MCPServerSettings], int]:
        data = self.settings.read()
        return [MCPServerSettings.model_validate(item) for item in data.get("mcp_servers", [])], int(data["revision"])

    def save_all(self, servers: list[MCPServerSettings], expected_revision: int | None) -> int:
        return self.settings.update_section(
            "mcp_servers", [server.model_dump(mode="json") for server in servers], expected_revision
        )
