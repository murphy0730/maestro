"""Model-provider configuration and health endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from maestro.foundation import model_config as mc

router = APIRouter()


class ProviderModel(BaseModel):
    id: str | None = None
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class ProviderSectionModel(BaseModel):
    providers: list[ProviderModel] = []
    active_id: str | None = None


class ModelsConfigModel(BaseModel):
    llm: ProviderSectionModel = ProviderSectionModel()
    embedding: ProviderSectionModel = ProviderSectionModel()


def _platform(request: Request):
    if not hasattr(request.app.state, "platform"):
        raise HTTPException(status_code=503, detail="platform not ready")
    return request.app.state.platform


def _apply_model_config(platform, providers: dict | None) -> None:
    """解析 active provider，原地热更新运行中的 LLMClient。"""
    base, key, model, embed_base, embed_key, embed_model = mc.resolve_from_providers(
        providers, platform.settings
    )
    platform.llm.reconfigure(base, key, model, embed_base, embed_key, embed_model)


@router.get("/health")
async def health(request: Request):
    platform = _platform(request)
    return {"status": "ok", "llm_available": platform.llm.available}


@router.get("/models")
async def get_models(request: Request):
    """返回当前已持久化的模型供应商配置。"""
    _platform(request)
    data = mc.load_model_providers()
    return data if data is not None else mc.EMPTY_PROVIDERS


@router.put("/models")
async def put_models(cfg: ModelsConfigModel, request: Request):
    """保存模型配置并热更新运行中的 LLM 客户端。"""
    platform = _platform(request)
    payload = cfg.model_dump()
    mc.save_model_providers(payload)
    _apply_model_config(platform, payload)
    return {"ok": True, "available": platform.llm.available}


@router.post("/admin/reload-model")
async def reload_model(request: Request):
    """重读模型配置并热更新运行中的 LLM 客户端。"""
    platform = _platform(request)
    _apply_model_config(platform, mc.load_model_providers())
    return {"ok": True, "available": platform.llm.available}
