"""MCP 服务器配置在 settings.json 上的读写。

与 `model_config.py` 同样的分节约定：配置落在 <数据根>/settings.json 的
`mcp_servers` 键下，由 `SettingsJsonStore` 做原子的分节写。

一份损坏的配置不应让其余服务器全部消失：解析按服务器逐条进行，坏的那条被
跳过并记录，其余照常返回。
"""

from __future__ import annotations

import logging
from pathlib import Path

from maestro.config import runtime_data_root
from maestro.foundation.settings_json_store import SettingsJsonStore
from maestro.mcp.types import MCPServerConfig

logger = logging.getLogger(__name__)

MCP_SERVERS_KEY = "mcp_servers"


def settings_json_path() -> Path:
    return runtime_data_root() / "settings.json"


class MCPConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self._store = SettingsJsonStore(path or settings_json_path())

    def load(self) -> list[MCPServerConfig]:
        raw = self._store.read().get(MCP_SERVERS_KEY)
        if not isinstance(raw, dict):
            return []
        configs = []
        for name, entry in raw.items():
            if not isinstance(name, str) or not isinstance(entry, dict):
                logger.warning("[mcp] 跳过格式不正确的服务器条目: %r", name)
                continue
            try:
                configs.append(MCPServerConfig.from_dict(name, entry))
            except ValueError as error:
                logger.warning("[mcp] 跳过无效的服务器配置 %s: %s", name, error)
        return configs

    def save(self, configs: list[MCPServerConfig]) -> int:
        return self._store.update_section(
            MCP_SERVERS_KEY, {config.name: config.to_dict() for config in configs}
        )

    def upsert(self, config: MCPServerConfig) -> int:
        remaining = [item for item in self.load() if item.name != config.name]
        return self.save([*remaining, config])

    def delete(self, name: str) -> bool:
        configs = self.load()
        remaining = [item for item in configs if item.name != name]
        if len(remaining) == len(configs):
            return False
        self.save(remaining)
        return True
