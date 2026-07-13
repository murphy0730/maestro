"""Download generated conversation artifacts without exposing host paths."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/artifacts/{artifact_path:path}")
async def download_artifact(artifact_path: str, request: Request):
    root = (Path(request.app.state.platform.settings.skill_execution_dir) / "artifacts").resolve()
    candidate = (root / artifact_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="产物不存在或已清理")
    return FileResponse(candidate, filename=candidate.name)
