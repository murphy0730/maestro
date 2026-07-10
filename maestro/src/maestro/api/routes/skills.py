"""Skill package management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from maestro.api.routes.knowledge import _MAX_UPLOAD_BYTES
from maestro.foundation.tools.builtin import QUERY_READONLY_TOOLS
from maestro.skills.parser import extract_package, validate_allowed_tools
from maestro.skills.schemas import SkillMeta, SkillValidationError

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/skills")
async def list_skills(request: Request):
    """列出全部已导入技能包的元数据。"""
    return {"skills": [meta.model_dump() for meta in request.app.state.platform.skill_store.list_all()]}


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
        frontmatter, body, attachments = extract_package(
            data, filename, platform.settings.skill_body_max_bytes
        )
        allowed = validate_allowed_tools(
            frontmatter,
            set(platform.tools.names()),
            list(QUERY_READONLY_TOOLS),
            set(platform.named_preconditions.keys()),
        )
    except SkillValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    meta = SkillMeta(
        **{**frontmatter.model_dump(), "allowed_tools": allowed},
        file_count=len(attachments),
        bytes=len(data),
        added_at=_now_iso(),
    )
    try:
        platform.skill_store.save(meta, body, attachments)
    except KeyError:
        raise HTTPException(status_code=409, detail=f"技能 {meta.name} 已存在") from None
    return meta


@router.delete("/skills/{name}")
async def delete_skill(name: str, request: Request):
    """删除技能包。不存在 → 404。"""
    if not request.app.state.platform.skill_store.delete(name):
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    return {"deleted": True, "name": name}
