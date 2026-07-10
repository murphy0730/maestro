"""Knowledge-base document endpoints."""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from maestro.engines.query.ingestor import DocumentNotFound
from maestro.foundation.loaders import UnsupportedFileType

router = APIRouter()
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _ingestor(request: Request):
    return request.app.state.platform.ingestor


@router.get("/knowledge")
async def list_knowledge(request: Request):
    """列出知识库全部文档，首次访问时惰性加载种子知识库。"""
    ingestor = _ingestor(request)
    await ingestor.seed_from_directory()
    docs = ingestor.list_docs()
    return {
        "docs": [doc.model_dump(mode="json") for doc in docs],
        "supported_extensions": ingestor.supported_extensions,
    }


@router.post("/knowledge")
async def add_knowledge(request: Request, file: UploadFile = File(...)):
    """上传一个文件入库。类型不支持 → 415；过大 → 413。"""
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
    try:
        doc = await _ingestor(request).add_upload(file.filename or "untitled", data)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    return doc.model_dump(mode="json")


@router.put("/knowledge/{doc_id}")
async def update_knowledge(
    doc_id: str,
    request: Request,
    file: UploadFile | None = File(None),
    name: str | None = Form(None),
):
    """传 file 换内容，传 name 改显示名。"""
    try:
        if file is not None:
            data = await file.read()
            if len(data) > _MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
            doc = await _ingestor(request).replace(doc_id, file.filename or "untitled", data)
        elif name is not None:
            doc = _ingestor(request).rename(doc_id, name)
        else:
            raise HTTPException(status_code=400, detail="需提供 file 或 name")
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}") from exc
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    return doc.model_dump(mode="json")


@router.delete("/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str, request: Request):
    """删除文档及其向量片段。"""
    try:
        removed = _ingestor(request).remove(doc_id)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}") from exc
    return {"doc_id": doc_id, "removed_chunks": removed}
