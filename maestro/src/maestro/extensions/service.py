from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from maestro.config import MCPServerSettings
from maestro.foundation.llm import LLMError
from maestro.foundation.tools.builtin import QUERY_READONLY_TOOLS
from maestro.skills.parser import validate_skill_package
from maestro.skills.schemas import SkillMeta, SkillValidationError
from maestro.skills.store import package_sha256

from .adapters import connector_items, skill_packages, stable_hash
from .github import GitHubClient
from .schemas import CatalogSkill, SourceState, SyncRun, utcnow
from .sources import SOURCES, SOURCE_BY_ID
from .store import ExtensionCatalogStore


LICENSE_ALLOWLIST = {"MIT", "Apache-2.0", "Apache 2.0", "BSD-3-Clause", "CC0-1.0"}


class ExtensionCatalogService:
    def __init__(self, store: ExtensionCatalogStore, platform):
        self.store = store
        self.platform = platform
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def validation_fingerprint(self, source_id: str) -> str:
        value = {
            "schema": 1,
            "adapter": 2,
            "source": source_id,
            "tools": sorted(self.platform.tools.names()),
            "preconditions": sorted(self.platform.named_preconditions),
            "skill_body_max": self.platform.settings.skill_body_max_bytes,
            "licenses": sorted(LICENSE_ALLOWLIST),
        }
        return stable_hash(value)

    async def _translate(self, text: str) -> tuple[str | None, str | None]:
        """把英文描述翻成 (中文简介, 中文描述)；LLM 不可用或失败时返回 (None, None) 走英文回退。"""
        text = (text or "").strip()
        if not text or not self.platform.llm.available:
            return None, None
        try:
            raw = await self.platform.llm.complete(
                '你是技术文档翻译助手。把用户给的英文扩展描述翻成中文，只输出 JSON，不要代码块或解释：'
                '{"summary":"一句话中文简介，≤30字","description":"完整中文描述"}。',
                [{"role": "user", "content": text}],
            )
            data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        except (LLMError, ValueError):
            return None, None
        summary = data.get("summary") if isinstance(data.get("summary"), str) else None
        description = data.get("description") if isinstance(data.get("description"), str) else None
        return (summary or None), (description or None)

    def start_sync(self, source_ids: list[str] | None = None, trigger: str = "manual", force: bool = False) -> SyncRun:
        if self._task and not self._task.done():
            active = next((run for run in reversed(self.store.runs) if run.status == "running"), None)
            if active:
                return active
        ids = source_ids or [source.id for source in SOURCES if source.enabled]
        unknown = [item for item in ids if item not in SOURCE_BY_ID]
        if unknown:
            raise KeyError(unknown[0])
        run = SyncRun(run_id=uuid.uuid4().hex, trigger=trigger, source_ids=ids)
        self.store.save_run(run)
        self._task = asyncio.create_task(self._sync(run, force))
        return run

    async def _sync(self, run: SyncRun, force: bool) -> None:
        counts = {name: 0 for name in ("discovered", "sources_unchanged", "items_unchanged", "added", "updated", "withdrawn", "failed")}
        client = GitHubClient(os.environ.get("GITHUB_TOKEN", ""))
        async with self._lock:
            try:
                for source_id in run.source_ids:
                    source = SOURCE_BY_ID[source_id]
                    state = self.store.states.get(source_id, SourceState(source_id=source_id))
                    fingerprint = self.validation_fingerprint(source_id)
                    try:
                        commit = await client.head_commit(source)
                        state.last_checked_at = utcnow()
                        if not force and not state.stale and state.last_synced_commit == commit and state.validation_fingerprint == fingerprint:
                            counts["sources_unchanged"] += 1
                            self.store.states[source_id] = state
                            continue
                        tree = await client.tree(source, commit)
                        if source.kind == "skill":
                            await self._sync_skills(client, source, commit, tree, counts)
                        else:
                            await self._sync_connectors(client, source, commit, tree, counts)
                        state.last_synced_commit = commit
                        state.validation_fingerprint = fingerprint
                        state.last_success_at = utcnow()
                        state.stale = False
                        state.last_error = None
                    except Exception as exc:  # source isolation is intentional
                        state.stale = True
                        state.last_error = str(exc)
                        run.errors[source_id] = str(exc)
                        counts["failed"] += 1
                    self.store.states[source_id] = state
                    self.store.save()
            finally:
                await client.close()
        run.counts = counts
        run.completed_at = utcnow()
        run.status = "completed" if not run.errors else ("partial" if len(run.errors) < len(run.source_ids) else "failed")
        self.store.save()
        self.store.save_run(run)

    async def _sync_skills(self, client, source, commit, tree, counts) -> None:
        seen = set()
        for fallback_name, root, package, blob_sha in await skill_packages(client, source, commit, tree):
            fm, body, attachments, report = validate_skill_package(package, f"{fallback_name}.zip", set(self.platform.tools.names()), list(QUERY_READONLY_TOOLS), set(self.platform.named_preconditions), self.platform.settings.skill_body_max_bytes)
            name = fm.name if fm else fallback_name
            catalog_id = f"{source.id}:{name}"
            seen.add(catalog_id)
            previous = self.store.skills.get(catalog_id)
            if previous and previous.blob_sha == blob_sha and self.store.package_path(catalog_id).exists():
                previous.last_checked_at = utcnow()
                previous.source_commit = commit
                if previous.installable and previous.summary_zh is None:
                    previous.summary_zh, previous.description_zh = await self._translate(previous.description)
                counts["items_unchanged"] += 1
                continue
            counts["discovered"] += 1
            if fm and body is not None:
                digest = package_sha256(body, attachments)
                license_value = fm.license
                installable = report.compatible and (license_value in LICENSE_ALLOWLIST or license_value is None)
                reason = None if installable else ("许可证未获准" if report.compatible else "; ".join(report.errors))
                item = CatalogSkill(catalog_id=catalog_id, name=fm.name, display_name=fm.display_name or fm.name, description=fm.description, author=fm.author, license=license_value, version=fm.version, source_id=source.id, source_name=source.display_name, source_url=f"{source.source_url}/tree/{commit}/{root}", source_ref=source.ref, source_commit=commit, blob_sha=blob_sha, package_sha256=digest, compatibility_status=report.compatibility_status, warnings=report.warnings, has_scripts=bool(fm.scripts), installable=installable, install_block_reason=reason)
                item.summary_zh, item.description_zh = await self._translate(fm.description)
            else:
                digest = hashlib.sha256(package).hexdigest()
                item = CatalogSkill(catalog_id=catalog_id, name=name, display_name=name, description="上游技能当前与 Maestro 不兼容", source_id=source.id, source_name=source.display_name, source_url=f"{source.source_url}/tree/{commit}/{root}", source_ref=source.ref, source_commit=commit, blob_sha=blob_sha, package_sha256=digest, compatibility_status="not_ready", warnings=report.errors, installable=False, install_block_reason="; ".join(report.errors))
            self.store.skills[catalog_id] = item
            self.store.put_package(catalog_id, package)
            counts["updated" if previous else "added"] += 1
        for item in self.store.skills.values():
            if item.source_id == source.id and item.catalog_id not in seen and not item.withdrawn:
                item.withdrawn = True
                item.installable = False
                item.install_block_reason = "上游已撤回"
                counts["withdrawn"] += 1

    async def _sync_connectors(self, client, source, commit, tree, counts) -> None:
        incoming = await connector_items(client, source, commit, tree)
        seen = {item.catalog_id for item in incoming}
        for item in incoming:
            previous = self.store.connectors.get(item.catalog_id)
            if previous and previous.catalog_template_sha256 == item.catalog_template_sha256 and previous.description == item.description:
                previous.source_commit = commit
                previous.last_checked_at = utcnow()
                if previous.summary_zh is None:
                    previous.summary_zh, _ = await self._translate(previous.description)
                counts["items_unchanged"] += 1
            else:
                # 英文简介未变则复用旧的中文翻译，仅在变化时才重新调用大模型
                if previous and previous.description == item.description and previous.summary_zh:
                    item.summary_zh = previous.summary_zh
                else:
                    item.summary_zh, _ = await self._translate(item.description)
                self.store.connectors[item.catalog_id] = item
                counts["updated" if previous else "added"] += 1
            counts["discovered"] += 1
        for item in self.store.connectors.values():
            if item.source_id == source.id and item.catalog_id not in seen and not item.withdrawn:
                item.withdrawn = True
                item.installable = False
                item.install_block_reason = "上游已撤回"
                counts["withdrawn"] += 1

    def list_skills(self, q: str = "", source_id: str | None = None):
        query = q.casefold()
        installed = {item.name: item for item in self.platform.skill_store.list_all()}
        # 同名去重：跨来源浏览时同名技能只保留优先级最高的来源（OpenAI 优先于 Anthropic，
        # 顺序取自 SOURCES）。按单一来源筛选时不去重，展示该来源自身全部条目。
        priority = {source.id: index for index, source in enumerate(SOURCES)}
        rank = lambda cid: priority.get(self.store.skills[cid].source_id, len(SOURCES))  # noqa: E731
        preferred: dict[str, str] = {}
        for original in self.store.skills.values():
            current = preferred.get(original.name)
            if current is None or priority.get(original.source_id, len(SOURCES)) < rank(current):
                preferred[original.name] = original.catalog_id
        result = []
        for original in self.store.skills.values():
            if source_id is None and preferred.get(original.name) != original.catalog_id:
                continue
            item = original.model_copy(deep=True)
            local = installed.get(item.name)
            item.installed = local is not None
            item.installed_sha256 = local.package_sha256 if local else None
            item.update_available = bool(local and local.package_sha256 != item.package_sha256)
            haystack = f"{item.name} {item.display_name} {item.description} {item.author or ''} {item.source_name}".casefold()
            if (not query or query in haystack) and (not source_id or item.source_id == source_id):
                result.append(item)
        return sorted(result, key=lambda item: (item.compatibility_status == "not_ready", item.display_name.casefold()))

    def list_connectors(self, q: str = "", source_id: str | None = None):
        query = q.casefold()
        configured, _ = self.platform.mcp_config_store.list()
        by_catalog = {item.catalog_id: item for item in configured if item.catalog_id}
        result = []
        for original in self.store.connectors.values():
            item = original.model_copy(deep=True)
            local = by_catalog.get(item.catalog_id)
            item.configured = local is not None
            item.configured_name = local.name if local else None
            item.configured_catalog_id = local.catalog_id if local else None
            item.configured_template_version = local.catalog_version if local else None
            item.update_available = bool(local and local.catalog_template_sha256 != item.catalog_template_sha256)
            haystack = f"{item.name} {item.display_name} {item.description} {item.author or ''} {item.source_name}".casefold()
            if (not query or query in haystack) and (not source_id or item.source_id == source_id):
                result.append(item)
        return sorted(result, key=lambda item: item.display_name.casefold())

    async def install_skill(self, catalog_id: str, expected_hash: str | None = None, update: bool = False):
        item = self.store.skills.get(catalog_id)
        if not item:
            raise KeyError(catalog_id)
        if not item.installable or item.withdrawn:
            raise SkillValidationError(item.install_block_reason or "技能不可安装")
        if expected_hash and expected_hash != item.package_sha256:
            raise ValueError("目录版本已变化，请重新检查")
        source = SOURCE_BY_ID[item.source_id]
        client = GitHubClient(os.environ.get("GITHUB_TOKEN", ""))
        try:
            tree = await client.tree(source, item.source_commit)
            candidates = await skill_packages(client, source, item.source_commit, tree)
            package = next((data for fallback, _root, data, _blob in candidates if fallback == item.source_url.rstrip("/").rsplit("/", 1)[-1]), None)
        finally:
            await client.close()
        if package is None:
            raise SkillValidationError("固定 commit 中已找不到该技能")
        fm, body, attachments, report = validate_skill_package(package, f"{item.name}.zip", set(self.platform.tools.names()), list(QUERY_READONLY_TOOLS), set(self.platform.named_preconditions), self.platform.settings.skill_body_max_bytes)
        if not report.compatible or not fm or body is None or package_sha256(body, attachments) != item.package_sha256:
            raise SkillValidationError("缓存包校验失败")
        meta = SkillMeta(**fm.model_dump(), file_count=1 + len(attachments), bytes=len(body.encode()) + sum(map(len, attachments.values())), archive_bytes=len(package), added_at=datetime.now(timezone.utc).isoformat(), compatibility_status=report.compatibility_status, warnings=report.warnings)
        meta.extensions["catalog"] = {"catalog_id": catalog_id, "source_commit": item.source_commit}
        if update:
            self.platform.skill_store.replace(meta, body, attachments)
        else:
            self.platform.skill_store.save(meta, body, attachments)
        return meta

    def add_connector(self, catalog_id: str, payload: dict):
        item = self.store.connectors.get(catalog_id)
        if not item or not item.installable or item.withdrawn:
            raise KeyError(catalog_id)
        servers, revision = self.platform.mcp_config_store.list()
        name = payload.get("name") or item.name
        if any(server.name == name for server in servers):
            raise ValueError("连接器名称已存在")
        env = dict(payload.get("env", {}))
        server = MCPServerSettings(name=name, display_name=payload.get("display_name") or item.display_name, description=item.description, command=item.command, args=payload.get("args", item.args), env=env, secret_env_keys=[spec.name for spec in item.env_schema if spec.secret], enabled=False, catalog_id=catalog_id, catalog_version=item.version, catalog_template_sha256=item.catalog_template_sha256)
        new_revision = self.platform.mcp_config_store.save_all(servers + [server], payload.get("expected_revision", revision))
        return server, new_revision
