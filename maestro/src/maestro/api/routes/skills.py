"""Runtime Skill catalog endpoints (no legacy SkillEngine semantics)."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from maestro.skills.parser import extract_package, parse_runtime_frontmatter
from maestro.skills.schemas import SkillValidationError

router = APIRouter()
_MAX_UPLOAD = 10 * 1024 * 1024


def _meta(item) -> dict:
    return {
        "name": item.name, "description": item.description,
        "allowed_tools": list(item.allowed_tools), "user_invocable": item.user_invocable,
        "disable_model_invocation": item.disable_model_invocation,
        "argument_hint": item.argument_hint, "file_count": 1,
        "bytes": item.path.stat().st_size, "added_at": datetime.now(UTC).isoformat(),
        "compatibility_status": "ready", "warnings": [], "package_sha256": "",
    }


@router.get("/skills")
async def list_skills(request: Request):
    return {"skills": [_meta(item) for item in request.app.state.platform.refresh_skills().values()]}


async def _upload(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(_MAX_UPLOAD + 1)
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, detail="skill exceeds 10 MB")
    return data, file.filename or "SKILL.md"


def _runtime_package(data: bytes, filename: str):
    # Extract safely, then use Runtime's strict (inert extensions) parser.
    _legacy, body, attachments = extract_package(data, filename)
    skill_text = "---\n" + data.decode("utf-8").split("---", 2)[1] + "---\n" + body if filename.lower().endswith(".md") else None
    if skill_text is None:
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = next(name for name in archive.namelist() if name.endswith("SKILL.md"))
            skill_text = archive.read(member).decode("utf-8")
    return parse_runtime_frontmatter(skill_text), skill_text, attachments


@router.post("/skills/validate")
async def validate_skill(request: Request, file: UploadFile = File(...)):
    try:
        data, filename = await _upload(file)
        frontmatter, _text, attachments = _runtime_package(data, filename)
        unknown = [name for name in (frontmatter.allowed_tools or []) if name not in {x.name for x in request.app.state.platform.capabilities.snapshot().values()}]
        if unknown:
            raise SkillValidationError(f"allowed-tools contains unknown capability: {unknown}")
    except (SkillValidationError, UnicodeDecodeError, ValueError) as error:
        return {"compatible": False, "compatibility_status": "not_ready", "capabilities": {"prompt": True, "attachments": False, "scripts": False}, "tool_mapping": {}, "normalized_frontmatter": {}, "warnings": [], "errors": [str(error)]}
    return {"compatible": True, "normalized_name": frontmatter.name, "compatibility_status": "ready", "capabilities": {"prompt": True, "attachments": bool(attachments), "scripts": False}, "tool_mapping": {}, "normalized_frontmatter": frontmatter.model_dump(), "warnings": [], "errors": []}


@router.post("/skills/import")
async def import_skill(request: Request, file: UploadFile = File(...)):
    data, filename = await _upload(file)
    try:
        frontmatter, skill_text, attachments = _runtime_package(data, filename)
        destination = request.app.state.platform.settings.skills_dir / frontmatter.name
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "SKILL.md").write_text(skill_text, "utf-8")
        for relative, content in attachments.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        item = request.app.state.platform.refresh_skills()[frontmatter.name]
    except (SkillValidationError, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(422, detail=str(error)) from error
    return _meta(item)


class TrustRequest(BaseModel):
    trusted: bool = True


@router.post("/skills/{name}/trust")
async def trust_skill(name: str, request: Request, payload: TrustRequest):
    if name not in request.app.state.platform.refresh_skills():
        raise HTTPException(404, detail="skill not found")
    request.app.state.skill_trust[name] = payload.trusted
    return {"level": "user_trusted" if payload.trusted else "untrusted", "valid": True, "package_sha256": ""}


@router.delete("/skills/{name}/trust")
async def revoke_trust(name: str, request: Request):
    request.app.state.skill_trust.pop(name, None)
    return {"level": "untrusted", "valid": True, "package_sha256": ""}


@router.delete("/skills/{name}")
async def delete_skill(name: str, request: Request):
    root = request.app.state.platform.settings.skills_dir / name
    if not root.is_dir():
        raise HTTPException(404, detail="skill not found")
    import shutil
    shutil.rmtree(root)
    request.app.state.platform.refresh_skills()
    return None
