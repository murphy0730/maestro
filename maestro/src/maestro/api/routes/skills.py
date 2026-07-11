"""Skill package management endpoints."""

from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from maestro.api.routes.knowledge import _MAX_UPLOAD_BYTES
from maestro.foundation.tools.builtin import QUERY_READONLY_TOOLS
from maestro.skills.parser import validate_skill_package
from maestro.skills.schemas import SkillMeta, SkillValidationError

router = APIRouter()


class TrustSkillRequest(BaseModel):
    package_sha256: str
    acknowledged_script_execution: bool = False


def _require_local_origin(request: Request) -> None:
    """Trust is a privileged local-desktop action; reject arbitrary web origins."""
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return
    host = urlparse(origin).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="技能信任操作仅允许来自本机应用")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/skills")
async def list_skills(request: Request):
    """列出全部已导入技能包的元数据。"""
    store = request.app.state.platform.skill_store
    return {
        "skills": [
            {**meta.model_dump(), "trust": store.trust_status(meta.name)}
            for meta in store.list_all()
        ]
    }


@router.post("/skills/import", status_code=201)
async def import_skill(request: Request, file: UploadFile = File(...)):
    """导入技能包（.md / .zip）。"""
    platform = request.app.state.platform
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
    filename = file.filename or ""
    if not (filename.lower().endswith(".md") or filename.lower().endswith(".zip")):
        raise HTTPException(status_code=415, detail="仅支持 .md / .zip 后缀")
    try:
        frontmatter, body, attachments, report = validate_skill_package(
            data,
            filename,
            set(platform.tools.names()),
            list(QUERY_READONLY_TOOLS),
            set(platform.named_preconditions.keys()),
            platform.settings.skill_body_max_bytes,
        )
        if not report.compatible or frontmatter is None or body is None:
            raise HTTPException(status_code=422, detail="; ".join(report.errors))
    except SkillValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    meta = SkillMeta(
        **frontmatter.model_dump(),
        file_count=len(attachments),
        bytes=len(data),
        added_at=_now_iso(),
        compatibility_status=report.compatibility_status,
        warnings=report.warnings,
    )
    try:
        platform.skill_store.save(meta, body, attachments)
    except KeyError:
        raise HTTPException(status_code=409, detail=f"技能 {meta.name} 已存在") from None
    return meta


@router.post("/skills/validate")
async def validate_skill(request: Request, file: UploadFile = File(...)):
    """预检兼容性，不写入技能仓库。"""
    platform = request.app.state.platform
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
    filename = file.filename or ""
    if not (filename.lower().endswith(".md") or filename.lower().endswith(".zip")):
        raise HTTPException(status_code=415, detail="仅支持 .md / .zip 后缀")
    _, _, _, report = validate_skill_package(
        data,
        filename,
        set(platform.tools.names()),
        list(QUERY_READONLY_TOOLS),
        set(platform.named_preconditions.keys()),
        platform.settings.skill_body_max_bytes,
    )
    return report.model_dump()


@router.get("/skills/{name}/trust")
async def get_skill_trust(name: str, request: Request):
    try:
        return request.app.state.platform.skill_store.trust_status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在") from None


@router.post("/skills/{name}/trust")
async def trust_skill(name: str, payload: TrustSkillRequest, request: Request):
    _require_local_origin(request)
    if not payload.acknowledged_script_execution:
        raise HTTPException(status_code=422, detail="必须明确确认将允许当前版本脚本进入权限执行流程")
    store = request.app.state.platform.skill_store
    try:
        store.trust(name, payload.package_sha256, principal_id="local-user")
        return store.trust_status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在") from None
    except SkillValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/skills/{name}/trust")
async def revoke_skill_trust(name: str, request: Request):
    _require_local_origin(request)
    store = request.app.state.platform.skill_store
    if store.get(name) is None:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    return {"revoked": store.revoke_trust(name), **store.trust_status(name)}


@router.delete("/skills/{name}")
async def delete_skill(name: str, request: Request):
    """删除技能包。不存在 → 404。"""
    if not request.app.state.platform.skill_store.delete(name):
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    return {"deleted": True, "name": name}
