"""Model-provider configuration and health endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from maestro.api.security import require_privileged
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
    """返回当前已持久化的模型供应商配置 (api_key 脱敏，附 api_key_set)。"""
    _platform(request)
    return mc.redact_providers(mc.load_model_providers())


@router.put("/models")
async def put_models(
    cfg: ModelsConfigModel, request: Request, principal: str = Depends(require_privileged)
):
    """保存模型配置并热更新运行中的 LLM 客户端。空 api_key 保留已存密钥。"""
    platform = _platform(request)
    payload = mc.merge_preserving_secrets(cfg.model_dump(), mc.load_model_providers())
    mc.save_model_providers(payload)
    _apply_model_config(platform, payload)
    platform.audit.record(
        principal,
        "models.update",
        {"llm_active": payload["llm"].get("active_id"),
         "embedding_active": payload["embedding"].get("active_id")},
        "allowed",
    )
    return {"ok": True, "available": platform.llm.available}


@router.post("/admin/reload-model")
async def reload_model(request: Request, principal: str = Depends(require_privileged)):
    """重读模型配置并热更新运行中的 LLM 客户端。"""
    platform = _platform(request)
    _apply_model_config(platform, mc.load_model_providers())
    platform.audit.record(principal, "models.reload", {}, "allowed")
    return {"ok": True, "available": platform.llm.available}
