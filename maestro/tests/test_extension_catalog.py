import asyncio
import io
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from maestro.api.app import create_app
from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.extensions.github import GitHubClient


SKILL = b"""---
name: catalog-test
display_name: Catalog Test
description: catalog test skill
allowed_tools: [query_orders]
license: MIT
---
Follow the catalog test workflow.
"""


def platform(tmp_path):
    settings = Settings(
        privileged_api_token="secret",
        vector_backend="memory",
        audit_log_file=None,
        pending_actions_db=None,
        sessions_dir=tmp_path / "sessions",
        skills_dir=tmp_path / "skills",
        extension_catalog_data_dir=tmp_path / "extensions",
        extension_catalog_sync_enabled=False,
    )
    return build_platform(settings=settings)


def test_catalog_mutation_requires_bearer_token(tmp_path):
    app = create_app()
    app.state.platform = platform(tmp_path)
    client = TestClient(app)
    assert client.get("/extension-catalog/sources").status_code == 200
    assert client.post("/extension-catalog/sources/nope/sync", json={}).status_code == 401
    response = client.post(
        "/extension-catalog/sources/nope/sync",
        json={},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sync_install_and_source_short_circuit(tmp_path, monkeypatch):
    p = platform(tmp_path)
    service = p.catalog_service
    calls = {"head": 0, "tree": 0, "raw": 0}

    async def head(self, source):
        calls["head"] += 1
        return "abc123"

    async def tree(self, source, commit):
        calls["tree"] += 1
        return [
            {"path": "skills/.curated/catalog-test/SKILL.md", "type": "blob", "sha": "blob1"}
        ]

    async def raw(self, source, commit, path):
        calls["raw"] += 1
        return SKILL

    monkeypatch.setattr(GitHubClient, "head_commit", head)
    monkeypatch.setattr(GitHubClient, "tree", tree)
    monkeypatch.setattr(GitHubClient, "raw", raw)

    first = service.start_sync(["openai-skills-curated"])
    await service._task
    assert first.status == "completed"
    item = service.list_skills()[0]
    assert item.installable is True
    assert (await service.install_skill(item.catalog_id)).name == "catalog-test"

    second = service.start_sync(["openai-skills-curated"])
    await service._task
    assert second.counts["sources_unchanged"] == 1
    assert calls == {"head": 2, "tree": 2, "raw": 2}


def test_scheduler_uses_shanghai_three_am(tmp_path):
    scheduler = platform(tmp_path).catalog_scheduler
    now = datetime(2026, 7, 11, 2, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    next_run = scheduler.next_run(now)
    assert (next_run.hour, next_run.minute, next_run.day) == (3, 0, 11)
