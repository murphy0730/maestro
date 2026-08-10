"""模型供应商配置。

用户在设置里维护一组供应商，其中一个为「启用」项；启用项的连接信息覆盖扁平的
`llm_*` / `embed_*` 配置（见 `foundation/model_config.py` 与 `bootstrap.py`）。

改动模型配置等于改变整个 Runtime 的推理来源，且载荷含明文 api_key，因此与 MCP、
Skill 包管理同属宿主管理行为：写路由一律经 `require_privileged`，凭证缺失或不符
返回 403 —— 从不返回 401。读路由开放，但 api_key 永远脱敏。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from maestro.api.security import require_privileged
from maestro.foundation import model_config as mc

router = APIRouter()

SECTIONS = ("llm", "embedding")


class ProviderPayload(BaseModel):
    id: str | None = None
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class ProviderSectionPayload(BaseModel):
    providers: list[ProviderPayload] = Field(default_factory=list)
    active_id: str | None = None


class ModelsConfigPayload(BaseModel):
    llm: ProviderSectionPayload = Field(default_factory=ProviderSectionPayload)
    embedding: ProviderSectionPayload = Field(default_factory=ProviderSectionPayload)


class ProviderTestPayload(BaseModel):
    section: str = "llm"
    id: str | None = None
    base_url: str = ""
    api_key: str = ""
    model: str = ""


def _platform(request: Request):
    return request.app.state.platform


def _apply(platform, providers: dict) -> None:
    """把启用项推给运行中的客户端。

    必须原地 `reconfigure`：`LLMRuntimeModel` 与 `LLMHistorySummarizer` 按引用持有
    这个实例，替换 `platform.llm` 会让协调器继续用旧连接。
    """
    platform.llm.reconfigure(*mc.resolve_from_providers(providers, platform.settings))


@router.get("/models")
async def get_models(request: Request):
    """只读：返回已持久化的供应商配置，api_key 一律脱敏为空串。"""
    _platform(request)
    return mc.redact_providers(mc.load_model_providers())


@router.put("/models")
async def put_models(
    payload: ModelsConfigPayload, request: Request, _: str = Depends(require_privileged)
):
    """保存配置并热更新运行中的客户端，无需重启后端。"""
    platform = _platform(request)
    merged = mc.merge_preserving_secrets(payload.model_dump(), mc.load_model_providers())
    mc.save_model_providers(merged)
    _apply(platform, merged)
    return {**mc.redact_providers(merged), "available": platform.llm.available}


@router.post("/models/test")
async def test_provider(
    payload: ProviderTestPayload, request: Request, _: str = Depends(require_privileged)
):
    """用候选参数发一次最小请求，验证连接是否可用。

    走一次性客户端，不触碰 `platform.llm` —— 测试失败不该影响正在服务的连接。
    """
    if payload.section not in SECTIONS:
        raise HTTPException(status_code=422, detail=f"未知的 section: {payload.section}")
    if not payload.model:
        return {"ok": False, "error": "未填写 model", "latency_ms": 0}

    # 测试已保存的条目时前端不会重传密钥（GET 已脱敏），此处回到磁盘取。
    api_key = payload.api_key
    if not api_key and payload.id:
        stored = mc.load_model_providers() or {}
        for provider in (stored.get(payload.section) or {}).get("providers") or []:
            if provider.get("id") == payload.id:
                api_key = provider.get("api_key", "")
                break
    if not api_key:
        return {"ok": False, "error": "未填写 api_key", "latency_ms": 0}

    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=payload.base_url or None, api_key=api_key)
    started = time.monotonic()
    try:
        if payload.section == "embedding":
            await client.embeddings.create(model=payload.model, input=["ping"])
        else:
            await client.chat.completions.create(
                model=payload.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
    except Exception as error:  # noqa: BLE001 — 任何失败都是一次「测试不通过」，不是 5xx
        return {
            "ok": False,
            "error": str(error),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    return {"ok": True, "error": "", "latency_ms": int((time.monotonic() - started) * 1000)}
