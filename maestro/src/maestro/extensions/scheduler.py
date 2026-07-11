from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class CatalogScheduler:
    def __init__(self, service, settings):
        self.service = service
        self.settings = settings

    def next_run(self, now: datetime | None = None) -> datetime:
        zone = ZoneInfo(self.settings.extension_catalog_sync_timezone)
        current = (now or datetime.now(zone)).astimezone(zone)
        hour, minute = map(int, self.settings.extension_catalog_sync_time.split(":"))
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate if candidate > current else candidate + timedelta(days=1)

    async def run(self) -> None:
        if not self.settings.extension_catalog_sync_enabled:
            await asyncio.Event().wait()
        if not any(state.last_success_at for state in self.service.store.states.values()):
            self.service.start_sync(trigger="startup_recovery")
        while True:
            delay = max(0.0, (self.next_run() - datetime.now(ZoneInfo(self.settings.extension_catalog_sync_timezone))).total_seconds())
            await asyncio.sleep(delay)
            self.service.start_sync(trigger="scheduled")
