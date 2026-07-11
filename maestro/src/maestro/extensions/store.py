from __future__ import annotations

import json
import threading
from pathlib import Path

from .schemas import CatalogConnector, CatalogSkill, SourceState, SyncRun


class ExtensionCatalogStore:
    def __init__(self, base_dir: Path):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.packages_dir = self.base / "packages"
        self.packages_dir.mkdir(exist_ok=True)
        self.path = self.base / "catalog.json"
        self.runs_path = self.base / "sync-runs.json"
        self.lock = threading.RLock()
        self.skills: dict[str, CatalogSkill] = {}
        self.connectors: dict[str, CatalogConnector] = {}
        self.states: dict[str, SourceState] = {}
        self.runs: list[SyncRun] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text("utf-8"))
            self.skills = {item["catalog_id"]: CatalogSkill(**item) for item in raw.get("skills", [])}
            self.connectors = {item["catalog_id"]: CatalogConnector(**item) for item in raw.get("connectors", [])}
            self.states = {item["source_id"]: SourceState(**item) for item in raw.get("states", [])}
        if self.runs_path.exists():
            self.runs = [SyncRun(**item) for item in json.loads(self.runs_path.read_text("utf-8"))]

    def _atomic_json(self, path: Path, value: object) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), "utf-8")
        tmp.replace(path)

    def save(self) -> None:
        with self.lock:
            self._atomic_json(self.path, {"skills": [x.model_dump(mode="json") for x in self.skills.values()], "connectors": [x.model_dump(mode="json") for x in self.connectors.values()], "states": [x.model_dump(mode="json") for x in self.states.values()]})

    def save_run(self, run: SyncRun) -> None:
        with self.lock:
            self.runs = [item for item in self.runs if item.run_id != run.run_id] + [run]
            self.runs = self.runs[-100:]
            self._atomic_json(self.runs_path, [x.model_dump(mode="json") for x in self.runs])

    def package_path(self, catalog_id: str) -> Path:
        safe = catalog_id.replace(":", "__")
        return self.packages_dir / f"{safe}.zip"

    def put_package(self, catalog_id: str, data: bytes) -> None:
        target = self.package_path(catalog_id)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)

    def get_package(self, catalog_id: str) -> bytes:
        return self.package_path(catalog_id).read_bytes()
