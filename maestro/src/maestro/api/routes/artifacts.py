"""Opaque, content-addressed Runtime artifacts."""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from maestro.runtime.store import InvalidStorageId

router = APIRouter()
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/artifacts", status_code=201)
async def create_artifact(request: Request, file: UploadFile = File(...)):
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"code": "artifact_too_large", "message": "file exceeds 10 MB"})
    artifact = request.app.state.platform.artifact_store.put(
        content, file.content_type or "application/octet-stream"
    )
    return artifact.model_dump()


@router.get("/artifacts/{artifact_id}")
async def download_artifact(artifact_id: str, request: Request):
    try:
        store = request.app.state.platform.artifact_store
        content = store.get(artifact_id)
        media_type = store.media_type(artifact_id)
    except (FileNotFoundError, InvalidStorageId):
        raise HTTPException(404, detail={"code": "artifact_not_found", "message": "artifact not found"}) from None
    return Response(content, media_type=media_type)
