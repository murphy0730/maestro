"""Runtime Skill catalog endpoints (no legacy SkillEngine semantics)."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from maestro.skills.package import compute_package_hash, package_stats
from maestro.skills.parser import validate_runtime_package
from maestro.skills.schemas import NAME_RE
from maestro.api.security import require_privileged

router = APIRouter()
_MAX_UPLOAD = 10 * 1024 * 1024
_INSTALL_MARKER = ".maestro-install.json"


def _installed_at(root: Path) -> str:
    """When the package was imported, not when it was listed."""
    marker = root / _INSTALL_MARKER
    try:
        return str(json.loads(marker.read_text("utf-8"))["added_at"])
    except (OSError, ValueError, KeyError):
        pass
    try:
        return datetime.fromtimestamp(root.stat().st_mtime, UTC).isoformat()
    except OSError:
        return ""


def _meta(item, warnings: list[str] | None = None, trust=None) -> dict:
    root = item.path.parent
    file_count, size = package_stats(root)
    scripts = sorted(
        path.relative_to(root).as_posix()
        for path in root.glob("scripts/**/*")
        if path.is_file()
    )
    warnings = list(warnings or [])
    if scripts:
        warnings.append("技能包含脚本；执行前须信任当前包 hash，且每次执行仍需人工确认")
    return {
        "name": item.name,
        "description": item.description,
        "allowed_tools": list(item.allowed_tools),
        "user_invocable": item.user_invocable,
        "disable_model_invocation": item.disable_model_invocation,
        "argument_hint": item.argument_hint,
        "scripts": scripts,
        "file_count": file_count,
        "bytes": size,
        "added_at": _installed_at(root),
        "compatibility_status": "degraded" if warnings else "ready",
        "warnings": warnings,
        "package_sha256": compute_package_hash(root),
        "trust": trust.status(item.name, root).as_dict() if trust is not None else None,
    }


@router.get("/skills")
async def list_skills(request: Request):
    platform = request.app.state.platform
    skills = [
        _meta(item, trust=platform.skill_trust)
        for item in platform.refresh_skills().values()
    ]
    return {
        "skills": skills,
        # A package that fails to parse is reported rather than silently dropped.
        "errors": [
            {"path": str(error.path), "source": error.source, "reason": error.reason}
            for error in platform.skill_catalog.errors
        ],
    }


async def _upload(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(_MAX_UPLOAD + 1)
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, detail="skill exceeds 10 MB")
    return data, file.filename or "SKILL.md"


def _registered(request: Request) -> set[str]:
    return {spec.name for spec in request.app.state.platform.capabilities.snapshot().values()}


@router.post("/skills/validate")
async def validate_skill(request: Request, file: UploadFile = File(...)):
    data, filename = await _upload(file)
    _package, report = validate_runtime_package(data, filename, _registered(request))
    return report.model_dump()


@router.post("/skills/import")
async def import_skill(request: Request, file: UploadFile = File(...), _admin: str = Depends(require_privileged)):
    data, filename = await _upload(file)
    # Import shares validate's path, so a package can never be installed under
    # looser rules than the ones the user was shown in the preflight.
    package, report = validate_runtime_package(data, filename, _registered(request))
    if package is None:
        raise HTTPException(422, detail="; ".join(report.errors) or "skill package rejected")
    platform = request.app.state.platform
    destination = platform.settings.skills_dir / package.frontmatter.name
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "SKILL.md").write_text(package.text, "utf-8")
    for relative, content in package.attachments.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (destination / _INSTALL_MARKER).write_text(
        json.dumps({"added_at": datetime.now(UTC).isoformat()}), "utf-8"
    )
    discovered = platform.refresh_skills()
    item = discovered.get(package.frontmatter.name)
    if item is None:
        raise HTTPException(422, detail="skill was written but could not be discovered")
    return _meta(item, report.warnings, trust=platform.skill_trust)


class TrustRequest(BaseModel):
    trusted: bool = True


def _package_root(request: Request, name: str) -> Path:
    item = request.app.state.platform.refresh_skills().get(name)
    if item is None:
        raise HTTPException(404, detail="skill not found")
    return item.path.parent


@router.post("/skills/{name}/trust")
async def trust_skill(name: str, request: Request, payload: TrustRequest, _admin: str = Depends(require_privileged)):
    platform = request.app.state.platform
    root = _package_root(request, name)
    store = platform.skill_trust
    status = store.trust(name, root) if payload.trusted else store.revoke(name, root)
    return status.as_dict()


@router.delete("/skills/{name}/trust")
async def revoke_trust(name: str, request: Request, _admin: str = Depends(require_privileged)):
    platform = request.app.state.platform
    return platform.skill_trust.revoke(name, _package_root(request, name)).as_dict()


@router.delete("/skills/{name}")
async def delete_skill(name: str, request: Request, _admin: str = Depends(require_privileged)):
    # `name` becomes a filesystem path; never let ".." or a separator through.
    if not NAME_RE.match(name):
        raise HTTPException(404, detail="skill not found")
    root = request.app.state.platform.settings.skills_dir / name
    if not root.is_dir():
        raise HTTPException(404, detail="skill not found")
    shutil.rmtree(root)
    request.app.state.platform.refresh_skills()
    return None
