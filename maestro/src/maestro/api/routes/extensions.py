from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from maestro.api.security import require_privileged
from maestro.foundation.settings_json_store import SettingsConflictError
from maestro.skills.schemas import SkillValidationError

router = APIRouter(prefix="/extension-catalog")


class SyncInput(BaseModel):
    force: bool = False


class SkillUpdateInput(BaseModel):
    expected_package_sha256: str


class ConnectorAddInput(BaseModel):
    name: str | None = None
    display_name: str | None = None
    args: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)
    expected_revision: int | None = None


class ConnectorUpdateInput(BaseModel):
    configured_name: str
    expected_revision: int
    expected_catalog_template_sha256: str


def _service(request: Request):
    return request.app.state.platform.catalog_service


@router.get("/sources")
async def sources():
    from maestro.extensions.sources import SOURCES
    return {"sources": [source.model_dump() for source in SOURCES]}


@router.get("/status")
async def status(request: Request):
    service = _service(request)
    active = next((run for run in reversed(service.store.runs) if run.status == "running"), None)
    latest = service.store.runs[-1] if service.store.runs else None
    return {"active": active.model_dump(mode="json") if active else None, "latest": latest.model_dump(mode="json") if latest else None, "sources": [state.model_dump(mode="json") for state in service.store.states.values()]}


@router.post("/sync", status_code=202)
async def sync_all(payload: SyncInput, request: Request, principal: str = Depends(require_privileged)):
    run = _service(request).start_sync(trigger="manual", force=payload.force)
    request.app.state.platform.audit.record(principal, "extension_catalog.sync", {"force": payload.force}, "allowed")
    return {"run_id": run.run_id, "status": run.status}


@router.post("/sources/{source_id}/sync", status_code=202)
async def sync_source(source_id: str, payload: SyncInput, request: Request, principal: str = Depends(require_privileged)):
    try:
        run = _service(request).start_sync([source_id], "manual", payload.force)
    except KeyError:
        raise HTTPException(404, "目录来源不存在") from None
    return {"run_id": run.run_id, "status": run.status}


def _page(items, page: int, page_size: int):
    start = (page - 1) * page_size
    return {"items": [item.model_dump(mode="json") for item in items[start:start + page_size]], "total": len(items), "page": page, "page_size": page_size}


@router.get("/skills")
async def skills(request: Request, q: str = "", source: str | None = None, compatibility: str | None = None, installed: bool | None = None, updates: bool | None = None, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    items = _service(request).list_skills(q, source)
    if compatibility:
        items = [item for item in items if item.compatibility_status == compatibility]
    if installed is not None:
        items = [item for item in items if item.installed == installed]
    if updates is not None:
        items = [item for item in items if item.update_available == updates]
    return _page(items, page, page_size)


@router.get("/skills/{catalog_id}")
async def skill_detail(catalog_id: str, request: Request):
    item = _service(request).store.skills.get(catalog_id)
    if not item:
        raise HTTPException(404, "目录技能不存在")
    return item


@router.post("/skills/{catalog_id}/install", status_code=201)
async def install_skill(catalog_id: str, request: Request, principal: str = Depends(require_privileged)):
    try:
        meta = await _service(request).install_skill(catalog_id)
    except KeyError:
        raise HTTPException(404, "目录技能不存在") from None
    except SkillValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    request.app.state.platform.audit.record(principal, "catalog_skill.install", {"catalog_id": catalog_id, "package_sha256": meta.package_sha256}, "allowed")
    return meta


@router.post("/skills/{catalog_id}/update")
async def update_skill(catalog_id: str, payload: SkillUpdateInput, request: Request, principal: str = Depends(require_privileged)):
    try:
        meta = await _service(request).install_skill(catalog_id, payload.expected_package_sha256, update=True)
        request.app.state.platform.audit.record(principal, "catalog_skill.update", {"catalog_id": catalog_id, "package_sha256": meta.package_sha256}, "allowed")
        return meta
    except KeyError:
        raise HTTPException(404, "目录技能或本地技能不存在") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SkillValidationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/connectors")
async def connectors(request: Request, q: str = "", source: str | None = None, configured: bool | None = None, updates: bool | None = None, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    items = _service(request).list_connectors(q, source)
    if configured is not None:
        items = [item for item in items if item.configured == configured]
    if updates is not None:
        items = [item for item in items if item.update_available == updates]
    return _page(items, page, page_size)


@router.get("/connectors/{catalog_id}/update-preview")
async def connector_preview(catalog_id: str, configured_name: str, request: Request):
    service = _service(request)
    item = service.store.connectors.get(catalog_id)
    servers, revision = request.app.state.platform.mcp_config_store.list()
    local = next((server for server in servers if server.name == configured_name and server.catalog_id == catalog_id), None)
    if not item or not local:
        raise HTTPException(404, "目录或已配置连接器不存在")
    return {"configured_name": configured_name, "revision": revision, "catalog_template_sha256": item.catalog_template_sha256, "changes": {"command": {"before": local.command, "after": item.command}, "args": {"before": local.args, "after": item.args}, "description": {"before": local.description, "after": item.description}}}


@router.post("/connectors/{catalog_id}/add", status_code=201)
async def add_connector(catalog_id: str, payload: ConnectorAddInput, request: Request, principal: str = Depends(require_privileged)):
    try:
        server, revision = _service(request).add_connector(catalog_id, payload.model_dump())
    except KeyError:
        raise HTTPException(404, "目录连接器不存在") from None
    except (ValueError, SettingsConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    request.app.state.platform.audit.record(principal, "catalog_connector.add", {"catalog_id": catalog_id, "name": server.name, "template_sha256": server.catalog_template_sha256}, "allowed")
    return {**server.model_dump(exclude={"env"}), "revision": revision}


@router.post("/connectors/{catalog_id}/update")
async def update_connector(catalog_id: str, payload: ConnectorUpdateInput, request: Request, principal: str = Depends(require_privileged)):
    service = _service(request)
    item = service.store.connectors.get(catalog_id)
    if not item:
        raise HTTPException(404, "目录连接器不存在")
    if item.catalog_template_sha256 != payload.expected_catalog_template_sha256:
        raise HTTPException(409, "目录模板已变化，请重新预览")
    servers, _ = request.app.state.platform.mcp_config_store.list()
    local = next((server for server in servers if server.name == payload.configured_name and server.catalog_id == catalog_id), None)
    if not local:
        raise HTTPException(404, "已配置连接器不存在")
    local.command, local.args, local.description = item.command, list(item.args), item.description
    local.catalog_version, local.catalog_template_sha256 = item.version, item.catalog_template_sha256
    try:
        revision = request.app.state.platform.mcp_config_store.save_all(servers, payload.expected_revision)
    except SettingsConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    request.app.state.platform.audit.record(principal, "catalog_connector.update", {"catalog_id": catalog_id, "name": local.name, "template_sha256": item.catalog_template_sha256}, "allowed")
    return {"updated": True, "name": local.name, "revision": revision}
