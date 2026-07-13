"""Skill package management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from maestro.api.routes.knowledge import _MAX_UPLOAD_BYTES
from maestro.skills.parser import validate_skill_package
from maestro.skills.schemas import SkillMeta, SkillValidationError
from maestro.api.security import require_privileged

router = APIRouter()


class TrustSkillRequest(BaseModel):
    package_sha256: str
    acknowledged_script_execution: bool = False


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
async def import_skill(request: Request, file: UploadFile = File(...), principal: str = Depends(require_privileged)):
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
            set(platform.named_preconditions.keys()),
            platform.settings.skill_body_max_bytes,
        )
        if not report.compatible or frontmatter is None or body is None:
            raise HTTPException(status_code=422, detail="; ".join(report.errors))
    except SkillValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    meta = SkillMeta(
        **frontmatter.model_dump(),
        file_count=1 + len(attachments),
        bytes=len(body.encode("utf-8")) + sum(len(content) for content in attachments.values()),
        archive_bytes=len(data),
        added_at=_now_iso(),
        compatibility_status=report.compatibility_status,
        warnings=report.warnings,
    )
    try:
        platform.skill_store.save(meta, body, attachments)
    except KeyError:
        raise HTTPException(status_code=409, detail=f"技能 {meta.name} 已存在") from None
    platform.audit.record(principal, "skill.import", {"name": meta.name, "package_sha256": meta.package_sha256}, "allowed")
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
    principal = require_privileged(request)
    if not payload.acknowledged_script_execution:
        raise HTTPException(status_code=422, detail="必须明确确认将允许当前版本脚本进入权限执行流程")
    store = request.app.state.platform.skill_store
    try:
        store.trust(name, payload.package_sha256, principal_id=principal)
        request.app.state.platform.audit.record(principal, "skill.trust", {"name": name, "package_sha256": payload.package_sha256}, "allowed")
        return store.trust_status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在") from None
    except SkillValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/skills/{name}/trust")
async def revoke_skill_trust(name: str, request: Request):
    principal = require_privileged(request)
    store = request.app.state.platform.skill_store
    if store.get(name) is None:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    revoked = store.revoke_trust(name)
    request.app.state.platform.audit.record(principal, "skill.trust.revoke", {"name": name}, "allowed")
    return {"revoked": revoked, **store.trust_status(name)}


@router.delete("/skills/{name}")
async def delete_skill(name: str, request: Request, principal: str = Depends(require_privileged)):
    """删除技能包。不存在 → 404。"""
    if not request.app.state.platform.skill_store.delete(name):
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    request.app.state.platform.audit.record(principal, "skill.delete", {"name": name}, "allowed")
    return {"deleted": True, "name": name}
