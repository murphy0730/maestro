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
from maestro.skills.schemas import SkillMeta


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
    stored_item = service.store.skills[item.catalog_id]
    stored_item.summary_zh = "目录测试技能"
    stored_item.description_zh = "用于验证目录安装流程的测试技能"
    installed = await service.install_skill(item.catalog_id)
    assert installed.name == "catalog-test"
    assert installed.summary_zh == "目录测试技能"
    assert installed.description_zh == "用于验证目录安装流程的测试技能"
    assert p.skill_store.get("catalog-test").summary_zh == "目录测试技能"

    second = service.start_sync(["openai-skills-curated"])
    await service._task
    assert second.counts["sources_unchanged"] == 1
    assert calls == {"head": 2, "tree": 2, "raw": 2}


def test_scheduler_uses_shanghai_three_am(tmp_path):
    scheduler = platform(tmp_path).catalog_scheduler
    now = datetime(2026, 7, 11, 2, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    next_run = scheduler.next_run(now)
    assert (next_run.hour, next_run.minute, next_run.day) == (3, 0, 11)


def test_catalog_uses_meaningful_chinese_summaries_without_llm(tmp_path):
    p = platform(tmp_path)
    service = p.catalog_service
    from maestro.extensions.schemas import CatalogConnector, CatalogSkill

    service.store.skills["source:pdf"] = CatalogSkill(
        catalog_id="source:pdf", name="pdf", display_name="PDF",
        description="Read and create PDF files", source_id="source",
        source_name="Source", source_url="https://example.com/pdf", source_ref="main",
        source_commit="abc", package_sha256="hash", compatibility_status="ready",
    )
    service.store.connectors["source:filesystem"] = CatalogConnector(
        catalog_id="source:filesystem", name="filesystem", display_name="Filesystem",
        description="来自 MCP Reference Servers 的官方 MCP 连接器", source_id="source",
        source_name="Source", source_url="https://example.com/filesystem", source_ref="main",
        source_commit="abc", command="npx", catalog_template_sha256="hash",
    )

    assert service.list_skills()[0].summary_zh == "读取、创建、编辑并检查 PDF 文档与页面排版"
    assert service.list_connectors()[0].summary_zh == "在授权目录内读取、搜索和管理本地文件与文件夹"


def test_existing_catalog_skill_localization_is_migrated(tmp_path):
    p = platform(tmp_path)
    service = p.catalog_service
    from maestro.extensions.schemas import CatalogSkill

    service.store.skills["source:legacy"] = CatalogSkill(
        catalog_id="source:legacy", name="legacy", display_name="Legacy",
        description="Legacy skill", summary_zh="旧版技能",
        description_zh="升级前已经安装的技能", source_id="source",
        source_name="Source", source_url="https://example.com/legacy", source_ref="main",
        source_commit="abc", package_sha256="hash", compatibility_status="ready",
    )
    meta = SkillMeta(
        name="legacy", description="Legacy skill", added_at="2026-07-13T00:00:00Z",
        extensions={"catalog": {"catalog_id": "source:legacy", "source_commit": "abc"}},
    )
    p.skill_store.save(meta, "legacy body", {})

    assert service.migrate_installed_localizations() == 1
    migrated = p.skill_store.get("legacy")
    assert migrated.summary_zh == "旧版技能"
    assert migrated.description_zh == "升级前已经安装的技能"
